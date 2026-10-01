#include <QtTest>
#include <QProcess>
#include <QTemporaryDir>
#include "tagReaderTaglib.h"
#include "coverReaderTaglib.h"
#ifdef Q_OS_WIN
#include <windows.h>
#endif

class TestIssue11 : public QObject
{
    Q_OBJECT
    QTemporaryDir fixtures;
    QString path;

    static void verifyReleased(const QString &file)
    {
#ifdef Q_OS_LINUX
        // POSIX rename succeeds even with an open descriptor: count actual handles instead.
        const QDir descriptors("/proc/self/fd");
        QVERIFY(descriptors.exists());
        int count = 0;
        for (const QString &entry : descriptors.entryList(QDir::AllEntries | QDir::NoDotAndDotDot)) {
            if (QFileInfo(descriptors.filePath(entry)).symLinkTarget() == file)
                ++count;
        }
        QCOMPARE(count, 0);
#elif defined(Q_OS_WIN)
        HANDLE handle = CreateFileW(reinterpret_cast<LPCWSTR>(file.utf16()),
            GENERIC_READ | GENERIC_WRITE | DELETE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
        const DWORD error = GetLastError();
        QVERIFY2(handle != INVALID_HANDLE_VALUE,
                 qPrintable(QString("Exclusive native open failed after release, Win32=%1").arg(error)));
        CloseHandle(handle);
#else
        QSKIP("Actual handle verification implemented for Linux /proc and Windows CreateFileW");
#endif
    }
private slots:
    void initTestCase()
    {
        QVERIFY(fixtures.isValid());
        path = fixtures.filePath("generated.mp3");
        QProcess ffmpeg;
        ffmpeg.start("ffmpeg", {"-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "libmp3lame", "-threads", "1", path});
        QVERIFY(ffmpeg.waitForFinished(30000));
        QVERIFY2(ffmpeg.exitCode() == 0, ffmpeg.readAllStandardError().constData());
    }
    void clearSharedSource_data()
    {
        QTest::addColumn<bool>("clearViaCover");
        QTest::newRow("tag-reader-release") << false;
        QTest::newRow("cover-reader-release") << true;
    }
    void clearSharedSource()
    {
        QFETCH(bool, clearViaCover);
        NTagReaderTaglib tags;
        NCoverReaderTaglib covers;
        // Production plugin-loader order initializes both before loading media.
        tags.init();
        covers.init();
        for (int iteration = 0; iteration < 100; ++iteration) {
            tags.setSource(path);
            covers.setSource(path);
            QVERIFY(!tags.getTag('B').isEmpty());
            QVERIFY(covers.isValid());
            covers.getImages();
#ifdef Q_OS_LINUX
            const QDir descriptors("/proc/self/fd");
            bool found = false;
            for (const QString &entry : descriptors.entryList(QDir::AllEntries | QDir::NoDotAndDotDot))
                found |= QFileInfo(descriptors.filePath(entry)).symLinkTarget() == path;
            QVERIFY(found); // prove the measurement can see the live reader handle
#endif
            if (clearViaCover)
                covers.setSource("");
            else
                tags.setSource("");
            QVERIFY(tags.getTag('B').isEmpty());
            QVERIFY(!covers.isValid());
            verifyReleased(path);
        }
    }
    void releaseAllowsRenameAndTagWrite()
    {
        const QString copy = fixtures.filePath("editable.mp3");
        const QString moved = fixtures.filePath("renamed.mp3");
        QVERIFY(QFile::copy(path, copy));
        NTagReaderTaglib tags;
        NCoverReaderTaglib covers;
        tags.init();
        covers.init();
        tags.setSource(copy);
        QVERIFY(!tags.getTag('B').isEmpty());
        covers.setSource("");
        verifyReleased(copy);
        QVERIFY(QFile::rename(copy, moved));
        tags.setSource(moved);
        const QString title = "Owned issue 11 fixture";
        QVERIFY(tags.setTags({{"TITLE", QStringList{title}}}).isEmpty());
        tags.setSource("");
        verifyReleased(moved);
        tags.setSource(moved);
        QCOMPARE(tags.getTag('t'), title);
        tags.setSource("");
        verifyReleased(moved);
        QVERIFY(QFile::remove(moved));
    }
    void nativeWindowsSharingWhileHeld()
    {
#ifndef Q_OS_WIN
        QSKIP("Windows sharing modes cannot be inferred from Linux descriptors or POSIX rename");
#else
        NTagReaderTaglib tags;
        tags.init();
        tags.setSource(path);
        QVERIFY(!tags.getTag('B').isEmpty());
        for (DWORD access : {DWORD(GENERIC_READ), DWORD(GENERIC_WRITE), DWORD(DELETE)}) {
            HANDLE handle = CreateFileW(reinterpret_cast<LPCWSTR>(path.utf16()), access,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                nullptr, OPEN_EXISTING, 0, nullptr);
            const DWORD error = handle == INVALID_HANDLE_VALUE ? GetLastError() : ERROR_SUCCESS;
            qInfo() << "Held TagLib reader: requested access" << access << "Win32 error" << error;
            if (handle != INVALID_HANDLE_VALUE)
                CloseHandle(handle);
            else
                QCOMPARE(error, DWORD(ERROR_SHARING_VIOLATION));
        }
        // The held-state outcomes are characterization, not a promise of write sharing.
        tags.setSource("");
        verifyReleased(path);
#endif
    }
};
QTEST_GUILESS_MAIN(TestIssue11)
#include "testIssue11.moc"
