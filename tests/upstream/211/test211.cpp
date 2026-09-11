// SPDX-License-Identifier: GPL-3.0-only
#include <QtTest>
#include <memory>
#include "common.h"
#include "fileOpenBurst.h"
#include "player.h"
#include "playlistWidget.h"
#include "playlistWidgetItem.h"
#include "playbackEngineInterface.h"
#include "settings.h"

class Test211 : public QObject
{
    Q_OBJECT
    QTemporaryDir media;
    QStringList files;
    std::unique_ptr<NPlayer> player;
private slots:
    void initTestCase()
    {
        QVERIFY(media.isValid());
        // Real, long PCM files: avoid natural EOS during timing assertions.
        for (int i = 0; i < 4; ++i) {
            const QString path = media.filePath(QString::number(i) + ".wav");
            QFile f(path);
            QVERIFY(f.open(QIODevice::WriteOnly));
            QDataStream s(&f);
            s.setByteOrder(QDataStream::LittleEndian);
            const quint32 bytes = 8000 * 2 * 30;
            s.writeRawData("RIFF", 4); s << quint32(36 + bytes);
            s.writeRawData("WAVEfmt ", 8); s << quint32(16) << quint16(1) << quint16(1)
                << quint32(8000) << quint32(16000) << quint16(2) << quint16(16);
            s.writeRawData("data", 4); s << bytes;
            f.write(QByteArray(bytes, '\0'));
            files << path;
        }
    }
    void init()
    {
        auto *settings = NSettings::instance();
        settings->clear();
        delete settings;
        settings = NSettings::instance();
        settings->setValue("RestorePlaylist", false);
        settings->setValue("EnqueueFiles", false);
        settings->setValue("PlayEnqueued", true);
        settings->setValue("Volume", 0.0);
        settings->setValue("TrayIcon", false);
        settings->setValue("DisplayLogDialog", false);
        settings->setValue("AutoCheckUpdates", false);
        player = std::make_unique<NPlayer>();
    }
    void cleanup()
    {
        player->playbackEngine()->stop();
        player.reset();
    }
    void boundedPolicy()
    {
        NFileOpenBurst burst;
        QVERIFY(!burst.isContinuation(false, true));
        QVERIFY(burst.isContinuation(false, true));
        QTest::qWait(NFileOpenBurst::IdleMsec + 50);
        QVERIFY(!burst.isContinuation(false, true));
        // Messages keep the idle gap short, but cannot slide the absolute cap.
        for (int i = 0; i < 6; ++i) {
            QTest::qWait(150);
            QVERIFY(burst.isContinuation(false, true));
        }
        QTest::qWait(150);
        QVERIFY(!burst.isContinuation(false, true));
    }
    void preferenceMatrix_data()
    {
        QTest::addColumn<bool>("enqueue");
        QTest::addColumn<bool>("playEnqueued");
        QTest::addColumn<int>("state");
        for (bool enqueue : {false, true})
            for (bool play : {false, true})
                for (int state : {0, 1, 2})
                    QTest::newRow(qPrintable(QString("enqueue-%1-play-%2-state-%3")
                        .arg(enqueue).arg(play).arg(state))) << enqueue << play << state;
    }
    void preferenceMatrix()
    {
        QFETCH(bool, enqueue);
        QFETCH(bool, playEnqueued);
        QFETCH(int, state);
        NSettings::instance()->setValue("EnqueueFiles", enqueue);
        NSettings::instance()->setValue("PlayEnqueued", playEnqueued);
        auto *list = player->playlistWidget();
        auto *engine = player->playbackEngine();
        list->setFiles({files[3]});
        if (state) {
            list->playRow(0);
            QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
            if (state == 2) engine->pause();
            engine->setPosition(0.4);
        }
        const qreal previousPosition = engine->position();
        player->readMessage(files[0]);
        QTimer::singleShot(20, player.get(), [this]() { player->readMessage(files[1]); });
        QTimer::singleShot(40, player.get(), [this]() { player->readMessage(files[2]); });
        QTest::qWait(150);
        QStringList expected;
        if (enqueue) expected << files[3];
        expected << files.mid(0, 3);
        QCOMPARE(list->count(), expected.size());
        for (int i = 0; i < expected.size(); ++i) {
            auto *item = list->itemAtRow(i);
            QCOMPARE(item->data(N::PathRole).toString(), expected[i]);
            item->setData(Qt::DisplayRole, "%i");
            QCOMPARE(item->data(Qt::DisplayRole).toString(), QString::number(i + 1));
        }
        const bool preserve = enqueue && !playEnqueued && state;
        const int row = preserve ? 0 : (enqueue ? 1 : 0);
        QTRY_COMPARE(list->playingRow(), row);
        QCOMPARE(engine->currentMedia(), expected[row]);
        if (preserve) {
            QCOMPARE(engine->state(), state == 2 ? N::PlaybackPaused : N::PlaybackPlaying);
            QVERIFY(qAbs(engine->position() - previousPosition) < 0.05);
        } else {
            QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
            QVERIFY(engine->position() < 0.05);
        }
    }
    void restoredStartup_data()
    {
        QTest::addColumn<bool>("enqueue");
        QTest::addColumn<bool>("playEnqueued");
        QTest::addColumn<bool>("startPaused");
        for (bool enqueue : {false, true})
            for (bool play : {false, true})
                for (bool paused : {false, true})
                    QTest::newRow(qPrintable(QString("enqueue-%1-play-%2-paused-%3")
                        .arg(enqueue).arg(play).arg(paused))) << enqueue << play << paused;
    }
    void restoredStartup()
    {
        QFETCH(bool, enqueue);
        QFETCH(bool, playEnqueued);
        QFETCH(bool, startPaused);
        player.reset();
        auto *settings = NSettings::instance();
        settings->setValue("RestorePlaylist", true);
        settings->setValue("StartPaused", startPaused);
        settings->setValue("EnqueueFiles", enqueue);
        settings->setValue("PlayEnqueued", playEnqueued);
        settings->setValue("PlaylistRow", QStringList{"0", "0.4"});
        QFile saved(NCore::defaultPlaylistPath());
        QVERIFY(saved.open(QIODevice::WriteOnly));
        saved.write(("#EXTM3U\n" + files[3] + "\n").toUtf8());
        saved.close();
        player = std::make_unique<NPlayer>();
        auto *list = player->playlistWidget();
        QCOMPARE(list->count(), 1);
        QCOMPARE(list->itemAtRow(0)->data(N::PathRole).toString(), files[3]);
        // Match the existing synchronous startup decision, before the event loop
        // settles GStreamer's asynchronous state. Do not implement #98 or #23.
        const bool startNew = !enqueue || playEnqueued ||
                              player->playbackEngine()->state() == N::PlaybackStopped;
        player->readMessage(files[0]);
        QTimer::singleShot(20, player.get(), [this]() { player->readMessage(files[1]); });
        QTimer::singleShot(40, player.get(), [this]() { player->readMessage(files[2]); });
        QTest::qWait(150);
        QCOMPARE(list->count(), enqueue ? 4 : 3);
        const int firstNew = enqueue ? 1 : 0;
        for (int i = 0; i < 3; ++i)
            QCOMPARE(list->itemAtRow(firstNew + i)->data(N::PathRole).toString(), files[i]);
        QTRY_COMPARE(list->playingRow(), startNew ? firstNew : 0);
    }
    void emptyAndMissingMessagesDoNotClear()
    {
        player->playlistWidget()->setFiles({files[0]});
        player->readMessage("");
        player->readMessage(media.filePath("missing.wav"));
        QCOMPARE(player->playlistWidget()->count(), 1);
        QCOMPARE(player->playlistWidget()->itemAtRow(0)->data(N::PathRole).toString(), files[0]);
        QCOMPARE(player->playbackEngine()->state(), N::PlaybackStopped);
    }
    void preferenceChangesStartFreshOpen_data()
    {
        QTest::addColumn<bool>("enqueueBefore");
        QTest::addColumn<bool>("playBefore");
        QTest::addColumn<bool>("enqueueAfter");
        QTest::newRow("replace-to-enqueue") << false << true << true;
        QTest::newRow("enqueue-to-replace") << true << true << false;
        QTest::newRow("play-enqueued-enabled") << true << false << true;
    }
    void preferenceChangesStartFreshOpen()
    {
        QFETCH(bool, enqueueBefore);
        QFETCH(bool, playBefore);
        QFETCH(bool, enqueueAfter);
        auto *settings = NSettings::instance();
        settings->setValue("EnqueueFiles", enqueueBefore);
        settings->setValue("PlayEnqueued", playBefore);
        player->readMessage(files[0]);
        QTRY_COMPARE(player->playlistWidget()->playingRow(), 0);
        settings->setValue("EnqueueFiles", enqueueAfter);
        settings->setValue("PlayEnqueued", true);
        player->readMessage(files[1]);
        QCOMPARE(player->playlistWidget()->count(), enqueueAfter ? 2 : 1);
        QTRY_COMPARE(player->playlistWidget()->playingRow(), enqueueAfter ? 1 : 0);
    }
    void commandsEndBurst_data()
    {
        QTest::addColumn<QString>("command");
        for (const QString &cmd : {"--next", "--prev", "--stop", "--pause"})
            QTest::newRow(qPrintable(cmd)) << cmd;
    }
    void commandsEndBurst()
    {
        QFETCH(QString, command);
        player->readMessage(files.mid(0, 2).join(MSG_SPLITTER));
        auto *list = player->playlistWidget();
        auto *engine = player->playbackEngine();
        QTRY_COMPARE(list->playingRow(), 0);
        if (command == "--prev") {
            list->playRow(1);
            QTRY_COMPARE(list->playingRow(), 1);
        }
        if (command == "--pause") engine->pause();
        player->readMessage(command + MSG_SPLITTER + files[3]);
        QCOMPARE(list->count(), 2); // A control option takes priority over paths.
        if (command == "--stop") QCOMPARE(engine->state(), N::PlaybackStopped);
        if (command == "--next") QCOMPARE(engine->currentMedia(), files[1]);
        if (command == "--prev") QCOMPARE(engine->currentMedia(), files[0]);
        player->readMessage(files[2]);
        QCOMPARE(list->count(), 1); // This is a new open, not a continuation.
        QCOMPARE(list->itemAtRow(0)->data(N::PathRole).toString(), files[2]);
        player->readMessage("--stop");
        QCOMPARE(engine->state(), N::PlaybackStopped);
        QTest::qWait(350);
        QCOMPARE(engine->state(), N::PlaybackStopped); // No late restart.
    }
    void continuedBurstCanOutlastInitialIdleWindow()
    {
        player->readMessage(files[0]);
        QTest::qWait(150);
        player->readMessage(files[1]);
        QTest::qWait(150);
        player->readMessage(files[2]);
        QCOMPARE(player->playlistWidget()->count(), 3);
        QTRY_COMPARE(player->playlistWidget()->playingRow(), 0);
    }
    void separateMessagesReplaceOnlyOnce()
    {
        player->readMessage(files[0]); // startup entry point from main.cpp
        QTimer::singleShot(20, player.get(), [this]() { player->readMessage(files[1]); });
        QTimer::singleShot(40, player.get(), [this]() { player->readMessage(files[2]); });
        QTest::qWait(150);
        auto *list = player->playlistWidget();
        QCOMPARE(list->count(), 3);
        for (int i = 0; i < 3; ++i)
            QCOMPARE(list->itemAtRow(i)->data(N::PathRole).toString(), files[i]);
        QTRY_COMPARE(list->playingRow(), 0);
    }
};

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    app.setApplicationName("Upstream211Test");
    app.setQuitOnLastWindowClosed(false);
    Test211 test;
    return QTest::qExec(&test, argc, argv);
}
#include "test211.moc"
