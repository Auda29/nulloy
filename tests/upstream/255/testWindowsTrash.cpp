#include "platform/trash.h"

#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QTemporaryDir>
#include <QtTest/QTest>

// Explicit native Windows test. Creates only its own temporary files.
// Successful fixtures remain in the recycle bin for inspection.
class TestWindowsTrash : public QObject
{
    Q_OBJECT
private slots:
    void realRecycleBin()
    {
        const QString root = qEnvironmentVariable("NULLOY_TRASH_TEST_ROOT");
        const QString expected = qEnvironmentVariable("NULLOY_TRASH_EXPECT_RECYCLE");
        QVERIFY2(!root.isEmpty() && QDir(root).exists(),
                 "Set NULLOY_TRASH_TEST_ROOT to an existing disposable test directory");
        QVERIFY2(expected == "0" || expected == "1",
                 "Set NULLOY_TRASH_EXPECT_RECYCLE=0 for bypass, or 1 for a working bin");
        QTemporaryDir fixtures(QDir(root).filePath("nulloy-trash-XXXXXX"));
        QVERIFY(fixtures.isValid());
        const QString source = fixtures.filePath(QString::fromUtf8("test-ä-日本.txt"));
        const QByteArray contents("Nulloy generated recycle-bin regression fixture\n");
        QFile file(source);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write(contents), qint64(contents.size()));
        file.close();

        QString error;
        const auto result = _trash(source, &error);
        QVERIFY(!result.cancelled); // Qt has no shell confirmation UI.
        if (expected == "0") {
            QVERIFY2(result.errorCode != 0, "Bypassed bin must not report successful recycling");
            QVERIFY2(file.open(QIODevice::ReadOnly), "Unrecyclable file must be preserved");
            QCOMPARE(file.readAll(), contents);
            QVERIFY(!error.isEmpty());
            return;
        }

        QCOMPARE(result.errorCode, 0);
        QVERIFY(!QFileInfo::exists(source));
        // Verify metadata AND payload. Disappearance alone would also pass
        // for the old, unsafe permanent-delete behavior.
        const QString nativeSource = QDir::toNativeSeparators(source);
        const QByteArray encoded(reinterpret_cast<const char *>(nativeSource.utf16()),
                                 nativeSource.size() * 2);
        const QString recycleRoot = source.left(3) + "$Recycle.Bin";
        QDirIterator metadata(recycleRoot, {"$I*"}, QDir::Files | QDir::Hidden | QDir::System,
                              QDirIterator::Subdirectories);
        bool verified = false;
        while (metadata.hasNext()) {
            QFile info(metadata.next());
            if (!info.open(QIODevice::ReadOnly) || !info.readAll().contains(encoded)) {
                continue;
            }
            const QFileInfo entry(info);
            QFile payload(entry.dir().filePath("$R" + entry.fileName().mid(2)));
            QVERIFY(payload.open(QIODevice::ReadOnly));
            QCOMPARE(payload.readAll(), contents);
            verified = true;
            break;
        }
        QVERIFY2(verified, "Expected original path and identical payload in the Windows recycle bin");
    }

    void missingFileIsAnError()
    {
        const QString root = qEnvironmentVariable("NULLOY_TRASH_TEST_ROOT");
        QVERIFY(!root.isEmpty() && QDir(root).exists());
        QTemporaryDir fixtures(QDir(root).filePath("nulloy-trash-missing-XXXXXX"));
        QVERIFY(fixtures.isValid());
        QString error;
        const auto result = _trash(fixtures.filePath("not-created.txt"), &error);
        QVERIFY(result.errorCode != 0);
        QVERIFY(!error.isEmpty());
    }
};

QTEST_GUILESS_MAIN(TestWindowsTrash)
#include "testWindowsTrash.moc"
