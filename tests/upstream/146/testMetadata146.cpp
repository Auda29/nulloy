#include "action.h"
#include "playbackEngineGstreamer.h"
#include "playlistWidget.h"
#include "playlistWidgetItem.h"
#include "pluginLoader.h"
#include "settings.h"
#include "tagReaderTaglib.h"
#include "trackInfoReader.h"
#include <QVBoxLayout>
#include <QtTest>
#include <mpegfile.h>
#include <id3v2tag.h>
#include <memory>

// Same bounded real-component harness as #218; no full NPlayer or native hook.
static NPlaybackEngineGStreamer *testEngine = nullptr;
NPlugin *NPluginLoader::getPlugin(N::PluginType type)
{
    return type == N::PlaybackEngine ? testEngine : nullptr;
}

class TestMetadata146 : public QObject
{
    Q_OBJECT
    QTemporaryDir directory;
    QStringList files;
    std::unique_ptr<NPlaybackEngineGStreamer> engine;
    std::unique_ptr<NTagReaderTaglib> tags;
    std::unique_ptr<NTrackInfoReader> reader;
    std::unique_ptr<QWidget> window;
    NPlaylistWidget *playlist = nullptr;
    NAction *previous = nullptr;
    NAction *next = nullptr;
    int expectedRow = 0;
    int observed = 0;
    const QString format = "%a - %t - %A";

    QString expected(int row) const
    {
        return QString::fromUtf8("Artista %1 - Canção %1 - Álbum %1").arg(row);
    }
    void verifyCurrent(int row)
    {
        QCOMPARE(playlist->playingRow(), row);
        QCOMPARE(playlist->playingItem(), playlist->itemAtRow(row));
        QCOMPARE(playlist->playingItem()->data(N::IdRole), playlist->item(row)->data(N::IdRole));
        QCOMPARE(engine->currentMedia(), files[row]);
        QCOMPARE(playlist->item(row)->data(Qt::DisplayRole).toString(), expected(row));
        QCOMPARE(playlist->item(row)->data(N::TitleFormatRole).toString(), format);
        QVERIFY(playlist->item(row)->data(N::DurationRole).toInt() > 0);
        QVERIFY(playlist->item(row)->data(N::PlayingRole).toBool());
        QVERIFY(!playlist->item(row)->data(N::FailedRole).toBool());
    }
private slots:
    void initTestCase()
    {
        QVERIFY(directory.isValid());
        const QString source = directory.filePath("source.mp3");
        QProcess ffmpeg;
        ffmpeg.start(FFMPEG_EXECUTABLE,
                     {"-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
                      "-f", "lavfi", "-i", "sine=frequency=440:duration=30", "-c:a",
                      "libmp3lame", "-threads", "1", source});
        QVERIFY(ffmpeg.waitForFinished(30000));
        QCOMPARE(ffmpeg.exitStatus(), QProcess::NormalExit);
        QVERIFY2(ffmpeg.exitCode() == 0, ffmpeg.readAllStandardError().constData());
        for (int row = 0; row < 20; ++row) {
            const QString path = directory.filePath(QString("track-%1.mp3").arg(row));
            QVERIFY(QFile::copy(source, path));
#ifdef WIN32
            TagLib::MPEG::File file(reinterpret_cast<const wchar_t *>(path.utf16()));
#else
            TagLib::MPEG::File file(path.toUtf8().constData());
#endif
            QVERIFY(file.isValid());
            auto *tag = file.ID3v2Tag(true);
            tag->setArtist(TagLib::String(QString("Artista %1").arg(row).toUtf8().constData(), TagLib::String::UTF8));
            tag->setTitle(TagLib::String(QString::fromUtf8("Canção %1").arg(row).toUtf8().constData(), TagLib::String::UTF8));
            tag->setAlbum(TagLib::String(QString::fromUtf8("Álbum %1").arg(row).toUtf8().constData(), TagLib::String::UTF8));
            QVERIFY(file.save(TagLib::MPEG::File::ID3v2, TagLib::File::StripOthers, TagLib::ID3v2::v4));
            files << path;
        }
        QCOMPARE(files.size(), 20);
    }
    void init()
    {
        NSettings::instance()->clear();
        delete NSettings::instance();
        NSettings::instance()->setValue("PlaylistTrackInfo", format);
        engine.reset(new NPlaybackEngineGStreamer);
        engine->init();
        testEngine = engine.get();
        tags.reset(new NTagReaderTaglib);
        tags->init();
        reader.reset(new NTrackInfoReader(tags.get()));
        window.reset(new QWidget);
        auto *layout = new QVBoxLayout(window.get());
        playlist = new NPlaylistWidget(window.get());
        playlist->setTrackInfoReader(reader.get());
        layout->addWidget(playlist);
        previous = new NAction(window.get());
        previous->setShortcuts(NSettings::instance()->value("Shortcuts/PrevAction").toStringList());
        next = new NAction(window.get());
        next->setShortcuts(NSettings::instance()->value("Shortcuts/NextAction").toStringList());
        // Exact actionManager connections, attached at NPlayer's window scope.
        connect(previous, &QAction::triggered, playlist, &NPlaylistWidget::playPrevItem);
        connect(next, &QAction::triggered, playlist, &NPlaylistWidget::playNextItem);
        window->addAction(previous);
        window->addAction(next);
        playlist->setFiles(files);
        window->resize(640, 160); // deliberately fewer visible rows than files
        window->show();
        window->activateWindow();
        playlist->setFocus();
        QTRY_VERIFY(playlist->hasFocus());
        connect(engine.get(), &NPlaybackEngineGStreamer::message, this,
                [](N::MessageIcon, const QString &, const QString &message) {
                    QFAIL(qPrintable(message));
                });
    }
    void cleanup()
    {
        engine->stop();
        window.reset();
        playlist = nullptr;
        reader.reset();
        tags.reset();
        engine.reset();
        testEngine = nullptr;
    }
    void shortcutsRefreshMetadata_data()
    {
        QTest::addColumn<bool>("arrows");
        QTest::addColumn<bool>("scroll");
        QTest::newRow("custom-arrows-scroll") << true << true;
        QTest::newRow("custom-arrows-no-scroll") << true << false;
        QTest::newRow("default-z-b-scroll") << false << true;
        QTest::newRow("default-z-b-no-scroll") << false << false;
    }
    void shortcutsRefreshMetadata()
    {
        QFETCH(bool, arrows);
        QFETCH(bool, scroll);
        QCOMPARE(previous->shortcuts(), QStringList{"Z"});
        QCOMPARE(next->shortcuts(), QStringList{"B"});
        NSettings::instance()->setValue("ScrollToItem", scroll);
        if (arrows) {
            previous->setShortcuts({"Up"});
            next->setShortcuts({"Down"});
        }
        QVERIFY(!playlist->viewport()->rect().intersects(playlist->visualItemRect(playlist->item(19))));
        // This row has not been loaded by the visible-item metadata pass.
        QCOMPARE(playlist->item(19)->data(N::DurationRole).toInt(), -1);
        QSet<int> ids;
        for (int row = 0; row < 20; ++row)
            ids.insert(playlist->item(row)->data(N::IdRole).toInt());
        QCOMPARE(ids.size(), 20);

        expectedRow = 0;
        observed = 0;
        // Assert inside the notification, before queued paint/visible-item work.
        connect(playlist, &NPlaylistWidget::playingItemChanged, this, [this]() {
            ++observed;
            verifyCurrent(expectedRow);
        });
        playlist->playRow(0);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        verifyCurrent(0);
        QSignalSpy changed(engine.get(), &NPlaybackEngineGStreamer::mediaChanged);
        QSignalSpy nextTriggered(next, &QAction::triggered);
        QSignalSpy prevTriggered(previous, &QAction::triggered);
        for (int row = 1; row < 20; ++row) {
            expectedRow = row;
            QTest::keyClick(playlist, arrows ? Qt::Key_Down : Qt::Key_B);
            // Decode/STREAM_START is asynchronous; metadata must already be
            // correct inside playingItemChanged above, not after a paint wait.
            QTRY_COMPARE(playlist->playingRow(), row);
            verifyCurrent(row);
            QCOMPARE(changed.count(), row);
            QCOMPARE(changed.last().at(1).toInt(), playlist->item(row)->data(N::IdRole).toInt());
            QVERIFY(!playlist->item(row - 1)->data(N::PlayingRole).toBool());
        }
        QCOMPARE(nextTriggered.count(), 19);
        if (!scroll)
            QVERIFY(!playlist->viewport()->rect().intersects(playlist->visualItemRect(playlist->item(19))));
        for (int row = 18; row >= 0; --row) {
            expectedRow = row;
            // A nonempty cached value with matching format/duration must still
            // be refreshed on activation. Real on-disk tags are the oracle.
            playlist->itemAtRow(row)->setText("stale cached metadata");
            QTest::keyClick(playlist, arrows ? Qt::Key_Up : Qt::Key_Z);
            QTRY_COMPARE(playlist->playingRow(), row);
            verifyCurrent(row);
            QCOMPARE(changed.last().at(1).toInt(), playlist->item(row)->data(N::IdRole).toInt());
            QVERIFY(!playlist->item(row + 1)->data(N::PlayingRole).toBool());
        }
        QCOMPARE(prevTriggered.count(), 19);
        QCOMPARE(changed.count(), 38);
        QCOMPARE(observed, 39);
        QCOMPARE(NSettings::instance()->value("Shortcuts/PrevAction").toStringList(), QStringList{"Z"});
        QCOMPARE(NSettings::instance()->value("Shortcuts/NextAction").toStringList(), QStringList{"B"});
        disconnect(playlist, &NPlaylistWidget::playingItemChanged, this, nullptr);
    }
    void unboundArrowsKeepPlayback()
    {
        playlist->playRow(0);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        playlist->setCurrentRow(0);
        QSignalSpy changed(engine.get(), &NPlaybackEngineGStreamer::mediaChanged);
        QTest::keyClick(playlist, Qt::Key_Down);
        QCOMPARE(playlist->currentRow(), 1);
        verifyCurrent(0);
        QTest::keyClick(playlist, Qt::Key_Up);
        QCOMPARE(playlist->currentRow(), 0);
        verifyCurrent(0);
        QCOMPARE(changed.count(), 0);
    }
};
QTEST_MAIN(TestMetadata146)
#include "testMetadata146.moc"
