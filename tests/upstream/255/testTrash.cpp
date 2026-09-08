#include "common.h"
#include "platform/trash.h"
#include "settings.h"

#include <QApplication>
#include <QCheckBox>
#include <QDir>
#include <QFile>
#include <QMessageBox>
#include <QPushButton>
#include <QSet>
#include <QTemporaryDir>
#include <QTimer>
#include <QtTest>

namespace
{
    QString settingsFile;
    QString trashDirectory;
    QStringList attempted;
    QSet<QString> refused;
    int refusedError;
} // namespace

// Keep production NSettings, but isolate its storage from user preferences.
QString NCore::settingsPath()
{
    return settingsFile;
}

// The only replaced behavior is the native OS trash boundary. A successful
// call really moves a generated file; no user file or system trash is touched.
NTrash::NativeResult _trash(const QString &file, QString *error)
{
    attempted << file;
    if (!refused.contains(file) &&
        QFile::rename(file, trashDirectory + "/" + QFileInfo(file).fileName())) {
        return {0, false};
    }
    *error = "Controlled trash failure";
    return {refusedError, false};
}

class TestTrash : public QObject
{
    Q_OBJECT
private:
    QTemporaryDir m_root;
    QTimer m_dialogDriver;
    QList<QMessageBox::StandardButton> m_answers;
    QList<QMessageBox::StandardButton> m_defaults;
    QStringList m_dialogTitles;
    QStringList m_informativeTexts;
    bool m_unexpectedDialog = false;
    bool m_disablePrompt = false;

    QString makeFile(const QString &name)
    {
        const QString path = m_root.filePath(name);
        QFile file(path);
        if (!file.open(QIODevice::WriteOnly) || file.write("generated fixture") < 0) {
            qFatal("Could not create generated file");
        }
        return path;
    }

private slots:
    void initTestCase()
    {
        QVERIFY(m_root.isValid());
        settingsFile = m_root.filePath("settings.ini");
        trashDirectory = m_root.filePath("trash");
        QVERIFY(QDir().mkpath(trashDirectory));
        connect(&m_dialogDriver, &QTimer::timeout, this, [this]() {
            auto *box = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
            if (!box) {
                return;
            }
            m_dialogTitles << box->windowTitle();
            m_informativeTexts << box->informativeText();
            m_defaults << box->standardButton(box->defaultButton());
            if (box->checkBox()) {
                box->checkBox()->setChecked(m_disablePrompt);
            }
            if (m_answers.isEmpty()) {
                m_unexpectedDialog = true;
            }
            const auto answer = m_answers.isEmpty() ? QMessageBox::Cancel : m_answers.takeFirst();
            if (!box->button(answer)) {
                m_unexpectedDialog = true;
                box->reject();
                return;
            }
            box->button(answer)->click();
        });
    }

    void init()
    {
        attempted.clear();
        refused.clear();
        refusedError = 1;
        m_answers.clear();
        m_defaults.clear();
        m_dialogTitles.clear();
        m_informativeTexts.clear();
        m_unexpectedDialog = false;
        m_disablePrompt = false;
        m_dialogDriver.start(0);
        NSettings::instance()->setValue("DisplayMoveToTrashConfirmDialog", false);
    }

    void cleanup()
    {
        m_dialogDriver.stop();
        QVERIFY(m_answers.isEmpty());
        QVERIFY(!m_unexpectedDialog);
    }

    void cleanupTestCase() { delete NSettings::instance(); }

    void successReturnsMovedPaths()
    {
        const QString first = makeFile("first.txt");
        const QString second = makeFile("second.txt");
        const QStringList files{first, second};
        const QStringList moved = NTrash::moveToTrash(files);
        QVERIFY(!QFile::exists(first));
        QVERIFY(!QFile::exists(second));
        QVERIFY(QFile::exists(trashDirectory + "/first.txt"));
        QVERIFY(QFile::exists(trashDirectory + "/second.txt"));
        QCOMPARE(attempted, files);
        QCOMPARE(moved, files);
    }

    void cancellationReturnsOnlyEarlierSuccesses_data()
    {
        QTest::addColumn<int>("successes");
        QTest::newRow("cancel-first") << 0;
        QTest::newRow("cancel-after-success") << 1;
    }

    void cancellationReturnsOnlyEarlierSuccesses()
    {
        QFETCH(int, successes);
        const QString prefix = QString("cancel-%1-").arg(successes);
        const QStringList files{makeFile(prefix + "first"), makeFile(prefix + "second"),
                                makeFile(prefix + "last")};
        NSettings::instance()->setValue("DisplayMoveToTrashConfirmDialog", true);
        for (int i = 0; i < successes; ++i) {
            m_answers << QMessageBox::Yes;
        }
        m_answers << QMessageBox::Cancel;
        const QStringList moved = NTrash::moveToTrash(files);
        QCOMPARE(attempted, files.mid(0, successes));
        for (int i = 0; i < files.size(); ++i) {
            QCOMPARE(QFile::exists(files.at(i)), i >= successes);
        }
        for (auto button : m_defaults) {
            QCOMPARE(button, QMessageBox::Cancel);
        }
        QCOMPARE(moved, files.mid(0, successes));
    }

    void duplicatesAreMovedOnceWithoutStoppingLaterFiles()
    {
        const QString first = makeFile("duplicate-first");
        const QString second = makeFile("duplicate-second");
        const QStringList unique{first, second};
        const QStringList moved = NTrash::moveToTrash({first, first, second, first});
        QCOMPARE(attempted, unique);
        QCOMPARE(moved, unique);
        QVERIFY(!QFile::exists(first));
        QVERIFY(!QFile::exists(second));
        QVERIFY(m_dialogTitles.isEmpty());
    }

    void trashErrorDeclinedKeepsFailedAndUnattemptedFiles_data()
    {
        QTest::addColumn<int>("successes");
        QTest::addColumn<int>("errorCode");
        QTest::newRow("total-failure") << 0 << 1;
        QTest::newRow("partial-success") << 1 << 1;
        QTest::newRow("negative-error-first") << 0 << -1;
        QTest::newRow("negative-error-after-success") << 1 << -1;
        QTest::newRow("native-error-first") << 0 << -43;
        QTest::newRow("native-error-after-success") << 1 << -43;
    }

    void trashErrorDeclinedKeepsFailedAndUnattemptedFiles()
    {
        QFETCH(int, successes);
        QFETCH(int, errorCode);
        refusedError = errorCode;
        const QString prefix = QString("error-%1-%2-").arg(successes).arg(errorCode);
        const QStringList files{makeFile(prefix + "first"), makeFile(prefix + "second"),
                                makeFile(prefix + "last")};
        refused.insert(files.at(successes));
        m_answers << QMessageBox::Cancel;
        const QStringList moved = NTrash::moveToTrash(files);
        QCOMPARE(moved, files.mid(0, successes));
        QCOMPARE(attempted, files.mid(0, successes + 1));
        for (int i = 0; i < files.size(); ++i) {
            QCOMPARE(QFile::exists(files.at(i)), i >= successes);
        }
        QCOMPARE(m_dialogTitles, QStringList{"Trash Error"});
        QCOMPARE(m_informativeTexts, QStringList{"Do you want to delete permanently?"});
        QCOMPARE(m_defaults, QList<QMessageBox::StandardButton>{QMessageBox::Cancel});
    }

    void permanentDeleteRequiresExplicitYesEvenWithTrashPromptDisabled()
    {
        const QString file = makeFile("permanent-delete");
        refused.insert(file);
        m_answers << QMessageBox::Cancel;
        QCOMPARE(NTrash::moveToTrash({file}), QStringList{});
        QVERIFY(QFile::exists(file));
        m_answers << QMessageBox::Yes;
        QCOMPARE(NTrash::moveToTrash({file, file}), QStringList{file});
        QVERIFY(!QFile::exists(file));
        QVERIFY(!QFile::exists(trashDirectory + "/permanent-delete"));
        QCOMPARE(attempted, (QStringList{file, file}));
        QCOMPARE(m_dialogTitles, (QStringList{"Trash Error", "Trash Error"}));
        QCOMPARE(m_informativeTexts, (QStringList{"Do you want to delete permanently?",
                                                  "Do you want to delete permanently?"}));
        QCOMPARE(m_defaults,
                 (QList<QMessageBox::StandardButton>{QMessageBox::Cancel, QMessageBox::Cancel}));
    }

    void permanentDeleteFailureReturnsOnlyEarlierSuccesses()
    {
        const QString first = makeFile("before-delete-error");
        const QString directory = m_root.filePath("undeletable-directory");
        QVERIFY(QDir().mkpath(directory));
        const QString child = makeFile("undeletable-directory/child");
        const QString last = makeFile("after-delete-error");
        refused.insert(directory);
        m_answers << QMessageBox::Yes << QMessageBox::Ok;
        const QStringList moved = NTrash::moveToTrash({first, directory, last});
        QCOMPARE(moved, QStringList{first});
        QCOMPARE(attempted, (QStringList{first, directory}));
        QVERIFY(!QFile::exists(first));
        QVERIFY(QFile::exists(directory));
        QVERIFY(QFile::exists(child));
        QVERIFY(QFile::exists(last));
        QCOMPARE(m_dialogTitles, (QStringList{"Trash Error", "File Delete Error"}));
    }

    void missingPathIsNotReportedDeleted()
    {
        const QString missing = m_root.filePath("never-created");
        QVERIFY(!QFile::exists(missing));
        m_answers << QMessageBox::Yes << QMessageBox::Ok;
        QCOMPARE(NTrash::moveToTrash({missing}), QStringList{});
        QCOMPARE(attempted, QStringList{missing});
        QCOMPARE(m_dialogTitles, (QStringList{"Trash Error", "File Delete Error"}));
    }

    void emptyInputDoesNothing()
    {
        NSettings::instance()->setValue("DisplayMoveToTrashConfirmDialog", true);
        QCOMPARE(NTrash::moveToTrash({}), QStringList{});
        QVERIFY(attempted.isEmpty());
        QVERIFY(m_dialogTitles.isEmpty());
    }

    void checkedOptOutAppliesOnlyAfterConfirmation_data()
    {
        QTest::addColumn<bool>("confirm");
        QTest::newRow("yes-disables-later-prompts") << true;
        QTest::newRow("cancel-keeps-prompts-enabled") << false;
    }

    void checkedOptOutAppliesOnlyAfterConfirmation()
    {
        QFETCH(bool, confirm);
        const QString prefix = confirm ? "optout-yes-" : "optout-cancel-";
        const QStringList files{makeFile(prefix + "first"), makeFile(prefix + "second")};
        NSettings::instance()->setValue("DisplayMoveToTrashConfirmDialog", true);
        m_disablePrompt = true;
        m_answers << (confirm ? QMessageBox::Yes : QMessageBox::Cancel);
        QCOMPARE(NTrash::moveToTrash(files), confirm ? files : QStringList{});
        QCOMPARE(attempted, confirm ? files : QStringList{});
        QCOMPARE(m_dialogTitles, QStringList{"Confirmation"});
        QCOMPARE(NSettings::instance()->value("DisplayMoveToTrashConfirmDialog").toBool(), !confirm);
        for (const QString &file : files) {
            QCOMPARE(QFile::exists(file), !confirm);
        }
    }
};

QTEST_MAIN(TestTrash)
#include "testTrash.moc"
