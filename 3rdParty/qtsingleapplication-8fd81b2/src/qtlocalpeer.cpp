#include <QRegularExpression>
/****************************************************************************
**
** Copyright (C) 2013 Digia Plc and/or its subsidiary(-ies).
** Contact: http://www.qt-project.org/legal
**
** This file is part of the Qt Solutions component.
**
** $QT_BEGIN_LICENSE:BSD$
** You may use this file under the terms of the BSD license as follows:
**
** "Redistribution and use in source and binary forms, with or without
** modification, are permitted provided that the following conditions are
** met:
**   * Redistributions of source code must retain the above copyright
**     notice, this list of conditions and the following disclaimer.
**   * Redistributions in binary form must reproduce the above copyright
**     notice, this list of conditions and the following disclaimer in
**     the documentation and/or other materials provided with the
**     distribution.
**   * Neither the name of Digia Plc and its Subsidiary(-ies) nor the names
**     of its contributors may be used to endorse or promote products derived
**     from this software without specific prior written permission.
**
**
** THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
** "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
** LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
** A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
** OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
** SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
** LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
** DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
** THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
** (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
** OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
**
** $QT_END_LICENSE$
**
****************************************************************************/


#include "qtlocalpeer.h"
#include "qtlocalpeertrace.h"
#include <QCoreApplication>
#include <QTime>
#include <QDataStream>

#if defined(Q_OS_WIN)
#include <QLibrary>
#include <qt_windows.h>
typedef BOOL(WINAPI*PProcessIdToSessionId)(DWORD,DWORD*);
static PProcessIdToSessionId pProcessIdToSessionId = 0;
#endif
#if defined(Q_OS_UNIX)
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#endif

namespace QtLP_Private {
#include "qtlockedfile.cpp"
#if defined(Q_OS_WIN)
#include "qtlockedfile_win.cpp"
#else
#include "qtlockedfile_unix.cpp"
#endif
}

const char* QtLocalPeer::ack = "ack";

QtLocalPeer::QtLocalPeer(QObject* parent, const QString &appId)
    : QObject(parent), id(appId)
{
    QString prefix = id;
    if (id.isEmpty()) {
        id = QCoreApplication::applicationFilePath();
#if defined(Q_OS_WIN)
        // A short 8.3 launch path and Explorer's long path identify the same
        // executable. Keep distinct installed/portable copies independent.
        const QString canonical = QFileInfo(id).canonicalFilePath();
        if (!canonical.isEmpty())
            id = canonical;
        // QFileInfo resolves links but preserves Windows 8.3 spelling.
        const QString native = QDir::toNativeSeparators(id);
        const DWORD length = GetLongPathNameW(reinterpret_cast<LPCWSTR>(native.utf16()), nullptr, 0);
        if (length) {
            QVector<wchar_t> buffer(length);
            const DWORD written = GetLongPathNameW(
                reinterpret_cast<LPCWSTR>(native.utf16()), buffer.data(), length);
            if (written && written < length)
                id = QDir::fromNativeSeparators(QString::fromWCharArray(buffer.constData(), written));
        }
        id = id.toLower();
#endif
        prefix = id.section(QLatin1Char('/'), -1);
    }
    prefix.remove(QRegularExpression("[^a-zA-Z]"));
    prefix.truncate(6);

    QByteArray idc = id.toUtf8();
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    quint16 idNum = qChecksum(idc);
#else
    quint16 idNum = qChecksum(idc.constData(), idc.size());
#endif
    socketName = QLatin1String("qtsingleapp-") + prefix
                 + QLatin1Char('-') + QString::number(idNum, 16);

#if defined(Q_OS_WIN)
    if (!pProcessIdToSessionId) {
        QLibrary lib("kernel32");
        pProcessIdToSessionId = (PProcessIdToSessionId)lib.resolve("ProcessIdToSessionId");
    }
    if (pProcessIdToSessionId) {
        DWORD sessionId = 0;
        pProcessIdToSessionId(GetCurrentProcessId(), &sessionId);
        socketName += QLatin1Char('-') + QString::number(sessionId, 16);
    }
#else
    socketName += QLatin1Char('-') + QString::number(::getuid(), 16);
#endif

    server = new QLocalServer(this);
    QString lockName = QDir(QDir::tempPath()).absolutePath()
                       + QLatin1Char('/') + socketName
                       + QLatin1String("-lockfile");
    lockFile.setFileName(lockName);
    lockFile.open(QIODevice::ReadWrite);
    startupTrace("peer-created", {{"id", id}, {"socket", socketName},
                                 {"lock", lockName}, {"lock_open", lockFile.isOpen()}});
}



bool QtLocalPeer::isClient()
{
    if (lockFile.isLocked())
        return false;

    if (!lockFile.lock(QtLP_Private::QtLockedFile::WriteLock, false)) {
        startupTrace("peer-client", {{"socket", socketName}});
        return true;
    }

    // On Windows listen() can accept a pipe and emit newConnection before it
    // returns. Subscribe first, and defer delivery until the caller has wired
    // its application receiver; otherwise that initial notification is lost.
    QObject::connect(server, SIGNAL(newConnection()), this, SLOT(receiveConnection()),
                     Qt::QueuedConnection);
    bool res = server->listen(socketName);
#if defined(Q_OS_UNIX) && (QT_VERSION >= QT_VERSION_CHECK(4,5,0))
    // ### Workaround
    if (!res && server->serverError() == QAbstractSocket::AddressInUseError) {
        QFile::remove(QDir::cleanPath(QDir::tempPath())+QLatin1Char('/')+socketName);
        res = server->listen(socketName);
    }
#endif
    if (!res)
        qWarning("QtSingleCoreApplication: listen on local socket failed, %s", qPrintable(server->errorString()));
    startupTrace("peer-primary", {{"socket", socketName}, {"listening", res},
                                 {"pending", server->hasPendingConnections()},
                                 {"error", server->errorString()}});
    return false;
}


bool QtLocalPeer::sendMessage(const QString &message, int timeout)
{
    startupTrace("send-begin", {{"message", message}, {"timeout", timeout}, {"socket", socketName}});
    if (!isClient())
        return false;

    QLocalSocket socket;
    bool connOk = false;
    for(int i = 0; i < 2; i++) {
        // Try twice, in case the other instance is just starting up
        socket.connectToServer(socketName);
        connOk = socket.waitForConnected(timeout/2);
        if (connOk || i)
            break;
        int ms = 250;
#if defined(Q_OS_WIN)
        Sleep(DWORD(ms));
#else
        struct timespec ts = { ms / 1000, (ms % 1000) * 1000 * 1000 };
        nanosleep(&ts, NULL);
#endif
    }
    startupTrace("send-connected", {{"connected", connOk}, {"error", socket.errorString()}});
    if (!connOk)
        return false;

    QByteArray uMsg(message.toUtf8());
    QDataStream ds(&socket);
    ds.writeBytes(uMsg.constData(), uMsg.size());
    bool res = socket.waitForBytesWritten(timeout);
    if (res) {
        res &= socket.waitForReadyRead(timeout);   // wait for ack
        if (res)
            res &= (socket.read(qstrlen(ack)) == ack);
    }
    startupTrace("send-end", {{"acknowledged", res}, {"error", socket.errorString()}});
    return res;
}


void QtLocalPeer::receiveConnection()
{
    QLocalSocket* socket = server->nextPendingConnection();
    if (!socket)
        return;
    startupTrace("receive-connection", {{"available", double(socket->bytesAvailable())}});

    while (socket->bytesAvailable() < (int)sizeof(quint32)) {
        if (!socket->waitForReadyRead(2000)) {
            qWarning("QtLocalPeer: Incomplete message header: %s", qPrintable(socket->errorString()));
            delete socket;
            return;
        }
    }
    QDataStream ds(socket);
    QByteArray uMsg;
    quint32 remaining;
    ds >> remaining;
    uMsg.resize(remaining);
    int got = 0;
    char* uMsgBuf = uMsg.data();
    do {
        got = ds.readRawData(uMsgBuf, remaining);
        remaining -= got;
        uMsgBuf += got;
    } while (remaining && got >= 0 && socket->waitForReadyRead(2000));
    if (got < 0) {
        qWarning("QtLocalPeer: Message reception failed %s", socket->errorString().toLatin1().constData());
        delete socket;
        return;
    }
    QString message(QString::fromUtf8(uMsg));
    startupTrace("receive-frame", {{"message", message}, {"remaining", double(remaining)}});
    socket->write(ack, qstrlen(ack));
    socket->waitForBytesWritten(1000);
    socket->waitForDisconnected(1000); // make sure client reads ack
    delete socket;
    startupTrace("receive-dispatch", {{"message", message}});
    emit messageReceived(message); //### (might take a long time to return)
}
