// SPDX-License-Identifier: GPL-3.0-only
#include "skinResources.h"
#include <QDir>
#include <QFile>
#include <QFontDatabase>
#include <QImage>
#include <QtTest>

class SkinResourceTest : public QObject
{
    Q_OBJECT
private slots:
    void containers_data();
    void containers();
    void invalidArchives_data();
    void invalidArchives();
    void pathsAndMasks();
    void fonts();
};

void SkinResourceTest::containers_data()
{
    QTest::addColumn<QString>("skin");
    QTest::addColumn<QString>("path");
    for (QString skin : {"slim", "native", "silver", "metro"}) {
        QTest::newRow(qPrintable(skin + "-directory")) << skin << QString(SKIN_SOURCE_ROOT "/") + skin;
        for (QString method : {"stored", "deflated"})
            QTest::newRow(qPrintable(skin + '-' + method)) << skin << QString(FIXTURE_ROOT "/") + skin + '-' + method + ".nzs";
    }
    QTest::newRow("data-descriptor") << QString("slim") << QString(FIXTURE_ROOT "/descriptor.nzs");
    QTest::newRow("nested") << QString("slim") << QString(FIXTURE_ROOT "/nested.nzs");
}
void SkinResourceTest::containers()
{
    QFETCH(QString, skin);
    QFETCH(QString, path);
    SkinResources resources;
    QString error;
    QVERIFY2(resources.load(path, &error), qPrintable(error));
    for (QString name : {"form.ui", "script.js", "id.txt"}) {
        QFile source(QString(SKIN_SOURCE_ROOT "/") + skin + '/' + name);
        QVERIFY(source.open(QIODevice::ReadOnly));
        QCOMPARE(resources.bytes(name), source.readAll());
    }
    if (path.endsWith("nested.nzs")) QCOMPARE(resources.bytes("images/nested.txt"), QByteArray("nested resource ä"));
}
void SkinResourceTest::invalidArchives_data()
{
    QTest::addColumn<QString>("name");
    for (QString name : {"traversal", "duplicate", "corrupt"}) QTest::newRow(qPrintable(name)) << name;
}
void SkinResourceTest::invalidArchives()
{
    QFETCH(QString, name);
    SkinResources resources;
    QString error;
    QVERIFY(!resources.load(QString(FIXTURE_ROOT "/") + name + ".nzs", &error));
    QVERIFY(!error.isEmpty());
    QVERIFY(!QFile::exists(QString(FIXTURE_ROOT "/escaped.txt")));
}
void SkinResourceTest::pathsAndMasks()
{
    SkinResources resources, other;
    QString error;
    QVERIFY(resources.load(SKIN_SOURCE_ROOT "/metro", &error));
    QVERIFY(other.load(SKIN_SOURCE_ROOT "/metro", &error));
    const QByteArray original = resources.bytes("play.png");
    QVERIFY(!original.isEmpty());
    QVERIFY(resources.maskImage("play.png", "#FFFFFF"));
    QImage white;
    QVERIFY(white.loadFromData(resources.bytes("play.png")));
    QVERIFY(resources.maskImage("play.png", "#3D3D3D"));
    QImage dark;
    QVERIFY(dark.loadFromData(resources.bytes("play.png")));
    QVERIFY(white != dark);
    QCOMPARE(other.bytes("play.png"), original);
    QVERIFY(resources.bytes("../id.txt").isEmpty());
    QVERIFY(!resources.maskImage("missing.png", "red"));
    QCOMPARE(resources.rewriteUrls("a{image:url(play.png)} b{image:url('nested/x.png')} c{image:url(:play.png)}"),
             "a{image:url(" + resources.prefix() + "play.png)} b{image:url('" + resources.prefix() + "nested/x.png')} c{image:url(:play.png)}");
    QFile css(SKIN_SOURCE_ROOT "/metro/light.css");
    QVERIFY(css.open(QIODevice::ReadOnly));
    QCOMPARE(resources.readFile("light.css"), QString::fromUtf8(css.readAll()));
}
void SkinResourceTest::fonts()
{
    QTemporaryDir directory;
    QVERIFY(directory.isValid());
    for (QString name : {"form.ui", "script.js", "id.txt"})
        QVERIFY(QFile::copy(QString(SKIN_SOURCE_ROOT "/slim/") + name, directory.filePath(name)));
    QVERIFY(QFile::copy(FIXTURE_ROOT "/fixture.ttf", directory.filePath("font.ttf")));
    SkinResources resources;
    QString error;
    QVERIFY(resources.load(directory.path(), &error));
    int font = resources.addApplicationFont("font.ttf");
    QVERIFY(font >= 0);
    QVERIFY(!QFontDatabase::applicationFontFamilies(font).isEmpty());
    QCOMPARE(resources.addApplicationFont("missing.ttf"), -1);
}
QTEST_MAIN(SkinResourceTest)
#include "testSkinResources.moc"
