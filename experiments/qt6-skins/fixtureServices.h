// SPDX-License-Identifier: GPL-3.0-only
// These services deliberately generate no audio and never use the user's profile.
#pragma once
#include "playbackEngineInterface.h"
#include "plugin.h"
#include "waveformBuilderInterface.h"
#include "tagReaderInterface.h"

class FixtureTags : public NTagReaderInterface
{
public:
    explicit FixtureTags(QObject *parent) : NTagReaderInterface(parent) {}
    void setSource(const QString &) override {}
    QString getTag(QChar key) const override { return key == 'D' ? "199" : QString(); }
};

class FixturePlayback : public NPlaybackEngineInterface, public NPlugin
{
    Q_OBJECT
public:
    QString interfaceString() const override { return PLAYBACK_INTERFACE; }
    void init() override {}
    Q_INVOKABLE bool hasMedia() const override { return !file_.isEmpty(); }
    Q_INVOKABLE QString currentMedia() const override { return file_; }
    Q_INVOKABLE N::PlaybackState state() const override { return state_; }
    Q_INVOKABLE qreal volume() const override { return volume_; }
    Q_INVOKABLE qreal position() const override { return position_; }
    Q_INVOKABLE qint64 durationMsec() const override { return 199000; }
    Q_INVOKABLE void setMedia(const QString &file, int context) override { file_ = file; emit mediaChanged(file, context); }
    Q_INVOKABLE void setVolume(qreal value) override { volume_ = value; emit volumeChanged(value); }
    Q_INVOKABLE void setPosition(qreal value) override { position_ = value; emit positionChanged(value); }
    Q_INVOKABLE void play() override { state_ = N::PlaybackPlaying; emit stateChanged(state_); }
    Q_INVOKABLE void pause() override { state_ = N::PlaybackPaused; emit stateChanged(state_); }
    Q_INVOKABLE void stop() override { state_ = N::PlaybackStopped; emit stateChanged(state_); }
signals:
    void positionChanged(qreal) override;
    void volumeChanged(qreal) override;
    void message(N::MessageIcon, const QString &, const QString &) override;
    void mediaChanged(const QString &, int) override;
    void nextMediaRequested() override;
    void mediaFinished(const QString &, int) override;
    void mediaFailed(const QString &, int) override;
    void stateChanged(N::PlaybackState) override;
    void tick(qint64) override;
private:
    QString file_;
    N::PlaybackState state_ = N::PlaybackStopped;
    qreal volume_ = .93, position_ = .25;
};

class FixtureWaveform : public NWaveformBuilderInterface, public NPlugin
{
public:
    FixtureWaveform();
    QString interfaceString() const override { return WAVEFORM_INTERFACE; }
    void init() override {}
    void start(const QString &) override {}
    void stop() override {}
    void positionAndIndex(float &position, int &index) override { position = 1; index = peaks_.size(); }
    const NWaveformPeaks &peaks() const override { return peaks_; }
private:
    NWaveformPeaks peaks_;
};
