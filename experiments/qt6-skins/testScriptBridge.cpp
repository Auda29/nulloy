// SPDX-License-Identifier: GPL-3.0-only
#include "scriptBridge.h"
#include "label.h"
#include <QBoxLayout>
#include <QPushButton>
#include <QSplitter>
#include <QtTest>

class ScriptBridgeTest : public QObject
{
    Q_OBJECT
private slots:
    void propertiesAndMethods();
    void signalSyntax();
    void layoutAndValues();
    void independentDoubleClicks();
};

void ScriptBridgeTest::propertiesAndMethods()
{
    NLabel label;
    QJSEngine engine;
    ScriptBridge bridge(&engine);
    engine.globalObject().setProperty("w", bridge.wrap(&label));
    auto result = engine.evaluate("w.text = 'Track ä'; w.setFontSize(12); w.move(20,30); w.resize(240,40); w.windowFlags |= 0x800; w.pos.x");
    QVERIFY2(!result.isError(), qPrintable(result.toString()));
    QCOMPARE(label.text(), QString::fromUtf8("Track ä"));
    QCOMPARE(label.font().pixelSize(), 12);
    QCOMPARE(label.size(), QSize(240, 40));
    QCOMPARE(result.toInt(), 20);
    QVERIFY(label.windowFlags() & Qt::FramelessWindowHint);
    engine.collectGarbage();
    QCOMPARE(label.text(), QString::fromUtf8("Track ä"));
}

void ScriptBridgeTest::signalSyntax()
{
    QPushButton button;
    QJSEngine engine;
    ScriptBridge bridge(&engine);
    engine.globalObject().setProperty("button", bridge.wrap(&button));
    auto result = engine.evaluate("var receiver={count:0, run:function(){++this.count}}; button['clicked()'].connect(receiver, 'run');");
    QVERIFY2(!result.isError(), qPrintable(result.toString()));
    button.click();
    QCOMPARE(engine.evaluate("receiver.count").toInt(), 1);
    button.setCheckable(true);
    result = engine.evaluate("var checkedValue=null; button['clicked(bool)'].connect(function(v){checkedValue=v});");
    QVERIFY2(!result.isError(), qPrintable(result.toString()));
    button.click();
    QVERIFY(engine.evaluate("checkedValue === true").toBool());
    button.click();
    QVERIFY(engine.evaluate("checkedValue === false").toBool());
}

void ScriptBridgeTest::layoutAndValues()
{
    QWidget window;
    auto layout = new QVBoxLayout(&window);
    auto button = new QPushButton(&window);
    layout->addWidget(button);
    QSplitter splitter;
    splitter.addWidget(new QWidget);
    splitter.addWidget(new QWidget);
    splitter.resize(400, 100);
    QJSEngine engine;
    ScriptBridge bridge(&engine);
    engine.globalObject().setProperty("w", bridge.wrap(&window));
    engine.globalObject().setProperty("b", bridge.wrap(button));
    engine.globalObject().setProperty("s", bridge.wrap(&splitter));
    auto result = engine.evaluate("w.layout().setContentsMargins(1,2,3,4); var m=w.layout().contentsMargins(); m.right=7; w.layout().setContentsMargins(m); w.layout().insertSpacing(1,0); w.layout().setSpacingAt(1,9); s.setSizes([100,200]); var a=s.sizes(); b.parentWidget().layout().setSpacing(6); a.length");
    QVERIFY2(!result.isError(), qPrintable(result.toString()));
    QCOMPARE(layout->contentsMargins(), QMargins(1,2,7,4));
    QCOMPARE(layout->spacing(), 6);
    QCOMPARE(layout->itemAt(1)->spacerItem()->sizeHint().height(), 9);
    QCOMPARE(result.toInt(), 2);
    QVERIFY(splitter.sizes()[1] > splitter.sizes()[0]);
}

void ScriptBridgeTest::independentDoubleClicks()
{
    QWidget first, second;
    QJSEngine engine;
    ScriptBridge bridge(&engine);
    engine.globalObject().setProperty("first", bridge.wrap(&first));
    engine.globalObject().setProperty("second", bridge.wrap(&second));
    auto result = engine.evaluate("var a=0,b=0; first.enableDoubleClick(); second.enableDoubleClick(); first.doubleClicked.connect(function(){++a}); second.doubleClicked.connect(function(){++b});");
    QVERIFY2(!result.isError(), qPrintable(result.toString()));
    QTest::mouseDClick(&first, Qt::LeftButton);
    QCOMPARE(engine.evaluate("a").toInt(), 1);
    QCOMPARE(engine.evaluate("b").toInt(), 0);
}

QTEST_MAIN(ScriptBridgeTest)
#include "testScriptBridge.moc"
