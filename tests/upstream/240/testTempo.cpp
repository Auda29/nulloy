#include "global.h"
#include "playbackEngineInterface.h"
#include "plugin.h"
#include <QtTest>
#include <cmath>
#include <gst/app/gstappsink.h>
// Sink instrumentation only; the production engine is compiled unchanged.
#define private public
#include "playbackEngineGstreamer.h"
#undef private

namespace NCore
{
    void cArgs(int *argc, const char ***argv)
    {
        static const char *args[] = {"testTempo", nullptr};
        *argc = 1;
        *argv = args;
    }
} // namespace NCore

struct Trace
{
    struct Cycle
    {
        qint64 frames = 0;
        qint64 tailFrames = 0;
        double renderedSeconds = 0;
    };
    QMutex mutex;
    QVector<Cycle> cycles;
    GstClockTime previous = GST_CLOCK_TIME_NONE;
    QString error;
    static GstFlowReturn receive(GstAppSink *sink, gpointer data)
    {
        auto &trace = *static_cast<Trace *>(data);
        GstSample *sample = gst_app_sink_pull_sample(sink);
        if (!sample)
            return GST_FLOW_ERROR;
        GstBuffer *buffer = gst_sample_get_buffer(sample);
        const GstSegment *segment = gst_sample_get_segment(sample);
        GstMapInfo map;
        QMutexLocker locker(&trace.mutex);
        const GstClockTime pts = GST_BUFFER_PTS(buffer);
        if (trace.cycles.isEmpty() ||
            (GST_CLOCK_TIME_IS_VALID(trace.previous) && pts < trace.previous))
            trace.cycles.append(Cycle{});
        trace.previous = pts;
        const GstStructure *caps = gst_caps_get_structure(gst_sample_get_caps(sample), 0);
        if (QString(gst_structure_get_string(caps, "format")) != "F32LE") {
            trace.error = "unexpected PCM format";
        } else if (gst_buffer_map(buffer, &map, GST_MAP_READ)) {
            Cycle &cycle = trace.cycles.last();
            cycle.frames += map.size / sizeof(float);
            cycle.renderedSeconds += double(map.size / sizeof(float)) / 48000.0 / segment->rate;
            for (gsize i = 0; i < map.size / sizeof(float); ++i) {
                float value;
                memcpy(&value, map.data + i * sizeof(float), sizeof(float));
                if (std::abs(value) > 0.2)
                    ++cycle.tailFrames;
            }
            gst_buffer_unmap(buffer, &map);
        }
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }
};

class TestTempo : public QObject
{
    Q_OBJECT
private:
    QTemporaryDir dir;
    QString wav;
private slots:
    void initTestCase()
    {
        QVERIFY(dir.isValid());
        wav = dir.filePath("two-seconds-tail-marker.wav");
        QFile file(wav);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QDataStream out(&file);
        out.setByteOrder(QDataStream::LittleEndian);
        constexpr int frames = 96000;
        out.writeRawData("RIFF", 4);
        out << quint32(36 + frames * 2);
        out.writeRawData("WAVEfmt ", 8);
        out << quint32(16) << quint16(1) << quint16(1) << quint32(48000) << quint32(96000)
            << quint16(2) << quint16(16);
        out.writeRawData("data", 4);
        out << quint32(frames * 2);
        for (int i = 0; i < frames; ++i) {
            const int amplitude = i >= 84000 ? 8192 : 4096;
            out << qint16(i % 48 < 24 ? amplitude : -amplitude);
        }
        QCOMPARE(out.status(), QDataStream::Ok);
    }
    void repeatReachesTailAtRequestedRate_data()
    {
        QTest::addColumn<double>("rate");
        QTest::newRow("half") << 0.5;
        QTest::newRow("normal") << 1.0;
        QTest::newRow("double") << 2.0;
    }
    void repeatReachesTailAtRequestedRate()
    {
        QFETCH(double, rate);
        Trace trace;
        NPlaybackEngineGStreamer engine;
        engine.init();
        GstElement *sink = gst_element_factory_make("appsink", nullptr);
        QVERIFY(sink);
        GstCaps *caps = gst_caps_from_string("audio/x-raw,format=F32LE,channels=1,rate=48000");
        g_object_set(sink, "caps", caps, "sync", TRUE, "emit-signals", TRUE, nullptr);
        gst_caps_unref(caps);
        g_signal_connect(sink, "new-sample", G_CALLBACK(Trace::receive), &trace);
        g_object_set(engine.m_playbin, "audio-sink", sink, nullptr);
        engine.setVolume(1.0);
        engine.setSpeed(rate);
        QSignalSpy errors(&engine, &NPlaybackEngineGStreamer::message);
        QSignalSpy finished(&engine, &NPlaybackEngineGStreamer::mediaFinished);
        int starts = 0;
        connect(&engine, &NPlaybackEngineGStreamer::mediaChanged, &engine,
                [&](const QString &, int) {
                    qInfo() << "stream start" << ++starts;
                    if (starts < 3)
                        engine.nextMediaRespond(wav, starts);
                });
        engine.setMedia(wav, 0);
        QElapsedTimer elapsed;
        elapsed.start();
        engine.play();
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 1, 20000);
        const qint64 wallMsec = elapsed.elapsed();
        QVERIFY(errors.isEmpty());
        QCOMPARE(starts, 3);
        QMutexLocker locker(&trace.mutex);
        QVERIFY2(trace.error.isEmpty(), qPrintable(trace.error));
        for (int i = 0; i < trace.cycles.size(); ++i) {
            const auto &cycle = trace.cycles[i];
            qInfo() << "cycle" << i << "rate" << rate << "frames" << cycle.frames << "tail frames"
                    << cycle.tailFrames << "rendered seconds" << cycle.renderedSeconds
                    << "total wall ms" << wallMsec;
        }
        QCOMPARE(trace.cycles.size(), 3);
        for (const auto &cycle : trace.cycles) {
            QVERIFY2(cycle.frames >= 90000 && cycle.frames <= 102000,
                     "loop lost or duplicated more than 125ms of media");
            QCOMPARE(cycle.tailFrames, qint64(12000));
            QVERIFY2(std::abs(cycle.renderedSeconds - 2.0 / rate) < 0.25,
                     "output segment timing does not follow playback rate");
        }
        QVERIFY2(std::abs(wallMsec - 6000.0 / rate) < 1000,
                 "clocked sink repeat timing differs from media/rate");
    }
};
QTEST_GUILESS_MAIN(TestTempo)
#include "testTempo.moc"
