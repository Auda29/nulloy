#include "playbackEngineGstreamer.h"
#include "playlistStorage.h"
#include "playlistWidget.h"
#include "playlistWidgetItem.h"
#include "pluginLoader.h"
#include "settings.h"
#include "tagReaderTaglib.h"
#include "trackInfoReader.h"
#include <QtTest>
#include <memory>

static NPlaybackEngineGStreamer *testEngine = nullptr;
// Discovery only: playback, metadata and widgets are actual production code.
NPlugin *NPluginLoader::getPlugin(N::PluginType type)
{
    return type == N::PlaybackEngine ? testEngine : nullptr;
}

class TestShuffle121 : public QObject
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
        for (int i = 0; i < 4; ++i) {
            const QString path = directory.filePath(QString("track-%1.wav").arg(i));
            QFile file(path);
            QVERIFY(file.open(QIODevice::WriteOnly));
            QDataStream stream(&file);
            stream.setByteOrder(QDataStream::LittleEndian);
            const quint32 bytes = 8000 * 120 * 2;
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
    void preservesPlaylist_data()
    {
        QTest::addColumn<int>("size");
        QTest::addColumn<int>("state");
        for (int size : {0, 1, 100, 5000})
            for (int state : {N::PlaybackPlaying, N::PlaybackPaused, N::PlaybackStopped}) {
                const QByteArray name = QByteArray::number(size) + '-' + QByteArray::number(state);
                QTest::newRow(name.constData()) << size << state;
            }
    }
    void preservesPlaylist()
    {
        QFETCH(int, size);
        QFETCH(int, state);
        QStringList paths;
        for (int i = 0; i < size; ++i)
            paths << files[i % files.size()];
        playlist->setFiles(paths);
        NSettings::instance()->setValue("LoopPlaylist", true);
        if (size) {
            playlist->playRow(size / 2);
            QTRY_COMPARE(playlist->playingRow(), size / 2);
        } else {
            // Loaded media outside an empty playlist is a valid engine state.
            engine->setMedia(files.first(), 1);
            engine->play();
        }
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QTRY_VERIFY(engine->position() > 0.0);
        if (state == N::PlaybackPaused)
            engine->pause();
        else if (state == N::PlaybackStopped)
            engine->stop();
        const auto *playing = playlist->playingItem();
        const QString media = engine->currentMedia();
        const qreal position = engine->position();
        QMap<int, QString> original;
        for (int i = 0; i < size; ++i)
            original[playlist->item(i)->data(N::IdRole).toInt()] = paths[i];
        QCOMPARE(original.size(), size);
        QSignalSpy changed(engine.get(), &NPlaybackEngineGStreamer::mediaChanged);
        for (int attempt = 0; attempt < 20; ++attempt) {
            playlist->shufflePlaylist();
            QCoreApplication::processEvents();
            QCOMPARE(playlist->count(), size);
            QMap<int, QString> actual;
            for (int i = 0; i < size; ++i) {
                actual[playlist->item(i)->data(N::IdRole).toInt()] =
                    playlist->item(i)->data(N::PathRole).toString();
                QCOMPARE(playlist->item(i)->data(N::TrackIndexRole).toInt(), i);
            }
            QCOMPARE(actual, original);
            QCOMPARE(playlist->playingItem(), playing);
            QCOMPARE(engine->currentMedia(), media);
            QCOMPARE(int(engine->state()), state);
            QCOMPARE(changed.count(), 0);
            if (state != N::PlaybackPlaying)
                QCOMPARE(engine->position(), position);
        }
        if (size > 0) {
            const int next = (playlist->playingRow() + 1) % size;
            const int successor = playlist->item(next)->data(N::IdRole).toInt();
            engine->play();
            QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
            QCoreApplication::processEvents();
            changed.clear();
            engine->setPosition(0.999);
            QTRY_VERIFY_WITH_TIMEOUT(!changed.isEmpty(), 4000);
            QCOMPARE(changed.first()[1].toInt(), successor);
            QCOMPARE(playlist->playingRow(), next);
        }
        engine->stop();
        QList<NPlaylistDataItem> items;
        QStringList order;
        for (int i = 0; i < size; ++i) {
            items << playlist->itemAtRow(i)->dataItem();
            order << playlist->item(i)->data(N::PathRole).toString();
        }
        const QString saved = directory.filePath("shuffled.m3u");
        NPlaylistStorage::writeM3u(saved, items, N::NulloyM3u);
        QCOMPARE(playlist->setPlaylist(saved), size != 0);
        QCOMPARE(playlist->count(), size);
        for (int i = 0; i < size; ++i) {
            QCOMPARE(playlist->item(i)->data(N::PathRole).toString(), order[i]);
            QCOMPARE(playlist->item(i)->data(N::TrackIndexRole).toInt(), i);
        }
    }
};
QTEST_MAIN(TestShuffle121)
#include "testShuffle121.moc"
