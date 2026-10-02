#include "global.h"
#include "playbackEngineInterface.h"
#include "plugin.h"
#include <QtTest>
#include <atomic>
#include <gst/gst.h>
// Test-only access attaches output observation; engine methods remain real.
#define private public
#include "playbackEngineGstreamer.h"
#undef private

namespace NCore
{
    void cArgs(int *argc, const char ***argv)
    {
        static const char *args[] = {"testStress", nullptr};
        *argc = 1;
        *argv = args;
    }
} // namespace NCore

class TestStress : public QObject
{
    Q_OBJECT
private:
    QTemporaryDir dir;
    QStringList files;
    static void handoff(GstElement *, GstBuffer *buffer, GstPad *, gpointer data)
    {
        if (gst_buffer_get_size(buffer) > 0)
            ++*static_cast<std::atomic<int> *>(data);
    }
private slots:
    void initTestCase()
    {
        QVERIFY(dir.isValid());
        for (int n = 0; n < 2; ++n) {
            const QString path = dir.filePath(QString("tone-%1.wav").arg(n));
            QFile file(path);
            QVERIFY(file.open(QIODevice::WriteOnly));
            QDataStream out(&file);
            out.setByteOrder(QDataStream::LittleEndian);
            const int frames = (2 + n) * 48000;
            out.writeRawData("RIFF", 4);
            out << quint32(36 + frames * 2);
            out.writeRawData("WAVEfmt ", 8);
            out << quint32(16) << quint16(1) << quint16(1) << quint32(48000) << quint32(96000)
                << quint16(2) << quint16(16);
            out.writeRawData("data", 4);
            out << quint32(frames * 2);
            for (int i = 0; i < frames; ++i)
                out << qint16(i % 48 < 24 ? 8192 : -8192);
            QCOMPARE(out.status(), QDataStream::Ok);
            files.append(path);
        }
    }
    void rapidSwitchSeekAndRecover()
    {
        std::atomic<int> buffers{0}; // Outlives engine/stream callbacks.
        NPlaybackEngineGStreamer engine;
        engine.init();
        GstElement *sink = nullptr;
        g_object_get(engine.m_playbin, "audio-sink", &sink, nullptr);
        QVERIFY(sink);
        g_object_set(sink, "signal-handoffs", TRUE, nullptr);
        g_signal_connect(sink, "handoff", G_CALLBACK(handoff), &buffers);
        gst_object_unref(sink);
        engine.setVolume(0.2);
        QSignalSpy errors(&engine, &NPlaybackEngineGStreamer::message);
        QSignalSpy starts(&engine, &NPlaybackEngineGStreamer::mediaChanged);
        QSignalSpy finished(&engine, &NPlaybackEngineGStreamer::mediaFinished);
        connect(&engine, &NPlaybackEngineGStreamer::mediaChanged, &engine,
                [&](const QString &path, int context) {
                    engine.nextMediaRespond(files[path == files[0] ? 1 : 0], context + 1);
                });
        constexpr int iterations = 100;
        QElapsedTimer elapsed;
        elapsed.start();
        for (int i = 0; i < iterations; ++i) {
            engine.setMedia(files[i % 2], i * 10);
            engine.play();
            QTRY_VERIFY_WITH_TIMEOUT(engine.position() > 0.0, 3000);
            const int before = buffers.load();
            engine.setPosition(0.98);
            QTest::qWait(25); // Real status timer and streaming callback race.
            engine.setPosition(0.15);
            QTest::qWait(25);
            engine.pause();
            QCOMPARE(engine.state(), N::PlaybackPaused);
            engine.play();
            QTRY_VERIFY_WITH_TIMEOUT(buffers.load() > before, 3000);
            if (i % 5 == 0)
                engine.stop();
            QVERIFY(errors.isEmpty());
        }
        qInfo() << "iterations" << iterations << "output buffers" << buffers.load()
                << "stream starts" << starts.count() << "elapsed ms" << elapsed.elapsed();
        QVERIFY(starts.count() >= iterations);
        // The stress phase must leave a fully functioning engine, not merely a
        // responsive Qt loop: disconnect successors and play a complete known file.
        disconnect(&engine, &NPlaybackEngineGStreamer::mediaChanged, &engine, nullptr);
        engine.stop();
        const int before = buffers.load();
        const int oldFinished = finished.count();
        engine.setMedia(files[0], 10000);
        engine.play();
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), oldFinished + 1, 5000);
        QVERIFY(buffers.load() > before);
        QCOMPARE(engine.state(), N::PlaybackStopped);
        QCOMPARE(engine.currentMedia(), files[0]);
        QVERIFY(errors.isEmpty());
    }
};
QTEST_GUILESS_MAIN(TestStress)
#include "testStress.moc"
