#include <QtTest>
#include <QProcess>
#include <QTemporaryDir>
#include "playbackEngineGstreamer.h"

// CLI-only shim: the actual engine and its GStreamer message handling are linked.
namespace NCore {
void cArgs(int *argc, const char ***argv)
{
    static const char *args[] = {"testIssue176", nullptr};
    *argc = 1;
    *argv = args;
}
}

// Change registry ranks only in this process, never installed plugin files.
class DisabledAlawDecoders
{
    QList<QPair<GstPluginFeature *, guint>> saved;
public:
    DisabledAlawDecoders()
    {
        GstCaps *caps = gst_caps_from_string("audio/x-alaw");
        GList *all = gst_element_factory_list_get_elements(GST_ELEMENT_FACTORY_TYPE_DECODER, GST_RANK_NONE);
        GList *matching = gst_element_factory_list_filter(all, caps, GST_PAD_SINK, FALSE);
        for (GList *it = matching; it; it = it->next) {
            auto *feature = GST_PLUGIN_FEATURE(it->data);
            saved.append({GST_PLUGIN_FEATURE(gst_object_ref(feature)), gst_plugin_feature_get_rank(feature)});
            gst_plugin_feature_set_rank(feature, GST_RANK_NONE);
        }
        gst_plugin_feature_list_free(matching);
        gst_plugin_feature_list_free(all);
        gst_caps_unref(caps);
    }
    ~DisabledAlawDecoders()
    {
        for (const auto &entry : saved) {
            gst_plugin_feature_set_rank(entry.first, entry.second);
            gst_object_unref(entry.first);
        }
    }
};

class TestIssue176 : public QObject
{
    Q_OBJECT
    QTemporaryDir fixtures;
    QString makeWav(const QString &codec)
    {
        const QString path = fixtures.filePath(codec + ".wav");
        QProcess ffmpeg;
        ffmpeg.start("ffmpeg", {"-v", "error", "-nostdin", "-y", "-threads", "1",
            "-filter_threads", "1", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000:duration=1",
            "-ac", "1", "-c:a", codec, "-threads", "1", path});
        if (!ffmpeg.waitForFinished(30000) || ffmpeg.exitCode() != 0) {
            qWarning() << ffmpeg.readAllStandardError();
            return {};
        }
        return path;
    }
private slots:
    void initTestCase()
    {
        QVERIFY(fixtures.isValid());
        gst_init(nullptr, nullptr);
        qInfo() << gst_version_string();
    }
    void recorderFormats_data()
    {
        QTest::addColumn<QString>("codec");
        QTest::addColumn<bool>("required");
        for (const char *codec : {"pcm_s16le", "pcm_s24le", "pcm_f32le", "pcm_alaw", "pcm_mulaw"})
            QTest::newRow(codec) << QString(codec) << true;
        for (const char *codec : {"adpcm_ms", "adpcm_ima_wav"})
            QTest::newRow(codec) << QString(codec) << false;
    }
    void recorderFormats()
    {
        QFETCH(QString, codec);
        QFETCH(bool, required);
        const QString path = makeWav(codec);
        QVERIFY(!path.isEmpty());
        NPlaybackEngineGStreamer engine;
        engine.init();
        QStringList messages;
        int failures = 0;
        int finished = 0;
        connect(&engine, &NPlaybackEngineGStreamer::message, this,
            [&](N::MessageIcon, const QString &file, const QString &text) {
                QCOMPARE(file, path);
                messages << text;
            });
        connect(&engine, &NPlaybackEngineGStreamer::mediaFailed, this,
            [&](const QString &, int) { ++failures; });
        connect(&engine, &NPlaybackEngineGStreamer::mediaFinished, this,
            [&](const QString &, int) { ++finished; });
        engine.setMedia(path, 176);
        engine.play();
        QTRY_VERIFY_WITH_TIMEOUT(finished > 0 || failures > 0, 10000);
        qInfo() << codec << "finished" << finished << "failed" << failures << messages;
        if (required || finished > 0) {
            QCOMPARE(failures, 0);
            QCOMPARE(finished, 1);
        } else {
            // Optional recorder decoders: classify missing, never silently pass arbitrary errors.
            QVERIFY(messages.join(" ").contains("Missing GStreamer plugin:"));
            QVERIFY(messages.join(" ").contains("audio/x-adpcm"));
        }
        engine.stop();
    }
    void missingDecoderReportsDetailsAndRecovers()
    {
        const QString missingPath = makeWav("pcm_alaw");
        const QString playablePath = makeWav("pcm_s16le");
        QVERIFY(!missingPath.isEmpty());
        QVERIFY(!playablePath.isEmpty());
        NPlaybackEngineGStreamer engine;
        engine.init();
        QStringList messages;
        int failures = 0;
        int finished = 0;
        connect(&engine, &NPlaybackEngineGStreamer::message, this,
            [&](N::MessageIcon, const QString &file, const QString &text) {
                QCOMPARE(file, missingPath);
                messages << text;
            });
        connect(&engine, &NPlaybackEngineGStreamer::mediaFailed, this,
            [&](const QString &, int) { ++failures; });
        connect(&engine, &NPlaybackEngineGStreamer::mediaFinished, this,
            [&](const QString &, int) { ++finished; });
        {
            DisabledAlawDecoders disabled;
            engine.setMedia(missingPath, 1);
            engine.play();
            QTRY_VERIFY_WITH_TIMEOUT(failures > 0, 10000);
            QVERIFY(messages.join(" ").contains("Missing GStreamer plugin:"));
            QVERIFY(messages.join(" ").contains("audio/x-alaw"));
            qInfo() << "Controlled missing-decoder diagnostics:" << messages;
            engine.stop();
        }
        failures = 0;
        engine.setMedia(playablePath, 2);
        engine.play();
        QTRY_COMPARE_WITH_TIMEOUT(finished, 1, 10000);
        QCOMPARE(failures, 0);
        engine.stop();
    }
};
QTEST_GUILESS_MAIN(TestIssue176)
#include "testIssue176.moc"
