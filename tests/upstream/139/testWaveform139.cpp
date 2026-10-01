// Native production-builder regressions and local-filesystem characterization.
#include <QtTest>
#include <QtEndian>
#include <memory>
#include <filesystem>
#include "common.h"
#include "waveformBuilderGstreamer.h"

// Expose only the existing protected cache operation for isolated I/O timing.
// Peaks still originate from a completed real GStreamer decode.
class CacheProbeBuilder : public NWaveformBuilderGstreamer
{
public:
    void storeCompleted(const QString &path) { peaksAppendToCache(path); }
    int cacheEntries() const { return m_peaksCache.size(); }
};

class TestWaveform139 : public QObject
{
    Q_OBJECT
    QTemporaryDir fixtures;
    QString shortFile, longFile, shortOgg, longFlac;
    int longSeconds = 600;
    QString metricsPath() const
    {
        const QString configured = qEnvironmentVariable("WAVEFORM_METRICS");
        return configured.isEmpty() ? QCoreApplication::applicationDirPath() + "/waveform-metrics.jsonl" : configured;
    }
    void metric(QJsonObject row)
    {
        row["test"] = QString::fromLatin1(QTest::currentTestFunction());
        QFile status("/proc/self/status");
        if (status.open(QIODevice::ReadOnly)) {
            const QList<QByteArray> lines = status.readAll().split('\n');
            for (const QByteArray &line : lines) {
                if (line.startsWith("VmRSS:") || line.startsWith("VmHWM:")) {
                    const QList<QByteArray> fields = line.simplified().split(' ');
                    row[fields[0] == "VmRSS:" ? "rss_kib" : "process_hwm_kib"] = fields[1].toDouble();
                }
            }
        }
        QFile output(metricsPath());
        QVERIFY2(output.open(QIODevice::WriteOnly | QIODevice::Append), qPrintable(output.errorString()));
        const QByteArray line = QJsonDocument(row).toJson(QJsonDocument::Compact) + '\n';
        QCOMPARE(output.write(line), qint64(line.size()));
    }
    QByteArray digest(const NWaveformPeaks &peaks)
    {
        QByteArray bytes;
        QDataStream stream(&bytes, QIODevice::WriteOnly);
        stream.setVersion(QDataStream::Qt_5_15);
        stream << peaks;
        return QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex();
    }
    void verifyComplete(NWaveformBuilderGstreamer &builder)
    {
        QVERIFY(builder.peaks().isCompleted());
        QVERIFY(!builder.isRunning());
        const NWaveformPeaks &peaks = builder.peaks();
        QVERIFY(peaks.size() > 1);
        QVERIFY(peaks.size() <= 2048);
        QVERIFY(peaks.positive(0) > 0.10 && peaks.positive(0) < 0.2);
        QVERIFY(peaks.negative(0) < -0.10 && peaks.negative(0) > -0.2);
        // The final bucket can contain less than a full signal period.
        QVERIFY(qMax(peaks.positive(peaks.size() - 1), peaks.positive(peaks.size() - 2)) > 0.65);
        QVERIFY(qMin(peaks.negative(peaks.size() - 1), peaks.negative(peaks.size() - 2)) < -0.65);
        float pos; int index;
        builder.positionAndIndex(pos, index);
        QCOMPARE(pos, 1.0f);
        QCOMPARE(index, peaks.size());
    }
    bool transcode(const QString &source, const QString &target, const QString &codec)
    {
        QProcess process;
        process.start(QStringLiteral(FFMPEG_EXECUTABLE), {"-nostdin", "-hide_banner", "-loglevel", "error",
                      "-y", "-i", source, "-c:a", codec, "-threads", "1", target});
        if (!process.waitForFinished(60000)) {
            process.kill(); process.waitForFinished();
            return false;
        }
        if (process.exitCode() != 0) qWarning().noquote() << process.readAllStandardError();
        return process.exitStatus() == QProcess::NormalExit && process.exitCode() == 0;
    }
    QString cachePath() const
    {
        return NCore::rcDir() + "/" + NCore::applicationBinaryName() + ".peaks";
    }
    // Deterministic PCM fixture, not an implementation of the peak algorithm.
    // Last quarter is louder: completion must include the tail, not just a prefix.
    bool writeWave(const QString &path, int seconds)
    {
        QFile file(path);
        if (!file.open(QIODevice::WriteOnly)) return false;
        const quint32 rate = 44100, bytes = rate * seconds * 4;
        QDataStream out(&file);
        out.setByteOrder(QDataStream::LittleEndian);
        out.writeRawData("RIFF", 4); out << quint32(36 + bytes);
        out.writeRawData("WAVEfmt ", 8); out << quint32(16) << quint16(1) << quint16(2);
        out << rate << quint32(rate * 4) << quint16(4) << quint16(16);
        out.writeRawData("data", 4); out << bytes;
        for (int second = 0; second < seconds; ++second) {
            QByteArray block(rate * 4, '\0');
            const qint16 amplitude = second >= seconds * 3 / 4 ? 24576 : 4096;
            for (quint32 sample = 0; sample < rate; ++sample) {
                const qint16 value = (sample / 100) % 2 ? amplitude : -amplitude;
                qToLittleEndian<qint16>(value, block.data() + sample * 4);
                qToLittleEndian<qint16>(value, block.data() + sample * 4 + 2);
            }
            if (file.write(block) != block.size()) return false;
        }
        return file.flush();
    }
private slots:
    void initTestCase()
    {
        QVERIFY(fixtures.isValid());
        shortFile = fixtures.filePath("short.wav");
        longFile = fixtures.filePath("long.wav");
        shortOgg = fixtures.filePath("short.ogg");
        longFlac = fixtures.filePath("long.flac");
        if (qEnvironmentVariableIsSet("WAVEFORM_LONG_SECONDS"))
            longSeconds = qEnvironmentVariableIntValue("WAVEFORM_LONG_SECONDS");
        QVERIFY(longSeconds >= 60 && longSeconds <= 3600);
        QVERIFY(writeWave(shortFile, 2));
        QVERIFY(writeWave(longFile, longSeconds));
        QVERIFY(transcode(shortFile, shortOgg, "libvorbis"));
        QVERIFY(transcode(longFile, longFlac, "flac"));
        QFile::remove(metricsPath());
        gchar *gstVersion = gst_version_string();
        metric({{"kind", "environment"}, {"qt", qVersion()},
                {"gstreamer", QString::fromLatin1(gstVersion)},
                {"long_seconds", longSeconds}, {"long_wav_bytes", double(QFileInfo(longFile).size())},
                {"long_flac_bytes", double(QFileInfo(longFlac).size())}});
        g_free(gstVersion);
    }
    void init() { QFile::remove(cachePath()); }
    void cleanup() { QFile::remove(cachePath()); }
    void coldAndWarmCache_data()
    {
        QTest::addColumn<QString>("path");
        QTest::newRow("short-wav") << shortFile;
        QTest::newRow("short-ogg") << shortOgg;
        QTest::newRow("long-wav") << longFile;
        QTest::newRow("long-flac") << longFlac;
    }
    void coldAndWarmCache()
    {
        QFETCH(QString, path);
        QByteArray expected;
        for (int pass = 0; pass < 3; ++pass) {
            NWaveformBuilderGstreamer builder;
            builder.init();
            QSignalSpy starts(&builder, &QThread::started);
            QElapsedTimer wall, gap;
            double maxGapMs = 0;
            QTimer heartbeat;
            heartbeat.setTimerType(Qt::PreciseTimer);
            connect(&heartbeat, &QTimer::timeout, this, [&] {
                maxGapMs = qMax(maxGapMs, gap.nsecsElapsed() / 1e6);
                gap.restart();
            });
            gap.start(); heartbeat.start(5); wall.start();
            builder.start(path);
            const double startMs = wall.nsecsElapsed() / 1e6;
            if (pass > 0) QVERIFY2(builder.peaks().isCompleted(), "Warm disk cache must complete synchronously");
            while (!builder.peaks().isCompleted() && wall.elapsed() < 30000)
                QTest::qWait(1);
            const double completeMs = wall.nsecsElapsed() / 1e6;
            maxGapMs = qMax(maxGapMs, gap.nsecsElapsed() / 1e6);
            heartbeat.stop();
            verifyComplete(builder);
            QVERIFY(QFileInfo(cachePath()).size() > 0);
            const QByteArray actual = digest(builder.peaks());
            if (pass == 0) {
                expected = actual;
                QCOMPARE(starts.count(), 1);
            } else {
                QCOMPARE(actual, expected);
                QCOMPARE(starts.count(), 0);
            }
            metric({{"kind", "complete"}, {"fixture", QFileInfo(path).fileName()},
                    {"cache", pass == 0 ? "cold" : "warm-disk"}, {"pass", pass},
                    {"start_ms", startMs}, {"complete_ms", completeMs}, {"max_event_gap_ms", maxGapMs},
                    {"pairs", builder.peaks().size()}, {"digest", QString::fromLatin1(actual)},
                    {"cache_bytes", double(QFileInfo(cachePath()).size())}});
        }
    }
    void cacheSerialization()
    {
        CacheProbeBuilder builder;
        builder.init(); builder.start(longFile);
        QTRY_VERIFY_WITH_TIMEOUT(builder.peaks().isCompleted(), 30000);
        verifyComplete(builder);
        const QByteArray expected = digest(builder.peaks());
        for (int entries = 1; entries <= 100; ++entries) {
            QString path = longFile;
            if (entries > 1) {
                // Real aliases of the same PCM, not fabricated cache records.
                path = fixtures.filePath(QString("cache-%1.wav").arg(entries));
                std::error_code error;
                std::filesystem::create_hard_link(
                    std::filesystem::u8path(longFile.toUtf8().constData()),
                    std::filesystem::u8path(path.toUtf8().constData()), error);
                if (error) QSKIP("Fixture filesystem does not support hard links");
            }
            QElapsedTimer elapsed; elapsed.start();
            builder.storeCompleted(path);
            const double saveMs = elapsed.nsecsElapsed() / 1e6;
            QCOMPARE(builder.cacheEntries(), entries);
            metric({{"kind", "cache-save"}, {"entries", entries}, {"save_ms", saveMs},
                    {"cache_bytes", double(QFileInfo(cachePath()).size())}});
            if (entries == 1 || entries == 10 || entries == 100) {
                NWaveformBuilderGstreamer loaded;
                loaded.init(); elapsed.restart(); loaded.start(path);
                const double loadMs = elapsed.nsecsElapsed() / 1e6;
                QVERIFY(loaded.peaks().isCompleted());
                QCOMPARE(digest(loaded.peaks()), expected);
                metric({{"kind", "cache-load"}, {"entries", entries}, {"load_ms", loadMs}});
            }
        }
    }
    void rapidCancellationAndClose()
    {
        NWaveformBuilderGstreamer reusable;
        reusable.init();
        for (int iteration = 0; iteration < 50; ++iteration) {
            const int delay = iteration % 3 == 0 ? 0 : iteration % 3 == 1 ? 1 : 10;
            reusable.start(longFile);
            if (delay) QTest::qWait(delay);
            QElapsedTimer elapsed;
            elapsed.start();
            reusable.stop();
            const double stopMs = elapsed.nsecsElapsed() / 1e6;
            QVERIFY(!reusable.isRunning());
            QVERIFY(!reusable.peaks().isCompleted());
            QVERIFY(!QFileInfo::exists(cachePath()));
            QVERIFY2(stopMs < 5000, "Stop exceeded generous hang watchdog");
            metric({{"kind", "cancel"}, {"iteration", iteration}, {"delay_ms", delay}, {"stop_ms", stopMs}});
            std::unique_ptr<NWaveformBuilderGstreamer> closing(new NWaveformBuilderGstreamer);
            closing->init(); closing->start(longFile);
            if (delay) QTest::qWait(delay);
            elapsed.restart();
            closing.reset();
            const double closeMs = elapsed.nsecsElapsed() / 1e6;
            QVERIFY(!QFileInfo::exists(cachePath()));
            QVERIFY2(closeMs < 5000, "Destructor exceeded generous hang watchdog");
            metric({{"kind", "close"}, {"iteration", iteration}, {"delay_ms", delay}, {"close_ms", closeMs}});
        }
        reusable.start(shortFile);
        QTRY_VERIFY_WITH_TIMEOUT(reusable.peaks().isCompleted(), 5000);
        verifyComplete(reusable);
    }
    void movedDirectoryDuringBuild()
    {
        const QString before = fixtures.filePath("Música original");
        const QString after = fixtures.filePath("Música moved");
        QVERIFY(QDir().mkdir(before));
        const QString oldPath = before + "/long.wav";
        const QString newPath = after + "/long.wav";
        QVERIFY(QFile::copy(longFile, oldPath));
        NWaveformBuilderGstreamer builder;
        builder.init(); builder.start(oldPath);
        QTest::qWait(10);
        QVERIFY(builder.isRunning());
        QVERIFY(!builder.peaks().isCompleted());
        QElapsedTimer elapsed; elapsed.start();
        const bool renamed = QDir().rename(before, after);
        const double renameMs = elapsed.nsecsElapsed() / 1e6;
        if (!renamed) QSKIP("Filesystem does not permit renaming the directory of an open file");
        QTRY_VERIFY_WITH_TIMEOUT(builder.peaks().isCompleted(), 30000);
        const double completionMs = elapsed.nsecsElapsed() / 1e6;
        verifyComplete(builder);
        builder.start(oldPath);
        QVERIFY(!builder.isRunning());
        QVERIFY(!builder.peaks().isCompleted());
        QCOMPARE(builder.peaks().size(), 0);
        builder.start(newPath);
        QTRY_VERIFY_WITH_TIMEOUT(builder.peaks().isCompleted(), 30000);
        verifyComplete(builder);
        metric({{"kind", "rename"}, {"rename_ms", renameMs}, {"complete_after_move_ms", completionMs}});
    }
    void removedDuringBuild()
    {
        const QString path = fixtures.filePath("removed.wav");
        QVERIFY(QFile::copy(longFile, path));
        NWaveformBuilderGstreamer builder;
        builder.init(); builder.start(path);
        QTest::qWait(10);
        QVERIFY(builder.isRunning());
        QVERIFY(!builder.peaks().isCompleted());
        QElapsedTimer elapsed; elapsed.start();
        if (!QFile::remove(path)) QSKIP("Filesystem does not permit unlinking an open file");
        QTRY_VERIFY_WITH_TIMEOUT(builder.peaks().isCompleted(), 30000);
        verifyComplete(builder);
        metric({{"kind", "unlink"}, {"complete_after_unlink_ms", elapsed.nsecsElapsed() / 1e6}});
        builder.start(path);
        QVERIFY(!builder.peaks().isCompleted());
        QCOMPARE(builder.peaks().size(), 0);
    }
    void decodeErrorStopsWorker()
    {
        const QString invalid = fixtures.filePath("invalid.wav");
        QFile file(invalid);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write("not an audio file"), qint64(17));
        file.close();
        NWaveformBuilderGstreamer builder;
        builder.init();
        builder.start(invalid);
        // Allow both thread start and the production 100 ms bus timer to run.
        QTest::qWait(300);
        QTRY_VERIFY_WITH_TIMEOUT(!builder.isRunning(), 1000);
        QVERIFY(!builder.peaks().isCompleted());
        QVERIFY(!QFileInfo::exists(cachePath()));
        builder.start(shortFile);
        QTRY_VERIFY_WITH_TIMEOUT(builder.peaks().isCompleted(), 5000);
    }
    void missingAfterCompletedClearsPeaks()
    {
        NWaveformBuilderGstreamer builder;
        builder.init();
        builder.start(shortFile);
        QTRY_VERIFY_WITH_TIMEOUT(builder.peaks().isCompleted(), 5000);
        builder.start(fixtures.filePath("missing.wav"));
        QVERIFY(!builder.isRunning());
        QVERIFY2(!builder.peaks().isCompleted(), "Missing input must not retain previous complete waveform");
        QCOMPARE(builder.peaks().size(), 0);
        float position; int index;
        builder.positionAndIndex(position, index);
        QCOMPARE(position, 0.0f);
        QCOMPARE(index, 0);
    }
};
QTEST_GUILESS_MAIN(TestWaveform139)
#include "testWaveform139.moc"
