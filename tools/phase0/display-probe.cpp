// Read-only Qt 5 display probe. Does not create a window or change system settings.
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QScreen>
#include <QSysInfo>
#include <cstdio>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    QJsonArray screens;
    for (QScreen *screen : app.screens()) {
        const QRect rect = screen->geometry();
        screens.append(QJsonObject{
            {"name", screen->name()},
            {"primary", screen == app.primaryScreen()},
            {"x", rect.x()}, {"y", rect.y()},
            {"width", rect.width()}, {"height", rect.height()},
            {"logicalDpi", screen->logicalDotsPerInch()},
            {"devicePixelRatio", screen->devicePixelRatio()},
            {"refreshRate", screen->refreshRate()}
        });
    }
    const QByteArray json = QJsonDocument(QJsonObject{
        {"qtRuntime", qVersion()},
        {"architecture", QSysInfo::currentCpuArchitecture()},
        {"os", QSysInfo::prettyProductName()},
        {"platform", app.platformName()},
        {"screens", screens}
    }).toJson();
    std::fwrite(json.constData(), 1, json.size(), stdout);
    return 0;
}
