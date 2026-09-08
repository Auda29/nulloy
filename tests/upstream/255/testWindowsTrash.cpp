#include "common.h"
#include "platform/trash.h"
#include "settings.h"
#include "shellapi.h"

#include <QApplication>
#include <QMessageBox>
#include <QPushButton>
#include <QTimer>

#include <QFile>
#include <QTemporaryDir>
#include <QtTest/QTest>

namespace
{
    int shellResult;
    bool shellAborted;
    unsigned short shellFlags;
    QString source;
    QString destination;
    bool validSourceBuffer;
    QString settingsFile;
    QStringList batchFiles;
    QStringList attempted;
    int batchSuccesses;
    int batchError;
} // namespace

QString NCore::settingsPath()
{
    return settingsFile;
}

int SHFileOperation(SHFILEOPSTRUCT *operation)
{
    if (!batchFiles.isEmpty()) {
        source = batchFiles.at(attempted.size());
        destination = source + ".trashed";
        shellAborted = attempted.size() >= batchSuccesses;
        shellResult = shellAborted ? batchError : 0;
        attempted << source;
    }
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
    void initTestCase() { settingsFile = m_root.filePath("settings.ini"); }
    void cleanupTestCase() { delete NSettings::instance(); }

    void init()
    {
        QVERIFY(m_root.isValid());
        source = m_root.filePath(QString::fromUtf8("generated space-ä-日本.txt"));
        destination = m_root.filePath("moved-fixture");
        QFile file(source);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write("generated fixture"), qint64(17));
        batchFiles.clear();
        attempted.clear();
        NSettings::instance()->setValue("DisplayMoveToTrashConfirmDialog", false);
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

    void nativeCancellationNeverOffersPermanentDeletion_data()
    {
        QTest::addColumn<int>("successes");
        QTest::addColumn<int>("code");
        QTest::addColumn<bool>("confirm");
        for (int successes : {0, 1}) {
            for (int code : {0, 5}) {
                for (bool confirm : {false, true}) {
                    const QByteArray name = QString("successes-%1-code-%2-confirm-%3")
                                                .arg(successes)
                                                .arg(code)
                                                .arg(confirm)
                                                .toLatin1();
                    QTest::newRow(name.constData()) << successes << code << confirm;
                }
            }
        }
    }

    void nativeCancellationNeverOffersPermanentDeletion()
    {
        QFETCH(int, successes);
        QFETCH(int, code);
        QFETCH(bool, confirm);
        QTemporaryDir fixtures;
        QVERIFY(fixtures.isValid());
        for (int i = 0; i < 3; ++i) {
            const QString path = fixtures.filePath(QString::number(i));
            QFile file(path);
            QVERIFY(file.open(QIODevice::WriteOnly));
            QVERIFY(file.write("generated fixture") > 0);
            batchFiles << path;
        }
        batchSuccesses = successes;
        batchError = code;
        NSettings::instance()->setValue("DisplayMoveToTrashConfirmDialog", confirm);
        QStringList unexpectedDialogs;
        int confirmations = 0;
        QTimer driver;
        connect(&driver, &QTimer::timeout, this, [&]() {
            auto *box = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
            if (!box) {
                return;
            }
            if (box->windowTitle() == "Confirmation") {
                ++confirmations;
                box->button(QMessageBox::Yes)->click();
            } else {
                unexpectedDialogs << box->windowTitle();
                box->reject();
            }
        });
        driver.start(0);
        const QStringList moved = NTrash::moveToTrash(batchFiles);
        driver.stop();
        QCOMPARE(moved, batchFiles.mid(0, successes));
        QCOMPARE(attempted, batchFiles.mid(0, successes + 1));
        for (int i = 0; i < batchFiles.size(); ++i) {
            QCOMPARE(QFile::exists(batchFiles.at(i)), i >= successes);
            QCOMPARE(QFile::exists(batchFiles.at(i) + ".trashed"), i < successes);
        }
        QCOMPARE(confirmations, confirm ? successes + 1 : 0);
        QVERIFY2(unexpectedDialogs.isEmpty(), qPrintable(unexpectedDialogs.join(", ")));
    }

    void zeroReturnWithAbortIsNotSuccess()
    {
        shellAborted = true;
        QString error;
        const NTrash::NativeResult result = _trash(source, &error);
        QVERIFY(QFile::exists(source));
        QVERIFY(!QFile::exists(destination));
        QVERIFY(validSourceBuffer);
        QVERIFY2(result.cancelled, "SHFileOperation returned zero but aborted: not a deletion");
        QCOMPARE(result.errorCode, 0);
    }

    void shellMustWarnBeforeUnrecyclablePermanentDeletion()
    {
        QString error;
        const NTrash::NativeResult result = _trash(source, &error);
        QCOMPARE(result.errorCode, 0);
        QVERIFY(!result.cancelled);
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
        const NTrash::NativeResult result = _trash(source, &error);
        QCOMPARE(result.errorCode, code);
        QCOMPARE(result.cancelled, aborted);
        QCOMPARE(QFile::exists(source), code != 0);
        QCOMPARE(QFile::exists(destination), code == 0);
        QVERIFY(validSourceBuffer);
    }
};

QTEST_MAIN(TestWindowsTrash)
#include "testWindowsTrash.moc"
