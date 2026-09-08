// SPDX-License-Identifier: GPL-3.0-only
#include "skinRuntime.h"
#include "fixtureServices.h"
#include "label.h"
#include "playlistWidget.h"
#include "pluginLoader.h"
#include "settings.h"
#include "waveformSlider.h"
#include <QAbstractButton>
#include <QSplitter>
#include <QtTest>

class SkinRuntimeTest : public QObject
{
    Q_OBJECT
private slots:
    void initTestCase() { QApplication::setStyle("Fusion"); }
    void init() {
        QTest::failOnWarning(QRegularExpression(".*(TypeError|ReferenceError|QFormBuilder was unable|Cannot open file|Could not create pixmap|setGeometry: Unable).*"));
    }
    void originalSkins_data();
    void originalSkins();
};
void SkinRuntimeTest::originalSkins_data()
{
    QTest::addColumn<QString>("skin");
    QTest::addColumn<QString>("path");
    for (QString skin : {"slim", "native", "silver", "metro"}) {
        QTest::newRow(qPrintable(skin + "-directory")) << skin << QString(SKIN_SOURCE_ROOT "/") + skin;
        QTest::newRow(qPrintable(skin + "-nzs")) << skin << QString(FIXTURE_ROOT "/") + skin + "-deflated.nzs";
    }
    if (!QString(REFERENCE_ROOT).isEmpty()) {
        for (QString skin : {"slim", "silver", "metro"}) {
            QString package = skin; package[0] = package[0].toUpper();
            QTest::newRow(qPrintable(skin + "-reference-099")) << skin << QString(REFERENCE_ROOT "/") + package + ".nzs";
        }
    }
}
void SkinRuntimeTest::originalSkins()
{
    QFETCH(QString, skin);
    QFETCH(QString, path);
    NSettings::instance()->clear();
    NSettings::instance()->setValue("ShowPlaybackControls", true);
    NSettings::instance()->setValue("PlaylistTrackInfo", "%F{ (%d)}");
    SkinRuntime runtime;
    QString error;
    QVERIFY2(runtime.load(path, &error), qPrintable(error));
    QVERIFY2(runtime.afterShow(&error), qPrintable(error));
    auto window = runtime.window();
    auto playlist = window->findChild<NPlaylistWidget *>("playlistWidget");
    QVERIFY(playlist);
    const QString track = QCoreApplication::applicationDirPath() + "/tests/01.wav";
    QVERIFY(QFile::exists(track));
    playlist->addFiles({track});
    QCOMPARE(playlist->count(), 1);
    QCOMPARE(playlist->item(0)->text(), QString("01.wav (3:19)"));
    auto wave = window->findChild<NWaveformSlider *>("waveformSlider");
    QVERIFY(wave);
    wave->setMedia(track);
    wave->setValue(.25);
    auto controls = window->findChild<QWidget *>("controlsContainer");
    QVERIFY(controls);
    auto play = window->findChild<QAbstractButton *>("playButton");
    QVERIFY(play);
    auto playback = dynamic_cast<FixturePlayback *>(NPluginLoader::getPlugin(N::PlaybackEngine));
    playback->play();
    if (skin != "native") QVERIFY(play->styleSheet().contains("pause.png"));
    else QVERIFY(!play->icon().isNull());
    playback->pause();
    if (skin == "slim") QVERIFY(play->styleSheet().isEmpty());
    window->setTitle("Test ä – 01");
    if (skin != "native") QCOMPARE(window->findChild<NLabel *>("titleLabel")->text(), QString("Test ä – 01"));
    window->showPlaybackControls(false);
    QVERIFY(controls->isHidden());
    window->showPlaybackControls(true);
    QVERIFY(!controls->isHidden());
    const QSize normalSize = window->size();
    window->toggleFullScreen();
    QVERIFY(controls->isHidden());
    window->toggleFullScreen();
    QVERIFY(!controls->isHidden());
    QTRY_COMPARE(window->size(), normalSize);
    window->toggleMaximize();
    QVERIFY(window->isMaximized());
    window->toggleMaximize();
    QVERIFY(!window->isMaximized());
    QTRY_COMPARE(window->size(), normalSize);
    auto splitter = window->findChild<QSplitter *>("splitter");
    QVERIFY(splitter);
    QVERIFY(QMetaObject::invokeMethod(splitter, "splitterMoved", Q_ARG(int, 100), Q_ARG(int, 1)));
    QString setting = skin; setting[0] = setting[0].toUpper();
    QVERIFY(NSettings::instance()->value(setting + "Skin/Splitter").isValid());
    if (skin == "slim" || skin == "metro") {
        auto menu = window->findChild<QAbstractButton *>("menuButton");
        menu->click();
        QCOMPARE(runtime.menuCalls, 1);
        QCOMPARE(runtime.lastMenuPosition, menu->pos() + QPoint(0, menu->height()));
    }
    if (skin == "metro") {
        auto theme = window->findChild<QAbstractButton *>("themeButton");
        auto before = runtime.resources()->bytes("play.png");
        auto beforeIcon = play->icon().pixmap(24, 24).toImage();
        theme->click();
        QVERIFY(before != runtime.resources()->bytes("play.png"));
        QVERIFY(beforeIcon != play->icon().pixmap(24, 24).toImage());
        QVERIFY(NSettings::instance()->value("MetroSkin/LightTheme").toBool());
        theme->click();
        QVERIFY(!NSettings::instance()->value("MetroSkin/LightTheme").toBool());
    }
    QTest::qWait(80);
    QVERIFY2(runtime.messages.isEmpty(), qPrintable(runtime.messages.join('\n')));
    QVERIFY(!runtime.engine()->hasError());
    QVERIFY(window->grab().save(QString(FIXTURE_ROOT "/") + QTest::currentDataTag() + ".png"));
    window->close();
}
QTEST_MAIN(SkinRuntimeTest)
#include "testSkinRuntime.moc"
