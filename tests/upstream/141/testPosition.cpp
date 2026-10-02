#include "global.h"
#include "playbackEngineInterface.h"
#include "plugin.h"
#include <QtTest>
#include <atomic>
#include <cmath>
#include <gst/app/gstappsink.h>
#define private public
#include "playbackEngineGstreamer.h"
#undef private

namespace NCore
{
    void cArgs(int *argc, const char ***argv)
    {
        static const char *args[] = {"testPosition", nullptr};
        *argc = 1;
        *argv = args;
    }
} // namespace NCore

struct OutputClock
{
    std::atomic<qint64> firstUsec{0};
    std::atomic<qint64> lastEndUsec{0};
    std::atomic<qint64> samples{0};
    static GstFlowReturn receive(GstAppSink *sink, gpointer data)
    {
        auto &clock = *static_cast<OutputClock *>(data);
        GstSample *sample = gst_app_sink_pull_sample(sink);
        if (!sample)
            return GST_FLOW_ERROR;
        GstBuffer *buffer = gst_sample_get_buffer(sample);
        qint64 now = g_get_monotonic_time();
        qint64 unset = 0;
        clock.firstUsec.compare_exchange_strong(unset, now);
        clock.samples += gst_buffer_get_size(buffer) / sizeof(float);
        clock.lastEndUsec = now + GST_BUFFER_DURATION(buffer) / GST_USECOND;
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }
};

class TestPosition : public QObject
{
    Q_OBJECT
private slots:
    void positionTracksClockedOutput_data()
    {
        QTest::addColumn<int>("durationMsec");
        QTest::newRow("50ms") << 50;
        QTest::newRow("250ms") << 250;
        QTest::newRow("800ms") << 800;
        QTest::newRow("2000ms") << 2000;
    }
    void positionTracksClockedOutput()
    {
        QFETCH(int, durationMsec);
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString path = dir.filePath("short-signal.wav");
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QDataStream out(&file);
        out.setByteOrder(QDataStream::LittleEndian);
        const int frames = durationMsec * 48;
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
        file.close();

        OutputClock clock;
        NPlaybackEngineGStreamer engine;
        engine.init();
        GstElement *sink = gst_element_factory_make("appsink", nullptr);
        QVERIFY(sink);
        GstCaps *caps = gst_caps_from_string("audio/x-raw,format=F32LE,channels=1,rate=48000");
        g_object_set(sink, "caps", caps, "sync", TRUE, "emit-signals", TRUE, nullptr);
        gst_caps_unref(caps);
        g_signal_connect(sink, "new-sample", G_CALLBACK(OutputClock::receive), &clock);
        g_object_set(engine.m_playbin, "audio-sink", sink, nullptr);
        engine.setVolume(0.2);
        QSignalSpy errors(&engine, &NPlaybackEngineGStreamer::message);
        QSignalSpy finished(&engine, &NPlaybackEngineGStreamer::mediaFinished);
        QVector<QPair<double, double>> positions;
        qint64 finishedUsec = 0;
        connect(&engine, &NPlaybackEngineGStreamer::positionChanged, &engine, [&](qreal p) {
            const qint64 start = clock.firstUsec.load();
            if (p > 0 && start > 0)
                positions.append({p, (g_get_monotonic_time() - start) / 1000.0});
        });
        connect(&engine, &NPlaybackEngineGStreamer::mediaFinished, &engine,
                [&](const QString &, int) { finishedUsec = g_get_monotonic_time(); });
        engine.setMedia(path, 0);
        engine.play();
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, durationMsec + 3000);
        QVERIFY(errors.isEmpty());
        QCOMPARE(clock.samples.load(), qint64(frames));
        QVERIFY(clock.firstUsec.load() > 0);
        // appsink receives at buffer presentation START. Include the final
        // buffer duration rather than mistaking callback time for audio END.
        QVERIFY2(finishedUsec >= clock.lastEndUsec.load() - 20000,
                 "engine completed before the final decoded buffer finished rendering");
        double maxSkew = 0;
        double highestPosition = 0;
        for (const auto &point : positions) {
            maxSkew = qMax(maxSkew, std::abs(point.first * durationMsec - point.second));
            highestPosition = qMax(highestPosition, point.first);
        }
        qInfo() << "duration ms" << durationMsec << "PCM samples" << clock.samples.load()
                << "position signals" << positions.size() << "max clock skew ms" << maxSkew
                << "highest position" << highestPosition;
        QVERIFY2(maxSkew < 60,
                 "position delivered to waveform is ahead of/behind decoded output clock");
        if (durationMsec >= 250)
            QVERIFY(highestPosition > 0.5);
        // A 50ms file can finish before the first100ms status tick. Do not claim
        // visible intermediate progress from an empty set of position signals.
    }
};
QTEST_GUILESS_MAIN(TestPosition)
#include "testPosition.moc"
