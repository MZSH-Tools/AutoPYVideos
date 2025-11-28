# 管理界面主窗口
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent


class MainWindow(QMainWindow):
    """管理界面主窗口"""

    Closed = Signal()

    def __init__(self):
        super().__init__()
        self.SetupUI()

    def SetupUI(self):
        """初始化界面"""
        self.setWindowTitle("AutoPYVideos Manager")
        self.setMinimumSize(800, 600)

        Central = QWidget()
        self.setCentralWidget(Central)

        Layout = QVBoxLayout(Central)

        Placeholder = QLabel("Manager UI - Coming Soon")
        Placeholder.setStyleSheet("font-size: 24px; color: #666;")
        Layout.addWidget(Placeholder)

    def closeEvent(self, Event: QCloseEvent):
        """关闭窗口时隐藏而非退出"""
        Event.ignore()
        self.hide()
        self.Closed.emit()
