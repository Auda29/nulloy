// SPDX-License-Identifier: GPL-3.0-only
#include <QtTest>
#include <QApplication>
#include <QDataStream>
#include <QElapsedTimer>
#include <QFile>
#include <QProcess>
#include <QRegularExpression>
#include <QLocalServer>
#include <QLocalSocket>
#include <QTemporaryDir>
#include <QThread>
#include <QTimer>
#include <QUuid>
#include <vector>

#include "singleInstanceStartup.h"
#include "qtsingleapplication.h"
#include "qtlocalpeer.h"
#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif

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
    if (output.contains(marker))
        return true;
    qWarning().noquote() << "child output marker timed out:" << marker
                         << "program=" << process.program()
                         << "error=" << process.errorString()
                         << "stderr=" << process.readAllStandardError();
    return false;
}

class ChildProcessCleanup
{
public:
    explicit ChildProcessCleanup(QProcess &process)
        : m_process(process)
    {
    }

    ~ChildProcessCleanup()
    {
        if (m_process.state() == QProcess::NotRunning)
            return;
        qWarning().noquote() << "terminating child during test cleanup:"
                             << m_process.program() << m_process.arguments()
                             << "error=" << m_process.errorString()
                             << "stderr=" << m_process.readAllStandardError();
        m_process.kill();
        if (!m_process.waitForFinished(3000))
            qWarning().noquote() << "child did not terminate during test cleanup:"
                                 << m_process.program() << m_process.arguments();
    }

private:
    QProcess &m_process;
};

bool releaseBarrier(const QString &path)
{
    QFile release(path);
    if (!release.open(QIODevice::WriteOnly))
        return false;
    return release.write("release\n") == 8;
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

    void launchPrimary(QProcess &process, const QString &id, int runMs,
                       const QString &releasePath = QString())
    {
        QStringList arguments {QStringLiteral("--primary"), id, QString::number(runMs)};
        if (!releasePath.isEmpty())
            arguments << releasePath;
        setupProcess(process, arguments);
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
        if (!process.waitForFinished(timeout)) {
            qWarning().noquote() << "child did not finish:" << process.program()
                                 << process.arguments() << "state=" << process.state()
                                 << "error=" << process.errorString()
                                 << "stderr=" << process.readAllStandardError();
            return false;
        }
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
    void windowsShortAndLongExecutablePathsShareIdentity()
    {
#ifdef Q_OS_WIN
        const QString executable = QFileInfo(QCoreApplication::applicationFilePath()).canonicalFilePath();
        const QString native = QDir::toNativeSeparators(executable);
        const DWORD length = GetShortPathNameW(reinterpret_cast<LPCWSTR>(native.utf16()), nullptr, 0);
        QVERIFY(length > 0);
        std::vector<wchar_t> buffer(length);
        QVERIFY(GetShortPathNameW(reinterpret_cast<LPCWSTR>(native.utf16()), buffer.data(), length) > 0);
        const QString shortPath = QString::fromWCharArray(buffer.data());
        if (shortPath.compare(native, Qt::CaseInsensitive) == 0)
            QSKIP("Test volume does not supply a distinct 8.3 executable alias");
        auto identity = [this](const QString &program) {
            QProcess process;
            setupProcess(process, {"--identity"});
            process.setProgram(program);
            process.start();
            if (!process.waitForStarted(3000) || !process.waitForFinished(5000)
                || process.exitCode() != 0) return QByteArray();
            return process.readAllStandardOutput().trimmed();
        };
        const QByteArray longId = identity(executable);
        QVERIFY(!longId.isEmpty());
        QCOMPARE(identity(shortPath), longId);
        QTemporaryDir other;
        QVERIFY(other.isValid());
        const QString copy = other.filePath("other-player.exe");
        QVERIFY(QFile::copy(executable, copy));
        const QByteArray otherId = identity(copy);
        QVERIFY(!otherId.isEmpty());
        QVERIFY(otherId != longId);
#else
        QSKIP("8.3 executable aliases are Windows-specific");
#endif
    }

    void windowsConnectionAcceptedInsideListenIsDelivered()
    {
#if defined(Q_OS_WIN) && QT_VERSION >= QT_VERSION_CHECK(6, 3, 0)
        class InspectablePeer : public QtLocalPeer {
        public:
            explicit InspectablePeer(const QString &id) : QtLocalPeer(nullptr, id) {}
            QString address() const { return socketName; }
            QLocalServer *listener() const { return server; }
        } peer(uniqueId());
        // Stretch actual Windows named-pipe initialization, not a mocked signal.
        // Qt5 has a fixed backlog and cannot make this interleaving deterministic.
        peer.listener()->setListenBacklogSize(4096);
        bool claimReturned = false, acceptedDuringListen = false;
        connect(peer.listener(), &QLocalServer::newConnection, &peer, [&] {
            acceptedDuringListen |= !claimReturned;
        });
        bool acknowledged = false;
        const QString address = peer.address();
        QThread *client = QThread::create([address, &acknowledged] {
            QLocalSocket socket;
            QElapsedTimer timer;
            timer.start();
            while (timer.elapsed() < 5000) {
                socket.connectToServer(address);
                if (socket.waitForConnected(20)) break;
                socket.abort();
                QThread::yieldCurrentThread();
            }
            if (socket.state() != QLocalSocket::ConnectedState) return;
            QDataStream stream(&socket);
            stream.writeBytes("early", 5);
            if (socket.bytesToWrite() && !socket.waitForBytesWritten(5000)) return;
            if (!socket.bytesAvailable() && !socket.waitForReadyRead(5000)) return;
            acknowledged = socket.read(3) == "ack";
        });
        struct JoinThread {
            QThread *thread;
            ~JoinThread() { thread->wait(); delete thread; }
        } cleanup{client};
        client->start();
        QVERIFY(!peer.isClient());
        claimReturned = true;
        QVERIFY2(acceptedDuringListen, "test did not exercise acceptance inside Windows listen()");
        // Match main.cpp: the player receiver is connected only after claiming
        // the primary role. Delivery during listen() would be lost as well.
        QStringList received;
        connect(&peer, &QtLocalPeer::messageReceived, &peer,
                [&received](const QString &message) { received << message; });
        QTRY_COMPARE_WITH_TIMEOUT(received, QStringList{"early"}, 7000);
        QVERIFY(client->wait(3000));
        QVERIFY(acknowledged);
#else
        QSKIP("Deterministic Windows listen-time interleaving requires Qt >= 6.3 backlog control");
#endif
    }

    void disconnectedClientWithoutHeaderDoesNotBlockPrimary()
    {
        const QString id = uniqueId();
        QProcess primary;
        ChildProcessCleanup primaryCleanup(primary);
        QByteArray output;
        launchPrimary(primary, id, 1000);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "LOOP_START", 3000, output));
        const QByteArray prefix("SOCKET=");
        const int start = output.indexOf(prefix);
        QVERIFY(start >= 0);
        const int valueStart = start + prefix.size();
        const QByteArray address = output.mid(valueStart).split('\n').first().trimmed();
        QLocalSocket client;
        client.connectToServer(QString::fromUtf8(address));
        QVERIFY2(client.waitForConnected(1000), qPrintable(client.errorString()));
        client.disconnectFromServer();
        if (client.state() != QLocalSocket::UnconnectedState)
            QVERIFY(client.waitForDisconnected(1000));
        QByteArray remainder;
        QVERIFY2(finish(primary, remainder, 4000), "empty disconnected client blocked primary event loop");
        output += remainder;
        QCOMPARE(primary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(primary.exitCode(), 0);
        QCOMPARE(receivedCount(output), 0);
    }

    void fastPrimaryForwardsOnceWithoutStartingPlayer()
    {
        const QString id = uniqueId();
        QByteArray primaryOutput;
        QProcess primary;
        ChildProcessCleanup primaryCleanup(primary);
        launchPrimary(primary, id, 1000);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "LOOP_START", 3000, primaryOutput));

        QProcess secondary;
        ChildProcessCleanup secondaryCleanup(secondary);
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

    void delayedAcknowledgementFailureIsBoundedAndNotLossless()
    {
        const QString id = uniqueId();
        QTemporaryDir barrier;
        QVERIFY(barrier.isValid());
        const QString releasePath = barrier.filePath(QStringLiteral("release"));
        QByteArray primaryOutput;
        QProcess primary;
        ChildProcessCleanup primaryCleanup(primary);
        launchPrimary(primary, id, 1000, releasePath);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "READY_TO_RECEIVE", 3000, primaryOutput));

        QProcess secondary;
        ChildProcessCleanup secondaryCleanup(secondary);
        launchProbe(secondary, id, true, 500);
        QVERIFY2(secondary.waitForStarted(3000), qPrintable(secondary.errorString()));
        QByteArray secondaryProgress;
        QVERIFY(waitForOutput(secondary, "SENDING", 3000, secondaryProgress));
        QByteArray secondaryOutput;
        QVERIFY2(finish(secondary, secondaryOutput, 5000),
                 "secondary did not report bounded IPC failure");
        secondaryProgress += secondaryOutput;

        QCOMPARE(secondary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(secondary.exitCode(), 3);
        QVERIFY2(secondaryProgress.contains("IPC_FAILED"), qPrintable(secondaryProgress));
        QVERIFY2(!secondaryProgress.contains("PLAYER_STARTED"), qPrintable(secondaryProgress));

        QVERIFY2(releaseBarrier(releasePath), qPrintable(releasePath));

        QByteArray primaryRemainder;
        QVERIFY2(finish(primary, primaryRemainder, 5000), "primary did not exit after release");
        primaryOutput += primaryRemainder;
        QCOMPARE(primary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(primary.exitCode(), 0);
        const int count = receivedCount(primaryOutput);
        QVERIFY2(count == 0 || count == 1, qPrintable(primaryOutput));
        QCOMPARE(primaryOutput.count("RECEIVED=probe"), count);
    }

    void delayedAcknowledgementWithinBudgetDeliversExactlyOnce()
    {
        const QString id = uniqueId();
        QTemporaryDir barrier;
        QVERIFY(barrier.isValid());
        const QString releasePath = barrier.filePath(QStringLiteral("release"));
        QByteArray primaryOutput;
        QProcess primary;
        ChildProcessCleanup primaryCleanup(primary);
        setupProcess(primary, {QStringLiteral("--primary-frame"), id,
                               QStringLiteral("1000"), releasePath});
        primary.start();
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "LOOP_START", 3000, primaryOutput));

        QProcess secondary;
        ChildProcessCleanup secondaryCleanup(secondary);
        launchProbe(secondary, id, true, 3000);
        QVERIFY2(secondary.waitForStarted(3000), qPrintable(secondary.errorString()));
        QByteArray secondaryOutput;
        QVERIFY(waitForOutput(primary, "FRAME_QUEUED", 3000, primaryOutput));
        // The full frame is queued but not acknowledged by the receiver yet.
        QVERIFY2(!secondary.waitForFinished(150), "sender finished before ACK release");
        QCOMPARE(secondary.state(), QProcess::Running);
        secondaryOutput += secondary.readAllStandardOutput();
        QVERIFY2(!secondaryOutput.contains("FORWARDED"), qPrintable(secondaryOutput));
        QVERIFY2(!secondaryOutput.contains("IPC_FAILED"), qPrintable(secondaryOutput));
        QVERIFY2(releaseBarrier(releasePath), qPrintable(releasePath));
        QByteArray secondaryRemainder;
        QVERIFY2(finish(secondary, secondaryRemainder, 5000),
                 "delayed forward did not finish");
        secondaryOutput += secondaryRemainder;

        QCOMPARE(secondary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(secondary.exitCode(), 0);
        QVERIFY2(secondaryOutput.contains("FORWARDED"), qPrintable(secondaryOutput));
        QVERIFY2(!secondaryOutput.contains("PLAYER_STARTED"), qPrintable(secondaryOutput));
        QVERIFY2(!secondaryOutput.contains("IPC_FAILED"), qPrintable(secondaryOutput));

        QByteArray primaryRemainder;
        QVERIFY2(finish(primary, primaryRemainder, 5000),
                 "primary did not exit after delayed delivery");
        primaryOutput += primaryRemainder;
        QCOMPARE(primary.exitStatus(), QProcess::NormalExit);
        QCOMPARE(primary.exitCode(), 0);
        const QRegularExpression heldPattern(QStringLiteral("ACK_HELD_MS=(\\d+)"));
        const auto held = heldPattern.match(QString::fromUtf8(primaryOutput));
        QVERIFY2(held.hasMatch(), qPrintable(primaryOutput));
        QVERIFY2(held.captured(1).toLongLong() >= 150, qPrintable(primaryOutput));
        qInfo() << "Observed frame-to-release delay (ms):" << held.captured(1).toLongLong();
        QCOMPARE(receivedCount(primaryOutput), 1);
        QCOMPARE(primaryOutput.count("RECEIVED=probe"), 1);
    }

    void firstLaunchStartsPrimary()
    {
        QProcess primary;
        ChildProcessCleanup primaryCleanup(primary);
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
        ChildProcessCleanup primaryCleanup(primary);
        launchPrimary(primary, id, 1000);
        QVERIFY2(primary.waitForStarted(3000), qPrintable(primary.errorString()));
        QVERIFY(waitForOutput(primary, "LOOP_START", 3000, primaryOutput));

        QProcess secondary;
        ChildProcessCleanup secondaryCleanup(secondary);
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
    const int runMs = QByteArray(argv[3]).toInt();
    const QString releasePath = argc > 4 ? QString::fromLocal8Bit(argv[4]) : QString();
    QtSingleApplication app(id, argc, argv);
    if (QByteArray(argv[1]) == "--primary-frame") {
        auto *server = app.findChild<QLocalServer *>();
        if (!server || releasePath.isEmpty())
            qFatal("Frame barrier requires a server and a unique release path");
        // Connect before isRunning() installs the production receiver. Qt runs
        // direct slots in connection order. Peek only: the unchanged receiver
        // must still consume and acknowledge the original, complete frame.
        QObject::connect(server, &QLocalServer::newConnection, &app, [server, releasePath] {
            const auto sockets = server->findChildren<QLocalSocket *>(
                QString(), Qt::FindDirectChildrenOnly);
            if (sockets.size() != 1)
                qFatal("Frame barrier requires exactly one connected socket");
            auto *socket = sockets.first();
            QByteArray frame;
            QDataStream stream(&frame, QIODevice::WriteOnly);
            stream.writeBytes("probe", 5);
            QElapsedTimer frameTimer;
            frameTimer.start();
            while (socket->bytesAvailable() < frame.size()) {
                const int remaining = 3000 - static_cast<int>(frameTimer.elapsed());
                if (remaining <= 0 || !socket->waitForReadyRead(remaining))
                    qFatal("Frame barrier did not observe the complete message");
            }
            if (socket->peek(frame.size()) != frame)
                qFatal("Frame barrier observed an unexpected message");
            QElapsedTimer heldTimer;
            heldTimer.start();
            QTextStream(stdout) << "FRAME_QUEUED" << Qt::endl;
            while (!QFile::exists(releasePath) && heldTimer.elapsed() < 5000)
                QThread::msleep(5);
            if (!QFile::exists(releasePath))
                qFatal("Frame barrier release timed out");
            QTextStream(stdout) << "ACK_HELD_MS=" << heldTimer.elapsed() << Qt::endl;
        });
    }
    if (app.isRunning())
        return 2;

    QTextStream(stdout) << "SOCKET=" << app.findChild<QLocalServer *>()->serverName() << Qt::endl;

    QStringList received;
    QObject::connect(&app, &QtSingleApplication::messageReceived,
                     &app, [&received](const QString &message) {
                         received << message;
                         QTextStream(stdout) << "RECEIVED=" << message << Qt::endl;
                     });
    QTextStream(stdout) << "CLAIMED" << Qt::endl;
    if (!releasePath.isEmpty() && QByteArray(argv[1]) != "--primary-frame") {
        QTextStream(stdout) << "READY_TO_RECEIVE" << Qt::endl;
        QElapsedTimer barrierTimer;
        barrierTimer.start();
        while (!QFile::exists(releasePath) && barrierTimer.elapsed() < 5000)
            QThread::msleep(10);
        if (!QFile::exists(releasePath)) {
            qWarning().noquote() << "primary release barrier timed out:" << releasePath;
            return 4;
        }
        QTextStream(stdout) << "RELEASED" << Qt::endl;
    }
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
        QTextStream(stdout) << "SENDING" << Qt::endl;
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
    if (argc > 1 && QByteArray(argv[1]) == "--identity") {
        QtSingleApplication app(argc, argv);
        QTextStream(stdout) << app.id() << Qt::endl;
        return 0;
    }
    if (argc > 1 && (QByteArray(argv[1]) == "--primary"
                    || QByteArray(argv[1]) == "--primary-frame"))
        return runPrimary(argc, argv);
    if (argc > 1 && QByteArray(argv[1]) == "--probe")
        return runProbe(argc, argv);

    QApplication app(argc, argv);
    SingleInstanceStartupTest test;
    return QTest::qExec(&test, argc, argv);
}

#include "testSingleInstanceStartup.moc"
