#include <QtTest>
#include <QProcess>
#include <QTemporaryDir>
#include "tagReaderTaglib.h"

class TestIssue245 : public QObject
{
    Q_OBJECT
private slots:
    void bitrate_data()
    {
        QTest::addColumn<QString>("extension");
        QTest::addColumn<QStringList>("options");
        QTest::addColumn<int>("minimum");
        QTest::addColumn<int>("maximum");
        QTest::newRow("mp3-cbr") << "mp3" << (QStringList{"-c:a", "libmp3lame", "-b:a", "128k"}) << 127 << 130; // TagLib rounds the file-average bitrate.
        QTest::newRow("mp3-vbr") << "mp3" << (QStringList{"-c:a", "libmp3lame", "-q:a", "4"}) << 1 << 320;
        QTest::newRow("wav-pcm") << "wav" << (QStringList{"-c:a", "pcm_s16le"}) << 1411 << 1412;
        QTest::newRow("flac") << "flac" << (QStringList{"-c:a", "flac"}) << 1 << 1412;
        QTest::newRow("vorbis") << "ogg" << (QStringList{"-c:a", "libvorbis", "-q:a", "4"}) << 1 << 500;
        QTest::newRow("opus") << "opus" << (QStringList{"-c:a", "libopus", "-b:a", "96k"}) << 1 << 500;
        QTest::newRow("wavpack") << "wv" << (QStringList{"-c:a", "wavpack"}) << 1 << 1412;
    }
    void bitrate()
    {
        QFETCH(QString, extension);
        QFETCH(QStringList, options);
        QFETCH(int, minimum);
        QFETCH(int, maximum);
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString path = dir.filePath("tone." + extension);
        QProcess ffmpeg;
        QStringList args{"-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1", "-f", "lavfi", "-i",
                         "sine=frequency=997:sample_rate=44100:duration=3", "-ac", "2"};
        args << options << "-threads" << "1" << path;
        ffmpeg.start("ffmpeg", args);
        QVERIFY(ffmpeg.waitForFinished(30000));
        QVERIFY2(ffmpeg.exitCode() == 0, ffmpeg.readAllStandardError().constData());
        NTagReaderTaglib reader;
        reader.init();
        reader.setSource(path);
        bool ok = false;
        const int bitrate = reader.getTag('B').toInt(&ok);
        qInfo() << extension << "bitrate kbps:" << bitrate;
        QVERIFY(ok);
        QVERIFY(bitrate >= minimum);
        QVERIFY(bitrate <= maximum);
        reader.setSource("");
        QVERIFY(reader.getTag('B').isEmpty());
    }
    void unavailableBitrateIsEmpty()
    {
        NTagReaderTaglib reader;
        reader.init();
        reader.setSource("/nonexistent/issue245.mp3");
        QVERIFY(reader.getTag('B').isEmpty());
        QTemporaryDir dir;
        QFile invalid(dir.filePath("invalid.mp3"));
        QVERIFY(invalid.open(QIODevice::WriteOnly));
        invalid.write("Not an audio file");
        invalid.close();
        reader.setSource(invalid.fileName());
        QVERIFY(reader.getTag('B').isEmpty());
        reader.setSource("");
    }
};
QTEST_GUILESS_MAIN(TestIssue245)
#include "testIssue245.moc"
