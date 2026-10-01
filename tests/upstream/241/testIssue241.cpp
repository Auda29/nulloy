#include <QtTest>
#include <QProcess>
#include <QTemporaryDir>
#include <mpegfile.h>
#include <id3v2tag.h>
#include <textidentificationframe.h>
#include "tagReaderTaglib.h"

class TestIssue241 : public QObject
{
    Q_OBJECT
private slots:
    void mixedEncodings_data()
    {
        QTest::addColumn<QString>("selection");
        QTest::addColumn<int>("encoding");
        QTest::addColumn<bool>("legacy");
        QTest::newRow("utf8-with-cp1251-selected") << "Windows-1251" << int(TagLib::String::UTF8) << false;
        QTest::newRow("utf16-with-cp1251-selected") << "Windows-1251" << int(TagLib::String::UTF16) << false;
        QTest::newRow("legacy-cp1251") << "Windows-1251" << int(TagLib::String::Latin1) << true;
        QTest::newRow("utf8-default") << "" << int(TagLib::String::UTF8) << false;
        QTest::newRow("utf8-selected") << "UTF-8" << int(TagLib::String::UTF8) << false;
        QTest::newRow("unknown-selection") << "not-a-codec" << int(TagLib::String::UTF8) << false;
    }
    void mixedEncodings()
    {
        QFETCH(QString, selection);
        QFETCH(int, encoding);
        QFETCH(bool, legacy);
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        const QString path = dir.filePath("generated.mp3");
        QProcess ffmpeg;
        ffmpeg.start("ffmpeg", {"-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1", "-f", "lavfi", "-i",
                               "sine=frequency=440:duration=1", "-c:a", "libmp3lame", "-threads", "1", path});
        QVERIFY(ffmpeg.waitForFinished(30000));
        QVERIFY2(ffmpeg.exitCode() == 0, ffmpeg.readAllStandardError().constData());
        const QString expected = legacy ? QString::fromUtf8("Зашумела шум-дуброўка")
                                        : QString::fromUtf8("Привет 日本語 🎵");
        {
#ifdef WIN32
            TagLib::MPEG::File file(reinterpret_cast<const wchar_t *>(path.utf16()));
#else
            TagLib::MPEG::File file(path.toUtf8().constData());
#endif
            QVERIFY(file.isValid());
            auto *tag = file.ID3v2Tag(true);
            for (const char *key : {"TIT2", "TPE1", "TALB"}) {
                tag->removeFrames(key);
                auto *frame = new TagLib::ID3v2::TextIdentificationFrame(
                    key, static_cast<TagLib::String::Type>(encoding));
                if (legacy) {
                    auto *codec = QTextCodec::codecForName("Windows-1251");
                    QVERIFY(codec);
                    const QByteArray bytes = codec->fromUnicode(expected);
                    frame->setText(TagLib::String(bytes.constData(), TagLib::String::Latin1));
                } else {
                    frame->setText(TagLib::String(expected.toUtf8().constData(), TagLib::String::UTF8));
                }
                tag->addFrame(frame);
            }
            QVERIFY(file.save(TagLib::MPEG::File::ID3v2, TagLib::File::StripOthers,
                              TagLib::ID3v2::v4));
        }
        NTagReaderTaglib reader;
        reader.init();
        reader.setEncoding(selection);
        reader.setSource(path);
        QCOMPARE(reader.getTag('t'), expected);
        QCOMPARE(reader.getTag('a'), expected);
        QCOMPARE(reader.getTag('A'), expected);
        QCOMPARE(reader.getTags().value("TITLE"), QStringList{expected});
        reader.setSource("");
    }
    void originalSampleReadOnly()
    {
        const QString path = qEnvironmentVariable("NULLOY_ISSUE241_SAMPLE");
        if (path.isEmpty())
            QSKIP("Optional upstream attachment: not redistributed; set NULLOY_ISSUE241_SAMPLE locally");
        QVERIFY(QFileInfo::exists(path));
        NTagReaderTaglib reader;
        reader.init();
        reader.setEncoding("Windows-1251");
        reader.setSource(path);
        QCOMPARE(reader.getTag('t'), QString::fromUtf8("Зашумела шум-дуброўка"));
        reader.setSource("");
    }
};
QTEST_GUILESS_MAIN(TestIssue241)
#include "testIssue241.moc"
