// SPDX-License-Identifier: GPL-3.0-only
#include "fixtureServices.h"
#include "pluginLoader.h"
#include "settings.h"
#include <QJSEngine>
#include <QTemporaryDir>
#include <cmath>

FixtureWaveform::FixtureWaveform()
{
    for (int i = 0; i < 100000; ++i) peaks_.append(std::sin(i * .13) * (.2 + .7 * std::abs(std::sin(i * .0005))));
    peaks_.complete();
}
NPlugin *NPluginLoader::getPlugin(N::PluginType type)
{
    static FixturePlayback playback;
    static FixtureWaveform waveform;
    if (type == N::PlaybackEngine) return &playback;
    if (type == N::WaveformBuilder) return &waveform;
    return nullptr;
}
void NPluginLoader::init() {}

static QString fixtureSettingsPath()
{
    static QTemporaryDir directory;
    if (!directory.isValid()) qFatal("Cannot create isolated skin fixture settings");
    return directory.filePath("settings.ini");
}
NSettings *NSettings::m_instance = nullptr;
NSettings::NSettings(QObject *parent) : QSettings(fixtureSettingsPath(), QSettings::IniFormat, parent)
{
    setValue("ShowPlaybackControls", true);
    setValue("FileFilters", "*.mp3 *.flac *.wav *.ogg");
    setValue("PlaylistTrackInfo", "%F");
}
NSettings::~NSettings() {}
NSettings *NSettings::instance()
{
    static NSettings settings;
    return &settings;
}
QVariant NSettings::value(const QString &key, const QVariant &fallback) const
{ return QSettings::value(key, fallback); }
void NSettings::setValue(const QString &key, const QVariant &value)
{
    const QVariant converted = value.metaType() == QMetaType::fromType<QJSValue>() ? value.value<QJSValue>().toVariant() : value;
    QSettings::setValue(key, converted);
    emit valueChanged(key, converted);
}
void NSettings::remove(const QString &key) { QSettings::remove(key); }
