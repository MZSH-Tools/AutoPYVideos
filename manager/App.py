# 应用程序入口
import sys
from PySide6.QtWidgets import QApplication

from Tray import TrayIcon


class ManagerApp:
    """后台管理程序"""

    def __init__(self):
        self.App = None
        self.Tray = None

    def Run(self):
        """启动程序"""
        self.App = QApplication(sys.argv)
        self.App.setQuitOnLastWindowClosed(False)

        self.Tray = TrayIcon(self.App)

        return self.App.exec()


def Main():
    """入口函数"""
    App = ManagerApp()
    sys.exit(App.Run())
