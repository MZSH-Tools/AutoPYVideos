# 系统托盘模块
import sys
import os
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PySide6.QtCore import QObject, Signal, QProcess

from MainWindow import (MainWindow, IsPaused, SetPaused, PauseEmitter,
                        SetDelayedRestart, DelayedRestartEmitter,
                        SetDelayedQuit, DelayedQuitEmitter)


class TrayIcon(QObject):
    """系统托盘图标"""

    ShowWindowSignal = Signal()

    def __init__(self, App: QApplication):
        super().__init__()
        self.App = App
        self.MainWin = None
        self.TrayIcon = None
        self.SetupTray()

    def SetupTray(self):
        """初始化托盘图标"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray not available")
            return

        # 创建图标
        Pixmap = QPixmap(64, 64)
        Pixmap.fill(QColor(70, 130, 180))
        Painter = QPainter(Pixmap)
        Painter.setPen(QColor(255, 255, 255))
        Painter.drawText(Pixmap.rect(), 0x0084, "AV")
        Painter.end()
        Icon = QIcon(Pixmap)

        self.TrayIcon = QSystemTrayIcon(self)
        self.TrayIcon.setIcon(Icon)
        self.TrayIcon.setToolTip("AutoPYVideos Manager")

        Menu = QMenu()

        OpenAction = QAction("打开管理界面", Menu)
        OpenAction.triggered.connect(self.ShowMainWindow)
        Menu.addAction(OpenAction)

        Menu.addSeparator()

        # 延迟暂停菜单项（当前阶段完成后暂停）
        self.PauseAction = QAction("延迟暂停", Menu)
        self.PauseAction.setCheckable(True)
        self.PauseAction.setChecked(IsPaused)
        self.PauseAction.triggered.connect(self.TogglePause)
        Menu.addAction(self.PauseAction)
        # 监听暂停状态变化，更新菜单项
        PauseEmitter.Changed.connect(self.OnPauseChanged)

        Menu.addSeparator()

        # 立即重启
        RestartAction = QAction("立即重启", Menu)
        RestartAction.triggered.connect(self.Restart)
        Menu.addAction(RestartAction)

        # 延迟重启菜单项（当前流程完成后重启）
        self.DelayedRestartAction = QAction("延迟重启", Menu)
        self.DelayedRestartAction.setCheckable(True)
        self.DelayedRestartAction.setChecked(False)
        self.DelayedRestartAction.triggered.connect(self.ToggleDelayedRestart)
        Menu.addAction(self.DelayedRestartAction)
        # 监听延迟重启状态变化
        DelayedRestartEmitter.Changed.connect(self.OnDelayedRestartChanged)
        DelayedRestartEmitter.DoRestart.connect(self.DoSilentRestart)

        Menu.addSeparator()

        # 延迟退出菜单项（当前流程完成后退出）
        self.DelayedQuitAction = QAction("延迟退出", Menu)
        self.DelayedQuitAction.setCheckable(True)
        self.DelayedQuitAction.setChecked(False)
        self.DelayedQuitAction.triggered.connect(self.ToggleDelayedQuit)
        Menu.addAction(self.DelayedQuitAction)
        # 监听延迟退出状态变化
        DelayedQuitEmitter.Changed.connect(self.OnDelayedQuitChanged)
        DelayedQuitEmitter.DoQuit.connect(self.Quit)

        QuitAction = QAction("退出", Menu)
        QuitAction.triggered.connect(self.Quit)
        Menu.addAction(QuitAction)

        self.TrayIcon.setContextMenu(Menu)
        self.TrayIcon.activated.connect(self.OnTrayActivated)
        self.TrayIcon.show()

        # 首次运行：只创建 MainWindow 不显示（统一静默模式）
        self.MainWin = MainWindow()
        self.MainWin.Closed.connect(self.OnWindowClosed)

    def ShowMainWindow(self):
        """显示主窗口"""
        if self.MainWin is None:
            self.MainWin = MainWindow()
            self.MainWin.Closed.connect(self.OnWindowClosed)

        self.MainWin.show()
        self.MainWin.raise_()
        self.MainWin.activateWindow()

    def OnWindowClosed(self):
        """窗口关闭时的处理"""
        pass

    def TogglePause(self, Checked: bool):
        """切换延迟暂停状态"""
        SetPaused(Checked)

    def OnPauseChanged(self, Paused: bool):
        """暂停状态变化时更新菜单项"""
        self.PauseAction.setChecked(Paused)

    def ToggleDelayedRestart(self, Checked: bool):
        """切换延迟重启状态"""
        SetDelayedRestart(Checked)

    def OnDelayedRestartChanged(self, DelayedRestart: bool):
        """延迟重启状态变化时更新菜单项"""
        self.DelayedRestartAction.setChecked(DelayedRestart)

    def ToggleDelayedQuit(self, Checked: bool):
        """切换延迟退出状态"""
        SetDelayedQuit(Checked)

    def OnDelayedQuitChanged(self, DelayedQuit: bool):
        """延迟退出状态变化时更新菜单项"""
        self.DelayedQuitAction.setChecked(DelayedQuit)

    def OnTrayActivated(self, Reason):
        """托盘图标被激活"""
        if Reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.ShowMainWindow()

    def DoSilentRestart(self):
        """执行静默重启"""
        if self.MainWin:
            self.MainWin.hide()
        self.TrayIcon.hide()
        # 启动新进程
        QProcess.startDetached(sys.executable, sys.argv, os.getcwd())
        self.App.quit()

    def Restart(self):
        """立即重启程序（静默）"""
        self.DoSilentRestart()

    def Quit(self):
        """退出程序"""
        if self.MainWin:
            self.MainWin.close()
        self.TrayIcon.hide()
        self.App.quit()
