#include "global.h"
#include "playbackEngineInterface.h"
#include "plugin.h"
#include <QtTest>
#include <cmath>
#include <gst/app/gstappsink.h>
// Test instrumentation only: replace the engine's sink, never its playback logic.
#define private public
#include "playbackEngineGstreamer.h"
#undef private

namespace NCore
{
    void cArgs(int *argc, const char ***argv)
    {
        static const char *args[] = {"testGain", nullptr};
        *argc = 1;
        *argv = args;
    }
} // namespace NCore

struct Capture
{
    QMutex mutex;
    qint64 samples = 0;
    double sumSquares = 0;
    double peak = 0;
    bool badCaps = false;

    void clear()
    {
        QMutexLocker lock(&mutex);
        samples = 0;
        sumSquares = peak = 0;
        badCaps = false;
    }
    static GstFlowReturn receive(GstAppSink *sink, gpointer data)
    {
        auto *self = static_cast<Capture *>(data);
        GstSample *sample = gst_app_sink_pull_sample(sink);
        if (!sample)
            return GST_FLOW_ERROR;
        GstMapInfo map;
        GstBuffer *buffer = gst_sample_get_buffer(sample);
        const GstStructure *caps = gst_caps_get_structure(gst_sample_get_caps(sample), 0);
        QMutexLocker lock(&self->mutex);
        if (QString(gst_structure_get_string(caps, "format")) != "F32LE") {
            self->badCaps = true;
        } else if (gst_buffer_map(buffer, &map, GST_MAP_READ)) {
            for (gsize i = 0; i < map.size / sizeof(float); ++i) {
                float value;
                memcpy(&value, map.data + i * sizeof(float), sizeof(float));
                self->sumSquares += double(value) * value;
                self->peak = qMax(self->peak, std::abs(double(value)));
                ++self->samples;
            }
            gst_buffer_unmap(buffer, &map);
        }
        gst_sample_unref(sample);
        return GST_FLOW_OK;
    }
};

class TestGain : public QObject
{
    Q_OBJECT
private:
    QTemporaryDir dir;
    QString wav;
    static constexpr int sampleRate = 48000;
    static constexpr int frameCount = 96000;
    // Exactly representable S16 square-wave amplitude, with an integral cycle count.
    static constexpr double inputPeak = 8192.0 / 32768.0;

    void checkCapture(Capture &capture, double gain, int repetitions = 1)
    {
        QMutexLocker lock(&capture.mutex);
        QVERIFY(!capture.badCaps);
        QCOMPARE(capture.samples, qint64(frameCount * repetitions));
        double rms = std::sqrt(capture.sumSquares / capture.samples);
        qInfo() << "PCM samples" << capture.samples << "gain" << gain << "RMS" << rms << "peak"
                << capture.peak;
        QVERIFY2(std::abs(rms - inputPeak * gain) < 0.00002,
                 "decoded output gain differs from request");
        QVERIFY2(std::abs(capture.peak - inputPeak * gain) < 0.00002,
                 "unexpected peak (including startup/transition)");
    }
private slots:
    void initTestCase()
    {
        QVERIFY(dir.isValid());
        wav = dir.filePath("known-square.wav");
        QFile file(wav);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QDataStream out(&file);
        out.setByteOrder(QDataStream::LittleEndian);
        out.writeRawData("RIFF", 4);
        out << quint32(36 + frameCount * 2);
        out.writeRawData("WAVEfmt ", 8);
        out << quint32(16) << quint16(1) << quint16(1) << quint32(sampleRate)
            << quint32(sampleRate * 2) << quint16(2) << quint16(16);
        out.writeRawData("data", 4);
        out << quint32(frameCount * 2);
        for (int i = 0; i < frameCount; ++i)
            out << qint16(i % 48 < 24 ? 8192 : -8192);
        QCOMPARE(out.status(), QDataStream::Ok);
    }
    void gainSurvivesLifecycle_data()
    {
        QTest::addColumn<double>("gain");
        QTest::newRow("muted") << 0.0;
        QTest::newRow("twenty-percent") << 0.2;
        QTest::newRow("unity") << 1.0;
    }
    void gainSurvivesLifecycle()
    {
        QFETCH(double, gain);
        Capture capture; // Must outlive the engine and streaming callbacks.
        NPlaybackEngineGStreamer engine;
        engine.init();
        GstElement *sink = gst_element_factory_make("appsink", nullptr);
        QVERIFY(sink);
        GstCaps *caps = gst_caps_from_string("audio/x-raw,format=F32LE,channels=1,rate=48000");
        g_object_set(sink, "caps", caps, "sync", TRUE, "emit-signals", TRUE, nullptr);
        gst_caps_unref(caps);
        g_signal_connect(sink, "new-sample", G_CALLBACK(Capture::receive), &capture);
        g_object_set(engine.m_playbin, "audio-sink", sink, nullptr);
        QSignalSpy errors(&engine, &NPlaybackEngineGStreamer::message);
        QSignalSpy finished(&engine, &NPlaybackEngineGStreamer::mediaFinished);
        engine.setVolume(gain);
        for (int reopen = 0; reopen < 3; ++reopen) {
            capture.clear();
            engine.setMedia(wav, reopen);
            engine.play();
            QTRY_COMPARE_WITH_TIMEOUT(finished.count(), reopen + 1, 3000);
            QVERIFY(errors.isEmpty());
            checkCapture(capture, gain);
            QVERIFY(std::abs(engine.volume() - gain) < 0.000001);
        }
        // stop/play without re-selecting the file must retain gain as well.
        capture.clear();
        engine.play();
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 4, 3000);
        checkCapture(capture, gain);

        // Real about-to-finish gapless handoffs, using the production successor API.
        capture.clear();
        int starts = 0;
        connect(&engine, &NPlaybackEngineGStreamer::mediaChanged, &engine,
                [&](const QString &, int) {
                    if (++starts < 3)
                        engine.nextMediaRespond(wav, starts);
                });
        engine.setMedia(wav, 0);
        engine.play();
        QTRY_COMPARE_WITH_TIMEOUT(finished.count(), 5, 9000);
        QCOMPARE(starts, 3);
        QVERIFY(errors.isEmpty());
        QVERIFY(std::abs(engine.volume() - gain) < 0.000001);
        checkCapture(capture, gain, 3);
    }
};
QTEST_GUILESS_MAIN(TestGain)
#include "testGain.moc"
