// SPDX-License-Identifier: GPL-3.0-only
#ifndef N_FILE_OPEN_BURST_H
#define N_FILE_OPEN_BURST_H

#include <QElapsedTimer>
#include <QObject>

// Tracks external file messages only. No queued files or deferred playback.
// The IPC protocol has no selection ID: this is a short-burst heuristic, not
// arbitrary shell-transaction detection. Bound both inactivity and total age.
class NFileOpenBurst : public QObject
{
    QElapsedTimer m_started;
    QElapsedTimer m_lastMessage;
    bool m_enqueue = false;
    bool m_playEnqueued = false;
public:
    enum { IdleMsec = 250, MaximumMsec = 1000 };

    explicit NFileOpenBurst(QObject *parent = nullptr) : QObject(parent) {}

    void reset() { m_started.invalidate(); }

    bool isContinuation(bool enqueue, bool playEnqueued)
    {
        const bool continuation = m_started.isValid() &&
                                  m_enqueue == enqueue && m_playEnqueued == playEnqueued &&
                                  m_started.elapsed() < MaximumMsec &&
                                  m_lastMessage.elapsed() < IdleMsec;
        if (!continuation)
            m_started.start();
        m_lastMessage.start();
        m_enqueue = enqueue;
        m_playEnqueued = playEnqueued;
        return continuation;
    }
};

#endif
