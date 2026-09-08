#include "shellapi.h"

#include <QFile>
#include <QTemporaryDir>
#include <QtTest/QTest>

int _trash(const QString &file, QString *error);

namespace
{
    int shellResult;
    bool shellAborted;
    unsigned short shellFlags;
    QString source;
    QString destination;
    bool validSourceBuffer;
} // namespace

int SHFileOperation(SHFILEOPSTRUCT *operation)
{
    shellFlags = operation->fFlags;
    // Windows consumes UTF-16, not the host's (possibly 32-bit) wchar_t.
    const auto *utf16 = reinterpret_cast<const QChar *>(operation->pFrom);
    validSourceBuffer = QString(utf16, source.size()) == source && utf16[source.size()].isNull() &&
                        utf16[source.size() + 1].isNull() && operation->wFunc == FO_DELETE;
    operation->fAnyOperationsAborted = shellAborted;
    if (!shellAborted && shellResult == 0) {
        if (!QFile::rename(source, destination)) {
            qFatal("Could not move generated fixture at OS boundary");
        }
    }
    return shellResult;
}

class TestWindowsTrash : public QObject
{
    Q_OBJECT
private:
    QTemporaryDir m_root;

private slots:
    void init()
    {
        QVERIFY(m_root.isValid());
        source = m_root.filePath(QString::fromUtf8("generated space-ä-日本.txt"));
        destination = m_root.filePath("moved-fixture");
        QFile file(source);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write("generated fixture"), qint64(17));
        shellResult = 0;
        shellAborted = false;
        shellFlags = 0;
        validSourceBuffer = false;
    }

    void cleanup()
    {
        if (QFile::exists(source)) {
            QVERIFY(QFile::remove(source));
        }
        if (QFile::exists(destination)) {
            QVERIFY(QFile::remove(destination));
        }
    }

    void zeroReturnWithAbortIsNotSuccess()
    {
        shellAborted = true;
        QString error;
        const int result = _trash(source, &error);
        QVERIFY(QFile::exists(source));
        QVERIFY(!QFile::exists(destination));
        QVERIFY(validSourceBuffer);
        QVERIFY2(result != 0, "SHFileOperation returned zero but aborted: not a deletion");
    }

    void shellMustWarnBeforeUnrecyclablePermanentDeletion()
    {
        QString error;
        QCOMPARE(_trash(source, &error), 0);
        QVERIFY(validSourceBuffer);
        QVERIFY(!QFile::exists(source));
        QVERIFY(QFile::exists(destination));
        QVERIFY(shellFlags & FOF_ALLOWUNDO);
        QVERIFY(shellFlags & FOF_NOCONFIRMATION);
        QVERIFY2(shellFlags & FOF_WANTNUKEWARNING,
                 "FOF_NOCONFIRMATION must not suppress permanent-delete warning");
    }

    void shellReturnCodesArePreserved_data()
    {
        QTest::addColumn<int>("code");
        QTest::addColumn<bool>("aborted");
        QTest::newRow("success") << 0 << false;
        QTest::newRow("error") << 5 << false;
        QTest::newRow("error-with-abort") << 5 << true;
    }

    void shellReturnCodesArePreserved()
    {
        QFETCH(int, code);
        QFETCH(bool, aborted);
        shellResult = code;
        shellAborted = aborted;
        QString error;
        QCOMPARE(_trash(source, &error), code);
        QCOMPARE(QFile::exists(source), code != 0);
        QCOMPARE(QFile::exists(destination), code == 0);
        QVERIFY(validSourceBuffer);
    }
};

QTEST_GUILESS_MAIN(TestWindowsTrash)
#include "testWindowsTrash.moc"
