# 应用程序入口
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtCore import QObject, Signal

from Tray import TrayIcon


SERVER_NAME = "AutoPYVideos_Manager_SingleInstance"


class SingleInstanceServer(QObject):
    """单实例服务器，监听来自其他实例的唤醒请求"""
    ShowWindowRequested = Signal()

    def __init__(self):
        super().__init__()
        self.Server = QLocalServer(self)
        self.Server.newConnection.connect(self.OnNewConnection)

    def Start(self):
        """启动服务器"""
        # 先尝试清理可能残留的服务器
        QLocalServer.removeServer(SERVER_NAME)
        if not self.Server.listen(SERVER_NAME):
            print(f"Failed to start server: {self.Server.errorString()}")
            return False
        return True

    def OnNewConnection(self):
        """收到新连接（其他实例请求唤醒）"""
        Socket = self.Server.nextPendingConnection()
        if Socket:
            Socket.waitForReadyRead(1000)
            Data = Socket.readAll().data().decode()
            if Data == "SHOW":
                self.ShowWindowRequested.emit()
            Socket.disconnectFromServer()


def TryWakeExisting() -> bool:
    """尝试唤醒已存在的实例，返回是否成功"""
    Socket = QLocalSocket()
    Socket.connectToServer(SERVER_NAME)
    if Socket.waitForConnected(500):
        Socket.write(b"SHOW")
        Socket.waitForBytesWritten(500)
        Socket.disconnectFromServer()
        return True
    return False


class ManagerApp:
    """后台管理程序"""

    def __init__(self):
        self.App = None
        self.Tray = None
        self.Server = None

    def Run(self):
        """启动程序"""
        self.App = QApplication(sys.argv)
        self.App.setQuitOnLastWindowClosed(False)

        # 启动单实例服务器
        self.Server = SingleInstanceServer()
        if not self.Server.Start():
            return 1

        self.Tray = TrayIcon(self.App)

        # 连接唤醒信号
        self.Server.ShowWindowRequested.connect(self.Tray.ShowMainWindow)

        return self.App.exec()


def Main():
    """入口函数"""
    # 先创建 QApplication（QLocalSocket 需要）
    App = QApplication(sys.argv)

    # 尝试唤醒已存在的实例
    if TryWakeExisting():
        print("Waking existing instance...")
        sys.exit(0)

    # 没有已存在的实例，正常启动
    App.setQuitOnLastWindowClosed(False)

    Manager = ManagerApp()
    Manager.App = App

    # 启动单实例服务器
    Manager.Server = SingleInstanceServer()
    if not Manager.Server.Start():
        sys.exit(1)

    Manager.Tray = TrayIcon(App)
    Manager.Server.ShowWindowRequested.connect(Manager.Tray.ShowMainWindow)

    sys.exit(App.exec())
