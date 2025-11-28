# 存储路径管理模块
import os
from pathlib import Path


def GetDataDir() -> Path:
    """获取数据目录"""
    if os.name == "nt":
        Base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        Base = Path.home() / ".local" / "share"

    DataDir = Base / "AutoPYVideos"
    DataDir.mkdir(parents=True, exist_ok=True)
    return DataDir


def GetTasksDir() -> Path:
    """获取任务存储目录"""
    TasksDir = GetDataDir() / "Tasks"
    TasksDir.mkdir(parents=True, exist_ok=True)
    return TasksDir


def ListTaskDirs() -> list[Path]:
    """遍历所有任务目录，按时间戳倒序"""
    TasksDir = GetTasksDir()
    Dirs = [D for D in TasksDir.iterdir() if D.is_dir() and D.name.isdigit()]
    Dirs.sort(key=lambda D: int(D.name), reverse=True)
    return Dirs
