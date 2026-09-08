// SPDX-License-Identifier: GPL-3.0-only
#ifndef N_WINDOW_GEOMETRY_H
#define N_WINDOW_GEOMETRY_H

#include <QList>
#include <QRect>

namespace NWindowGeometry
{
    // Rectangles use Qt logical desktop coordinates; the preferred screen is first.
    inline QRect restored(const QRect &stored, const QList<QRect> &availableScreens)
    {
        const QRect titlebar(stored.topLeft(), QSize(stored.width(), qMin(32, stored.height())));
        QRect fallback;
        for (const QRect &screen : availableScreens) {
            if (!screen.isValid())
                continue;
            if (!fallback.isValid())
                fallback = screen;
            const QRect visible = titlebar.intersected(screen);
            // A sliver of the body is not enough to grab the window. Keep intentional
            // partial placement when a usable part of the top edge remains reachable.
            if (visible.width() >= qMin(100, qMin(stored.width(), screen.width())) &&
                visible.height() >= qMin(16, qMin(stored.height(), screen.height())))
                return stored;
        }
        if (!fallback.isValid())
            return stored;
        const QSize size = stored.size().boundedTo(fallback.size());
        return QRect(fallback.topLeft() + QPoint((fallback.width() - size.width()) / 2,
                                                 (fallback.height() - size.height()) / 2),
                     size);
    }
} // namespace NWindowGeometry
#endif
