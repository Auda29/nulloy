// SPDX-License-Identifier: GPL-3.0-only
#ifndef N_PLAYBACK_FILE_ACCESS_INTERFACE_H
#define N_PLAYBACK_FILE_ACCESS_INTERFACE_H

#include "global.h"
#include <QObject>

// Optional capability: keep the playback plugin's existing ABI unchanged.
// Suspension closes native readers without changing the visible state/position.
class NPlaybackFileAccessInterface
{
public:
    virtual ~NPlaybackFileAccessInterface() {}
    virtual void suspendFileAccess() = 0;
    virtual void restoreFileAccess(const QString &file, int context, qreal position,
                                   N::PlaybackState state) = 0;
};

Q_DECLARE_INTERFACE(NPlaybackFileAccessInterface, "Nulloy/NPlaybackFileAccessInterface/1.0")

#endif
