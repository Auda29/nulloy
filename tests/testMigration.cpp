// SPDX-License-Identifier: GPL-3.0-only
#include <QtTest>
#include <QProcess>
#include <QTemporaryDir>
#include <QUuid>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <qt_windows.h>
#include <qtlocalpeer.h>
#include <qxtglobalshortcut.h>
#include "common.h"
#include "playlistStorage.h"
#include "settings.h"
#include "abstractWaveformBuilder.h"
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
#include "qt6/scriptBridge.h"
#endif

class CacheProbe : public NAbstractWaveformBuilder
{
public:
    qreal position() const override { return 0; }
    using NAbstractWaveformBuilder::peaksFindFromCache;
    using NAbstractWaveformBuilder::peaksAppendToCache;
};

class TestMigration : public QObject
{
    Q_OBJECT
private slots:
    void portablePaths()
    {
        QTemporaryDir caller;
        const QString previous = QDir::currentPath();
        QVERIFY(QDir::setCurrent(caller.path()));
        const QString resolved = NCore::absoluteMediaArgument(QString::fromUtf8("Grüße.wav"));
        QVERIFY(QDir::setCurrent(previous));
        QCOMPARE(resolved, caller.filePath(QString::fromUtf8("Grüße.wav")));
        QCOMPARE(NCore::absoluteMediaArgument("https://example.com/audio.ogg"),
                 QString("https://example.com/audio.ogg"));
#ifdef _N_PORTABLE_FORK_
        QCOMPARE(NCore::rcDir(), QCoreApplication::applicationDirPath() + "/Data");
#endif
    }
    void legacyWaveformCache()
    {
        QTemporaryDir directory;
        const auto mediaPath = directory.filePath("audio.wav");
        QFile media(mediaPath);
        QVERIFY(media.open(QIODevice::WriteOnly));
        media.write("test");
        media.close();
        const auto cachePath = NCore::rcDir() + "/" + NCore::applicationBinaryName() + ".peaks";
        const auto relative = QDir(NCore::rcDir()).relativeFilePath(mediaPath);
        const auto hash = QCryptographicHash::hash(relative.toUtf8(), QCryptographicHash::Sha1);
        NWaveformPeaks peaks;
        for (int i = 0; i < 3000; ++i) peaks.append(i % 2 ? -0.75 : 0.5);
        peaks.complete();
        QByteArray buffer;
        QDataStream legacy(&buffer, QIODevice::WriteOnly);
        legacy.setVersion(QDataStream::Qt_5_15);
        legacy << QList<QByteArray>{hash} << QList<NWaveformPeaks>{peaks}
               << QHash<QByteArray, QString>{{hash, QFileInfo(mediaPath).lastModified().toString(Qt::ISODate)}};
        QFile cache(cachePath);
        QVERIFY(cache.open(QIODevice::WriteOnly));
        QDataStream file(&cache);
        file.setVersion(QDataStream::Qt_5_15);
        file << qCompress(buffer);
        cache.close();
        CacheProbe migrated;
        QVERIFY(migrated.peaksFindFromCache(mediaPath));
        QVERIFY(migrated.peaks().isCompleted());
        QCOMPARE(migrated.peaks().size(), peaks.size());
        QCOMPARE(migrated.peaks().positive(0), 0.5);
        QCOMPARE(migrated.peaks().negative(0), -0.75);
        migrated.peaksAppendToCache(mediaPath);
        CacheProbe reopened;
        QVERIFY(reopened.peaksFindFromCache(mediaPath));
        QCOMPARE(reopened.peaks().negative(0), -0.75);
    }
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    void scriptSettingsSurviveReload()
    {
        {
            QJSEngine engine;
            ScriptBridge bridge(&engine);
            engine.globalObject().setProperty("Settings", bridge.wrap(NSettings::instance()));
            const auto result = engine.evaluate("Settings.setValue('Skin/TestSizes', [123,456]); Settings.setValue('Skin/TestTheme', {color:'#123456', enabled:true});");
            QVERIFY2(!result.isError(), qPrintable(result.toString()));
        }
        NSettings::instance()->sync();
        delete NSettings::instance();
        QCOMPARE(NSettings::instance()->value("Skin/TestSizes").toList(), QVariantList({123,456}));
        const auto theme = NSettings::instance()->value("Skin/TestTheme").toMap();
        QCOMPARE(theme.value("color").toString(), QString("#123456"));
        QCOMPARE(theme.value("enabled").toBool(), true);
    }
#endif
    void settingsFromLegacyIni()
    {
        delete NSettings::instance();
        QFile ini(NCore::settingsPath());
        QVERIFY(ini.open(QIODevice::WriteOnly));
        const QByteArray legacy = QString::fromUtf8(
            "[General]\nSettingsVersion=0.8\nSkin=Slim/0.9\nVolume=0.375\n"
            "LastDirectory=D:/Musik/Grüße 日本語\nPosition=150, 250\nRestorePlaylist=true\n"
            "[Shortcuts]\nRemoveFromPlaylistAction=Delete\n").toUtf8();
        QCOMPARE(ini.write(legacy), legacy.size());
        ini.close();
        auto settings = NSettings::instance();
        QCOMPARE(settings->value("Skin").toString(), QString("Slim/0.9"));
        QCOMPARE(settings->value("LastDirectory").toString(), QString::fromUtf8("D:/Musik/Grüße 日本語"));
        QCOMPARE(settings->value("Position").toStringList(), QStringList({"150", "250"}));
        QCOMPARE(settings->value("Volume").toDouble(), 0.375);
        QVERIFY(settings->value("RestorePlaylist").toBool());
        QCOMPARE(settings->value("Shortcuts/RemoveFromPlaylistAction").toStringList(), QStringList({"Delete"}));
        const auto before = settings->value("LastDirectory");
        settings->sync();
        QCOMPARE(settings->status(), QSettings::NoError);
        delete settings;
        QCOMPARE(NSettings::instance()->value("LastDirectory"), before);
    }

    void extendedPlaylistRoundTrip()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto mediaPath = directory.filePath(QString::fromUtf8("Grüße 日本語.wav"));
        QFile media(mediaPath);
        QVERIFY(media.open(QIODevice::WriteOnly));
        media.close();
        const auto path = directory.filePath("copy.m3u");
        QFile playlist(path);
        QVERIFY(playlist.open(QIODevice::WriteOnly));
        playlist.write(QString::fromUtf8("#EXTM3U\n#NULLOY:0,7,0.375,%a – %t\n#EXTINF:199,Grüße 日本語\nGrüße 日本語.wav\n").toUtf8());
        playlist.close();
        const auto original = NPlaylistStorage::readM3u(path);
        QCOMPARE(original.size(), 1);
        QCOMPARE(original[0].path, mediaPath);
        QCOMPARE(original[0].title, QString::fromUtf8("Grüße 日本語"));
        QCOMPARE(original[0].duration, 199);
        QCOMPARE(original[0].playbackCount, 7);
        QCOMPARE(original[0].playbackPosition, 0.375f);
        QCOMPARE(original[0].titleFormat, QString::fromUtf8("%a – %t"));
        QVERIFY(!original[0].failed);
        NPlaylistStorage::writeM3u(path, original, N::NulloyM3u);
        const auto copy = NPlaylistStorage::readM3u(path);
        QCOMPARE(copy.size(), 1);
        QCOMPARE(copy[0].path, original[0].path);
        QCOMPARE(copy[0].title, original[0].title);
        QCOMPARE(copy[0].duration, original[0].duration);
        QCOMPARE(copy[0].playbackCount, original[0].playbackCount);
        QCOMPARE(copy[0].playbackPosition, original[0].playbackPosition);
        QCOMPARE(copy[0].titleFormat, original[0].titleFormat);
    }

    void singleInstanceUnicodeMessage()
    {
        const QString id = "Nulloy-migration-test-" + QUuid::createUuid().toString();
        const QString message = QString::fromUtf8("D:/Musik/Grüße 日本語.mp3<|>D:/Musik/zweiter Titel.mp3");
        QtLocalPeer server(nullptr, id);
        QVERIFY(!server.isClient());
        QSignalSpy received(&server, &QtLocalPeer::messageReceived);
        QProcess client;
        client.start(QCoreApplication::applicationFilePath(), {"--ipc-send", id, message});
        QVERIFY(client.waitForStarted());
        QTRY_COMPARE_WITH_TIMEOUT(client.state(), QProcess::NotRunning, 10000);
        QCOMPARE(client.exitStatus(), QProcess::NormalExit);
        QCOMPARE(client.exitCode(), 0);
        QCOMPARE(received.size(), 1);
        QCOMPARE(received[0][0].toString(), message);
    }

    void nativeHotkeyRegistrationAndDispatch()
    {
        const QKeySequence key("Ctrl+Alt+Shift+F12");
        QxtGlobalShortcut shortcut;
        QVERIFY(shortcut.setShortcut(key));
        const UINT modifiers = MOD_CONTROL | MOD_ALT | MOD_SHIFT;
        // A competing registration must fail while Qxt owns this combination.
        QVERIFY(!RegisterHotKey(nullptr, 0x5f01, modifiers, VK_F12));
        QCOMPARE(GetLastError(), DWORD(ERROR_HOTKEY_ALREADY_REGISTERED));
        QSignalSpy activated(&shortcut, &QxtGlobalShortcut::activated);
        // Exercise this application's native event filter without sending keyboard input.
        QVERIFY(PostThreadMessage(GetCurrentThreadId(), WM_HOTKEY, 0, MAKELPARAM(modifiers, VK_F12)));
        QTRY_COMPARE(activated.size(), 1);
        shortcut.setEnabled(false);
        QVERIFY(PostThreadMessage(GetCurrentThreadId(), WM_HOTKEY, 0, MAKELPARAM(modifiers, VK_F12)));
        QTest::qWait(50);
        QCOMPARE(activated.size(), 1);
    }
};

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    if (app.arguments().value(1) == "--profile-snapshot") {
        // Compare a copied profile with both Qt builds; never edit the source.
        const auto source = app.arguments().value(2);
        const auto output = app.arguments().value(3);
        QFile input(source);
        if (!input.open(QIODevice::ReadOnly)) return 2;
        QFile isolated(NCore::settingsPath());
        if (!isolated.open(QIODevice::WriteOnly)) return 3;
        isolated.write(input.readAll());
        isolated.close();
        auto settings = NSettings::instance();
        QJsonObject values;
        for (const auto &key : settings->allKeys()) values[key] = QJsonValue::fromVariant(settings->value(key));
        if (!app.arguments().value(4).isEmpty()) {
            QJsonArray playlist;
            for (const auto &item : NPlaylistStorage::readM3u(app.arguments().value(4))) {
                playlist.append(QJsonObject{{"path", item.path}, {"title", item.title},
                    {"duration", item.duration}, {"failed", item.failed},
                    {"count", item.playbackCount}, {"position", double(item.playbackPosition)},
                    {"titleFormat", item.titleFormat}});
            }
            values["__playlist"] = playlist;
        }
        settings->sync();
        QFile result(output);
        if (!result.open(QIODevice::WriteOnly)) return 4;
        result.write(QJsonDocument(values).toJson());
        return 0;
    }
    if (app.arguments().value(1) == "--ipc-send") {
        QtLocalPeer client(nullptr, app.arguments().value(2));
        return client.isClient() && client.sendMessage(app.arguments().value(3), 5000) ? 0 : 1;
    }
    TestMigration test;
    return QTest::qExec(&test, argc, argv);
}
#include "testMigration.moc"
