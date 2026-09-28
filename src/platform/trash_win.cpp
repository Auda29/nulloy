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

#include "trash.h"

#include <QFile>
#include <QFileInfo>
#include <QObject>

NTrash::NativeResult _trash(const QString &file, QString *error)
{
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    // On supported Windows versions Qt uses IFileOperation with
    // FOFX_RECYCLEONDELETE and a progress sink that refuses permanent deletion.
    // SHFileOperation silently deleted files on a volume with NukeOnDelete=1,
    // even with FOF_WANTNUKEWARNING and without FOF_NOCONFIRMATION.
    QFile source(QFileInfo(file).absoluteFilePath());
    if (source.moveToTrash() && !QFileInfo::exists(file)) {
        return {0, false};
    }
    if (error) {
        *error = source.errorString();
    }
#else
    Q_UNUSED(file);
    if (error) {
        *error = QObject::tr("Safe recycling requires Qt 5.15 or newer.");
    }
#endif
    // No shell confirmation UI is opened by Qt. Failure reaches the existing
    // explicit permanent-delete question; the adapter never deletes directly.
    return {1, false};
}
