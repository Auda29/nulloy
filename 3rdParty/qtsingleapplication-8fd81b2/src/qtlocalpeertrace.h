// SPDX-License-Identifier: GPL-3.0-only
// Opt-in diagnostic used by the disposable packaged-startup acceptance runs.
#ifndef QTLOCALPEERTRACE_H
#define QTLOCALPEERTRACE_H

#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMutex>
#include <QMutexLocker>

inline void startupTrace(const char *event, QJsonObject fields = {})
{
    const QString directory = qEnvironmentVariable("NULLOY_STARTUP_TRACE_DIR");
    if (directory.isEmpty())
        return;
    static QMutex mutex;
    QMutexLocker lock(&mutex);
    fields.insert("event", QString::fromLatin1(event));
    fields.insert("time_msec", double(QDateTime::currentMSecsSinceEpoch()));
    fields.insert("pid", double(QCoreApplication::applicationPid()));
    fields.insert("executable", QCoreApplication::applicationFilePath());
    QFile file(QDir(directory).filePath(QString::number(QCoreApplication::applicationPid()) + ".jsonl"));
    if (file.open(QIODevice::WriteOnly | QIODevice::Append))
        file.write(QJsonDocument(fields).toJson(QJsonDocument::Compact) + '\n');
}

#endif
