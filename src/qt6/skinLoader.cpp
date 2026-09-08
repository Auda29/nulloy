// SPDX-License-Identifier: GPL-3.0-only
// Preserves the original skin identifiers, selection and search order.
#include "skinLoader.h"
#include "skinResources.h"
#include "common.h"
#include "settings.h"
#include <QApplication>
#include <QDir>
#include <QFile>
#include <QTemporaryFile>
#include <QPointer>
#include <memory>

namespace {
class SkinSession : public QObject
{
public:
    QStringList identifiers;
    std::unique_ptr<SkinResources> selected;
    QTemporaryFile form, script;
    SkinSession() : QObject(qApp)
    {
        QStringList directories{":/skins", QCoreApplication::applicationDirPath() + "/skins"};
        QStringList paths;
        for (const auto &directory : directories) {
            for (const auto &entry : QDir(directory).entryInfoList(QDir::AllDirs | QDir::Files | QDir::NoDotAndDotDot)) {
                if (!entry.isDir() && entry.suffix() != "nzs") continue;
                SkinResources candidate;
                QString error;
                if (!candidate.load(entry.absoluteFilePath(), &error)) {
                    qWarning() << "Skipping skin" << entry.fileName() << error;
                    continue;
                }
                QString id = QString::fromUtf8(candidate.bytes("id.txt")).section('\n', 0, 0).trimmed();
                if (entry.absoluteFilePath().startsWith(':')) id.insert(id.lastIndexOf('/'), tr(" (Built-in)"));
                identifiers.append(id);
                paths.append(entry.absoluteFilePath());
            }
        }
        if (paths.isEmpty()) qFatal("No skins found");
        int index = identifiers.indexOf("Nulloy/Skin/" + NSettings::instance()->value("Skin").toString());
        if (index < 0) {
            index = 0;
            for (int i = 0; i < identifiers.size(); ++i)
                if (identifiers[i].startsWith("Nulloy/Skin/Slim")) { index = i; break; }
        }
        selected = std::make_unique<SkinResources>();
        QString error;
        if (!selected->load(paths[index], &error)) qFatal("Skin load failed: %s", qPrintable(error));
        auto prepare = [&](QTemporaryFile &file, const QString &name) {
            const auto data = selected->readFile(name).toUtf8();
            if (!file.open() || file.write(data) != data.size() || !file.flush()) qFatal("Cannot prepare skin file");
        };
        prepare(form, "form.ui");
        prepare(script, "script.js");
        NSettings::instance()->setValue("Skin", identifiers[index].section('/', 2));
    }
};
QPointer<SkinSession> instance;
SkinSession *session()
{
    if (!instance) instance = new SkinSession;
    return instance;
}
}
QStringList NSkinLoader::skinIdentifiers() { return session()->identifiers; }
QString NSkinLoader::skinUiFormFile() { return session()->form.fileName(); }
QString NSkinLoader::skinScriptFile() { return session()->script.fileName(); }
SkinResources *NSkinLoader::resources() { return session()->selected.get(); }
void NSkinLoader::releaseResources() { delete instance.data(); }
