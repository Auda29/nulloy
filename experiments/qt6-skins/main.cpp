// SPDX-License-Identifier: GPL-3.0-only
#include "skinRuntime.h"
#include "fixtureServices.h"
#include "playlistWidget.h"
#include "pluginLoader.h"
#include "settings.h"
#include "waveformSlider.h"
#include <QApplication>
#include <QAbstractButton>
#include <QFileInfo>
#include <QMessageBox>
#include <QShortcut>

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    app.setStyle("Fusion");
    if (app.arguments().size() != 2) return 2;
    SkinRuntime runtime;
    QString error;
    if (!runtime.load(app.arguments().at(1), &error) || !runtime.afterShow(&error)) {
        QMessageBox::critical(nullptr, "Skin-Prototyp", error);
        return 1;
    }
    auto window = runtime.window();
    window->setTitle("Nulloy · Skin-Prototyp");
    auto playback = dynamic_cast<FixturePlayback *>(NPluginLoader::getPlugin(N::PlaybackEngine));
    auto play = window->findChild<QAbstractButton *>("playButton");
    if (play) QObject::connect(play, &QAbstractButton::clicked, playback, [playback] {
        if (playback->state() == N::PlaybackPlaying) playback->pause(); else playback->play();
    });
    auto close = window->findChild<QAbstractButton *>("closeButton");
    if (close) QObject::connect(close, &QAbstractButton::clicked, window, &QWidget::close);
    auto minimize = window->findChild<QAbstractButton *>("minimizeButton");
    if (minimize) QObject::connect(minimize, &QAbstractButton::clicked, window, &QWidget::showMinimized);
    auto fullscreen = new QShortcut(QKeySequence(Qt::Key_F11), window);
    QObject::connect(fullscreen, &QShortcut::activated, window, &NMainWindow::toggleFullScreen);
    auto playlist = window->findChild<NPlaylistWidget *>("playlistWidget");
    auto wave = window->findChild<NWaveformSlider *>("waveformSlider");
    const auto fixture = app.applicationDirPath() + "/tests/01.wav";
    if (playlist && QFileInfo::exists(fixture)) playlist->addFiles({fixture});
    if (wave && QFileInfo::exists(fixture)) { wave->setMedia(fixture); wave->setValue(.25); }
    return app.exec();
}
