// SPDX-License-Identifier: GPL-3.0-only
#include "mainWindow.h"
#include "settings.h"
#include "windowGeometry.h"
#include <QApplication>
#include <QScreen>
#include <QTemporaryDir>
#include <QtTest/QTest>

// Keep the real NSettings implementation, isolating only its on-disk location.
namespace NCore
{
    QString settingsPath()
    {
        static QTemporaryDir directory;
        return directory.filePath("window.cfg");
    }
} // namespace NCore

class TestWindowRestoration : public QObject
{
    Q_OBJECT
private slots:
    void init()
    {
        NSettings::instance()->setValue("Maximized", false);
        NSettings::instance()->setValue("Size", QStringList({"430", "350"}));
        NSettings::instance()->setValue("Position", QStringList({"100000", "100000"}));
    }

    void titlebarMustBeReachable_data()
    {
        QTest::addColumn<QRect>("stored");
        QTest::newRow("only-bottom-visible") << QRect(100, -300, 430, 350);
        QTest::newRow("one-pixel-at-right") << QRect(799, 100, 430, 350);
        QTest::newRow("one-pixel-at-bottom") << QRect(100, 799, 430, 350);
        QTest::newRow("only-body-on-screen") << QRect(100, -40, 430, 350);
    }

    void titlebarMustBeReachable()
    {
        QFETCH(QRect, stored);
        const QRect available(0, 0, 800, 800);
        QVERIFY(available.contains(NWindowGeometry::restored(stored, {available})));
    }

    void reachableGeometryIsPreserved_data()
    {
        QTest::addColumn<QRect>("stored");
        QTest::addColumn<QList<QRect>>("screens");
        const QList<QRect> screens = {QRect(0, 0, 1920, 1040), QRect(-1920, -200, 1920, 1080)};
        QTest::newRow("normal") << QRect(150, 250, 430, 350) << screens;
        QTest::newRow("negative-monitor") << QRect(-1700, -100, 430, 350) << screens;
        QTest::newRow("partially-visible-titlebar")
            << QRect(-330, 100, 430, 350) << QList<QRect>{QRect(0, 0, 800, 800)};
        QTest::newRow("partially-clipped-titlebar-top")
            << QRect(100, -10, 430, 350) << QList<QRect>{QRect(0, 0, 800, 800)};
        QTest::newRow("logical-dpi-coordinates")
            << QRect(-1000, 50, 430, 350)
            << QList<QRect>{QRect(0, 0, 1536, 824), QRect(-1280, 0, 1280, 680)};
        QTest::newRow("deliberate-spanning-window") << QRect(-1500, 50, 2500, 650) << screens;
    }

    void reachableGeometryIsPreserved()
    {
        QFETCH(QRect, stored);
        QFETCH(QList<QRect>, screens);
        QCOMPARE(NWindowGeometry::restored(stored, screens), stored);
    }

    void showRecoversAfterMonitorChange_data()
    {
        QTest::addColumn<bool>("minimized");
        QTest::newRow("hidden") << false;
        QTest::newRow("minimized") << true;
    }

    void showRecoversAfterMonitorChange()
    {
        QFETCH(bool, minimized);
        NMainWindow window;
        window.setWindowFlag(Qt::FramelessWindowHint);
        window.resize(430, 350);
        window.move(100000, 100000);
        if (minimized)
            window.showMinimized();
        window.show();
        QVERIFY(window.isVisible());
        QVERIFY(!window.isMinimized());
        QVERIFY(QGuiApplication::primaryScreen()->availableGeometry().contains(
            QRect(window.pos(), window.size())));
        QCOMPARE(window.size(), QSize(430, 350));
    }

    void cachedNormalGeometryRecovers_data()
    {
        QTest::addColumn<bool>("fullscreen");
        QTest::addColumn<bool>("frameless");
        QTest::newRow("native-maximized") << false << false;
        QTest::newRow("frameless-maximized") << false << true;
        QTest::newRow("native-fullscreen") << true << false;
        QTest::newRow("frameless-fullscreen") << true << true;
    }

    void cachedNormalGeometryRecovers()
    {
        QFETCH(bool, fullscreen);
        QFETCH(bool, frameless);
        NMainWindow window;
        window.setWindowFlag(Qt::FramelessWindowHint, frameless);
        window.resize(430, 350);
        window.move(100000, 100000);
        if (fullscreen) {
            window.toggleFullScreen();
            window.toggleFullScreen();
        } else {
            window.toggleMaximize();
            window.toggleMaximize();
        }
        QVERIFY(!window.isMinimized());
        QVERIFY(!window.isMaximized());
        QVERIFY(!window.isFullScreen());
        QVERIFY(QGuiApplication::primaryScreen()->availableGeometry().contains(
            QRect(window.pos(), window.size())));
        QCOMPARE(window.size(), QSize(430, 350));
    }

    void layoutChangeRecoversWithoutChangingState_data()
    {
        QTest::addColumn<int>("state");
        QTest::newRow("visible-normal") << 0;
        QTest::newRow("hidden-normal") << 1;
        QTest::newRow("minimized") << 2;
        QTest::newRow("maximized") << 3;
        QTest::newRow("fullscreen") << 4;
    }

    void layoutChangeRecoversWithoutChangingState()
    {
        QFETCH(int, state);
        NMainWindow window;
        window.setWindowFlag(Qt::FramelessWindowHint);
        window.resize(430, 350);
        window.move(100000, 100000);
        if (state == 0)
            window.QDialog::show();
        else if (state == 2)
            window.showMinimized();
        else if (state == 3)
            window.toggleMaximize();
        else if (state == 4)
            window.toggleFullScreen();
        const auto oldState = window.windowState();
        const bool visible = window.isVisible();
        QScreen *screen = QGuiApplication::primaryScreen();
        // Deliver Qt's real layout notification, with a window left at a vanished
        // monitor's coordinates. Geometry policy separately tests multiple screens.
        screen->availableGeometryChanged(screen->availableGeometry());
        QCoreApplication::processEvents();
        window.saveSettings();
        const QStringList position = NSettings::instance()->value("Position").toStringList();
        const QStringList size = NSettings::instance()->value("Size").toStringList();
        const QRect saved(position[0].toInt(), position[1].toInt(), size[0].toInt(),
                          size[1].toInt());
        QVERIFY(screen->availableGeometry().contains(saved));
        QCOMPARE(saved.size(), QSize(430, 350));
        QCOMPARE(window.windowState(), oldState);
        QCOMPARE(window.isVisible(), visible);
        if (state == 0 || state == 1)
            QCOMPARE(QRect(window.pos(), window.size()), saved);
        else {
            // Native/taskbar restoration bypasses NMainWindow::show().
            window.showNormal();
            QCoreApplication::processEvents();
            QVERIFY(screen->availableGeometry().contains(QRect(window.pos(), window.size())));
            QCOMPARE(window.size(), QSize(430, 350));
            window.move(50, 60);
            window.saveSettings();
            QCOMPARE(NSettings::instance()->value("Position").toStringList(),
                     QStringList({"50", "60"}));
        }
    }

    void otherScreenNotifications_data()
    {
        QTest::addColumn<int>("notification");
        QTest::newRow("geometry-changed") << 0;
        QTest::newRow("screen-removed") << 1;
        QTest::newRow("screen-added") << 2;
        QTest::newRow("primary-changed") << 3;
    }

    void otherScreenNotifications()
    {
        QFETCH(int, notification);
        NMainWindow window;
        window.setWindowFlag(Qt::FramelessWindowHint);
        window.resize(430, 350);
        window.move(100000, 100000);
        QScreen *screen = QGuiApplication::primaryScreen();
        if (notification == 0)
            screen->geometryChanged(screen->geometry());
        else if (notification == 1)
            qApp->screenRemoved(nullptr);
        else if (notification == 2)
            qApp->screenAdded(screen);
        else
            qApp->primaryScreenChanged(screen);
        QCoreApplication::processEvents();
        QVERIFY(screen->availableGeometry().contains(QRect(window.pos(), window.size())));
        QVERIFY(!window.isVisible());
    }

    void malformedSettings_data()
    {
        QTest::addColumn<QStringList>("position");
        QTest::addColumn<QStringList>("size");
        QTest::newRow("single-position") << QStringList{"123"} << QStringList{};
        QTest::newRow("single-size") << QStringList{} << QStringList{"430"};
        QTest::newRow("invalid-size") << QStringList{} << QStringList{"oops", "350"};
        QTest::newRow("negative-size") << QStringList{} << QStringList{"-430", "350"};
        QTest::newRow("zero-size") << QStringList{} << QStringList{"0", "0"};
        QTest::newRow("overflow-size") << QStringList{} << QStringList{"999999999999", "350"};
        QTest::newRow("missing-settings") << QStringList{} << QStringList{};
    }

    void malformedSettings()
    {
        QFETCH(QStringList, position);
        QFETCH(QStringList, size);
        NSettings::instance()->setValue("Position", position);
        NSettings::instance()->setValue("Size", size);
        NMainWindow window;
        window.setWindowFlag(Qt::FramelessWindowHint);
        window.loadSettings();
        QCOMPARE(window.size(), QSize(430, 350));
        QVERIFY(QGuiApplication::primaryScreen()->availableGeometry().contains(
            QRect(window.pos(), window.size())));
    }

    void recoveryHandlesWorkAreaLimits_data()
    {
        QTest::addColumn<QRect>("stored");
        QTest::addColumn<QList<QRect>>("screens");
        QTest::addColumn<QRect>("expectedArea");
        QTest::newRow("huge-window-small-screen")
            << QRect(100000, 100000, 100000, 100000) << QList<QRect>{QRect(0, 30, 320, 170)}
            << QRect(0, 30, 320, 170);
        QTest::newRow("tiny-screen") << QRect(-100000, -100000, 430, 350)
                                     << QList<QRect>{QRect(-4, -5, 8, 10)} << QRect(-4, -5, 8, 10);
        QTest::newRow("negative-fallback")
            << QRect(100000, 100000, 430, 350) << QList<QRect>{QRect(-1600, -900, 1600, 860)}
            << QRect(-1600, -900, 1600, 860);
        QTest::newRow("invalid-screen-before-valid")
            << QRect(100000, 100000, 430, 350) << QList<QRect>{QRect(), QRect(0, 0, 800, 600)}
            << QRect(0, 0, 800, 600);
        QTest::newRow("gap-between-monitors")
            << QRect(900, 100, 430, 350)
            << QList<QRect>{QRect(0, 0, 800, 600), QRect(1400, 0, 800, 600)}
            << QRect(0, 0, 800, 600);
    }

    void recoveryHandlesWorkAreaLimits()
    {
        QFETCH(QRect, stored);
        QFETCH(QList<QRect>, screens);
        QFETCH(QRect, expectedArea);
        const QRect restored = NWindowGeometry::restored(stored, screens);
        QVERIFY(restored.isValid());
        QVERIFY(expectedArea.contains(restored));
        QCOMPARE(restored.size(), stored.size().boundedTo(expectedArea.size()));
        QCOMPARE(NWindowGeometry::restored(restored, screens), restored);
    }

    void noUsableScreensDoesNotDestroyGeometry()
    {
        const QRect stored(-1500, -400, 430, 350);
        QCOMPARE(NWindowGeometry::restored(stored, {}), stored);
        QCOMPARE(NWindowGeometry::restored(stored, {QRect(), QRect(0, 0, 0, 0)}), stored);
    }

    void reachableSettingsRoundTrip_data()
    {
        QTest::addColumn<bool>("frameless");
        QTest::addColumn<bool>("maximized");
        QTest::newRow("native-normal") << false << false;
        QTest::newRow("frameless-normal") << true << false;
        QTest::newRow("native-maximized") << false << true;
        QTest::newRow("frameless-maximized") << true << true;
    }

    void reachableSettingsRoundTrip()
    {
        QFETCH(bool, frameless);
        QFETCH(bool, maximized);
        const QPoint position = QGuiApplication::primaryScreen()->availableGeometry().topLeft() +
                                QPoint(50, 60);
        const QStringList savedPosition{QString::number(position.x()),
                                        QString::number(position.y())};
        NSettings::instance()->setValue("Position", savedPosition);
        NSettings::instance()->setValue("Maximized", maximized);
        NMainWindow window;
        window.setWindowFlag(Qt::FramelessWindowHint, frameless);
        window.loadSettings();
        window.show();
        QCOMPARE(window.isMaximized(), maximized);
        window.showMinimized();
        window.saveSettings();
        QCOMPARE(NSettings::instance()->value("Position").toStringList(), savedPosition);
        QCOMPARE(NSettings::instance()->value("Size").toStringList(), QStringList({"430", "350"}));
        window.show();
        if (maximized)
            window.toggleMaximize();
        QCoreApplication::processEvents();
        QCOMPARE(window.pos(), position);
        QCOMPARE(window.size(), QSize(430, 350));
    }

    void disconnectedMonitorAtStartup()
    {
        NMainWindow window;
        window.setWindowFlag(Qt::FramelessWindowHint);
        window.loadSettings();
        const QRect available = QGuiApplication::primaryScreen()->availableGeometry();
        QVERIFY2(available.contains(QRect(window.pos(), window.size())),
                 qPrintable(QString("Restored rectangle %1,%2 %3x%4 outside %5,%6 %7x%8")
                                .arg(window.x())
                                .arg(window.y())
                                .arg(window.width())
                                .arg(window.height())
                                .arg(available.x())
                                .arg(available.y())
                                .arg(available.width())
                                .arg(available.height())));
        QCOMPARE(window.size(), QSize(430, 350));
    }
};
QTEST_MAIN(TestWindowRestoration)
#include "testWindowRestoration.moc"
