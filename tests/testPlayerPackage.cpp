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
