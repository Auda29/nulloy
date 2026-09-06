// SPDX-License-Identifier: GPL-3.0-only
#include "skinRuntime.h"
#include "coverWidget.h"
#include "fixtureServices.h"
#include "label.h"
#include "playlistWidget.h"
#include "pluginLoader.h"
#include "settings.h"
#include "trackInfoReader.h"
#include "volumeSlider.h"
#include "waveformSlider.h"
#include <QMetaEnum>
#include <QSizeGrip>
#include <QTemporaryFile>
#include <QUiLoader>

class OriginalWidgetLoader : public QUiLoader
{
protected:
    QWidget *createWidget(const QString &name, QWidget *parent, const QString &objectName) override
    {
        QWidget *widget = nullptr;
        if (name == "NLabel") widget = new NLabel(parent);
        else if (name == "NCoverWidget") widget = new NCoverWidget(parent);
        else if (name == "NPlaylistWidget") widget = new NPlaylistWidget(parent);
        else if (name == "NVolumeSlider") widget = new NVolumeSlider(parent);
        else if (name == "NSlider") widget = new NSlider(parent);
        else if (name == "NWaveformSlider") widget = new NWaveformSlider(parent);
        else if (name == "QSizeGrip") widget = new QSizeGrip(parent);
        else return QUiLoader::createWidget(name, parent, objectName);
        widget->setObjectName(objectName);
        return widget;
    }
};

SkinRuntime::SkinRuntime(QObject *parent) : QObject(parent), bridge_(&engine_) {}

static QJSValue enums(QJSEngine &engine, const QMetaObject &meta)
{
    auto result = engine.newObject();
    for (int i = 0; i < meta.enumeratorCount(); ++i) {
        const auto e = meta.enumerator(i);
        for (int k = 0; k < e.keyCount(); ++k) result.setProperty(QString::fromLatin1(e.key(k)), e.value(k));
    }
    return result;
}

bool SkinRuntime::load(const QString &path, QString *error)
{
    if (!resources_.load(path, error)) return false;
    QTemporaryFile form;
    if (!form.open()) { *error = "Cannot create prepared UI form"; return false; }
    form.write(resources_.readFile("form.ui").toUtf8());
    form.flush();
    OriginalWidgetLoader loader;
    window_ = std::make_unique<NMainWindow>(form.fileName(), nullptr, &loader);
    window_->resize(430, 350);
    auto playlist = window_->findChild<NPlaylistWidget *>("playlistWidget");
    if (playlist) {
        auto tags = new FixtureTags(window_.get());
        playlist->setTrackInfoReader(new NTrackInfoReader(tags, window_.get()));
    }
    auto playback = dynamic_cast<FixturePlayback *>(NPluginLoader::getPlugin(N::PlaybackEngine));
    auto waveform = window_->findChild<NWaveformSlider *>("waveformSlider");
    if (waveform) connect(playback, &FixturePlayback::stateChanged, waveform,
        [waveform](N::PlaybackState state) { waveform->setPausedState(state == N::PlaybackPaused); });
    auto ui = engine_.newObject();
    auto widgets = window_->findChildren<QWidget *>();
    widgets.append(window_.get());
    for (auto widget : widgets)
        if (!widget->objectName().isEmpty()) ui.setProperty(widget->objectName(), bridge_.wrap(widget));
    auto global = engine_.globalObject();
    global.setProperty("Ui", ui);
    global.setProperty("Qt", enums(engine_, Qt::staticMetaObject));
    global.setProperty("N", enums(engine_, N::staticMetaObject));
    global.setProperty("QT_VERSION", QT_VERSION);
    global.setProperty("Q_WS", "win");
    global.setProperty("WS_WM_BUTTON_DIRECTION", "right");
    global.setProperty("WS_WM_TILING", false);
    global.setProperty("Settings", bridge_.wrap(NSettings::instance()));
    global.setProperty("PlaybackEngine", bridge_.wrap(dynamic_cast<QObject *>(NPluginLoader::getPlugin(N::PlaybackEngine))));
    global.setProperty("Player", bridge_.wrap(this));
    global.setProperty("Resources", engine_.newQObject(&resources_));
    QJSEngine::setObjectOwnership(&resources_, QJSEngine::CppOwnership);
    auto helpers = engine_.evaluate(R"JS(
        function print(message) { Player.print(String(message)); }
        function readFile(name) { return Resources.readFile(name); }
        function maskImage(name, color, opacity) {
            if (!Resources.maskImage(name, color, opacity === undefined ? 1 : opacity))
                throw new Error('maskImage failed: ' + name);
        }
        function addApplicationFont(name) { return Resources.addApplicationFont(name); }
    )JS");
    if (helpers.isError()) { *error = helpers.toString(); return false; }
    auto result = engine_.evaluate(resources_.readFile("script.js"), path + "/script.js");
    if (result.isError()) { *error = result.toString(); return false; }
    main_ = global.property("Main").callAsConstructor();
    if (main_.isError() || !messages.isEmpty()) {
        *error = main_.isError() ? main_.toString() : messages.join('\n'); return false;
    }
    return true;
}

bool SkinRuntime::afterShow(QString *error)
{
    window_->show();
    auto result = main_.property("afterShow").callWithInstance(main_);
    if (result.isError() || !messages.isEmpty()) {
        *error = result.isError() ? result.toString() : messages.join('\n'); return false;
    }
    return true;
}
