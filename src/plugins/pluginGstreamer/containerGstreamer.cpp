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

#include "containerGstreamer.h"
#include <QCoreApplication>
#include <QDir>
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

#include "common.h"
#include "playbackEngineGstreamer.h"
#include "waveformBuilderGstreamer.h"
#ifdef _N_GSTREAMER_TAGREADER_PLUGIN_
#include "tagReaderGstreamer.h"
#endif

NContainerGstreamer::NContainerGstreamer(QObject *parent) : QObject(parent)
{
    // The CMake test package keeps the GStreamer modules beside the application.
    // Resolve from the executable so extraction paths and working directories do not matter.
    const QString appDir = QCoreApplication::applicationDirPath();
    const QString bundledPlugins = appDir + "/gstreamer-1.0";
    const auto setPath = [](const char *name, const QString &path) {
#ifdef Q_OS_WIN
        // GLib reads the Unicode Windows environment. Passing UTF-8 through
        // the ANSI CRT environment corrupts extraction paths containing umlauts.
        const QString key = QString::fromLatin1(name);
        SetEnvironmentVariableW(reinterpret_cast<LPCWSTR>(key.utf16()),
                                reinterpret_cast<LPCWSTR>(path.utf16()));
#else
        qputenv(name, path.toUtf8());
#endif
    };
    if (QDir(bundledPlugins).exists()) {
        setPath("GST_PLUGIN_SYSTEM_PATH_1_0", bundledPlugins);
        setPath("GST_PLUGIN_SCANNER_1_0", appDir + "/gst-plugin-scanner.exe");
    }
    setPath("GST_REGISTRY", QString("%1/gstreamer-1.0.registry.bin").arg(NCore::rcDir()));

    m_plugins << new NPlaybackEngineGStreamer()
#ifdef _N_GSTREAMER_TAGREADER_PLUGIN_
              << new NTagReaderGstreamer()
#endif
              << new NWaveformBuilderGstreamer();
}

NContainerGstreamer::~NContainerGstreamer()
{
    foreach (NPlugin *plugin, m_plugins)
        delete plugin;
}

QList<NPlugin *> NContainerGstreamer::plugins() const
{
    return m_plugins;
}
