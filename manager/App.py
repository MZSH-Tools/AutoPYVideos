# 应用程序入口
import sys
import atexit
from pathlib import Path
from PySide6.QtWidgets import QApplication

from Tray import TrayIcon
from Cache import GetCacheDir


def GetLockFile() -> Path:
    """获取锁文件路径"""
    return GetCacheDir() / "manager.lock"


def IsAlreadyRunning() -> bool:
    """检查程序是否已在运行"""
    LockFile = GetLockFile()
    if LockFile.exists():
        # 检查锁文件中的 PID 是否还在运行
        try:
            import psutil
            Pid = int(LockFile.read_text().strip())
            if psutil.pid_exists(Pid):
                return True
        except Exception:
            pass
        # PID 不存在或读取失败，删除旧锁文件
        LockFile.unlink(missing_ok=True)
    return False


def CreateLock():
    """创建锁文件"""
    import os
    LockFile = GetLockFile()
    LockFile.write_text(str(os.getpid()))


def RemoveLock():
    """删除锁文件"""
    GetLockFile().unlink(missing_ok=True)


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
    if IsAlreadyRunning():
        print("Manager is already running.")
        sys.exit(1)

    CreateLock()
    atexit.register(RemoveLock)

    App = ManagerApp()
    sys.exit(App.Run())
