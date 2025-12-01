# 应用程序入口
import os
import sys
import shutil
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtCore import QObject, Signal


def CleanupOldTmp():
    """清理旧的 tmp 文件夹（保留当前进程的）"""
    RootDir = Path(__file__).parent.parent
    CurTmp = f'tmp{os.getpid()}'
    for Item in RootDir.iterdir():
        if Item.is_dir() and Item.name.startswith('tmp') and Item.name != CurTmp:
            try:
                shutil.rmtree(Item)
            except:
                pass


# 清理旧的临时文件夹
CleanupOldTmp()

# 配置 FFmpeg 路径（跨平台）
if sys.platform == "win32":
    # Windows: 优先使用 winget 安装的 ffmpeg（带 libx264）
    FFMPEG_PATH = os.path.expanduser(
        r"~\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
    )
    if os.path.exists(FFMPEG_PATH):
        os.environ["PATH"] = FFMPEG_PATH + os.pathsep + os.environ.get("PATH", "")
# macOS/Linux: ffmpeg 通常已在 PATH 中（brew install ffmpeg / apt install ffmpeg）

# 加载项目配置并应用到 videotrans
import Config
Config.ApplyToVideotrans()

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
    """尝试唤醒已存在的实例"""
    Socket = QLocalSocket()
    Socket.connectToServer(SERVER_NAME)
    if Socket.waitForConnected(500):
        Socket.write(b"SHOW")
        Socket.waitForBytesWritten(500)
        Socket.disconnectFromServer()
        return True
    return False


def Main():
    """入口函数"""
    App = QApplication(sys.argv)

    # 尝试唤醒已存在的实例
    if TryWakeExisting():
        print("Waking existing instance...")
        sys.exit(0)

    # 启用深色主题
    import qdarkstyle
    App.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))

    App.setQuitOnLastWindowClosed(False)

    # 启动单实例服务器
    Server = SingleInstanceServer()
    if not Server.Start():
        sys.exit(1)

    Tray = TrayIcon(App)
    Server.ShowWindowRequested.connect(Tray.ShowMainWindow)

    sys.exit(App.exec())
