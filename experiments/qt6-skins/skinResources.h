// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <QObject>
#include <QTemporaryDir>

// A private, disposable overlay per skin. QDir search paths are public Qt API.
// Never writes into the original directory or archive.
class SkinResources : public QObject
{
    Q_OBJECT
public:
    explicit SkinResources(QObject *parent = nullptr);
    ~SkinResources() override;
    bool load(const QString &source, QString *error);
    QString prefix() const { return prefix_ + ':'; }
    QString resolve(const QString &name) const;
    QString rewriteUrls(const QString &text) const;
    QByteArray bytes(const QString &name) const;
    Q_INVOKABLE QString readFile(QString name) const;
    Q_INVOKABLE bool maskImage(QString name, QString color, double opacity = 1.0);
    Q_INVOKABLE int addApplicationFont(QString name);
private:
    bool extract(const QString &archive, QString *error);
    bool write(const QString &name, const QByteArray &data);
    static bool validName(const QString &name);
    QTemporaryDir temporary_;
    QString prefix_;
    QString directory_;
    QList<int> fonts_;
};
