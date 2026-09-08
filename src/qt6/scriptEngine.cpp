// SPDX-License-Identifier: GPL-3.0-only
#include "scriptEngine.h"
#include "global.h"
#include "mainWindow.h"
#include "playbackEngineInterface.h"
#include "player.h"
#include "settings.h"
#include "skinLoader.h"
#include "skinResources.h"
#include <QMetaEnum>

static QJSValue enums(QJSEngine &engine, const QMetaObject &meta)
{
    auto result = engine.newObject();
    for (int i = 0; i < meta.enumeratorCount(); ++i) {
        const auto e = meta.enumerator(i);
        for (int k = 0; k < e.keyCount(); ++k) result.setProperty(QString::fromLatin1(e.key(k)), e.value(k));
    }
    return result;
}

NScriptEngine::NScriptEngine(NPlayer *player) : QJSEngine(player), m_bridge(this)
{
    installExtensions(QJSEngine::ConsoleExtension);
    auto global = globalObject();
    auto ui = newObject();
    auto window = player->mainWindow();
    auto widgets = window->findChildren<QWidget *>();
    widgets.append(window);
    for (auto widget : widgets)
        if (!widget->objectName().isEmpty()) ui.setProperty(widget->objectName(), m_bridge.wrap(widget));
    global.setProperty("Ui", ui);
    global.setProperty("Qt", enums(*this, Qt::staticMetaObject));
    global.setProperty("N", enums(*this, N::staticMetaObject));
    global.setProperty("QT_VERSION", QT_VERSION);
    global.setProperty("Q_WS", "win");
    global.setProperty("WS_WM_BUTTON_DIRECTION", "right");
    global.setProperty("WS_WM_TILING", false);
    global.setProperty("Settings", m_bridge.wrap(NSettings::instance()));
    global.setProperty("PlaybackEngine", m_bridge.wrap(player->playbackEngine()));
    global.setProperty("Player", m_bridge.wrap(player));
#ifndef _N_NO_SKINS_
    auto resources = NSkinLoader::resources();
    QJSEngine::setObjectOwnership(resources, QJSEngine::CppOwnership);
    global.setProperty("Resources", newQObject(resources));
    evaluate(R"JS(
        function readFile(name) { return Resources.readFile(name); }
        function maskImage(name, color, opacity) {
            if (!Resources.maskImage(name, color, opacity === undefined ? 1 : opacity))
                throw new Error('maskImage failed: ' + name);
        }
        function addApplicationFont(name) { return Resources.addApplicationFont(name); }
    )JS");
#endif
    evaluate("function print(message) { console.log(String(message)); }");
}
