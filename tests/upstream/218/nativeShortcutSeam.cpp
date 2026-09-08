#include "qxtglobalshortcut_p.h"

// Native registration is deliberately not emulated. These tests exercise local
// NAction/QAction keyboard routing only; accidentally using global hooks fails.
quint32 QxtGlobalShortcutPrivate::nativeKeycode(Qt::Key)
{
    qFatal("Global shortcut hooks are outside the local keyboard harness");
}
quint32 QxtGlobalShortcutPrivate::nativeModifiers(Qt::KeyboardModifiers)
{
    qFatal("Global shortcut hooks are outside the local keyboard harness");
}
bool QxtGlobalShortcutPrivate::registerShortcut(quint32, quint32)
{
    qFatal("Global shortcut hooks are outside the local keyboard harness");
}
bool QxtGlobalShortcutPrivate::unregisterShortcut(quint32, quint32)
{
    qFatal("Global shortcut hooks are outside the local keyboard harness");
}
#ifndef Q_OS_MAC
bool QxtGlobalShortcutPrivate::nativeEventFilter(const QByteArray &, void *, QxtNativeEventResult *)
{
    qFatal("Global shortcut hooks are outside the local keyboard harness");
}
#endif
