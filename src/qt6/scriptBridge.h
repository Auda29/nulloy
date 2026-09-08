// SPDX-License-Identifier: GPL-3.0-only
// Experimental Qt 6 replacement for scriptQtPrototypes; original skins stay unchanged.
#pragma once
#include <QJSEngine>
#include <QPointer>
#include <QWidget>

class ScriptBridge;
class ObjectBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(int windowFlags READ windowFlags WRITE setWindowFlags)
    Q_PROPERTY(bool settings READ isSettings CONSTANT)
public:
    ObjectBridge(QObject *object, ScriptBridge *owner);
    int windowFlags() const;
    bool isSettings() const;
    Q_INVOKABLE void setSetting(QString key, QJSValue value);
    void setWindowFlags(int flags);
    Q_INVOKABLE void setAttribute(int attribute, bool enabled = true);
    Q_INVOKABLE QJSValue parentWidget();
    Q_INVOKABLE void move(int x, int y);
    Q_INVOKABLE void resize(int width, int height);
    Q_INVOKABLE void setSizeGripEnabled(bool enabled);
    Q_INVOKABLE void setStandardIcon(QString name, QString fallback = {});
    Q_INVOKABLE QJSValue layout();
    Q_INVOKABLE void setFontSize(int size);
    Q_INVOKABLE void enableDoubleClick();
    Q_INVOKABLE void setParent(QJSValue parent);
    Q_INVOKABLE QVariantMap contentsMargins() const;
    Q_INVOKABLE void setContentsMargins(int left, int top, int right, int bottom);
    Q_INVOKABLE void setContentsMargins(QVariantMap margins);
    Q_INVOKABLE void setSpacing(int spacing);
    Q_INVOKABLE void setSpacingAt(int index, int spacing);
    Q_INVOKABLE void insertWidget(int index, QJSValue widget);
    Q_INVOKABLE void insertSpacing(int index, int size);
    Q_INVOKABLE QList<int> sizes() const;
    Q_INVOKABLE void setSizes(QList<int> sizes);
    Q_INVOKABLE QVariantMap position() const;
    Q_INVOKABLE void showContextMenu(QVariantMap position);
    Q_INVOKABLE QString signalName(QString signature) const;
signals:
    void doubleClicked();
    void clicked(bool checked);
protected:
    bool eventFilter(QObject *object, QEvent *event) override;
private:
    QWidget *widget() const;
    QPointer<QObject> object_;
    ScriptBridge *owner_;
};

class ScriptBridge : public QObject
{
    Q_OBJECT
public:
    explicit ScriptBridge(QJSEngine *engine);
    QJSValue wrap(QObject *object);
    static QObject *unwrap(const QJSValue &value);
private:
    QJSEngine *engine_;
    QJSValue factory_;
    QHash<QObject *, QJSValue> wrappers_;
};
