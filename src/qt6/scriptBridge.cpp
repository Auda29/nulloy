// SPDX-License-Identifier: GPL-3.0-only
// Adapts the Nulloy scriptQtPrototypes contract, Copyright (C) 2010-2024
// Sergey Vlasov <sergey@vlasov.me>; see the original files and LICENSE.GPL3.
#include "scriptBridge.h"
#include <QAbstractButton>
#include <QBoxLayout>
#include <QDialog>
#include <QMouseEvent>
#include <QMetaMethod>
#include <QSplitter>
#include <QSettings>

ScriptBridge::ScriptBridge(QJSEngine *engine) : engine_(engine)
{
    // QObject wrappers do not implement QtScript's default prototypes. A per-object
    // proxy supplies the missing public QWidget/Layout methods without global state.
    factory_ = engine_->evaluate(R"JS(
      (function(raw, bridge) {
        function signal(s) {
          return {
            connect: function(receiver, method) {
              if (typeof method === 'string') return s.connect(receiver, receiver[method]);
              if (arguments.length === 1) return s.connect(receiver);
              return s.connect(receiver, method);
            },
            disconnect: function(receiver, method) {
              if (typeof method === 'string') return s.disconnect(receiver, receiver[method]);
              if (arguments.length === 1) return s.disconnect(receiver);
              return s.disconnect(receiver, method);
            }
          };
        }
        return new Proxy({}, {
          get: function(target, key) {
            if (key === '__qobject') return raw;
            if (key === 'setValue' && bridge.settings) return bridge.setSetting;
            if (key === 'pos') return bridge.position();
            if (key === 'showContextMenu') return bridge.showContextMenu;
            if (key === 'windowFlags') return bridge.windowFlags;
            if (key === 'doubleClicked') return signal(bridge.doubleClicked);
            if (key === 'clicked' || key === 'clicked()' || key === 'clicked(bool)')
              return signal(bridge.clicked);
            if (key === 'setSizes') return function(sizes) { bridge.setSizes(sizes == null ? [] : sizes); };
            var extra = ['parentWidget','move','resize','setAttribute','layout',
              'setSizeGripEnabled','setStandardIcon','setFontSize','enableDoubleClick',
              'doubleClicked','setParent','contentsMargins','setContentsMargins',
              'setSpacing','setSpacingAt','insertWidget','insertSpacing','sizes','setSizes'];
            if (extra.indexOf(key) !== -1) return bridge[key];
            if (typeof key === 'string') {
              var name = bridge.signalName(key);
              if (name) return signal(raw[name]);
            }
            return raw[key];
          },
          set: function(target, key, value) {
            if (key === 'windowFlags') bridge.windowFlags = value;
            else raw[key] = value;
            return true;
          }
        });
      })
    )JS", "widget-compatibility.js");
}

QJSValue ScriptBridge::wrap(QObject *object)
{
    if (!object) return QJSValue(QJSValue::NullValue);
    if (wrappers_.contains(object)) return wrappers_.value(object);
    QJSEngine::setObjectOwnership(object, QJSEngine::CppOwnership);
    auto bridge = new ObjectBridge(object, this);
    auto value = factory_.call({engine_->newQObject(object), engine_->newQObject(bridge)});
    wrappers_.insert(object, value);
    connect(object, &QObject::destroyed, this, [this, object, bridge] {
        wrappers_.remove(object);
        bridge->deleteLater();
    });
    return value;
}

QObject *ScriptBridge::unwrap(const QJSValue &value)
{
    return value.property("__qobject").toQObject();
}

ObjectBridge::ObjectBridge(QObject *object, ScriptBridge *owner)
    : QObject(owner), object_(object), owner_(owner)
{
    // QJSEngine resolves QAbstractButton's default-argument signal to its zero-arg
    // clone. Forward the actual bool signal so Metro's theme switch receives it.
    if (auto button = qobject_cast<QAbstractButton *>(object))
        connect(button, &QAbstractButton::clicked, this, &ObjectBridge::clicked);
}
QWidget *ObjectBridge::widget() const { return qobject_cast<QWidget *>(object_); }
bool ObjectBridge::isSettings() const { return qobject_cast<QSettings *>(object_) != nullptr; }
void ObjectBridge::setSetting(QString key, QJSValue value)
{
    if (!object_) return;
    // QJSEngine otherwise wraps JS arrays/objects in QVariant(QJSValue), which
    // cannot be serialized by QSettings. Invoke the real setter to keep signals.
    const QVariant native = value.toVariant();
    QMetaObject::invokeMethod(object_, "setValue", Q_ARG(QString, key), Q_ARG(QVariant, native));
}
int ObjectBridge::windowFlags() const { return widget() ? int(widget()->windowFlags()) : 0; }
void ObjectBridge::setWindowFlags(int flags) { if (widget()) widget()->setWindowFlags(Qt::WindowFlags(flags)); }
void ObjectBridge::setAttribute(int a, bool b) { if (widget()) widget()->setAttribute(Qt::WidgetAttribute(a), b); }
QJSValue ObjectBridge::parentWidget() { return owner_->wrap(widget() ? widget()->parentWidget() : nullptr); }
void ObjectBridge::move(int x, int y) { if (widget()) widget()->move(x, y); }
void ObjectBridge::resize(int w, int h) { if (widget()) widget()->resize(w, h); }
void ObjectBridge::setSizeGripEnabled(bool enabled) { if (auto d = qobject_cast<QDialog *>(object_)) d->setSizeGripEnabled(enabled); }
void ObjectBridge::setStandardIcon(QString name, QString fallback)
{
    if (auto button = qobject_cast<QAbstractButton *>(object_))
        button->setIcon(QIcon::fromTheme(name, QIcon(fallback)));
}
QJSValue ObjectBridge::layout() { return owner_->wrap(widget() ? widget()->layout() : nullptr); }
void ObjectBridge::setFontSize(int size)
{
    if (widget()) { auto font = widget()->font(); font.setPixelSize(size); widget()->setFont(font); }
}
void ObjectBridge::enableDoubleClick() { if (widget()) widget()->installEventFilter(this); }
bool ObjectBridge::eventFilter(QObject *, QEvent *event)
{
    if (event->type() == QEvent::MouseButtonDblClick && static_cast<QMouseEvent *>(event)->button() == Qt::LeftButton) {
        emit doubleClicked(); return true;
    }
    return false;
}
void ObjectBridge::setParent(QJSValue parent)
{
    if (widget()) widget()->setParent(qobject_cast<QWidget *>(ScriptBridge::unwrap(parent)));
}
QVariantMap ObjectBridge::contentsMargins() const
{
    auto layout = qobject_cast<QLayout *>(object_);
    auto m = layout ? layout->contentsMargins() : QMargins();
    return {{"left", m.left()}, {"top", m.top()}, {"right", m.right()}, {"bottom", m.bottom()}};
}
void ObjectBridge::setContentsMargins(int l, int t, int r, int b)
{ if (auto layout = qobject_cast<QLayout *>(object_)) layout->setContentsMargins(l, t, r, b); }
void ObjectBridge::setContentsMargins(QVariantMap m)
{ setContentsMargins(m.value("left").toInt(), m.value("top").toInt(), m.value("right").toInt(), m.value("bottom").toInt()); }
void ObjectBridge::setSpacing(int n) { if (auto layout = qobject_cast<QLayout *>(object_)) layout->setSpacing(n); }
void ObjectBridge::setSpacingAt(int index, int spacing)
{
    if (auto layout = qobject_cast<QBoxLayout *>(object_)) {
        if (index < 0 || index >= layout->count() || !layout->itemAt(index)->spacerItem()) return;
        delete layout->takeAt(index); layout->insertSpacing(index, spacing);
    }
}
void ObjectBridge::insertWidget(int index, QJSValue value)
{
    if (auto layout = qobject_cast<QBoxLayout *>(object_))
        if (auto w = qobject_cast<QWidget *>(ScriptBridge::unwrap(value))) layout->insertWidget(index, w);
}
void ObjectBridge::insertSpacing(int index, int size)
{ if (auto layout = qobject_cast<QBoxLayout *>(object_)) layout->insertSpacing(index, size); }
QList<int> ObjectBridge::sizes() const
{ if (auto splitter = qobject_cast<QSplitter *>(object_)) return splitter->sizes(); return {}; }
void ObjectBridge::setSizes(QList<int> sizes)
{ if (auto splitter = qobject_cast<QSplitter *>(object_)) splitter->setSizes(sizes); }
QVariantMap ObjectBridge::position() const
{ auto p = widget() ? widget()->pos() : QPoint(); return {{"x", p.x()}, {"y", p.y()}}; }
void ObjectBridge::showContextMenu(QVariantMap position)
{
    if (!object_) return;
    const QPoint point(position.value("x").toInt(), position.value("y").toInt());
    if (object_->metaObject()->indexOfMethod("showContextMenu(QPoint)") >= 0)
        QMetaObject::invokeMethod(object_, "showContextMenu", Q_ARG(QPoint, point));
    else // The independent skin probe provides a recording fixture.
        QMetaObject::invokeMethod(object_, "showContextMenu", Q_ARG(QVariantMap, position));
}
QString ObjectBridge::signalName(QString signature) const
{
    if (!object_) return {};
    const auto normalized = QMetaObject::normalizedSignature(signature.toUtf8());
    const auto meta = object_->metaObject();
    if (!signature.contains('(')) {
        for (int i = 0; i < meta->methodCount(); ++i) {
            const auto m = meta->method(i);
            if (m.methodType() == QMetaMethod::Signal && m.name() == signature.toLatin1())
                return signature;
        }
        return {};
    }
    const int index = meta->indexOfSignal(normalized);
    if (index < 0) return {};
    return QString::fromLatin1(meta->method(index).name());
}
