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
#include "winIcon.h"

#include <QDir>
#include <QPixmap>
#include <QVector>
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
#include <QImage>
#else
#include <QtWin>
#endif

#include <qt_windows.h>
#include <shellapi.h>

QList<QIcon> NWinIcon::getIcons(const QString &dllPath)
{
    QList<QIcon> icons;

    if (!QFileInfo::exists(dllPath)) {
        return icons;
    }

    const QString nativePath = QDir::toNativeSeparators(dllPath);
    const wchar_t *path = reinterpret_cast<const wchar_t *>(nativePath.utf16());
    const UINT count = ExtractIconExW(path, -1, 0, 0, 0);
    if (count == 0 || count == UINT(-1)) {
        return icons;
    }

    QVector<HICON> large(count);
    QVector<HICON> small(count);

    ExtractIconExW(path, 0, large.data(), small.data(), count);

    for (int i = 0; i < count; ++i) {
        QIcon icon;
        HICON hIcon;

        hIcon = small[i];
        if (hIcon) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
            icon.addPixmap(QPixmap::fromImage(QImage::fromHICON(hIcon)));
#else
            icon.addPixmap(QtWin::fromHICON(hIcon));
#endif
            DestroyIcon(hIcon);
        }

        hIcon = large[i];
        if (hIcon) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
            icon.addPixmap(QPixmap::fromImage(QImage::fromHICON(hIcon)));
#else
            icon.addPixmap(QtWin::fromHICON(hIcon));
#endif
            DestroyIcon(hIcon);
        }

        icons.append(icon);
    }

    return icons;
}
