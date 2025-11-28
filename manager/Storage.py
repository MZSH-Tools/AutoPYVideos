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


def GetVideoDir() -> Path:
    """获取视频存储目录"""
    VideoDir = GetDataDir() / "Videos"
    VideoDir.mkdir(parents=True, exist_ok=True)
    return VideoDir


def GetTasksPath() -> Path:
    """获取任务文件路径"""
    return GetDataDir() / "Tasks.json"
