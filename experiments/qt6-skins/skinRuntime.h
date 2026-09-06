// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "mainWindow.h"
#include "scriptBridge.h"
#include "skinResources.h"
#include <memory>

class SkinRuntime : public QObject
{
    Q_OBJECT
public:
    explicit SkinRuntime(QObject *parent = nullptr);
    bool load(const QString &path, QString *error);
    bool afterShow(QString *error);
    NMainWindow *window() const { return window_.get(); }
    QJSEngine *engine() { return &engine_; }
    SkinResources *resources() { return &resources_; }
    QStringList messages;
    QPoint lastMenuPosition;
    int menuCalls = 0;
    Q_INVOKABLE void print(QString message) { messages.append(message); }
    Q_INVOKABLE void showContextMenu(QVariantMap position)
    { lastMenuPosition = QPoint(position.value("x").toInt(), position.value("y").toInt()); ++menuCalls; }
private:
    SkinResources resources_;
    QJSEngine engine_;
    ScriptBridge bridge_;
    std::unique_ptr<NMainWindow> window_;
    QJSValue main_;
};
