// SPDX-License-Identifier: GPL-3.0-only
#include <QtTest>
#include <QApplication>
#include <QElapsedTimer>
#include <QProcess>
#include <QThread>
#include <QTimer>
#include <QUuid>

#include "singleInstanceStartup.h"
#include "qtsingleapplication.h"

namespace {

QString uniqueId()
{
    return QStringLiteral("nulloy-startup-test-")
        + QUuid::createUuid().toString(QUuid::WithoutBraces);
}

bool waitForOutput(QProcess &process, const QByteArray &marker, int timeout,
                   QByteArray &output)
{
    QElapsedTimer timer;
    timer.start();
    while (timer.elapsed() < timeout) {
        output += process.readAllStandardOutput();
        if (output.contains(marker))
            return true;
        const int remaining = timeout - static_cast<int>(timer.elapsed());
        if (remaining <= 0)
            break;
        process.waitForReadyRead(qMin(remaining, 50));
    }
    output += process.readAllStandardOutput();
    return output.contains(marker);
}

class SingleInstanceStartupTest : public QObject
{
    Q_OBJECT

private:
    void setupProcess(QProcess &process, const QStringList &arguments)
    {
        process.setProgram(QCoreApplication::applicationFilePath());
        process.setArguments(arguments);
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        environment.insert(QStringLiteral("QT_QPA_PLATFORM"), QStringLiteral("offscreen"));
        process.setProcessEnvironment(environment);
    }

    void launchPrimary(QProcess &process, const QString &id, int delayMs, int runMs)
    {
        setupProcess(process, {QStringLiteral("--primary"), id,
                               QString::number(delayMs), QString::number(runMs)});
        process.start();
    }

    void launchProbe(QProcess &process, const QString &id, bool enabled, int timeoutMs)
    {
        setupProcess(process, {QStringLiteral("--probe"), id,
                               enabled ? QStringLiteral("enabled") : QStringLiteral("disabled"),
                               QString::number(timeoutMs)});
        process.start();
    }

    static bool finish(QProcess &process, QByteArray &output, int timeout = 5000)
    {
        if (!process.waitForFinished(timeout))
            return false;
        output = process.readAllStandardOutput();
        return true;
    }

    static int receivedCount(const QByteArray &output)
    {
        const QByteArray prefix("RECEIVED_COUNT=");
        const int start = output.indexOf(prefix);
        if (start < 0)
            return -1;
        const int valueStart = start + prefix.size();
        const int end = output.indexOf('\n', valueStart);
        return QByteArray(output.mid(valueStart, end < 0 ? -1 : end - valueStart))
            .trimmed().toInt();
    }

private slots:
    void fastPrimaryForwardsOnceWithoutStartingPlayer()
    {
        const QString id = uniqueId();
        QByteArray primaryOutput;
        QProcess primary;
        launchPrimary(primary, id, 0, 1000);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "LOOP_START", 3000, primaryOutput));

        QProcess secondary;
        launchProbe(secondary, id, true, 500);
        QVERIFY2(secondary.waitForStarted(3000), qPrintable(secondary.errorString()));
        QByteArray secondaryOutput;
        QVERIFY(finish(secondary, secondaryOutput));

        QCOMPARE(secondary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(secondary.exitCode(), 0);
        QVERIFY(secondaryOutput.contains("FORWARDED"));
        QVERIFY(!secondaryOutput.contains("PLAYER_STARTED"));

        QByteArray primaryRemainder;
        QVERIFY(finish(primary, primaryRemainder));
        primaryOutput += primaryRemainder;
        QCOMPARE(receivedCount(primaryOutput), 1);
        QVERIFY(primaryOutput.contains("RECEIVED=probe"));
    }

    void lateAcknowledgementFailsWithoutSecondLaunchOrResend()
    {
        const QString id = uniqueId();
        QByteArray primaryOutput;
        QProcess primary;
        launchPrimary(primary, id, 450, 1000);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "CLAIMED", 3000, primaryOutput));

        QProcess secondary;
        launchProbe(secondary, id, true, 100);
        QVERIFY2(secondary.waitForStarted(3000), qPrintable(secondary.errorString()));
        QByteArray secondaryOutput;
        QVERIFY(finish(secondary, secondaryOutput));

        QCOMPARE(secondary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(secondary.exitCode(), 3);
        QVERIFY(secondaryOutput.contains("IPC_FAILED"));
        QVERIFY(!secondaryOutput.contains("PLAYER_STARTED"));

        QByteArray primaryRemainder;
        QVERIFY(finish(primary, primaryRemainder, 5000));
        primaryOutput += primaryRemainder;
        QCOMPARE(receivedCount(primaryOutput), 1);
        QVERIFY(primaryOutput.contains("RECEIVED=probe"));
    }

    void firstLaunchStartsPrimary()
    {
        QProcess primary;
        launchProbe(primary, uniqueId(), true, 500);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QByteArray output;
        QVERIFY(finish(primary, output));

        QCOMPARE(primary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(primary.exitCode(), 0);
        QVERIFY(output.contains("PLAYER_STARTED"));
        QVERIFY(!output.contains("FORWARDED"));
        QVERIFY(!output.contains("IPC_FAILED"));
    }

    void disabledSingletonStillStartsSecondProcess()
    {
        const QString id = uniqueId();
        QByteArray primaryOutput;
        QProcess primary;
        launchPrimary(primary, id, 0, 1000);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "LOOP_START", 3000, primaryOutput));

        QProcess secondary;
        launchProbe(secondary, id, false, 500);
        QVERIFY2(secondary.waitForStarted(3000), qPrintable(secondary.errorString()));
        QByteArray secondaryOutput;
        QVERIFY(finish(secondary, secondaryOutput));

        QCOMPARE(secondary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(secondary.exitCode(), 0);
        QVERIFY(secondaryOutput.contains("PLAYER_STARTED"));
        QVERIFY(!secondaryOutput.contains("FORWARDED"));
        QVERIFY(!secondaryOutput.contains("IPC_FAILED"));

        QByteArray primaryRemainder;
        QVERIFY(finish(primary, primaryRemainder));
        primaryOutput += primaryRemainder;
        QCOMPARE(receivedCount(primaryOutput), 0);
    }
};

} // namespace

int runPrimary(int argc, char **argv)
{
    const QString id = QString::fromLocal8Bit(argv[2]);
    const int delayMs = QByteArray(argv[3]).toInt();
    const int runMs = QByteArray(argv[4]).toInt();
    QtSingleApplication app(id, argc, argv);
    if (app.isRunning())
        return 2;

    QStringList received;
    QObject::connect(&app, &QtSingleApplication::messageReceived,
                     &app, [&received](const QString &message) {
                         received << message;
                         QTextStream(stdout) << "RECEIVED=" << message << Qt::endl;
                     });
    QTextStream(stdout) << "CLAIMED" << Qt::endl;
    QThread::msleep(static_cast<unsigned long>(delayMs));
    QTextStream(stdout) << "LOOP_START" << Qt::endl;
    QTimer::singleShot(runMs, &app, &QCoreApplication::quit);
    const int result = app.exec();
    QTextStream(stdout) << "RECEIVED_COUNT=" << received.size() << Qt::endl;
    return result;
}

int runProbe(int argc, char **argv)
{
    const QString id = QString::fromLocal8Bit(argv[2]);
    const bool enabled = QString::fromLocal8Bit(argv[3]) == QStringLiteral("enabled");
    const int timeoutMs = QByteArray(argv[4]).toInt();
    QtSingleApplication app(id, argc, argv);

    if (enabled) {
        const auto result = singleInstanceStartup(app, QStringLiteral("probe"), timeoutMs);
        if (result == SingleInstanceStartupResult::MessageDelivered) {
            QTextStream(stdout) << "FORWARDED" << Qt::endl;
            return 0;
        }
        if (result == SingleInstanceStartupResult::MessageDeliveryFailed) {
            QTextStream(stdout) << "IPC_FAILED" << Qt::endl;
            return 3;
        }
    }

    // This marker is the production seam: main constructs NPlayer only here.
    QTextStream(stdout) << "PLAYER_STARTED" << Qt::endl;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 1 && QByteArray(argv[1]) == "--primary")
        return runPrimary(argc, argv);
    if (argc > 1 && QByteArray(argv[1]) == "--probe")
        return runProbe(argc, argv);

    QApplication app(argc, argv);
    SingleInstanceStartupTest test;
    return QTest::qExec(&test, argc, argv);
}

#include "testSingleInstanceStartup.moc"
