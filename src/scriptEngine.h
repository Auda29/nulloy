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

#ifndef N_SCRIPT_ENGINE_H
#define N_SCRIPT_ENGINE_H

#include <QtGlobal>
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
#include <QJSEngine>
#include "qt6/scriptBridge.h"
#else
#include <QScriptEngine>
#endif

class NPlayer;

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
class NScriptEngine : public QJSEngine
#else
class NScriptEngine : public QScriptEngine
#endif
{
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    ScriptBridge m_bridge;
#endif
public:
    NScriptEngine(NPlayer *player);
    virtual ~NScriptEngine(){};
};

#endif
