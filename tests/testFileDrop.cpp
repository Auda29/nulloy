// SPDX-License-Identifier: GPL-3.0-or-later
// Phase-0 regression reference for external file drops through Qt's event boundary.
#include <QtTest/QtTest>
#include <QDragEnterEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QMimeData>
#include <QTemporaryDir>

#include "playbackEngineInterface.h"
#include "playlistWidget.h"
#include "pluginLoader.h"

class TestFileDrop : public QObject
{
    Q_OBJECT
private slots:
    void initTestCase() { NPluginLoader::init(); }

    void externalFiles_data()
    {
        QTest::addColumn<int>("fileCount");
        QTest::addColumn<bool>("existingPlaylist");
        QTest::newRow("single-file-empty") << 1 << false;
        QTest::newRow("multiple-files-empty") << 2 << false;
        QTest::newRow("single-file-append") << 1 << true;
        QTest::newRow("multiple-files-append") << 2 << true;
    }

    void externalFiles()
    {
        QFETCH(int, fileCount);
        QFETCH(bool, existingPlaylist);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString fixture = QCoreApplication::applicationDirPath() + "/tests/01.wav";
        QVERIFY2(QFile::exists(fixture), "Build upstream's WAV fixtures first");
        QStringList paths;
        QList<QUrl> urls;
        for (int i = 0; i < fileCount; ++i) {
            const QString name = QString::fromUtf8("Neuer Track \xc3\xa4 %1.wav").arg(i + 1);
            const QString path = directory.filePath(name);
            QVERIFY(QFile::copy(fixture, path));
            paths << QDir::cleanPath(path);
            urls << QUrl::fromLocalFile(path);
        }
        NPlaylistWidget playlist;
        playlist.resize(640, 400);
        playlist.show();
        QTest::qWait(50);
        QCOMPARE(playlist.count(), 0);
        const QString existingPath = directory.filePath("existing.wav");
        if (existingPlaylist) {
            QVERIFY(QFile::copy(fixture, existingPath));
            playlist.addFiles(QStringList() << existingPath);
            QCOMPARE(playlist.count(), 1);
        }
        const int initialCount = playlist.count();

        QMimeData mime;
        mime.setUrls(urls);
        QDragEnterEvent enter(QPoint(20, 300), Qt::CopyAction, &mime,
                              Qt::LeftButton, Qt::NoModifier);
        QCoreApplication::sendEvent(playlist.viewport(), &enter);
        QVERIFY(enter.isAccepted());
        QDragMoveEvent move(QPoint(20, 300), Qt::CopyAction, &mime,
                            Qt::LeftButton, Qt::NoModifier);
        QCoreApplication::sendEvent(playlist.viewport(), &move);
        QVERIFY(move.isAccepted());
        QDropEvent drop(QPointF(20, 300), Qt::CopyAction, &mime,
                        Qt::LeftButton, Qt::NoModifier);
        QCoreApplication::sendEvent(playlist.viewport(), &drop);
        QVERIFY(drop.isAccepted());
        QCOMPARE(playlist.count(), initialCount + fileCount);
        if (existingPlaylist) {
            QCOMPARE(QDir::cleanPath(playlist.item(0)->data(N::PathRole).toString()),
                     QDir::cleanPath(existingPath));
        }
        for (int i = 0; i < fileCount; ++i) {
            QCOMPARE(QDir::cleanPath(playlist.item(initialCount + i)->data(N::PathRole).toString()), paths.at(i));
            QVERIFY(QFile::exists(paths.at(i)));
            QCOMPARE(QFileInfo(paths.at(i)).size(), QFileInfo(fixture).size());
        }
        auto *engine = dynamic_cast<NPlaybackEngineInterface *>(NPluginLoader::getPlugin(N::PlaybackEngine));
        QVERIFY(engine);
        engine->stop();
    }
};

QTEST_MAIN(TestFileDrop)
#include "testFileDrop.moc"
