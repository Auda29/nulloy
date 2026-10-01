// SPDX-License-Identifier: GPL-3.0-only
#include "playbackEngineGstreamer.h"
#include <QtTest>

namespace NCore
{
    void cArgs(int *argc, const char ***argv)
    {
        static const char *args[] = {"testPlaybackFileAccess", nullptr};
        *argc = 1;
        *argv = args;
    }
}

class TestPlaybackFileAccess : public QObject
{
    Q_OBJECT
private slots:
    void suspendAndRestore_data()
    {
        QTest::addColumn<int>("state");
        QTest::addColumn<bool>("replace");
        for (int state : {int(N::PlaybackPlaying), int(N::PlaybackPaused), int(N::PlaybackStopped)})
            for (bool replace : {false, true})
                QTest::newRow(qPrintable(QString("state-%1-replace-%2").arg(state).arg(replace)))
                    << state << replace;
    }

    void suspendAndRestore()
    {
        QFETCH(int, state);
        QFETCH(bool, replace);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        QStringList files;
        for (int n = 0; n < 2; ++n) {
            const QString path = directory.filePath(QString("tone-%1.wav").arg(n));
            QFile file(path);
            QVERIFY(file.open(QIODevice::WriteOnly));
            QDataStream out(&file);
            out.setByteOrder(QDataStream::LittleEndian);
            const int frames = 8 * 48000;
            out.writeRawData("RIFF", 4);
            out << quint32(36 + frames * 2);
            out.writeRawData("WAVEfmt ", 8);
            out << quint32(16) << quint16(1) << quint16(1) << quint32(48000) << quint32(96000)
                << quint16(2) << quint16(16);
            out.writeRawData("data", 4);
            out << quint32(frames * 2);
            for (int i = 0; i < frames; ++i) out << qint16(i % 48 < 24 ? 8192 : -8192);
            QCOMPARE(out.status(), QDataStream::Ok);
            files << path;
        }
        NPlaybackEngineGStreamer engine;
        engine.init();
        QVERIFY(qobject_cast<NPlaybackFileAccessInterface *>(&engine));
        QSignalSpy errors(&engine, &NPlaybackEngineGStreamer::message);
        engine.setMedia(files[0], 10);
        engine.play();
        QTRY_VERIFY(engine.position() > 0.05);
        engine.setPosition(0.3);
        QTest::qWait(150);
        QTRY_VERIFY(engine.position() >= 0.29);
        if (state == N::PlaybackPaused) engine.pause();
        if (state == N::PlaybackStopped) engine.stop();
        const qreal position = engine.position();
        const qint64 duration = engine.durationMsec();
        QSignalSpy states(&engine, &NPlaybackEngineGStreamer::stateChanged);
        QSignalSpy positions(&engine, &NPlaybackEngineGStreamer::positionChanged);
        QSignalSpy media(&engine, &NPlaybackEngineGStreamer::mediaChanged);
        engine.suspendFileAccess();
        QTest::qWait(100);
        QCOMPARE(int(engine.state()), state);
        QCOMPARE(engine.position(), position);
        QCOMPARE(engine.durationMsec(), duration);
        QCOMPARE(states.count(), 0);
        QCOMPARE(positions.count(), 0);
        QCOMPARE(media.count(), 0);
        // Renaming this generated fixture exercises native reader release; it
        // is not a recycle-bin test and never touches user media.
        const QString parked = directory.filePath("parked.wav");
        QVERIFY(QFile::rename(files[0], parked));
        if (!replace) QVERIFY(QFile::rename(parked, files[0]));
        const QString target = files[replace ? 1 : 0];
        const qreal restored = replace ? 0.0 : position;
        engine.restoreFileAccess(target, replace ? 20 : 10, restored, N::PlaybackState(state));
        QCOMPARE(engine.currentMedia(), target);
        QCOMPARE(int(engine.state()), state);
        QCOMPARE(engine.position(), restored);
        QCOMPARE(media.count(), replace ? 1 : 0);
        QTest::qWait(300);
        QTRY_COMPARE(int(engine.state()), state);
        if (state != N::PlaybackPlaying) QVERIFY(qAbs(engine.position() - restored) < 0.015);
        QCOMPARE(media.count(), replace ? 1 : 0);
        engine.play();
        QTRY_COMPARE(engine.state(), N::PlaybackPlaying);
        QTRY_VERIFY(engine.position() > restored + 0.01);
        QCOMPARE(engine.currentMedia(), target);
        QCOMPARE(media.count(), replace ? 1 : 0);
        QVERIFY(errors.isEmpty());
        engine.stop();
    }
};

QTEST_GUILESS_MAIN(TestPlaybackFileAccess)
#include "testPlaybackFileAccess.moc"
