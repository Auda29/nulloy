/********************************************************************
**  Nulloy Music Player, http://nulloy.com
**  Copyright (C) 2010-2024 Sergey Vlasov <sergey@vlasov.me>
**
**  This program can be distributed under the terms of the GNU
**  General Public License version 3.0 as published by the Free
**  Software Foundation and appearing in the file LICENSE.GPL3
**  included in the packaging of this file.  Please review the
**  following information to ensure the GNU General Public License
**  version 3.0 requirements will be met:
**
**  http://www.gnu.org/licenses/gpl-3.0.html
**
*********************************************************************/

#include "mainWindow.h"

#include "common.h"
#include "settings.h"
#include "windowGeometry.h"

#ifndef _N_NO_SKINS_
#include <QUiLoader>

#endif

#ifdef Q_OS_WIN
#include <dwmapi.h>
#include <windows.h>

#include "w7TaskBar.h"
// These window messages are not defined in dwmapi.h
#ifndef WM_DWMCOMPOSITIONCHANGED
#define WM_DWMCOMPOSITIONCHANGED 0x031E
#endif
#endif

#include <QApplication>
#include <QScreen>
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
#include <QDesktopWidget>
#endif
#include <QEvent>
#include <QFile>
#include <QIcon>
#include <QLayout>
#include <QTime>
#include <QTimer>
#include <QWindowStateChangeEvent>

#define RESIZE_BORDER 5

NMainWindow::NMainWindow(const QString &uiFile, QWidget *parent, QUiLoader *skinUiLoader) : QDialog(parent)
{
#ifdef Q_OS_WIN
    m_framelessShadow = false;
#endif

    setObjectName("mainWindow");

#ifndef _N_NO_SKINS_
    QUiLoader loader;
    QFile formFile(uiFile);
    formFile.open(QIODevice::ReadOnly);
    QWidget *form = (skinUiLoader ? skinUiLoader : &loader)->load(&formFile);
    formFile.close();

    QVBoxLayout *layout = new QVBoxLayout;
    layout->addWidget(form->layout()->itemAt(0)->widget());
    layout->setContentsMargins(0, 0, 0, 0);
    setLayout(layout);
    setStyleSheet(form->styleSheet());
    form->setStyleSheet("");
    delete form;
#else
    Q_UNUSED(uiFile)
    Q_UNUSED(skinUiLoader)
    ui.setupUi(this);
#endif

    m_unmaximizedSize = QSize();
    m_unmaximizedPos = QPoint();
    m_isFullScreen = false;
    m_dragActive = false;
    m_resizeActive = false;
    m_resizeSection = Qt::NoSection;

    // enabling dragging window from any point
    QList<QWidget *> widgets = findChildren<QWidget *>();
    foreach (QWidget *widget, widgets)
        widget->installEventFilter(this);

    QIcon icon;
#ifdef Q_OS_LINUX
    icon = QIcon::fromTheme("nulloy");
#endif
    if (icon.isNull()) {
        icon.addFile(":icon.svg");
    }
    setWindowIcon(icon);

    QMetaObject::connectSlotsByName(this);

    const auto watchScreen = [this](QScreen *screen) {
        const auto connection = Qt::ConnectionType(Qt::QueuedConnection | Qt::UniqueConnection);
        connect(screen, &QScreen::availableGeometryChanged, this,
                &NMainWindow::ensureVisibleGeometry, connection);
        connect(screen, &QScreen::geometryChanged, this, &NMainWindow::ensureVisibleGeometry,
                connection);
    };
    for (QScreen *screen : QGuiApplication::screens())
        watchScreen(screen);
    // Register a new screen synchronously while its pointer is valid, but defer
    // recovery until Qt has finished updating the screen list and work areas.
    connect(qApp, &QGuiApplication::screenAdded, this, watchScreen);
    connect(qApp, &QGuiApplication::screenAdded, this, &NMainWindow::ensureVisibleGeometry,
            Qt::QueuedConnection);
    connect(qApp, &QGuiApplication::screenRemoved, this, &NMainWindow::ensureVisibleGeometry,
            Qt::QueuedConnection);
    connect(qApp, &QGuiApplication::primaryScreenChanged, this, &NMainWindow::ensureVisibleGeometry,
            Qt::QueuedConnection);
}

NMainWindow::~NMainWindow() {}

bool NMainWindow::isFullSceen()
{
    return m_isFullScreen;
}

void NMainWindow::loadSettings()
{
    const QStringList posList = NSettings::instance()->value("Position").toStringList();
    if (posList.size() == 2) {
        bool xValid = false;
        bool yValid = false;
        const int x = posList.at(0).toInt(&xValid);
        const int y = posList.at(1).toInt(&yValid);
        if (xValid && yValid)
            move(x, y);
    }

    QSize storedSize(430, 350);
    const QStringList sizeList = NSettings::instance()->value("Size").toStringList();
    if (sizeList.size() == 2) {
        bool widthValid = false;
        bool heightValid = false;
        const int width = sizeList.at(0).toInt(&widthValid);
        const int height = sizeList.at(1).toInt(&heightValid);
        if (widthValid && heightValid && width > 0 && height > 0)
            storedSize = QSize(width, height);
    }
    resize(storedSize);
    ensureVisibleGeometry();

    if (NSettings::instance()->value("Maximized").toBool()) {
        m_unmaximizedPos = pos();
        m_unmaximizedSize = size();
        toggleMaximize();
    }
}

void NMainWindow::saveSettings()
{
    NSettings::instance()->setValue("Maximized", isMaximized());

    QPoint _pos = pos();
    QSize _size = size();
    if (m_unmaximizedSize.isValid()) {
        _pos = m_unmaximizedPos;
        _size = m_unmaximizedSize;
    }

    NSettings::instance()->setValue("Position", QStringList() << QString::number(_pos.x())
                                                              << QString::number(_pos.y()));
    NSettings::instance()->setValue("Size", QStringList() << QString::number(_size.width())
                                                          << QString::number(_size.height()));
}

void NMainWindow::ensureVisibleGeometry()
{
    QList<QRect> availableScreens;
    QScreen *primary = QGuiApplication::primaryScreen();
    if (primary)
        availableScreens.append(primary->availableGeometry());
    for (QScreen *screen : QGuiApplication::screens()) {
        if (screen != primary)
            availableScreens.append(screen->availableGeometry());
    }
    const bool normal = !isMinimized() && !isMaximized() && !isFullScreen();
    QRect current(pos(), size());
    if (m_unmaximizedSize.isValid())
        current = QRect(m_unmaximizedPos, m_unmaximizedSize);
    else if (!normal && normalGeometry().isValid())
        current = normalGeometry();
    const QRect restored = NWindowGeometry::restored(current, availableScreens);
    if (!normal) {
        // Do not unminimize, unmaximize, or reveal a tray-hidden window on hotplug.
        if (restored != current) {
            m_unmaximizedPos = restored.topLeft();
            m_unmaximizedSize = restored.size();
        }
    } else {
        m_unmaximizedPos = QPoint();
        m_unmaximizedSize = QSize();
        if (restored != QRect(pos(), size())) {
            resize(restored.size());
            move(restored.topLeft());
        }
    }
}

void NMainWindow::show()
{
    if (isMaximized()) {
        showMaximized();
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
        setGeometry(QApplication::desktop()->availableGeometry(this));
        showMaximized();
#endif
    } else {
        showNormal();
        ensureVisibleGeometry();
    }
}

void NMainWindow::toggleMaximize()
{
    if (isMaximized()) {
        // Native window state notifications can clear these during showNormal().
        const QSize normalSize = m_unmaximizedSize;
        const QPoint normalPos = m_unmaximizedPos;
        showNormal();
        if (normalSize.isValid()) {
            resize(normalSize);
            move(normalPos);
        }
        m_unmaximizedPos = QPoint();
        m_unmaximizedSize = QSize();
        ensureVisibleGeometry();
    } else {
        m_unmaximizedPos = pos();
        m_unmaximizedSize = size();
        showMaximized();
#if defined(Q_OS_WIN) && QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
        setGeometry(QApplication::desktop()->availableGeometry(this));
        showMaximized();
#endif
    }

    emit fullScreenEnabled(false);
    emit maximizeEnabled(isMaximized());
}

void NMainWindow::toggleFullScreen()
{
    if (!m_isFullScreen) {
        if (!m_unmaximizedSize.isValid()) {
            m_unmaximizedSize = size();
            m_unmaximizedPos = pos();
        }
        QDialog::showFullScreen();
    } else {
        QPoint _pos = m_unmaximizedPos;
        QSize _size = m_unmaximizedSize;
        QDialog::showNormal();
        m_unmaximizedPos = _pos;
        m_unmaximizedSize = _size;
        if (m_unmaximizedSize.isValid()) {
            resize(m_unmaximizedSize);
            move(m_unmaximizedPos);
            m_unmaximizedSize = QSize();
            m_unmaximizedPos = QPoint();
        }
        ensureVisibleGeometry();
    }

    m_isFullScreen = !m_isFullScreen;
    emit fullScreenEnabled(m_isFullScreen);
}

void NMainWindow::setTitle(QString title)
{
    setWindowTitle(title);
    emit newTitle(title);
}

void NMainWindow::changeEvent(QEvent *event)
{
    QWidget::changeEvent(event);

    emit focusChanged(isActiveWindow());

    if (windowFlags() & Qt::FramelessWindowHint)
        setAttribute(Qt::WA_Hover, true);

    if (event->type() == QEvent::WindowStateChange) {
        QWindowStateChangeEvent *stateEvent = static_cast<QWindowStateChangeEvent *>(event);
        if (stateEvent->oldState() == Qt::WindowNoState && isMaximized()) {
            if (!m_unmaximizedSize.isValid()) {
                m_unmaximizedPos = pos();
                m_unmaximizedSize = size();
            }
        } else if (!isMaximized() && !isMinimized() && !isFullScreen()) {
            // Native restore can bypass show()/toggleMaximize(). Wait for Qt to
            // finish applying the window manager's geometry before correcting it.
            QTimer::singleShot(0, this, [this]() {
                if (!isMaximized() && !isMinimized() && !isFullScreen()) {
                    m_isFullScreen = false;
                    ensureVisibleGeometry();
                }
            });
        }
    }
}

Qt::WindowFrameSection NMainWindow::getSection(const QPoint &pos)
{
    int x = pos.x();
    int y = pos.y();
    QRect r = rect();
    int left = r.left();
    int right = r.right();
    int top = r.top();
    int bottom = r.bottom();

    if ((x >= left && x < left + RESIZE_BORDER) && (y >= top && y < top + RESIZE_BORDER)) {
        return Qt::TopLeftSection;
    } else if ((x < right && x >= right - RESIZE_BORDER) && (y >= top && y < top + RESIZE_BORDER)) {
        return Qt::TopRightSection;
    } else if ((x < right && x >= right - RESIZE_BORDER) &&
               (y < bottom && y >= bottom - RESIZE_BORDER)) {
        return Qt::BottomRightSection;
    } else if ((x >= left && x < left + RESIZE_BORDER) &&
               (y < bottom && y >= bottom - RESIZE_BORDER)) {
        return Qt::BottomLeftSection;
    } else if (y >= top && y < top + RESIZE_BORDER) {
        return Qt::TopSection;
    } else if (x < right && x >= right - RESIZE_BORDER) {
        return Qt::RightSection;
    } else if (y < bottom && y >= bottom - RESIZE_BORDER) {
        return Qt::BottomSection;
    } else if (x >= left && x < left + RESIZE_BORDER) {
        return Qt::LeftSection;
    } else {
        return Qt::NoSection;
    }
}

void NMainWindow::updateCursor(Qt::WindowFrameSection section)
{
    switch (section) {
        case Qt::TopLeftSection:
        case Qt::BottomRightSection:
            setCursor(Qt::SizeFDiagCursor);
            break;
        case Qt::TopRightSection:
        case Qt::BottomLeftSection:
            setCursor(Qt::SizeBDiagCursor);
            break;
        case Qt::TopSection:
        case Qt::BottomSection:
            setCursor(Qt::SizeVerCursor);
            break;
        case Qt::RightSection:
        case Qt::LeftSection:
            setCursor(Qt::SizeHorCursor);
            break;
        default:
            setCursor(Qt::ArrowCursor);
    }
}

bool NMainWindow::event(QEvent *event)
{
    if (event->type() == QEvent::HoverMove && !m_dragActive) {
        QPoint pos = static_cast<QHoverEvent *>(event)->pos();
        if (!m_resizeActive) {
            m_resizeSection = getSection(pos);
            updateCursor(m_resizeSection);
            return true;
        }
    }

    return QDialog::event(event);
}

bool NMainWindow::eventFilter(QObject *, QEvent *event)
{
    if (event->type() == QEvent::MouseButtonPress) {
        m_dragActive = false;
        m_resizeActive = false;
    }

    return false;
}

void NMainWindow::mousePressEvent(QMouseEvent *event)
{
    activateWindow();
    m_dragActive = false;
    m_resizeActive = false;
    if (event->button() == Qt::LeftButton) {
        if (m_resizeSection != Qt::NoSection) {
            m_resizeActive = true;
            m_resizePoint = event->pos();
            m_resizeRect = rect();
        } else {
            m_dragActive = true;
            m_dragPoint = event->globalPos() - frameGeometry().topLeft();
        }
        event->accept();
    }
}

void NMainWindow::mouseMoveEvent(QMouseEvent *event)
{
    if ((event->buttons() & Qt::LeftButton) && !isMaximized()) {
        if (m_dragActive) {
            move(event->globalPos() - m_dragPoint);
            event->accept();
        } else if (m_resizeActive) {
            QRect g = geometry();
            QRect origR = geometry();
            QPoint pos = event->globalPos() - m_resizePoint;
            switch (m_resizeSection) {
                case Qt::TopLeftSection:
                    g.setTopLeft(pos + m_resizeRect.topLeft());
                    break;
                case Qt::TopRightSection:
                    g.setTopRight(pos + m_resizeRect.topRight());
                    break;
                case Qt::BottomRightSection:
                    g.setBottomRight(pos + m_resizeRect.bottomRight());
                    break;
                case Qt::BottomLeftSection:
                    g.setBottomLeft(pos + m_resizeRect.bottomLeft());
                    break;
                case Qt::TopSection:
                    g.setTop(pos.y() + m_resizeRect.top());
                    break;
                case Qt::RightSection:
                    g.setRight(pos.x() + m_resizeRect.right());
                    break;
                case Qt::BottomSection:
                    g.setBottom(pos.y() + m_resizeRect.bottom());
                    break;
                case Qt::LeftSection:
                    g.setLeft(pos.x() + m_resizeRect.left());
                    break;
                default:
                    break;
            }
            QSize min = QLayout::closestAcceptableSize(this, g.size());
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
            QRect desk = screen()->availableGeometry();
#else
            QRect desk = QApplication::desktop()->availableGeometry(this);
#endif
            if (min.width() > g.width() || min.height() > g.height() || desk.left() > g.left() ||
                desk.right() < g.right() || desk.top() > g.top() || desk.bottom() < g.bottom()) {
                switch (m_resizeSection) {
                    case Qt::TopLeftSection:
                    case Qt::TopSection:
                    case Qt::LeftSection:
                        if (min.width() > g.width()) {
                            g.setLeft(origR.left());
                        } else if (desk.left() > g.left()) {
                            g.setLeft(desk.left());
                        }
                        if (min.height() > g.height()) {
                            g.setTop(origR.top());
                        } else if (desk.top() > g.top()) {
                            g.setTop(desk.top());
                        }
                        break;
                    case Qt::TopRightSection:
                        if (min.width() > g.width()) {
                            g.setRight(origR.right());
                        } else if (desk.right() < g.right()) {
                            g.setRight(desk.right());
                        }
                        if (min.height() > g.height()) {
                            g.setTop(origR.top());
                        } else if (desk.top() > g.top()) {
                            g.setTop(desk.top());
                        }
                        break;
                    case Qt::BottomRightSection:
                    case Qt::BottomSection:
                    case Qt::RightSection:
                        if (min.width() > g.width()) {
                            g.setRight(origR.right());
                        } else if (desk.right() < g.right()) {
                            g.setRight(desk.right());
                        }
                        if (min.height() > g.height()) {
                            g.setBottom(origR.bottom());
                        } else if (desk.bottom() < g.bottom()) {
                            g.setBottom(desk.bottom());
                        }
                        break;
                    case Qt::BottomLeftSection:
                        if (min.width() > g.width()) {
                            g.setLeft(origR.left());
                        } else if (desk.left() > g.left()) {
                            g.setLeft(desk.left());
                        }
                        if (min.height() > g.height()) {
                            g.setBottom(origR.bottom());
                        } else if (desk.bottom() < g.bottom()) {
                            g.setBottom(desk.bottom());
                        }
                        break;
                    default:
                        break;
                }
            }
            setGeometry(g);
        }
    }
}

void NMainWindow::mouseReleaseEvent(QMouseEvent *event)
{
    m_resizeActive = false;
    m_dragActive = false;
    updateCursor(Qt::NoSection);

    QDialog::mouseReleaseEvent(event);
}

void NMainWindow::wheelEvent(QWheelEvent *event)
{
    QDialog::wheelEvent(event);

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    if (event->angleDelta().y()) {
        emit scrolled(event->angleDelta().y());
    }
#else
    if (event->orientation() == Qt::Vertical) {
        emit scrolled(event->delta());
    }
#endif
}

void NMainWindow::showPlaybackControls(bool enable)
{
    NSettings::instance()->setValue("ShowPlaybackControls", enable);
    emit showPlaybackControlsEnabled(enable);
}

void NMainWindow::resizeEvent(QResizeEvent *event)
{
    QDialog::resizeEvent(event);
    emit resized();
}

void NMainWindow::closeEvent(QCloseEvent *event)
{
    accept();
    QDialog::closeEvent(event);
    emit closed();
}

#ifdef Q_OS_WIN
bool _DwmIsCompositionEnabled()
{
    HMODULE library = LoadLibrary(L"dwmapi.dll");
    bool result = false;
    if (library) {
        BOOL enabled = false;
        // clang-format off
        HRESULT (WINAPI *pFn)(BOOL *enabled) = (HRESULT (WINAPI *)(BOOL *enabled))(GetProcAddress(library, "DwmIsCompositionEnabled"));
        // clang-format on
        result = SUCCEEDED(pFn(&enabled)) && enabled;
        FreeLibrary(library);
    }
    return result;
}

void NMainWindow::setFramelessShadow(bool enabled)
{
    if (enabled != m_framelessShadow) {
        m_framelessShadow = enabled;
        updateFramelessShadow();
    }
}

void NMainWindow::updateFramelessShadow()
{
    DWORD version = GetVersion();
    DWORD major = (DWORD)(LOBYTE(LOWORD(version))); // major = 6 for vista/7/2008

    if (_DwmIsCompositionEnabled() && m_framelessShadow && major == 6) {
        SetClassLongPtr((HWND)winId(), GCL_STYLE,
                        GetClassLongPtr((HWND)winId(), GCL_STYLE) | CS_DROPSHADOW);
    } else {
        SetClassLongPtr((HWND)winId(), GCL_STYLE,
                        GetClassLongPtr((HWND)winId(), GCL_STYLE) & ~CS_DROPSHADOW);
    }

    hide();
    show();
}

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
bool NMainWindow::nativeEvent(const QByteArray &eventType, void *message, qintptr *result)
#else
bool NMainWindow::nativeEvent(const QByteArray &eventType, void *message, long *result)
#endif
{
    MSG *msg = reinterpret_cast<MSG *>(message);
    if (msg->message == WM_DWMCOMPOSITIONCHANGED) {
        updateFramelessShadow();
        return true;
    } else {
        return NW7TaskBar::instance()->nativeEvent(eventType, message, result);
    }
}
#endif

bool NMainWindow::isOnTop()
{
#ifdef Q_OS_WIN
    DWORD dwExStyle = GetWindowLong((HWND)this->winId(), GWL_EXSTYLE);
    return (dwExStyle & WS_EX_TOPMOST);
#else
    Qt::WindowFlags flags = windowFlags();
    return (flags & Qt::WindowStaysOnTopHint);
#endif
}

void NMainWindow::setOnTop(bool onTop)
{
#ifdef Q_OS_WIN
    if (onTop)
        SetWindowPos((HWND)this->winId(), HWND_TOPMOST, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    else
        SetWindowPos((HWND)this->winId(), HWND_NOTOPMOST, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
#else
    Qt::WindowFlags flags = windowFlags();
    if (onTop) {
        flags |= Qt::WindowStaysOnTopHint;
    } else {
        flags &= ~Qt::WindowStaysOnTopHint;
    }
    setWindowFlags(flags);
    show();
#endif

#ifdef Q_OS_WIN
    NW7TaskBar::instance()->setWindow(this);
#endif
}
