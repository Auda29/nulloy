// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <QApplication>
#include <QStyleHints>
#include <qt_windows.h>

inline void preserveLegacyWindowsAppearance()
{
    // Qt 5 used DEFAULT_GUI_FONT; Qt 6 switched to the larger message font.
    // Keep the former system-derived font without changing any skin assets.
    LOGFONTW native{};
    if (GetObjectW(GetStockObject(DEFAULT_GUI_FONT), sizeof(native), &native)) {
        QString family = QString::fromWCharArray(native.lfFaceName);
        if (family == "MS Shell Dlg") family = "MS Shell Dlg 2";
        QFont font(family);
        font.setPointSizeF(qAbs(native.lfHeight) * 72.0 / GetDpiForSystem());
        font.setWeight(QFont::Weight(qBound(100, int(native.lfWeight), 900)));
        font.setItalic(native.lfItalic);
        font.setUnderline(native.lfUnderline);
        font.setStrikeOut(native.lfStrikeOut);
        QApplication::setFont(font);
    }
    // Skin CSS supplies the dark themes. Qt 5 used the light platform palette
    // underneath; following Windows dark mode here changes Native and selection text.
    QGuiApplication::styleHints()->setColorScheme(Qt::ColorScheme::Light);
}
