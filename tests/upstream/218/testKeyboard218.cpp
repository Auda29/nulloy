#include "action.h"
#include "playbackEngineGstreamer.h"
#include "playlistWidget.h"
#include "pluginLoader.h"
#include "settings.h"
#include "tagReaderTaglib.h"
#include "trackInfoReader.h"
#include <QLineEdit>
#include <QVBoxLayout>
#include <QtTest>
#include <memory>

static NPlaybackEngineGStreamer *testEngine = nullptr;
NPlugin *NPluginLoader::getPlugin(N::PluginType type)
{
    return type == N::PlaybackEngine ? testEngine : nullptr;
}

class TestKeyboard218 : public QObject
{
    Q_OBJECT
    QTemporaryDir directory;
    QStringList files;
    std::unique_ptr<NPlaybackEngineGStreamer> engine;
    std::unique_ptr<NTagReaderTaglib> tags;
    std::unique_ptr<NTrackInfoReader> reader;
    std::unique_ptr<QWidget> window;
    NPlaylistWidget *playlist = nullptr;
    QLineEdit *editor = nullptr;
    NAction *remove = nullptr;
    NAction *speedReset = nullptr;
private slots:
    void initTestCase()
    {
        QVERIFY(directory.isValid());
        for (int i = 0; i < 3; ++i) {
            const QString path = directory.filePath(QString("track-%1.wav").arg(i));
            QFile file(path);
            QVERIFY(file.open(QIODevice::WriteOnly));
            QDataStream stream(&file);
            stream.setByteOrder(QDataStream::LittleEndian);
            const quint32 bytes = 8000 * 30 * 2;
            stream.writeRawData("RIFF", 4);
            stream << quint32(36 + bytes);
            stream.writeRawData("WAVEfmt ", 8);
            stream << quint32(16) << quint16(1) << quint16(1) << quint32(8000) << quint32(16000)
                   << quint16(2) << quint16(16);
            stream.writeRawData("data", 4);
            stream << bytes;
            const QByteArray silence(bytes, '\0');
            QCOMPARE(stream.writeRawData(silence.constData(), bytes), int(bytes));
            files << path;
        }
    }
    void init()
    {
        NSettings::instance()->clear();
        delete NSettings::instance();
        engine.reset(new NPlaybackEngineGStreamer);
        engine->init();
        testEngine = engine.get();
        tags.reset(new NTagReaderTaglib);
        tags->init();
        reader.reset(new NTrackInfoReader(tags.get()));
        window.reset(new QWidget);
        auto *layout = new QVBoxLayout(window.get());
        playlist = new NPlaylistWidget(window.get());
        playlist->setTrackInfoReader(reader.get());
        editor = new QLineEdit(window.get());
        layout->addWidget(playlist);
        layout->addWidget(editor);
        remove = new NAction(window.get());
        remove->setShortcuts(
            NSettings::instance()->value("Shortcuts/RemoveFromPlaylistAction").toStringList());
        connect(remove, &QAction::triggered, playlist, &NPlaylistWidget::removeSelected);
        window->addAction(remove); // same window-level scope as NPlayer::initActions
        speedReset = new NAction(window.get());
        speedReset->setShortcuts(
            NSettings::instance()->value("Shortcuts/SpeedResetAction").toStringList());
        connect(speedReset, &QAction::triggered, this, [this]() { engine->setSpeed(1.0); });
        window->addAction(speedReset);
        playlist->setFiles(files);
        window->resize(640, 400);
        window->show();
        window->activateWindow();
        playlist->setFocus();
        QTRY_VERIFY(playlist->hasFocus());
        connect(engine.get(), &NPlaybackEngineGStreamer::message, this,
                [](N::MessageIcon, const QString &, const QString &message) {
                    QFAIL(qPrintable(message));
                });
    }
    void cleanup()
    {
        engine->stop();
        window.reset();
        playlist = nullptr;
        reader.reset();
        tags.reset();
        engine.reset();
        testEngine = nullptr;
    }
    void activatesSelected_data()
    {
        QTest::addColumn<int>("key");
        QTest::addColumn<bool>("playing");
        for (int key : {int(Qt::Key_Return), int(Qt::Key_Enter)})
            for (bool playing : {false, true}) {
                const QByteArray name = QByteArray::number(key) + '-' + QByteArray::number(playing);
                QTest::newRow(name.constData()) << key << playing;
            }
    }
    void activatesSelected()
    {
        QFETCH(int, key);
        QFETCH(bool, playing);
        playlist->playRow(0);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QTRY_COMPARE(playlist->playingRow(), 0);
        if (!playing)
            engine->stop();
        playlist->setCurrentRow(2);
        QCOMPARE(playlist->playingRow(), 0);
        QSignalSpy changed(engine.get(), &NPlaybackEngineGStreamer::mediaChanged);
        QTest::keyClick(playlist, Qt::Key(key),
                        key == Qt::Key_Enter ? Qt::KeypadModifier : Qt::NoModifier);
        QTRY_COMPARE(playlist->playingRow(), 2);
        QTRY_COMPARE(engine->state(), N::PlaybackPlaying);
        QCOMPARE(engine->currentMedia(), files[2]);
        QTest::qWait(150);
        QCOMPARE(changed.count(), 1);
    }
    void editorDoesNotActivate_data()
    {
        QTest::addColumn<int>("key");
        QTest::newRow("return") << int(Qt::Key_Return);
        QTest::newRow("keypad-enter") << int(Qt::Key_Enter);
    }
    void editorDoesNotActivate()
    {
        QFETCH(int, key);
        playlist->playRow(0);
        QTRY_COMPARE(playlist->playingRow(), 0);
        playlist->setCurrentRow(2);
        editor->setFocus();
        QTRY_VERIFY(editor->hasFocus());
        QSignalSpy changed(engine.get(), &NPlaybackEngineGStreamer::mediaChanged);
        QTest::keyClick(editor, Qt::Key(key),
                        key == Qt::Key_Enter ? Qt::KeypadModifier : Qt::NoModifier);
        QTest::qWait(150);
        QCOMPARE(changed.count(), 0);
        QCOMPARE(playlist->playingRow(), 0);
    }
    void removesSelection_data()
    {
        QTest::addColumn<bool>("backspace");
        QTest::newRow("default-delete") << false;
        QTest::newRow("custom-backspace") << true;
    }
    void removesSelection()
    {
        QFETCH(bool, backspace);
        if (backspace) {
            // Backspace is already SpeedReset by default. A non-conflicting
            // user configuration must free it before binding removal.
            speedReset->setShortcuts({});
            remove->setShortcuts({"Backspace"});
        }
        const auto key = backspace ? Qt::Key_Backspace : Qt::Key_Delete;
        playlist->setCurrentRow(1);
        QSignalSpy triggered(remove, &QAction::triggered);
        editor->setText("abc");
        editor->setCursorPosition(backspace ? 3 : 0);
        editor->setFocus();
        QTRY_VERIFY(editor->hasFocus());
        QTest::keyClick(editor, key);
        QCOMPARE(editor->text(), backspace ? QString("ab") : QString("bc"));
        QCOMPARE(playlist->count(), 3);
        QCOMPARE(triggered.count(), 0);
        playlist->setFocus();
        QTRY_VERIFY(playlist->hasFocus());
        QTest::keyClick(playlist, key);
        QCOMPARE(triggered.count(), 1);
        QCOMPARE(playlist->count(), 2);
        QCOMPARE(playlist->item(0)->data(N::PathRole).toString(), files[0]);
        QCOMPARE(playlist->item(1)->data(N::PathRole).toString(), files[2]);
    }
    void defaultBackspaceKeepsPlaylist()
    {
        QCOMPARE(speedReset->shortcuts(), QStringList{"Backspace"});
        QCOMPARE(remove->sequences(), QList<QKeySequence>{QKeySequence(Qt::Key_Delete)});
        playlist->setCurrentRow(1);
        QSignalSpy reset(speedReset, &QAction::triggered);
        QTest::keyClick(playlist, Qt::Key_Backspace);
        QCOMPARE(reset.count(), 1);
        QCOMPARE(playlist->count(), 3);
    }
};
QTEST_MAIN(TestKeyboard218)
#include "testKeyboard218.moc"
