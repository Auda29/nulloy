// SPDX-License-Identifier: GPL-3.0-only
// Test-only platform boundary: no global desktop hotkeys in the offscreen harness.
// The player, IPC transport, playlist and playback plugin are not substituted.
#include "qxtglobalshortcut_p.h"
bool QxtGlobalShortcutPrivate::nativeEventFilter(const QByteArray &, void *, QxtNativeEventResult *)
{ return false; }
quint32 QxtGlobalShortcutPrivate::nativeKeycode(Qt::Key key) { return quint32(key); }
quint32 QxtGlobalShortcutPrivate::nativeModifiers(Qt::KeyboardModifiers mods) { return quint32(mods); }
bool QxtGlobalShortcutPrivate::registerShortcut(quint32, quint32) { return true; }
bool QxtGlobalShortcutPrivate::unregisterShortcut(quint32, quint32) { return true; }
