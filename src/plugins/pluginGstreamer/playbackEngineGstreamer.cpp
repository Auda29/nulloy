/********************************************************************
**  Nulloy Music Player, http://nulloy.com
**  Copyright (C) 2010-2024 Sergey Vlasov <sergey@vlasov.me>
**
**  This program can be distributed under the terms of the GNU
**  General Public License version 3.0 as published by the Free
**  Software Foundation and appearing in the file LICENSE.GPL3
**  included in the packaging of this file.  Please review the
**  following information to ensure the GNU General Public License
**  version 3.0 requirements will be met:
**
**  http://www.gnu.org/licenses/gpl-3.0.html
**
*********************************************************************/

#include "playbackEngineGstreamer.h"

#include <QTimer>
#include <QtGlobal>
#include <gst/pbutils/missing-plugins.h>

#include "common.h"

#define NSEC_IN_MSEC 1000000
#define SHORT_TICK_THRESHOLD_MSEC 30000    // 30 seconds
#define SHORT_TICK_MSEC 20
#define LONG_TICK_MSEC 100
#define STATE_CHANGE_DEBOUNCE_MSEC 50
#define GST_BUS_POP_MSEC 50

static void _on_about_to_finish(GstElement *, gpointer userData)
{
    NPlaybackEngineGStreamer *obj = reinterpret_cast<NPlaybackEngineGStreamer *>(userData);
    obj->_handleAboutToFinish();
}

void NPlaybackEngineGStreamer::_handleAboutToFinish()
{
    // Adapted from nulloy/nulloy#263. This callback runs on a streaming thread;
    // it must never wait for the GUI, which may itself be seeking in GStreamer.
    QMutexLocker locker(&m_nextMediaMutex);
    if (!m_acceptNextMedia || m_nextMediaUri.isEmpty() || !m_pendingMedia.isEmpty()) {
        return;
    }
    m_pendingMedia = m_nextMediaFile;
    m_pendingContext = m_nextMediaContext;
    g_object_set(m_playbin, "uri", m_nextMediaUri.constData(), NULL);
    m_nextMediaFile.clear();
    m_nextMediaUri.clear();
}

void NPlaybackEngineGStreamer::resetPipeline()
{
    {
        QMutexLocker locker(&m_nextMediaMutex);
        m_acceptNextMedia = false;
        m_nextMediaFile.clear();
        m_nextMediaUri.clear();
    }
    // Never hold the cache mutex while waiting for streaming threads to stop.
    // Any callback already setting the URI has finished before this reset.
    gst_element_set_state(m_playbin, GST_STATE_NULL);
    {
        QMutexLocker locker(&m_nextMediaMutex);
        m_pendingMedia.clear();
        m_pendingContext = 0;
    }
    m_initialStreamStart = true;
    m_suppressStreamStart = false;
    m_positionPostponed = false;
    m_durationNsec = GST_CLOCK_TIME_NONE;
}

void NPlaybackEngineGStreamer::restartCurrentMedia()
{
    // A URI already handed to playbin cannot be revoked by clearing our cache.
    // Reload the visible track and restore its position before allowing another
    // handoff. This is only needed when an in-flight transition is cancelled.
    const qreal position = m_position;
    // GStreamer may temporarily report PAUSED while processing a flushing seek.
    // Restore the user's requested state, not that transient pipeline state.
    const GstState state = m_requestedState;
    resetPipeline();
    if (!gstSetFile(m_currentMedia, m_currentContext)) {
        return;
    }
    m_suppressStreamStart = true;
    m_initialStreamStart = false;
    m_position = position;
    m_positionPostponed = true;
    gst_element_set_state(m_playbin, state);
}

N::PlaybackState NPlaybackEngineGStreamer::fromGstState(GstState state) const
{
    switch (state) {
        case GST_STATE_PAUSED:
            return N::PlaybackPaused;
        case GST_STATE_PLAYING:
            return N::PlaybackPlaying;
        default:
            return N::PlaybackStopped;
    }
}

void NPlaybackEngineGStreamer::init()
{
    if (m_init) {
        return;
    }

    int argc;
    const char **argv;
    GError *err = NULL;
    NCore::cArgs(&argc, &argv);
    gst_init(&argc, (char ***)&argv);
    if (!gst_init_check(&argc, (char ***)&argv, &err)) {
        emit message(N::Critical, tr("Playback error"),
                     err ? QString::fromUtf8(err->message) : tr("Unknown error"));
        if (err) {
            g_error_free(err);
        }
    }
    m_playbin = gst_element_factory_make("playbin", NULL);
    g_signal_connect(m_playbin, "about-to-finish", G_CALLBACK(_on_about_to_finish), this);
    gst_element_add_property_notify_watch(m_playbin, "volume", TRUE);

    // FIXME: https://gitlab.freedesktop.org/gstreamer/gst-plugins-bad/-/issues/1798
    //m_pitchElement = gst_element_factory_make("pitch", NULL);
    m_pitchElement = NULL;
    if (!m_pitchElement) {
        //emit message(N::Critical, "Playback Engine", "Failed to create pitch element");
    } else {
        GstElement *sink = gst_element_factory_make("autoaudiosink", NULL);
        GstElement *bin = gst_bin_new(NULL);
        gst_bin_add_many(GST_BIN(bin), m_pitchElement, sink, NULL);
        gst_element_link_many(m_pitchElement, sink, NULL);

        GstPad *pad = gst_element_get_static_pad(m_pitchElement, "sink");
        gst_element_add_pad(bin, gst_ghost_pad_new("sink", pad));
        gst_object_unref(pad);

        g_object_set(m_playbin, "audio-sink", bin, NULL);
    }

#ifdef _TESTS_
    GstElement *sink = gst_element_factory_make("fakesink", NULL);
    g_object_set(sink, "sync", TRUE, NULL);
    g_object_set(m_playbin, "audio-sink", sink, NULL);

    sink = gst_element_factory_make("fakesink", NULL);
    g_object_set(sink, "sync", TRUE, NULL);
    g_object_set(m_playbin, "video-sink", sink, NULL);
#endif

    m_speed = 1.0;
    m_speedPostponed = false;
    m_pitch = 1.0;
    m_volume = -1.0;
    m_position = 0.0;
    m_gstState = GST_STATE_NULL;
    m_positionPostponed = false;
    m_currentMedia = "";
    m_currentContext = 0;
    m_durationNsec = GST_CLOCK_TIME_NONE;

    m_checkStatusTimer = new QTimer(this);
    connect(m_checkStatusTimer, SIGNAL(timeout()), this, SLOT(checkStatus()));

    m_emitStateTimer = new QTimer(this);
    m_emitStateTimer->setSingleShot(true);
    m_emitStateTimer->setInterval(STATE_CHANGE_DEBOUNCE_MSEC);
    connect(m_emitStateTimer, &QTimer::timeout,
            [this]() { emit stateChanged(fromGstState(m_gstState)); });

    m_gstBusPopTimer = new QTimer(this);
    m_gstBusPopTimer->setInterval(GST_BUS_POP_MSEC);
    connect(m_gstBusPopTimer, &QTimer::timeout, [this]() {
        GstBus *bus = gst_pipeline_get_bus(GST_PIPELINE(m_playbin));
        GstMessage *msg;
        while ((msg = gst_bus_pop(bus)) != NULL) {
            processGstMessage(msg);
            gst_message_unref(msg);
        }
        gst_object_unref(bus);
    });

    m_init = true;
}

NPlaybackEngineGStreamer::~NPlaybackEngineGStreamer()
{
    if (!m_init) {
        return;
    }

    stop();
    gst_object_unref(m_playbin);
}

bool NPlaybackEngineGStreamer::gstSetFile(const QString &file, int context)
{
    if (file.isEmpty()) {
        stop();
        m_currentMedia = "";
        m_currentContext = 0;
        emit mediaChanged(m_currentMedia, m_currentContext);
        return false;
    }

    if (!QFile(file).exists()) {
        emit message(N::Warning, file, tr("No such file or directory"));
        fail();
        return false;
    }

    GError *err = NULL;
    gchar *uri = g_filename_to_uri(QFileInfo(file).absoluteFilePath().toUtf8().constData(), NULL,
                                   &err);
    if (uri) {
        m_currentMedia = file;
        m_currentContext = context;
        g_object_set(m_playbin, "uri", uri, NULL);
        g_free(uri);
    } else {
        emit message(N::Critical, file, err ? QString::fromUtf8(err->message) : tr("Invalid path"));
        if (err) {
            g_error_free(err);
        }
        fail();
        return false;
    }
    return true;
}

void NPlaybackEngineGStreamer::setMedia(const QString &file, int context)
{
    resetPipeline();
    m_position = 0.0;

    if (!gstSetFile(file, context)) {
        return;
    }
}

void NPlaybackEngineGStreamer::nextMediaRespond(const QString &file, int context)
{
    if (m_initialStreamStart) {
        return;
    }
    // Resolve paths on the GUI thread, before publishing the next track.
    QByteArray uri;
    if (!file.isEmpty() && QFileInfo(file).isFile()) {
        gchar *value = g_filename_to_uri(QFileInfo(file).absoluteFilePath().toUtf8().constData(),
                                        NULL, NULL);
        if (value) {
            uri = value;
            g_free(value);
        }
    }
    bool cancelPending;
    {
        QMutexLocker locker(&m_nextMediaMutex);
        cancelPending = !m_pendingMedia.isEmpty() &&
                        (m_pendingMedia != file || m_pendingContext != context);
        if (cancelPending) {
            m_acceptNextMedia = false;
        } else {
            m_nextMediaFile = file;
            m_nextMediaUri = uri;
            m_nextMediaContext = context;
            return;
        }
    }
    if (cancelPending) {
        restartCurrentMedia();
    }
    {
        QMutexLocker locker(&m_nextMediaMutex);
        m_nextMediaFile = file;
        m_nextMediaUri = uri;
        m_nextMediaContext = context;
    }
}

qreal NPlaybackEngineGStreamer::speed() const
{
    return m_speed;
}

void NPlaybackEngineGStreamer::setSpeed(qreal speed)
{
    m_speed = speed;
    m_speedPostponed = true;
}

qreal NPlaybackEngineGStreamer::pitch() const
{
    return m_pitch;
}

void NPlaybackEngineGStreamer::setPitch(qreal pitch)
{
    if (!m_pitchElement) {
        return;
    }
    m_pitch = pitch;
    g_object_set(m_pitchElement, "pitch", m_pitch, NULL);
}

void NPlaybackEngineGStreamer::setVolume(qreal volume)
{
    m_volume = qBound(0.0, volume, 1.0);
    g_object_set(m_playbin, "volume", m_volume, NULL);
}

qreal NPlaybackEngineGStreamer::volume() const
{
    return m_volume;
}

void NPlaybackEngineGStreamer::setPosition(qreal pos)
{
    if (!hasMedia() || pos < 0.0 || pos > 1.0) {
        return;
    }

    bool pending;
    {
        QMutexLocker locker(&m_nextMediaMutex);
        m_acceptNextMedia = false;
        pending = !m_pendingMedia.isEmpty();
    }
    if (pending) {
        restartCurrentMedia();
    }
    m_position = pos;
    m_positionPostponed = true;
}

void NPlaybackEngineGStreamer::jump(qint64 msec)
{
    if (!hasMedia()) {
        return;
    }

    if (!GST_CLOCK_TIME_IS_VALID(m_durationNsec) || m_durationNsec <= 0) {
        return;
    }
    setPosition(qBound(0.0, m_position + ((qreal)msec * NSEC_IN_MSEC) / m_durationNsec, 1.0));
}

qreal NPlaybackEngineGStreamer::position() const
{
    return m_position;
}

qint64 NPlaybackEngineGStreamer::durationMsec() const
{
    return m_durationNsec / NSEC_IN_MSEC;
}

void NPlaybackEngineGStreamer::play()
{
    if (!hasMedia()) {
        return;
    }

    m_requestedState = GST_STATE_PLAYING;
    m_gstBusPopTimer->start();
    m_checkStatusTimer->start(LONG_TICK_MSEC);
    {
        QMutexLocker locker(&m_nextMediaMutex);
        m_acceptNextMedia = !m_positionPostponed;
    }
    gst_element_set_state(m_playbin, GST_STATE_PLAYING);
}

void NPlaybackEngineGStreamer::pause()
{
    if (!hasMedia()) {
        return;
    }

    m_requestedState = GST_STATE_PAUSED;
    gst_element_set_state(m_playbin, GST_STATE_PAUSED);

    m_checkStatusTimer->stop();
    m_gstBusPopTimer->stop();

    m_gstState = GST_STATE_PAUSED;
    emit stateChanged(fromGstState(m_gstState));

    checkStatus();
}

void NPlaybackEngineGStreamer::stop()
{
    m_requestedState = GST_STATE_NULL;
    resetPipeline();
    m_emitStateTimer->stop();
    m_durationNsec = 0;
    m_position = 0.0;

    m_gstState = GST_STATE_NULL;
    emit stateChanged(N::PlaybackStopped);
    emit positionChanged(m_position);

    m_checkStatusTimer->stop();
    m_gstBusPopTimer->stop();
}

bool NPlaybackEngineGStreamer::hasMedia() const
{
    return !m_currentMedia.isEmpty();
}

QString NPlaybackEngineGStreamer::currentMedia() const
{
    return m_currentMedia;
}

N::PlaybackState NPlaybackEngineGStreamer::state() const
{
    return fromGstState(m_gstState);
}

void NPlaybackEngineGStreamer::processGstMessage(GstMessage *msg)
{
    //qDebug() << "message type:" << GST_MESSAGE_TYPE_NAME(msg);
    switch (GST_MESSAGE_TYPE(msg)) {
        case GST_MESSAGE_EOS: {
            stop();
            emit mediaFinished(m_currentMedia, m_currentContext);
            break;
        }
        case GST_MESSAGE_ERROR: {
            gchar *debug;
            GError *err = NULL;
            gst_message_parse_error(msg, &err, &debug);
            g_free(debug);

            emit message(N::Critical, QFileInfo(m_currentMedia).absoluteFilePath(),
                         err ? QString::fromUtf8(err->message) : tr("Unknown error"));
            fail();
            if (err) {
                g_error_free(err);
            }
            break;
        }
        case GST_MESSAGE_ELEMENT: {
            if (gst_is_missing_plugin_message(msg)) {
                QString str = tr("Missing GStreamer plugin:<br/>");
                gchar *detail = gst_missing_plugin_message_get_installer_detail(msg);
                if (detail) {
                    QStringList fields = QString::fromUtf8(detail).split('|').mid(3);
                    str += QString::fromUtf8(detail).split('|').mid(3).join("<br/>");
                    g_free(detail);
                } else {
                    str += tr("Unknown plugin");
                }
                emit message(N::Critical, QFileInfo(m_currentMedia).absoluteFilePath(), str);
                fail();
            }
            break;
        }
        case GST_MESSAGE_DURATION_CHANGED: {
            m_durationNsec = GST_CLOCK_TIME_NONE;
            break;
        }
        case GST_MESSAGE_STREAM_START: {
            {
                QMutexLocker locker(&m_nextMediaMutex);
                // A short first track may have queued its successor before the
                // GUI drains the first STREAM_START message.
                if (!m_initialStreamStart && !m_pendingMedia.isEmpty()) {
                    m_currentMedia = m_pendingMedia;
                    m_currentContext = m_pendingContext;
                    m_pendingMedia.clear();
                    m_position = 0.0;
                    // A flushing seek may discard the restart's STREAM_START.
                    // Never suppress the subsequent real track transition.
                    m_suppressStreamStart = false;
                }
                m_initialStreamStart = false;
            }
            if (m_speed != 1.0) {
                m_speedPostponed = true;
            }
            m_durationNsec = GST_CLOCK_TIME_NONE;
            if (m_suppressStreamStart) {
                m_suppressStreamStart = false;
                emit nextMediaRequested();
            } else {
                emit mediaChanged(m_currentMedia, m_currentContext);
            }
            break;
        }
        case GST_MESSAGE_PROPERTY_NOTIFY: {
            const gchar *name;
            const GValue *value;
            gst_message_parse_property_notify(msg, NULL, &name, &value);
            if (QString(name) == "volume") {
                gdouble gstVolume = g_value_get_double(value);
                if (gstVolume != m_volume) {
                    m_volume = gstVolume;
                    emit volumeChanged(m_volume);
                }
            }
            break;
        }
        case GST_MESSAGE_STATE_CHANGED: {
            if (GST_MESSAGE_SRC(msg) == GST_OBJECT(m_playbin)) {
                GstState newState, oldState, pendingState;
                gst_message_parse_state_changed(msg, &oldState, &newState, &pendingState);
                //qDebug() << "state changed old:" << gst_element_state_get_name(oldState)
                //         << " new:" << gst_element_state_get_name(newState)
                //         << " pending:" << gst_element_state_get_name(pendingState);
                if (newState != m_gstState) {
                    m_gstState = newState;
                    m_emitStateTimer->start();
                }
            }
            break;
        }
        default:
            break;
    }
}

void NPlaybackEngineGStreamer::checkStatus()
{
    if (!GST_CLOCK_TIME_IS_VALID(m_durationNsec)) {
        gst_element_query_duration(m_playbin, GST_FORMAT_TIME, &m_durationNsec);
    }

    if (GST_CLOCK_TIME_IS_VALID(m_durationNsec) && m_durationNsec > 0) {
        gint64 gstPos = 0;
        if (gst_element_query_position(m_playbin, GST_FORMAT_TIME, &gstPos)) {
            if (!m_positionPostponed) {
                m_position = (qreal)gstPos / m_durationNsec;
                emit positionChanged(m_position);
            }
            emit tick(gstPos / NSEC_IN_MSEC * m_speed);
        }

        if (m_positionPostponed || m_speedPostponed) {
            if (m_positionPostponed) {
                gstPos = m_position * m_durationNsec;
            }
            {
                QMutexLocker locker(&m_nextMediaMutex);
                // Seeking near EOS can emit about-to-finish before seek returns.
                // Publish readiness first, without holding this lock in seek.
                m_acceptNextMedia = true;
            }
            gst_element_seek(m_playbin, m_speed, GST_FORMAT_TIME,
                             GstSeekFlags(GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT |
                                          GST_SEEK_FLAG_SNAP_NEAREST),
                             GST_SEEK_TYPE_SET, gstPos, GST_SEEK_TYPE_NONE, GST_CLOCK_TIME_NONE);
            m_positionPostponed = false;
            m_speedPostponed = false;
        }

        if (m_durationNsec / NSEC_IN_MSEC <= SHORT_TICK_THRESHOLD_MSEC) {
            m_checkStatusTimer->setInterval(SHORT_TICK_MSEC);
        }
    }
}

void NPlaybackEngineGStreamer::fail()
{
    stop();

    emit mediaFailed(m_currentMedia, m_currentContext);

    m_currentMedia = "";
    m_currentContext = 0;
}
