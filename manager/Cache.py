# 缓存管理模块
import os
import json
import time
from pathlib import Path
from enum import Enum


class TaskStatus(Enum):
    """任务状态"""
    Queued = "queued"           # 等待下载
    Downloading = "downloading" # 下载中
    Processing = "processing"   # 视频处理中
    Ready = "ready"             # 处理完成待发布
    Published = "published"     # 已发布


def GetCacheDir() -> Path:
    """获取缓存目录"""
    if os.name == "nt":
        Base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        Base = Path.home() / ".cache"

    CacheDir = Base / "AutoPYVideos"
    CacheDir.mkdir(parents=True, exist_ok=True)
    return CacheDir


def GetVideoDir() -> Path:
    """获取视频缓存目录"""
    VideoDir = GetCacheDir() / "Videos"
    VideoDir.mkdir(parents=True, exist_ok=True)
    return VideoDir


def GetTasksPath() -> Path:
    """获取任务文件路径"""
    return GetCacheDir() / "Tasks.json"


class TaskManager:
    """任务管理器，以时间戳为 Key"""

    def __init__(self):
        self.Path = GetTasksPath()
        self.Tasks = {}  # Key: 时间戳, Value: 任务信息
        self.Load()

    def Load(self):
        """加载任务"""
        if self.Path.exists():
            with open(self.Path, "r", encoding="utf-8") as F:
                self.Tasks = json.load(F)
        else:
            self.Tasks = {}

    def Save(self):
        """保存任务"""
        with open(self.Path, "w", encoding="utf-8") as F:
            json.dump(self.Tasks, F, ensure_ascii=False, indent=2)

    def Add(self, Url: str, Title: str = "") -> str:
        """添加任务，返回时间戳 Key"""
        Key = str(int(time.time() * 1000))
        self.Tasks[Key] = {
            "Url": Url,
            "Title": Title,
            "Status": TaskStatus.Queued.value,
            "Progress": 0,
            "OutputPath": "",
            "Error": ""
        }
        self.Save()
        return Key

    def Update(self, Key: str, **Fields):
        """更新任务字段"""
        if Key in self.Tasks:
            for K, V in Fields.items():
                if K == "Status" and isinstance(V, TaskStatus):
                    V = V.value
                self.Tasks[Key][K] = V
            self.Save()

    def Get(self, Key: str) -> dict | None:
        """获取任务"""
        return self.Tasks.get(Key)

    def FindByUrl(self, Url: str) -> tuple[str, dict] | None:
        """根据 URL 查找任务，返回 (Key, Task)"""
        for Key, Task in self.Tasks.items():
            if Task["Url"] == Url:
                return (Key, Task)
        return None

    def GetByStatus(self, Status: TaskStatus) -> list[tuple[str, dict]]:
        """获取指定状态的任务，按时间戳降序"""
        Result = [(K, V) for K, V in self.Tasks.items() if V["Status"] == Status.value]
        Result.sort(key=lambda X: int(X[0]), reverse=True)
        return Result

    def GetAll(self) -> list[tuple[str, dict]]:
        """获取所有任务，按时间戳降序"""
        Result = list(self.Tasks.items())
        Result.sort(key=lambda X: int(X[0]), reverse=True)
        return Result

    def Delete(self, Key: str):
        """删除任务"""
        if Key in self.Tasks:
            del self.Tasks[Key]
            self.Save()
