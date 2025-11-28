# 缓存管理模块
import os
import json
from pathlib import Path
from datetime import datetime


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


def GetHistoryPath() -> Path:
    """获取历史记录文件路径"""
    return GetCacheDir() / "History.json"


class HistoryMgr:
    """历史记录管理"""

    def __init__(self):
        self.Path = GetHistoryPath()
        self.Records = []
        self.Load()

    def Load(self):
        """加载历史记录"""
        if self.Path.exists():
            with open(self.Path, "r", encoding="utf-8") as F:
                self.Records = json.load(F)
        else:
            self.Records = []

    def Save(self):
        """保存历史记录"""
        with open(self.Path, "w", encoding="utf-8") as F:
            json.dump(self.Records, F, ensure_ascii=False, indent=2)

    def Add(self, Url: str, Title: str, Status: str, OutputPath: str = ""):
        """添加记录"""
        Record = {
            "Url": Url,
            "Title": Title,
            "Status": Status,
            "OutputPath": OutputPath,
            "Time": datetime.now().isoformat()
        }
        self.Records.insert(0, Record)
        self.Save()

    def Find(self, Url: str) -> dict | None:
        """根据 URL 查找记录"""
        for R in self.Records:
            if R["Url"] == Url:
                return R
        return None

    def GetAll(self) -> list:
        """获取所有记录"""
        return self.Records

    def Clear(self):
        """清空记录"""
        self.Records = []
        self.Save()
