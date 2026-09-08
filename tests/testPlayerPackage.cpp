// SPDX-License-Identifier: GPL-3.0-or-later
// Run from an extracted package with its real playback plugin and no toolchain PATH.
#include <QtTest>
#include <QDragEnterEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QMessageBox>
#include <QMimeData>
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
#ifndef _N_NO_SKINS_
#include "skinFileSystem.h"
Q_IMPORT_PLUGIN(NWidgetCollection)
#endif

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
#ifndef _N_NO_SKINS_
        NSkinFileSystem::init();
#endif
        QElapsedTimer clock;
        clock.start();
        auto player = std::make_unique<NPlayer>();
        QVERIFY(player->mainWindow()->isVisible());
        QVERIFY(QTest::qWaitForWindowExposed(player->mainWindow()));
        qInfo() << "window-exposed-ms" << clock.elapsed();
        QCOMPARE(settings->value("Skin").toString(), skin);
        auto *playlist = player->playlistWidget();
        QVERIFY(playlist);
        QCOMPARE(playlist->count(), 0);
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
        QVERIFY(qAbs(engine->durationMsec() - tagDuration * 1000) < 2000);
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
        engine->stop();
        waveform->stop();
        player->quit();
        QVERIFY(QFile::exists(NCore::defaultPlaylistPath()));
        clock.restart();
        player.reset();
        qInfo() << "player-destruction-ms" << clock.elapsed();
    }
};

int main(int argc, char **argv)
{
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
