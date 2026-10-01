// SPDX-License-Identifier: GPL-3.0-only
#include <QtTest>
#include <memory>
#include "common.h"
#include "player.h"
#include "playlistWidget.h"
#include "playlistWidgetItem.h"
#include "playbackEngineInterface.h"
#include "settings.h"

class Test132 : public QObject
{
    Q_OBJECT
    QTemporaryDir media;
    QStringList files;
    std::unique_ptr<NPlayer> player;

    void start(const QStringList &row, bool restore = true, bool paused = false)
    {
        // Persist and destroy the settings object before production startup reads it.
        auto *settings = NSettings::instance();
        settings->clear();
        delete settings;
        settings = NSettings::instance();
        settings->setValue("RestorePlaylist", restore);
        settings->setValue("StartPaused", paused);
        settings->setValue("PlaylistRow", row);
        settings->setValue("Volume", 0.0);
        settings->setValue("TrayIcon", false);
        settings->setValue("DisplayLogDialog", false);
        settings->setValue("AutoCheckUpdates", false);
        settings->sync();
        QCOMPARE(settings->status(), QSettings::NoError);
        delete settings;
        QSettings persisted(NCore::settingsPath(), QSettings::IniFormat);
        QCOMPARE(persisted.value("PlaylistRow").toStringList(), row);
        QCOMPARE(persisted.value("RestorePlaylist").toBool(), restore);
        QCOMPARE(persisted.value("StartPaused").toBool(), paused);
        // Calls real private loadDefaultPlaylist() through its normal constructor path.
        player = std::make_unique<NPlayer>();
    }

    void verifyIdle()
    {
        auto *engine = player->playbackEngine();
        QCOMPARE(player->playlistWidget()->count(), 2);
        QCOMPARE(player->playlistWidget()->playingRow(), -1);
        QVERIFY(!engine->hasMedia());
        QCOMPARE(engine->state(), N::PlaybackStopped);
        QTest::qWait(200);
        QVERIFY(!engine->hasMedia());
        QCOMPARE(engine->state(), N::PlaybackStopped);
    }

private slots:
    void initTestCase()
    {
        QVERIFY(media.isValid());
        for (int i = 0; i < 2; ++i) {
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
        QFile playlist(NCore::defaultPlaylistPath());
        QVERIFY(playlist.open(QIODevice::WriteOnly));
        playlist.write(("#EXTM3U\n" + files.join('\n') + '\n').toUtf8());
    }
    void cleanup()
    {
        if (player) {
            player->playbackEngine()->stop();
            player.reset();
        }
    }
    void invalidNumbersAreIgnored_data()
    {
        QTest::addColumn<QStringList>("row");
        QTest::newRow("non-numeric-row") << QStringList{"bogus", "0.25"};
        QTest::newRow("non-numeric-position") << QStringList{"1", "bogus"};
        QTest::newRow("row-overflow") << QStringList{"999999999999999999999", "0.25"};
        QTest::newRow("negative-position") << QStringList{"1", "-0.1"};
        QTest::newRow("position-over-one") << QStringList{"1", "1.1"};
        QTest::newRow("nan-position") << QStringList{"1", "nan"};
        QTest::newRow("infinite-position") << QStringList{"1", "inf"};
    }
    void invalidNumbersAreIgnored()
    {
        QFETCH(QStringList, row);
        start(row);
        QVERIFY(player);
        verifyIdle();
    }
    void otherInvalidRowsAreIgnored_data()
    {
        QTest::addColumn<QStringList>("row");
        QTest::addColumn<bool>("paused");
        for (bool paused : {false, true}) {
            const QByteArray suffix = paused ? "-paused" : "-autoplay";
            QTest::newRow(("empty" + suffix).constData()) << QStringList{} << paused;
            QTest::newRow(("extra-value" + suffix).constData())
                << QStringList{"1", "0.5", "unexpected"} << paused;
            QTest::newRow(("negative-row" + suffix).constData())
                << QStringList{"-1", "0.5"} << paused;
            QTest::newRow(("out-of-range-row" + suffix).constData())
                << QStringList{"2", "0.5"} << paused;
        }
    }
    void otherInvalidRowsAreIgnored()
    {
        QFETCH(QStringList, row);
        QFETCH(bool, paused);
        start(row, true, paused);
        QVERIFY(player);
        verifyIdle();
    }
    void restorationPolicy_data()
    {
        QTest::addColumn<bool>("restore");
        QTest::addColumn<bool>("paused");
        QTest::newRow("restore-off-autoplay") << false << false;
        QTest::newRow("restore-off-paused") << false << true;
        QTest::newRow("restore-on-autoplay") << true << false;
        QTest::newRow("restore-on-paused") << true << true;
    }
    void restorationPolicy()
    {
        QFETCH(bool, restore);
        QFETCH(bool, paused);
        start({"1", "0.5"}, restore, paused);
        QVERIFY(player);
        auto *engine = player->playbackEngine();
        auto *list = player->playlistWidget();
        if (!restore) {
            QCOMPARE(list->count(), 0);
            QCOMPARE(list->playingRow(), -1);
            QVERIFY(!engine->hasMedia());
            QTest::qWait(250);
            QVERIFY(!engine->hasMedia());
            QCOMPARE(engine->state(), N::PlaybackStopped);
            return;
        }
        QCOMPARE(list->count(), 2);
        for (int i = 0; i < files.size(); ++i)
            QCOMPARE(list->itemAtRow(i)->data(N::PathRole).toString(), files.at(i));
        QCOMPARE(engine->currentMedia(), files.at(1));
        if (paused) {
            // Existing StartPaused stages media/position without starting the pipeline.
            QCOMPARE(list->playingRow(), 1);
            QCOMPARE(engine->state(), N::PlaybackStopped);
            QCOMPARE(engine->position(), 0.5);
            QTest::qWait(250);
            QCOMPARE(engine->state(), N::PlaybackStopped);
            QCOMPARE(engine->position(), 0.5);
            player->playPause();
        }
        QTRY_COMPARE_WITH_TIMEOUT(engine->state(), N::PlaybackPlaying, 5000);
        QTRY_COMPARE_WITH_TIMEOUT(list->playingRow(), 1, 5000);
        QTRY_VERIFY_WITH_TIMEOUT(engine->position() >= 0.5 && engine->position() < 0.6, 5000);
        QTest::qWait(250);
        QVERIFY(engine->position() > 0.5 && engine->position() < 0.6);
        QCOMPARE(engine->currentMedia(), files.at(1));
    }
    void restorationDisabledIgnoresMalformedRow_data()
    {
        QTest::addColumn<bool>("paused");
        QTest::newRow("autoplay") << false;
        QTest::newRow("paused") << true;
    }
    void restorationDisabledIgnoresMalformedRow()
    {
        QFETCH(bool, paused);
        start({"1"}, false, paused);
        QVERIFY(player);
        QCOMPARE(player->playlistWidget()->count(), 0);
        QVERIFY(!player->playbackEngine()->hasMedia());
        QTest::qWait(200);
        QCOMPARE(player->playbackEngine()->state(), N::PlaybackStopped);
    }
    void pausedPositionEndpoints_data()
    {
        QTest::addColumn<QString>("position");
        QTest::newRow("beginning") << QString("0");
        QTest::newRow("end") << QString("1");
    }
    void pausedPositionEndpoints()
    {
        QFETCH(QString, position);
        start({"0", position}, true, true);
        QVERIFY(player);
        QCOMPARE(player->playlistWidget()->playingRow(), 0);
        QCOMPARE(player->playbackEngine()->currentMedia(), files.at(0));
        QCOMPARE(player->playbackEngine()->position(), position.toDouble());
        QCOMPARE(player->playbackEngine()->state(), N::PlaybackStopped);
    }
    void singleValueIsIgnored()
    {
        start({"1"});
        QVERIFY(player);
        verifyIdle();
    }
};

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    app.setApplicationName("Upstream132Test");
    app.setQuitOnLastWindowClosed(false);
    Test132 test;
    return QTest::qExec(&test, argc, argv);
}
#include "test132.moc"
