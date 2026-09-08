// SPDX-License-Identifier: GPL-3.0-only
// Image masking preserves Nulloy scriptEngine.cpp behavior, Copyright (C)
// 2010-2024 Sergey Vlasov <sergey@vlasov.me>; see LICENSE.GPL3.
#include "skinResources.h"
#include <QBuffer>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFontDatabase>
#include <QImage>
#include <QPainter>
#include <QPixmapCache>
#include <QRegularExpression>
#include <QSet>
#include <QUuid>
#include <QtEndian>
#include <QtIOCompressor>
#include <zlib.h>

SkinResources::SkinResources(QObject *parent) : QObject(parent)
{
    prefix_ = "nulloyskin" + QUuid::createUuid().toString(QUuid::Id128);
}
SkinResources::~SkinResources()
{
    QDir::setSearchPaths(prefix_, {});
    for (int id : fonts_) QFontDatabase::removeApplicationFont(id);
}
bool SkinResources::validName(const QString &name)
{
    if (name.isEmpty() || QDir::isAbsolutePath(name) || name.contains(':') ||
        name.contains('\\') || name.contains(QChar(0))) return false;
    for (const auto &part : name.split('/'))
        if (part == ".." || part == "." || part.endsWith(' ') || part.endsWith('.')) return false;
    return true;
}
bool SkinResources::load(const QString &source, QString *error)
{
    if (!directory_.isEmpty()) { *error = "A resource session loads exactly one skin"; return false; }
    if (!temporary_.isValid()) { *error = "Cannot create temporary skin directory"; return false; }
    if (QFileInfo(source).isDir()) directory_ = QFileInfo(source).absoluteFilePath();
    else {
        if (!extract(source, error)) return false;
        directory_ = temporary_.path();
    }
    QDir::setSearchPaths(prefix_, {temporary_.path(), directory_});
    if (bytes("form.ui").isEmpty() || bytes("script.js").isEmpty() || bytes("id.txt").isEmpty()) {
        *error = "Skin requires form.ui, script.js and id.txt"; return false;
    }
    return true;
}
QString SkinResources::resolve(const QString &name) const
{ return validName(name) ? prefix() + name : QString(); }
QByteArray SkinResources::bytes(const QString &name) const
{
    if (!validName(name)) return {};
    QFile file(resolve(name));
    return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray();
}
QString SkinResources::readFile(QString name) const
{ return rewriteUrls(QString::fromUtf8(bytes(name))); }
QString SkinResources::rewriteUrls(const QString &text) const
{
    static const QRegularExpression url(R"RX(url\(\s*(['"]?)([^'"\)]+)\1\s*\))RX");
    QString result;
    qsizetype end = 0;
    auto matches = url.globalMatch(text);
    while (matches.hasNext()) {
        const auto match = matches.next();
        result += text.mid(end, match.capturedStart() - end);
        const auto path = match.captured(2).trimmed();
        if (validName(path)) result += "url(" + match.captured(1) + prefix() + path + match.captured(1) + ')';
        else result += match.captured();
        end = match.capturedEnd();
    }
    return result + text.mid(end);
}
bool SkinResources::write(const QString &name, const QByteArray &data)
{
    if (!validName(name)) return false;
    const auto path = temporary_.filePath(name);
    if (!QDir().mkpath(QFileInfo(path).absolutePath())) return false;
    QFile file(path);
    return file.open(QIODevice::WriteOnly) && file.write(data) == data.size();
}
bool SkinResources::maskImage(QString name, QString color, double opacity)
{
    QImage mask;
    if (!mask.loadFromData(bytes(name)) || !QColor(color).isValid() || opacity < 0 || opacity > 1) return false;
    QImage result(mask.size(), QImage::Format_ARGB32_Premultiplied);
    result.fill(QColor(color));
    {
        QPainter painter(&result);
        painter.setCompositionMode(QPainter::CompositionMode_DestinationIn);
        QColor legacyPixel(color); legacyPixel.setAlpha(243);
        painter.fillRect(0, 0, 1, 1, legacyPixel);
        painter.drawImage(0, 0, mask);
    }
    if (opacity != 1) {
        const QImage copy = result;
        result.fill(Qt::transparent);
        QPainter painter(&result);
        painter.setCompositionMode(QPainter::CompositionMode_Source);
        painter.setOpacity(opacity);
        painter.drawImage(0, 0, copy);
    }
    QByteArray data;
    QBuffer buffer(&data);
    if (!result.save(&buffer, "PNG") || !write(name, data)) return false;
    QPixmapCache::clear();
    return true;
}
int SkinResources::addApplicationFont(QString name)
{
    int id = QFontDatabase::addApplicationFontFromData(bytes(name));
    if (id >= 0) fonts_.append(id);
    return id;
}

bool SkinResources::extract(const QString &archive, QString *error)
{
    // Read the central directory, including archives whose local entries use data
    // descriptors. Classic ZIP stored/deflated is the existing .nzs format.
    auto fail = [&](QString reason) { *error = reason; return false; };
    QFile file(archive);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 64 * 1024 * 1024)
        return fail("Skin archive unreadable or larger than 64 MiB");
    const QByteArray zip = file.readAll();
    const auto u16 = [&](qsizetype p) { return qFromLittleEndian<quint16>(zip.constData() + p); };
    const auto u32 = [&](qsizetype p) { return qFromLittleEndian<quint32>(zip.constData() + p); };
    qsizetype end = -1;
    for (qsizetype p = zip.size() - 22; p >= qMax(qsizetype(0), zip.size() - 65557); --p)
        if (u32(p) == 0x06054b50 && p + 22 + u16(p + 20) == zip.size()) { end = p; break; }
    if (end < 0) return fail("Missing ZIP central directory");
    if (u16(end + 4) || u16(end + 6) || u16(end + 8) != u16(end + 10))
        return fail("Multi-volume ZIP is unsupported");
    quint32 centralSize = u32(end + 12);
    qsizetype pos = u32(end + 16);
    if (pos + centralSize != end) return fail("Invalid ZIP central directory bounds");
    QSet<QString> names;
    quint64 total = 0;
    for (int i = 0; i < u16(end + 10); ++i) {
        if (pos + 46 > end || u32(pos) != 0x02014b50) return fail("Invalid ZIP entry");
        const auto flags = u16(pos + 8), method = u16(pos + 10);
        const quint32 compressed = u32(pos + 20), size = u32(pos + 24), crc = u32(pos + 16);
        const auto nameSize = u16(pos + 28), extra = u16(pos + 30), comment = u16(pos + 32);
        const qsizetype local = u32(pos + 42);
        if (pos + 46 + nameSize + extra + comment > end || local + 30 > zip.size())
            return fail("Truncated ZIP entry");
        if ((flags & ~quint16(0x080e)) || (method != 0 && method != 8) || u16(pos + 34))
            return fail("Unsupported ZIP encryption, compression or volume");
        const QByteArray encodedName = zip.mid(pos + 46, nameSize);
        const auto name = QString::fromUtf8(encodedName);
        const auto unixMode = u32(pos + 38) >> 16;
        if (!validName(name) || (unixMode & 0170000) == 0120000 || names.contains(name.toCaseFolded()))
            return fail("Unsafe or duplicate ZIP path");
        names.insert(name.toCaseFolded());
        if (u32(local) != 0x04034b50 || u16(local + 8) != method || u16(local + 6) != flags)
            return fail("ZIP local header mismatch");
        const qsizetype dataOffset = local + 30 + u16(local + 26) + u16(local + 28);
        if (dataOffset + compressed > u32(end + 16) || zip.mid(local + 30, u16(local + 26)) != encodedName)
            return fail("ZIP data bounds or filename mismatch");
        total += size;
        if (size > 32 * 1024 * 1024 || total > 128 * 1024 * 1024) return fail("Expanded skin exceeds limits");
        QByteArray data = zip.mid(dataOffset, compressed);
        if (method == 8) {
            QBuffer buffer(&data);
            QtIOCompressor stream(&buffer);
            stream.setStreamFormat(QtIOCompressor::RawZipFormat);
            if (!stream.open(QIODevice::ReadOnly)) return fail("Cannot inflate ZIP entry");
            data = stream.read(qint64(size) + 1);
        }
        if (quint32(data.size()) != size || crc32(0, reinterpret_cast<const Bytef *>(data.constData()), data.size()) != crc)
            return fail("ZIP size or checksum mismatch");
        if (!name.endsWith('/') && !write(name, data)) return fail("Cannot write extracted resource");
        pos += 46 + nameSize + extra + comment;
    }
    return pos == end ? true : fail("Unexpected central directory data");
}
