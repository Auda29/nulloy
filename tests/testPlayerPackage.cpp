// SPDX-License-Identifier: GPL-3.0-or-later
// Run from an extracted package with its real playback plugin and no toolchain PATH.
#include <QtTest>
#include <QDragEnterEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QMessageBox>
#include <QMimeData>
#include <QMenu>
#include <QAbstractButton>
#include <QThread>
#include <memory>
#include <qt_windows.h>
#include "action.h"
#include "common.h"
#include "mainWindow.h"
#include "player.h"
#include "playlistWidget.h"
#include "playlistStorage.h"
#include "playbackEngineInterface.h"
#include "pluginLoader.h"
#include "settings.h"
#include "tagReaderInterface.h"
#include "waveformBuilderInterface.h"
#if !defined(_N_NO_SKINS_) && QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
#include "skinFileSystem.h"
Q_IMPORT_PLUGIN(NWidgetCollection)
#endif

namespace {
QElapsedTimer *startupClock = nullptr;
QtMessageHandler previousHandler = nullptr;
void startupMessage(QtMsgType type, const QMessageLogContext &context, const QString &message)
{
    if (startupClock && (message.startsWith("found container") || message.startsWith("registering plugin")))
        previousHandler(QtInfoMsg, context, QString("startup-ms %1: %2").arg(startupClock->elapsed()).arg(message));
    previousHandler(type, context, message);
}

class MenuObserver : public QObject
{
public:
    bool opened = false;
    bool eventFilter(QObject *object, QEvent *event) override
    {
        if (event->type() == QEvent::Show) {
            if (auto menu = qobject_cast<QMenu *>(object)) {
                opened = !menu->actions().isEmpty();
                QTimer::singleShot(0, menu, &QMenu::close);
            }
        }
        return false;
    }
};
}

class TestPlayerPackage : public QObject
{
    Q_OBJECT
private slots:
    void trashHandleOwnership_data()
    {
        QTest::addColumn<QString>("state");
        for (const QString &state : {QString("playing"), QString("paused"), QString("stopped")})
            QTest::newRow(qPrintable(state)) << state;
    }

    void trashHandleOwnership()
    {
        QFETCH(QString, state);
        const QString root = qEnvironmentVariable("NULLOY_NATIVE_TRASH_PLAYER_ROOT");
        if (root.isEmpty()) QSKIP("Explicit disposable native test root required");
        QTemporaryDir directory(root + "/handle-probe-XXXXXX");
        QVERIFY(directory.isValid());
        const QString file = directory.filePath("owned-tone.wav");
        QVERIFY(QFile::copy(QCoreApplication::applicationDirPath() + "/tests/01.wav", file));
        auto *settings = NSettings::instance();
        settings->setValue("RestorePlaylist", false);
        settings->setValue("DisplayLogDialog", false);
        settings->setValue("Volume", 0.0);
#if !defined(_N_NO_SKINS_) && QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
        NSkinFileSystem::init();
#endif
        auto player = std::make_unique<NPlayer>();
        auto check = [&](const char *stage) {
            HANDLE handle = CreateFileW(reinterpret_cast<LPCWSTR>(file.utf16()), DELETE,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            const DWORD error = handle == INVALID_HANDLE_VALUE ? GetLastError() : 0;
            if (handle != INVALID_HANDLE_VALUE) CloseHandle(handle);
            qInfo() << "delete-access" << stage << "win32-error" << error;
            return error;
        };
        QCOMPARE(check("before-load"), DWORD(0));
        player->playlistWidget()->setFiles({file});
        player->playlistWidget()->playRow(0);
        QTRY_COMPARE(player->playbackEngine()->state(), N::PlaybackPlaying);
        QTRY_VERIFY(player->playbackEngine()->position() > 0.05);
        check("playing");
        if (state == "paused") player->playbackEngine()->pause();
        if (state == "stopped") player->playbackEngine()->stop();
        check(qPrintable("requested-state-" + state));
        // Reverse the former release order to identify residual ownership:
        // playback NULL alone is not evidence that metadata/waveform are closed.
        player->playbackEngine()->stop();
        check("playback-stopped-before-reader-release");
        auto *waveform = dynamic_cast<NWaveformBuilderInterface *>(NPluginLoader::getPlugin(N::WaveformBuilder));
        QVERIFY(waveform);
        waveform->stop();
        check("waveform-stopped");
        player->tagReader()->setSource(QString());
        QCOMPARE(check("all-player-readers-released"), DWORD(0));
        player.reset();
        QCOMPARE(check("player-destroyed"), DWORD(0));
    }

    void trashPlayer_data()
    {
        QTest::addColumn<QString>("state");
        QTest::addColumn<QString>("operation");
        for (const QString &state : {QString("playing"), QString("paused"), QString("stopped")})
            for (const QString &operation : {QString("cancel"), QString("partial"),
                     QString("duplicates"), QString("current"), QString("cancel-current"),
                     QString("next"), QString("locked"), QString("locked-current")})
                QTest::newRow(qPrintable(state + "-" + operation)) << state << operation;
    }

    void trashPlayer()
    {
        const QString testRoot = qEnvironmentVariable("NULLOY_NATIVE_TRASH_PLAYER_ROOT");
        if (testRoot.isEmpty())
            QSKIP("Native player recycling requires an explicit disposable test root");
        QFETCH(QString, state);
        QFETCH(QString, operation);
        QTemporaryDir directory(testRoot + "/player-trash-XXXXXX");
        QVERIFY(directory.isValid());
        const QString sample = QCoreApplication::applicationDirPath() + "/tests/01.wav";
        QFile original(sample);
        QVERIFY(original.open(QIODevice::ReadOnly));
        const QByteArray bytes = original.readAll();
        QStringList files;
        for (int i = 0; i < 3; ++i) {
            const QString file = directory.filePath(QString::fromUtf8("tone-ä-%1.wav").arg(i));
            QVERIFY(QFile::copy(sample, file));
            files << file;
        }
        auto *settings = NSettings::instance();
        settings->clear();
        delete settings;
        settings = NSettings::instance();
        settings->setValue("Skin", qEnvironmentVariable("NULLOY_TEST_SKIN", "Slim/0.9")
            .replace("Native/", "Native (Built-in)/"));
        settings->setValue("Language", "en");
        settings->setValue("RestorePlaylist", false);
        settings->setValue("DisplayMoveToTrashConfirmDialog", true);
        settings->setValue("DisplayLogDialog", false);
        settings->setValue("Volume", 0.0);
#if !defined(_N_NO_SKINS_) && QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
        NSkinFileSystem::init();
#endif
        auto player = std::make_unique<NPlayer>();
        auto *list = player->playlistWidget();
        auto *engine = player->playbackEngine();
        list->addFiles({files[0], files[1], files[1], files[2]});
        QCOMPARE(list->count(), 4);
        list->playRow(0);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        // Cancellation at position zero does not establish seek/resume safety.
        QTRY_VERIFY(engine->position() > 0.05);
        if (state == "paused") engine->pause();
        if (state == "stopped") engine->stop();
        const auto initialState = engine->state();
        const qreal initialPosition = engine->position();
        const QString initialMedia = engine->currentMedia();
        const bool current = operation == "current" || operation == "cancel-current" ||
                             operation == "locked-current";
        list->clearSelection();
        list->item(current ? 0 : 1)->setSelected(true);
        if (operation == "partial") list->item(3)->setSelected(true);
        if (operation == "duplicates") list->item(2)->setSelected(true);

        // A Windows handle without FILE_SHARE_DELETE forces a real recycle
        // failure; cancelling the player's permanent-delete question must retain bytes.
        struct OwnedHandle {
            HANDLE value = INVALID_HANDLE_VALUE;
            ~OwnedHandle() { if (value != INVALID_HANDLE_VALUE) CloseHandle(value); }
        } locked;
        const bool externallyLocked = operation == "locked" || operation == "locked-current";
        if (externallyLocked) {
            locked.value = CreateFileW(reinterpret_cast<LPCWSTR>(files[current ? 0 : 1].utf16()), GENERIC_READ,
                // TagLib can already hold read/write access to the current
                // file. Allow both, but deliberately deny FILE_SHARE_DELETE.
                FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            QVERIFY2(locked.value != INVALID_HANDLE_VALUE,
                qPrintable(QString("Could not create external delete lock: Win32 %1").arg(GetLastError())));
        }
        int confirmations = 0, fallbacks = 0, unexpected = 0;
        QSet<QMessageBox *> seen;
        QTimer dialogs;
        connect(&dialogs, &QTimer::timeout, [&]() {
            auto *box = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
            if (!box || seen.contains(box)) return;
            seen.insert(box);
            connect(box, &QObject::destroyed, [&seen, box]() { seen.remove(box); });
            QMessageBox::StandardButton answer = QMessageBox::Cancel;
            if (box->windowTitle() == "Confirmation") {
                ++confirmations;
                if (operation != "cancel" && operation != "cancel-current"
                    && !(operation == "partial" && confirmations == 2))
                    answer = QMessageBox::Yes;
            } else if (box->windowTitle() == "Trash Error") {
                ++fallbacks;
                qInfo() << "native-trash-error" << box->text() << box->informativeText();
            } else {
                ++unexpected;
            }
            box->done(answer);
        });
        dialogs.start(10);
        auto *action = player->findChild<NAction *>("MoveToTrashAction");
        QVERIFY(action);
        action->trigger();
        dialogs.stop();
        QCOMPARE(unexpected, 0);
        QCOMPARE(confirmations, operation == "partial" ? 2 : 1);
        // Validate retained bytes and player state even when the current-track
        // recycle expectation fails. Never let an early assertion hide these.
        const bool removed = operation != "cancel" && operation != "cancel-current"
                             && !externallyLocked && fallbacks == 0;
        const int removedFile = current ? 0 : 1;
        QStringList expected = {files[0], files[1], files[1], files[2]};
        if (removed) expected.removeAll(files[removedFile]);
        QCOMPARE(list->count(), expected.size());
        for (int i = 0; i < expected.size(); ++i)
            QCOMPARE(list->item(i)->data(N::PathRole).toString(), expected[i]);
        for (int i = 0; i < files.size(); ++i) {
            if (removed && i == removedFile) {
                QVERIFY(!QFile::exists(files[i]));
            } else {
                QFile retained(files[i]);
                QVERIFY(retained.open(QIODevice::ReadOnly));
                QCOMPARE(retained.readAll(), bytes);
            }
        }
        // Preserve pause/stop; require the next explicit play action to resolve
        // to a surviving file after removing the playing item or its successor.
        if (state != "playing" || !current || !removed)
            QCOMPARE(engine->state(), initialState);
        if (!removed) {
            QCOMPARE(engine->currentMedia(), initialMedia);
            if (state != "playing")
                QCOMPARE(engine->position(), initialPosition);
            if (state == "paused" && externallyLocked) {
                // Check settled preroll and the actual subsequent resumed seek,
                // not merely the engine's cached position immediately on return.
                QTest::qWait(300);
                QTRY_COMPARE(engine->state(), N::PlaybackPaused);
                QVERIFY(qAbs(engine->position() - initialPosition) < 0.015);
                engine->play();
                QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
                QTRY_VERIFY(engine->position() >= initialPosition - 0.015);
                engine->pause();
            }
            qInfo() << "cancelled-trash-retained-bytes-playback-state-and-paused-position";
        }
        if (removed && current) {
            QCOMPARE(engine->currentMedia(), files[1]);
            QCOMPARE(list->playingRow(), 0);
            QCOMPARE(engine->position(), qreal(0.0));
        }
        list->playNextItem();
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QVERIFY(list->playingRow() >= 0);
        QVERIFY(QFile::exists(list->item(list->playingRow())->data(N::PathRole).toString()));
        QVERIFY(expected.contains(engine->currentMedia()));
        engine->stop();
        player->quit();
        QCOMPARE(fallbacks, externallyLocked ? 1 : 0);
    }

    void portableProcesses()
    {
        const QString otherExe = qEnvironmentVariable("NULLOY_TEST_SECOND_PLAYER");
        if (otherExe.isEmpty()) QSKIP("Separate portable process check");
        const QString firstExe = QCoreApplication::applicationDirPath() + "/NulloyFork.exe";
        const QString firstRoot = QFileInfo(firstExe).absolutePath();
        const QString otherRoot = QFileInfo(otherExe).absolutePath();
        for (const QString &root : {firstRoot, otherRoot}) {
            QDir().mkpath(root + "/Data");
            QSettings settings(root + "/Data/NulloyFork.cfg", QSettings::IniFormat);
            settings.clear();
            settings.setValue("SingleInstance", true);
            settings.setValue("EnqueueFiles", true);
            settings.setValue("PlayEnqueued", false);
            settings.setValue("QuitOnClose", true);
            settings.setValue("Volume", 0.0);
            settings.setValue("DisplayLogDialog", false);
            settings.setValue("Skin", "Slim/0.9");
            settings.sync();
            QFile::remove(root + "/Data/NulloyFork.m3u");
        }
        const auto window = [](QProcess &process) {
            struct Search { DWORD pid; HWND result = nullptr; } search{DWORD(process.processId())};
            EnumWindows([](HWND hwnd, LPARAM data) -> BOOL {
                auto *s = reinterpret_cast<Search *>(data);
                DWORD pid = 0;
                GetWindowThreadProcessId(hwnd, &pid);
                if (pid == s->pid && IsWindowVisible(hwnd) && !GetWindow(hwnd, GW_OWNER)) {
                    s->result = hwnd;
                    return FALSE;
                }
                return TRUE;
            }, reinterpret_cast<LPARAM>(&search));
            return search.result;
        };
        QProcess first, other, forwarded;
        first.setWorkingDirectory(firstRoot + "/tests");
        first.start(firstExe, {"01.wav"});
        QVERIFY(first.waitForStarted());
        QTRY_VERIFY_WITH_TIMEOUT(window(first), 30000);
        other.setWorkingDirectory(otherRoot + "/tests");
        other.start(otherExe, {"02.wav"});
        QVERIFY(other.waitForStarted());
        QTRY_VERIFY_WITH_TIMEOUT(window(other), 30000);
        forwarded.setWorkingDirectory(firstRoot + "/tests");
        forwarded.start(firstExe, {"02.wav"});
        QVERIFY(forwarded.waitForStarted());
        QTRY_COMPARE_WITH_TIMEOUT(forwarded.state(), QProcess::NotRunning, 10000);
        QCOMPARE(forwarded.exitCode(), 0);
        QCOMPARE(first.state(), QProcess::Running);
        QCOMPARE(other.state(), QProcess::Running);
        QTest::qWait(250);
        QVERIFY(PostMessage(window(first), WM_CLOSE, 0, 0));
        QVERIFY(PostMessage(window(other), WM_CLOSE, 0, 0));
        QTRY_COMPARE_WITH_TIMEOUT(first.state(), QProcess::NotRunning, 10000);
        QTRY_COMPARE_WITH_TIMEOUT(other.state(), QProcess::NotRunning, 10000);
        QCOMPARE(first.exitCode(), 0);
        QCOMPARE(other.exitCode(), 0);
        const auto firstList = NPlaylistStorage::readM3u(firstRoot + "/Data/NulloyFork.m3u");
        const auto otherList = NPlaylistStorage::readM3u(otherRoot + "/Data/NulloyFork.m3u");
        QCOMPARE(firstList.size(), 2);
        QCOMPARE(otherList.size(), 1);
        QCOMPARE(QFileInfo(firstList[0].path).canonicalFilePath(), QFileInfo(firstRoot + "/tests/01.wav").canonicalFilePath());
        QCOMPARE(QFileInfo(firstList[1].path).canonicalFilePath(), QFileInfo(firstRoot + "/tests/02.wav").canonicalFilePath());
        QCOMPARE(QFileInfo(otherList[0].path).canonicalFilePath(), QFileInfo(otherRoot + "/tests/02.wav").canonicalFilePath());
        qInfo() << "portable-process-isolation-relative-cli-and-ipc-passed";
    }
    void playerWorkflow()
    {
        QCOMPARE(GetACP(), UINT(CP_UTF8));
        NSettings::instance()->clear();
        delete NSettings::instance();
        auto *settings = NSettings::instance();
        QString skin = qEnvironmentVariable("NULLOY_TEST_SKIN", "Slim/0.9");
        if (skin == "Native/0.9") {
            skin = "Native (Built-in)/0.9";
        }
        settings->setValue("Language", "en");
        settings->setValue("Skin", skin);
        settings->setValue("SingleInstance", false);
        settings->setValue("RestorePlaylist", false);
        settings->setValue("PlayEnqueued", false);
        settings->setValue("Volume", 0.0);
        settings->setValue("TrayIcon", false);
        settings->setValue("DisplayLogDialog", false);
        settings->setValue("ShowPlaylist", true);
#if !defined(_N_NO_SKINS_) && QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
        NSkinFileSystem::init();
#endif
        QElapsedTimer clock;
        clock.start();
        if (qEnvironmentVariableIsSet("NULLOY_TEST_STARTUP_TRACE")) {
            startupClock = &clock;
            previousHandler = qInstallMessageHandler(startupMessage);
        }
        auto player = std::make_unique<NPlayer>();
        if (startupClock) {
            qInstallMessageHandler(previousHandler);
            startupClock = nullptr;
        }
        QVERIFY(player->mainWindow()->isVisible());
        QVERIFY(QTest::qWaitForWindowExposed(player->mainWindow()));
        qInfo() << "window-exposed-ms" << clock.elapsed();
        QCOMPARE(settings->value("Skin").toString(), skin);
        auto *playlist = player->playlistWidget();
        QVERIFY(playlist);
        qInfo() << "ui-font" << QApplication::font().toString()
                << "playlist-text" << playlist->palette().color(QPalette::Text).name()
                << "inactive-text" << playlist->palette().color(QPalette::Inactive, QPalette::Text).name()
                << "logical-size" << player->mainWindow()->size()
                << "device-scale" << player->mainWindow()->devicePixelRatioF();
        QCOMPARE(playlist->count(), 0);
        // The taskbar requires a native minimize capability even for skins
        // that draw their own window buttons. showMinimized() alone misses it.
        const auto hwnd = reinterpret_cast<HWND>(player->mainWindow()->winId());
        QVERIFY2(GetWindowLongPtr(hwnd, GWL_STYLE) & WS_MINIMIZEBOX,
                 "The Windows taskbar cannot minimize a window without WS_MINIMIZEBOX");
        QVERIFY(GetWindowLongPtr(hwnd, GWL_STYLE) & WS_SYSMENU);
        const QSize beforeMinimize = player->mainWindow()->size();
        SendMessage(hwnd, WM_SYSCOMMAND, SC_MINIMIZE, 0);
        QTRY_VERIFY(IsIconic(hwnd));
        QTRY_VERIFY(player->mainWindow()->isMinimized());
        SendMessage(hwnd, WM_SYSCOMMAND, SC_RESTORE, 0);
        QTRY_VERIFY(!IsIconic(hwnd));
        QTRY_VERIFY(!player->mainWindow()->isMinimized());
        QCOMPARE(player->mainWindow()->size(), beforeMinimize);
        qInfo() << "native-taskbar-minimize-restore-passed";
        const QDir samples(QCoreApplication::applicationDirPath() + "/tests");
        QStringList files = qEnvironmentVariable("NULLOY_TEST_MEDIA").split('|', Qt::SkipEmptyParts);
        const bool referenceMedia = !files.isEmpty();
        if (!referenceMedia) {
            files = QStringList{samples.absoluteFilePath("01.wav"), samples.absoluteFilePath("02.wav")};
        }
        QCOMPARE(files.size(), 2);
        for (const QString &file : files) {
            QVERIFY(QFile::exists(file));
        }
        if (qEnvironmentVariableIsSet("NULLOY_TEST_WRITE_TAGS")) {
            // The runner supplies disposable synthetic media copies only.
            auto tags = player->tagReader();
            tags->setEncoding("UTF-8");
            tags->setSource(files[0]);
            QVERIFY(tags->isWriteSupported());
            const QMap<QString, QStringList> expected{
                {"TITLE", {QString::fromUtf8("Grüße 日本語")}},
                {"ARTIST", {QString::fromUtf8("Künstler Ä")}},
                {"ALBUM", {"Migration test"}}, {"TRACKNUMBER", {"7"}}};
            const auto unsaved = tags->setTags(expected);
            QVERIFY2(unsaved.isEmpty(), qPrintable(unsaved.keys().join(',')));
            tags->setSource(files[1]);
            tags->setSource(files[0]);
            const auto reopened = tags->getTags();
            for (auto it = expected.cbegin(); it != expected.cend(); ++it)
                QCOMPARE(reopened.value(it.key()), it.value());
            QCOMPARE(tags->getTag('t'), expected.value("TITLE").first());
            qInfo() << "unicode-tags-written-and-reopened" << QFileInfo(files[0]).suffix();
        }
        // One file, followed by a simultaneous two-file external drop.
        for (const QList<QUrl> urls : {QList<QUrl>{QUrl::fromLocalFile(files[0])},
                                     QList<QUrl>{QUrl::fromLocalFile(files[0]), QUrl::fromLocalFile(files[1])}}) {
            QMimeData mime;
            mime.setUrls(urls);
            const QPoint pos(10, playlist->viewport()->height() - 5);
            QDragEnterEvent enter(pos, Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
            QCoreApplication::sendEvent(playlist->viewport(), &enter);
            QVERIFY(enter.isAccepted());
            QDragMoveEvent move(pos, Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
            QCoreApplication::sendEvent(playlist->viewport(), &move);
            QDropEvent drop(pos, Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
            QCoreApplication::sendEvent(playlist->viewport(), &drop);
            QVERIFY(drop.isAccepted());
        }
        QCOMPARE(playlist->count(), 3);
        QCOMPARE(playlist->item(0)->data(N::PathRole).toString(), files[0]);
        QCOMPARE(playlist->item(1)->data(N::PathRole).toString(), files[0]);
        QCOMPARE(playlist->item(2)->data(N::PathRole).toString(), files[1]);
        auto *engine = player->playbackEngine();
        auto *waveform = dynamic_cast<NWaveformBuilderInterface *>(NPluginLoader::getPlugin(N::WaveformBuilder));
        QVERIFY(waveform);
        clock.restart();
        playlist->playRow(0);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QTRY_COMPARE(playlist->playingRow(), 0);
        QTRY_VERIFY_WITH_TIMEOUT(waveform->peaks().isCompleted(), 30000);
        QVERIFY(waveform->peaks().size() > 0);
        qInfo() << "full-waveform-ms" << clock.elapsed();
        QTRY_VERIFY(engine->position() > 0);
        player->tagReader()->setSource(files[0]);
        const qint64 tagDuration = player->tagReader()->getTag('D').toLongLong();
        QVERIFY(tagDuration > 0);
        QTRY_VERIFY2(qAbs(engine->durationMsec() - tagDuration * 1000) < 2000,
                     qPrintable(QString("Playback duration %1 ms, tag duration %2 s")
                                    .arg(engine->durationMsec()).arg(tagDuration)));
        if (!referenceMedia) {
            QCOMPARE(engine->durationMsec(), qint64(10000));
            QCOMPARE(tagDuration, qint64(10));
        }
        engine->pause();
        QCOMPARE(engine->state(), N::PlaybackPaused);
        engine->setPosition(0.5);
        engine->play();
        QTRY_VERIFY(engine->position() >= 0.5);
        clock.restart();
        waveform->start(files[0]);
        QVERIFY(waveform->peaks().isCompleted());
        qInfo() << "cached-waveform-ms" << clock.elapsed();
        auto *removeAction = player->findChild<NAction *>("RemoveFromPlaylistAction");
        QVERIFY(removeAction);
        QVERIFY(removeAction->shortcuts().contains("Del") || removeAction->shortcuts().contains("Delete"));
        playlist->setCurrentRow(2);
        removeAction->trigger();
        QCOMPARE(playlist->count(), 2);
        QVERIFY(QFile::exists(files[1]));
        QVERIFY(player->mainWindow()->grab().save(QCoreApplication::applicationDirPath() + "/render.png"));
        if (auto menuButton = player->mainWindow()->findChild<QAbstractButton *>("menuButton")) {
            // Observe the real show event; desktop focus can close a popup
            // before an arbitrary delayed visibility check runs.
            MenuObserver observer;
            qApp->installEventFilter(&observer);
            menuButton->click();
            qApp->removeEventFilter(&observer);
            QVERIFY(observer.opened);
        }
        const QSize normalSize = player->mainWindow()->size();
        player->mainWindow()->toggleMaximize();
        QTRY_VERIFY(player->mainWindow()->isMaximized());
        player->mainWindow()->toggleMaximize();
        QTRY_VERIFY(!player->mainWindow()->isMaximized());
        QCOMPARE(player->mainWindow()->size(), normalSize);
        player->mainWindow()->toggleFullScreen();
        QTRY_VERIFY(player->mainWindow()->isFullSceen());
        player->mainWindow()->toggleFullScreen();
        QTRY_VERIFY(!player->mainWindow()->isFullSceen());
        QCOMPARE(player->mainWindow()->size(), normalSize);
        auto tray = player->findChild<QSystemTrayIcon *>();
        QVERIFY(tray && tray->contextMenu() && !tray->icon().isNull());
        tray->show();
        QVERIFY(tray->isVisible());
        tray->hide();
        engine->stop();
        waveform->stop();
        // Same parser used for messages delivered by QtSingleApplication.
        player->readMessage(files.join(MSG_SPLITTER));
        QCOMPARE(playlist->count(), 4);
        QCOMPARE(playlist->item(3)->data(N::PathRole).toString(), files[1]);
        player->quit();
        QVERIFY(QFile::exists(NCore::defaultPlaylistPath()));
        settings->sync();
        QSettings persisted(NCore::settingsPath(), QSettings::IniFormat);
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
        persisted.setIniCodec("UTF-8");
#endif
        if (skin.startsWith("Slim")) {
            QCOMPARE(persisted.value("SlimSkin/Splitter").toList().size(), 2);
        }
        // Close while a previously uncomputed track is still being processed.
        waveform->start(files[1]);
        auto *worker = dynamic_cast<QThread *>(waveform);
        QVERIFY(worker && worker->isRunning());
        QVERIFY(!waveform->peaks().isCompleted());
        clock.restart();
        player.reset();
        qInfo() << "shutdown-during-waveform-ms" << clock.elapsed();
        QVERIFY(clock.elapsed() < 5000);
    }
};

int main(int argc, char **argv)
{
    QGuiApplication::setHighDpiScaleFactorRoundingPolicy(Qt::HighDpiScaleFactorRoundingPolicy::Round);
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    QCoreApplication::setAttribute(Qt::AA_UseHighDpiPixmaps);
    QCoreApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
#endif
    QApplication app(argc, argv);
    app.setApplicationName("Nulloy package test");
    app.setApplicationVersion(_N_VERSION_);
    app.setQuitOnLastWindowClosed(false);
    // An unexpected modal error must fail CI rather than wait for a person.
    QTimer dialogGuard;
    QObject::connect(&dialogGuard, &QTimer::timeout, [] {
        for (QWidget *widget : QApplication::topLevelWidgets()) {
            if (auto *dialog = qobject_cast<QMessageBox *>(widget); dialog && dialog->isVisible()) {
                qCritical() << "Unexpected dialog:" << dialog->text();
                std::exit(2);
            }
        }
    });
    dialogGuard.start(100);
    TestPlayerPackage test;
    return QTest::qExec(&test, argc, argv);
}
#include "testPlayerPackage.moc"
