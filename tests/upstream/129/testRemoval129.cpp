#include <QSignalSpy>
#include <QtTest>
#include <memory>

#include "playbackEngineGstreamer.h"
#include "playlistWidget.h"
#include "playlistWidgetItem.h"
#include "pluginLoader.h"
#include "settings.h"
#include "tagReaderTaglib.h"
#include "trackInfoReader.h"

// Only plugin discovery is substituted: the widget receives the real engine.
// This avoids building/loading the unrelated waveform/container plugins.
static NPlaybackEngineGStreamer *testEngine = nullptr;
NPlugin *NPluginLoader::getPlugin(N::PluginType type)
{
    return type == N::PlaybackEngine ? testEngine : nullptr;
}

class TestRemoval129 : public QObject
{
    Q_OBJECT
    QTemporaryDir directory;
    QStringList files;
    std::unique_ptr<NPlaybackEngineGStreamer> engine;
    std::unique_ptr<NTagReaderTaglib> tags;
    std::unique_ptr<NTrackInfoReader> reader;
    std::unique_ptr<NPlaylistWidget> playlist;

private slots:
    void initTestCase()
    {
        QVERIFY(directory.isValid());
        qRegisterMetaType<N::PlaybackState>();
        // Real, locally generated PCM WAVs; no codecs or network fixtures assumed.
        for (int i = 0; i < 4; ++i) {
            const QString path = directory.filePath(QString("track-%1.wav").arg(i));
            QFile file(path);
            QVERIFY(file.open(QIODevice::WriteOnly));
            QDataStream stream(&file);
            stream.setByteOrder(QDataStream::LittleEndian);
            const quint32 bytes = 8000 * 30 * 2;
            stream.writeRawData("RIFF", 4);
            stream << quint32(36 + bytes);
            stream.writeRawData("WAVEfmt ", 8);
            stream << quint32(16) << quint16(1) << quint16(1) << quint32(8000) << quint32(16000)
                   << quint16(2) << quint16(16);
            stream.writeRawData("data", 4);
            stream << bytes;
            const QByteArray silence(bytes, '\0');
            QCOMPARE(stream.writeRawData(silence.constData(), bytes), int(bytes));
            files << path;
        }
    }

    void init()
    {
        NSettings::instance()->clear();
        delete NSettings::instance();
        engine.reset(new NPlaybackEngineGStreamer);
        engine->init();
        testEngine = engine.get();
        tags.reset(new NTagReaderTaglib);
        tags->init();
        reader.reset(new NTrackInfoReader(tags.get()));
        playlist.reset(new NPlaylistWidget);
        playlist->setTrackInfoReader(reader.get());
        playlist->resize(640, 400);
        playlist->show();
        playlist->setFiles(files);
        connect(engine.get(), &NPlaybackEngineGStreamer::message, this,
                [](N::MessageIcon, const QString &, const QString &message) {
                    QFAIL(qPrintable(message));
                });
    }

    void cleanup()
    {
        engine->stop();
        playlist.reset();
        reader.reset();
        tags.reset();
        engine.reset();
        testEngine = nullptr;
    }

    void pausedCurrentRemoval()
    {
        playlist->playRow(0);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QTRY_COMPARE(playlist->playingRow(), 0);
        engine->pause();
        QCOMPARE(engine->state(), N::PlaybackPaused);
        QSignalSpy states(engine.get(), &NPlaybackEngineGStreamer::stateChanged);
        playlist->setCurrentRow(0);
        playlist->removeSelected();
        QCOMPARE(playlist->count(), 3);
        QTest::qWait(250); // include asynchronous GStreamer state delivery
        QCOMPARE(engine->state(), N::PlaybackPaused);
        for (const auto &state : states)
            QVERIFY(state.at(0).value<N::PlaybackState>() != N::PlaybackPlaying);
    }

    void removalStates_data()
    {
        QTest::addColumn<int>("state");
        QTest::addColumn<QString>("scenario");
        for (int state : {N::PlaybackPlaying, N::PlaybackPaused, N::PlaybackStopped}) {
            for (const char *scenario : {"current", "next", "last", "last-loop", "all", "duplicate",
                                         "discontiguous", "files-current", "files-next", "none"}) {
                const QByteArray name = QByteArray(scenario) + '-' + QByteArray::number(state);
                QTest::newRow(name.constData()) << state << QString(scenario);
            }
        }
    }

    void removalStates()
    {
        QFETCH(int, state);
        QFETCH(QString, scenario);
        if (scenario == "duplicate")
            playlist->setFiles({files[0], files[0], files[1], files[2]});
        const int start = scenario.startsWith("last") ? 3 : 0;
        NSettings::instance()->setValue("LoopPlaylist", scenario == "last-loop");
        playlist->playRow(start);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QTRY_COMPARE(playlist->playingRow(), start);
        QTRY_VERIFY(engine->position() > 0.0);
        if (state == N::PlaybackPaused)
            engine->pause();
        else if (state == N::PlaybackStopped)
            engine->stop();
        QCOMPARE(int(engine->state()), state);
        const QString originalMedia = engine->currentMedia();
        const qreal originalPosition = engine->position();
        QList<int> oldIds;
        for (int i = 0; i < playlist->count(); ++i)
            oldIds << playlist->item(i)->data(N::IdRole).toInt();
        QList<int> removedRows;
        if (scenario == "all")
            removedRows = {0, 1, 2, 3};
        else if (scenario == "discontiguous")
            removedRows = {0, 2};
        else if (scenario != "none")
            removedRows = {scenario.contains("next") ? 1 : start};
        QList<int> expectedIds;
        QList<int> removedIds;
        for (int i = 0; i < oldIds.size(); ++i) {
            if (removedRows.contains(i))
                removedIds << oldIds[i];
            else
                expectedIds << oldIds[i];
        }
        QSignalSpy states(engine.get(), &NPlaybackEngineGStreamer::stateChanged);
        QSignalSpy changed(engine.get(), &NPlaybackEngineGStreamer::mediaChanged);
        playlist->clearSelection();
        for (int row : removedRows)
            playlist->item(row)->setSelected(true);
        if (scenario.startsWith("files-"))
            playlist->removeFiles({files[removedRows.first()]});
        else
            playlist->removeSelected();
        QCOMPARE(playlist->count(), int(expectedIds.size()));
        for (int i = 0; i < playlist->count(); ++i) {
            QCOMPARE(playlist->item(i)->data(N::IdRole).toInt(), expectedIds[i]);
            if (!scenario.startsWith("files-"))
                QCOMPARE(playlist->item(i)->data(N::TrackIndexRole).toInt(), i);
        }
        if (scenario == "all") {
            QCOMPARE(engine->state(), N::PlaybackStopped);
            QVERIFY(!engine->hasMedia());
            QCOMPARE(playlist->playingRow(), -1);
        } else if (state == N::PlaybackPlaying && removedRows.contains(start) &&
                   !scenario.startsWith("files-")) {
            const int expectedRow = scenario == "last" ? 2 : 0;
            QTRY_COMPARE(playlist->playingRow(), expectedRow);
            QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
            QCOMPARE(playlist->playingItem()->data(N::IdRole).toInt(), expectedIds[expectedRow]);
            QCOMPARE(engine->currentMedia(), playlist->playingItem()->data(N::PathRole).toString());
        } else {
            QCOMPARE(engine->currentMedia(), originalMedia);
            QCOMPARE(playlist->playingRow(), removedRows.contains(start) ? -1 : start);
            QCOMPARE(changed.count(), 0);
            if (state != N::PlaybackPlaying)
                QCOMPARE(engine->position(), originalPosition);
        }
        // Removed IDs must not be dereferenced or resurrected by late EOS/failure.
        const int playingRow = playlist->playingRow();
        for (int id : removedIds) {
            engine->mediaFinished(originalMedia, id);
            engine->mediaFailed(originalMedia, id);
        }
        QCOMPARE(playlist->playingRow(), playingRow);
        QTest::qWait(150);
        QCOMPARE(int(engine->state()), scenario == "all" ? int(N::PlaybackStopped) : state);
        if (state != N::PlaybackPlaying) {
            for (const auto &entry : states)
                QVERIFY(entry.at(0).value<N::PlaybackState>() != N::PlaybackPlaying);
        }
    }

    void nextRemovalHandoff_data()
    {
        QTest::addColumn<bool>("byPath");
        QTest::newRow("selected") << false;
        QTest::newRow("path") << true;
    }

    void nextRemovalHandoff()
    {
        QFETCH(bool, byPath);
        playlist->playRow(0);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QTRY_COMPARE(playlist->playingRow(), 0);
        const int successor = playlist->item(2)->data(N::IdRole).toInt();
        if (byPath)
            playlist->removeFiles({files[1]});
        else {
            playlist->setCurrentRow(1);
            playlist->removeSelected();
        }
        QCoreApplication::processEvents();
        QSignalSpy changed(engine.get(), &NPlaybackEngineGStreamer::mediaChanged);
        engine->setPosition(0.99);
        QTRY_VERIFY_WITH_TIMEOUT(!changed.isEmpty(), 3000);
        QCOMPARE(changed.first()[1].toInt(), successor);
        QCOMPARE(playlist->playingRow(), 1);
    }

    void emptyAndDuplicatePaths()
    {
        playlist->setFiles({files[0], files[0], files[1], files[0]});
        const int survivor = playlist->item(2)->data(N::IdRole).toInt();
        playlist->removeFiles({files[0], files[0], directory.filePath("absent.wav")});
        QCOMPARE(playlist->count(), 1);
        QCOMPARE(playlist->item(0)->data(N::IdRole).toInt(), survivor);
        playlist->removeFiles({});
        QCOMPARE(playlist->count(), 1);
        playlist->selectAll();
        playlist->removeSelected();
        playlist->removeSelected();
        playlist->removeFiles(files);
        QCOMPARE(playlist->count(), 0);
        QCOMPARE(playlist->playingRow(), -1);
        QCOMPARE(engine->state(), N::PlaybackStopped);
    }

    void largePlaylist_data()
    {
        QTest::addColumn<int>("size");
        QTest::addColumn<QString>("pattern");
        for (int size : {100, 1000, 5000}) {
            for (const char *pattern : {"all", "alternating", "by-path"}) {
                const QByteArray name = QByteArray::number(size) + '-' + pattern;
                QTest::newRow(name.constData()) << size << QString(pattern);
            }
        }
    }

    void largePlaylist()
    {
        QFETCH(int, size);
        QFETCH(QString, pattern);
        QTemporaryDir tracks;
        QVERIFY(tracks.isValid());
        // Unique, valid one-second WAVs exercise actual TagLib I/O. Fixture
        // creation is outside timings; OS caches are not claimed to be cold.
        QFile source(files.first());
        QVERIFY(source.open(QIODevice::ReadOnly));
        QByteArray wav = source.read(44 + 16000);
        QBuffer buffer(&wav);
        QVERIFY(buffer.open(QIODevice::WriteOnly));
        QDataStream header(&buffer);
        header.setByteOrder(QDataStream::LittleEndian);
        QVERIFY(buffer.seek(4));
        header << quint32(wav.size() - 8);
        QVERIFY(buffer.seek(40));
        header << quint32(wav.size() - 44);
        buffer.close();
        QStringList paths;
        for (int i = 0; i < size; ++i) {
            const QString path = tracks.filePath(QString("track-%1.wav").arg(i));
            QFile file(path);
            QVERIFY(file.open(QIODevice::WriteOnly));
            QCOMPARE(file.write(wav), qint64(wav.size()));
            paths << path;
        }
        for (int sample = 0; sample < 3; ++sample) {
            QElapsedTimer timer;
            timer.start();
            playlist->setFiles(paths);
            const qint64 loadNs = timer.nsecsElapsed();
            QCoreApplication::processEvents();
            QCOMPARE(playlist->count(), size);
            QList<int> survivors;
            QStringList removedPaths;
            timer.restart();
            QItemSelection selection;
            for (int i = 0; i < size; ++i) {
                if (pattern == "all" || i % 2 == 0) {
                    const QModelIndex index = playlist->model()->index(i, 0);
                    if (pattern != "all")
                        selection.select(index, index);
                    removedPaths << paths[i];
                } else {
                    survivors << playlist->item(i)->data(N::IdRole).toInt();
                }
            }
            if (pattern == "all")
                playlist->selectAll();
            else
                playlist->selectionModel()->select(selection, QItemSelectionModel::ClearAndSelect);
            const qint64 selectionNs = timer.nsecsElapsed();
            QSignalSpy durations(playlist.get(), &NPlaylistWidget::durationChanged);
            bool heartbeat = false;
            QTimer::singleShot(0, playlist.get(), [&heartbeat]() { heartbeat = true; });
            timer.restart();
            if (pattern == "by-path")
                playlist->removeFiles(removedPaths);
            else
                playlist->removeSelected();
            const qint64 removalNs = timer.nsecsElapsed();
            QCoreApplication::processEvents();
            const qint64 eventNs = timer.nsecsElapsed();
            QVERIFY(heartbeat);
            QCOMPARE(playlist->count(), int(survivors.size()));
            for (int i = 0; i < playlist->count(); ++i) {
                QCOMPARE(playlist->item(i)->data(N::IdRole).toInt(), survivors[i]);
                QCOMPARE(playlist->item(i)->data(N::PathRole).toString(), paths[2 * i + 1]);
                if (pattern != "by-path")
                    QCOMPARE(playlist->item(i)->data(N::TrackIndexRole).toInt(), i);
            }
            if (pattern != "by-path") {
                QVERIFY(!durations.isEmpty());
                int knownDuration = 0;
                for (int i = 0; i < playlist->count(); ++i)
                    knownDuration += qMax(0, playlist->item(i)->data(N::DurationRole).toInt());
                QCOMPARE(durations.last()[0].toInt(), knownDuration);
            }
            QCOMPARE(engine->state(), N::PlaybackStopped);
            // Record observations, not an invented historical latency budget.
            // CTest's process timeout remains the bounded hang guard.
            qInfo().noquote() << QString("BENCH size=%1 pattern=%2 sample=%3 load_ns=%4 "
                                         "selection_ns=%5 removal_ns=%6 event_return_ns=%7")
                                     .arg(size)
                                     .arg(pattern)
                                     .arg(sample)
                                     .arg(loadNs)
                                     .arg(selectionNs)
                                     .arg(removalNs)
                                     .arg(eventNs);
        }
        // Include queued model work followed by actual widget destruction.
        QElapsedTimer closeTimer;
        closeTimer.start();
        playlist.reset();
        QCoreApplication::processEvents();
        qInfo().noquote() << QString("CLOSE size=%1 pattern=%2 ns=%3")
                                 .arg(size)
                                 .arg(pattern)
                                 .arg(closeTimer.nsecsElapsed());
    }
};

QTEST_MAIN(TestRemoval129)
#include "testRemoval129.moc"
