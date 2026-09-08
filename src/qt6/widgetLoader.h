// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "coverWidget.h"
#include "label.h"
#include "playlistWidget.h"
#include "volumeSlider.h"
#include "waveformSlider.h"
#include <QSizeGrip>
#include <QUiLoader>

// Uses the existing widget classes and forms without a Qt Designer plugin.
class OriginalWidgetLoader : public QUiLoader
{
protected:
    QWidget *createWidget(const QString &name, QWidget *parent, const QString &objectName) override
    {
        QWidget *widget = nullptr;
        if (name == "NLabel") widget = new NLabel(parent);
        else if (name == "NCoverWidget") widget = new NCoverWidget(parent);
        else if (name == "NPlaylistWidget") widget = new NPlaylistWidget(parent);
        else if (name == "NVolumeSlider") widget = new NVolumeSlider(parent);
        else if (name == "NSlider") widget = new NSlider(parent);
        else if (name == "NWaveformSlider") widget = new NWaveformSlider(parent);
        else if (name == "QSizeGrip") widget = new QSizeGrip(parent);
        else return QUiLoader::createWidget(name, parent, objectName);
        widget->setObjectName(objectName);
        return widget;
    }
};
