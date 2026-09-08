// SPDX-License-Identifier: GPL-3.0-only
#include <QtTest>
#include <QTemporaryDir>
#include "pluginLoader.h"
#include "tagReaderInterface.h"
#include "coverReaderInterface.h"
#include "waveformBuilderInterface.h"

class TestPluginResources : public QObject
{
    Q_OBJECT
private slots:
    void initTestCase() { NPluginLoader::init(); }

    void sharedTagFileRelease()
    {
        auto *cover = dynamic_cast<NCoverReaderInterface *>(NPluginLoader::getPlugin(N::CoverReader));
        auto *tags = dynamic_cast<NTagReaderInterface *>(NPluginLoader::getPlugin(N::TagReader));
        QVERIFY(cover);
        QVERIFY(tags);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString path = directory.filePath(QString::fromUtf8("Grüße 日本語.wav"));
        QVERIFY(QFile::copy(QCoreApplication::applicationDirPath() + "/tests/01.wav", path));
        const QMap<QString, QStringList> values{{"TITLE", {QString::fromUtf8("Grüße 日本語")}}};
        tags->setSource(path);
        QVERIFY(tags->setTags(values).isEmpty());
        cover->setSource("");
        QVERIFY(!cover->isValid());
        QCOMPARE(tags->setTags(values).value("Error"), QStringList{"Write"});
        QCOMPARE(tags->getTags().value("Error"), QStringList{"Invalid"});
        QVERIFY(tags->getTag('t').isEmpty());
        // Cover and tag readers may select the same file in either order.
        cover->setSource(path);
        QVERIFY(cover->isValid());
        tags->setSource(path);
        QCOMPARE(tags->getTags().value("TITLE"), values.value("TITLE"));
        tags->setSource(directory.filePath("missing.wav"));
        QCOMPARE(tags->setTags(values).value("Error"), QStringList{"Write"});
        QFile invalid(directory.filePath("unsupported.bin"));
        QVERIFY(invalid.open(QIODevice::WriteOnly));
        invalid.write("not an audio file");
        invalid.close();
        tags->setSource(invalid.fileName());
        QCOMPARE(tags->setTags(values).value("Error"), QStringList{"Write"});
        tags->setSource("");
    }

    void waveformRepeatedBuildAndCancel()
    {
        auto *wave = dynamic_cast<NWaveformBuilderInterface *>(NPluginLoader::getPlugin(N::WaveformBuilder));
        QVERIFY(wave);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        for (int i = 0; i < 8; ++i) {
            const QString path = directory.filePath(QString("wave-%1.wav").arg(i));
            QVERIFY(QFile::copy(QCoreApplication::applicationDirPath() + "/tests/01.wav", path));
            wave->start(path);
            if (i % 2 == 0) {
                QTRY_VERIFY(wave->peaks().isCompleted());
                QVERIFY(wave->peaks().size() > 0);
            }
            wave->stop();
            QVERIFY(!wave->isRunning());
        }
    }
};

QTEST_MAIN(TestPluginResources)
#include "testPluginResources.moc"
