# 任务管理模块
import json
import time
import shutil
from pathlib import Path
from enum import Enum

from Storage import GetVideoDir, GetTasksPath
from Download import FetchVideoInfo, DownloadVideo


class TaskStatus(Enum):
    """任务状态"""
    Queued = "queued"
    Downloading = "downloading"
    Recognizing = "recognizing"
    Translating = "translating"
    Dubbing = "dubbing"
    Merging = "merging"
    Ready = "ready"
    Published = "published"


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self.Path = GetTasksPath()
        self.Tasks = {}
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

    def Add(self, Url: str) -> str:
        """添加任务，返回时间戳 Key"""
        Key = str(int(time.time() * 1000))
        self.Tasks[Key] = {
            "Url": Url,
            "Title": "",
            "Author": "",
            "Duration": 0,
            "Description": "",
            "Thumbnail": "",
            "VideoId": "",
            "Status": TaskStatus.Queued.value,
            "Progress": 0,
            "VideoPath": "",
            "OutputPath": "",
            "PublishUrl": "",
            "Error": ""
        }
        self.Save()
        return Key

    def FetchInfo(self, Key: str) -> bool:
        """获取视频信息并更新任务"""
        Task = self.Get(Key)
        if not Task:
            print(f"FetchInfo: Task {Key} not found")
            return False

        print(f"FetchInfo: Fetching info for {Task['Url']}")
        Info = FetchVideoInfo(Task["Url"])
        if Info:
            print(f"FetchInfo: Got title '{Info['Title']}', author '{Info['Author']}'")
            self.Update(Key,
                Title=Info["Title"],
                Author=Info["Author"],
                Duration=Info["Duration"],
                Description=Info["Description"],
                Thumbnail=Info["Thumbnail"],
                VideoId=Info["VideoId"]
            )
            return True
        print("FetchInfo: Failed to get info")
        return False

    def GetTaskDir(self, Key: str) -> Path:
        """获取任务的工作目录"""
        TaskDir = GetVideoDir() / Key
        TaskDir.mkdir(parents=True, exist_ok=True)
        return TaskDir

    def WriteInfoFile(self, Key: str):
        """写入任务信息文件到任务目录"""
        Task = self.Get(Key)
        if not Task:
            return

        TaskDir = self.GetTaskDir(Key)
        InfoPath = TaskDir / "info.txt"

        StatusText = {
            "queued": "Queued",
            "downloading": "Downloading",
            "recognizing": "Recognizing",
            "translating": "Translating",
            "dubbing": "Dubbing",
            "merging": "Merging",
            "ready": "Ready",
            "published": "Published",
        }.get(Task["Status"], Task["Status"])

        Lines = [
            f"Title: {Task.get('Title', '')}",
            f"Author: {Task.get('Author', '')}",
            f"URL: {Task['Url']}",
            f"Status: {StatusText}",
            f"Progress: {Task['Progress']}%",
        ]

        if Task.get("Duration", 0) > 0:
            Minutes = Task["Duration"] // 60
            Seconds = Task["Duration"] % 60
            Lines.append(f"Duration: {Minutes}:{Seconds:02d}")

        if Task.get("PublishUrl"):
            Lines.append(f"Publish URL: {Task['PublishUrl']}")

        if Task.get("Description"):
            Lines.append(f"\n--- Description ---\n{Task['Description']}")

        with open(InfoPath, "w", encoding="utf-8") as F:
            F.write("\n".join(Lines))

    def Download(self, Key: str, ProgressCallback=None) -> bool:
        """下载视频"""
        Task = self.Get(Key)
        if not Task:
            return False

        self.Update(Key, Status=TaskStatus.Downloading, Progress=0, Error="")
        TaskDir = self.GetTaskDir(Key)

        def OnProgress(Percent, Status, Speed):
            self.Update(Key, Progress=Percent)
            if ProgressCallback:
                ProgressCallback(Percent, Status, Speed)

        VideoPath = DownloadVideo(Task["Url"], TaskDir, OnProgress)
        if VideoPath:
            self.Update(Key, VideoPath=str(VideoPath), Progress=100)
            return True
        else:
            self.Update(Key, Status=TaskStatus.Queued, Error="Download failed")
            return False

    def Archive(self, Key: str, PublishUrl: str):
        """归档任务：设为已发布，删除缓存文件"""
        Task = self.Get(Key)
        if not Task:
            return

        if Task.get("OutputPath"):
            OutputPath = Path(Task["OutputPath"])
            if OutputPath.exists():
                if OutputPath.is_dir():
                    shutil.rmtree(OutputPath)
                else:
                    OutputPath.unlink()

        self.Update(Key,
            Status=TaskStatus.Published,
            PublishUrl=PublishUrl,
            OutputPath=""
        )

    def Update(self, Key: str, **Fields):
        """更新任务字段"""
        if Key in self.Tasks:
            for K, V in Fields.items():
                if K == "Status" and isinstance(V, TaskStatus):
                    V = V.value
                self.Tasks[Key][K] = V
            self.Save()
            self.WriteInfoFile(Key)

    def Get(self, Key: str) -> dict | None:
        """获取任务"""
        return self.Tasks.get(Key)

    def FindByUrl(self, Url: str) -> tuple[str, dict] | None:
        """根据 URL 查找任务"""
        for Key, Task in self.Tasks.items():
            if Task["Url"] == Url:
                return (Key, Task)
        return None

    def GetByStatus(self, Status: TaskStatus) -> list[tuple[str, dict]]:
        """获取指定状态的任务"""
        Result = [(K, V) for K, V in self.Tasks.items() if V["Status"] == Status.value]
        Result.sort(key=lambda X: int(X[0]), reverse=True)
        return Result

    def GetAll(self) -> list[tuple[str, dict]]:
        """获取所有任务"""
        Result = list(self.Tasks.items())
        Result.sort(key=lambda X: int(X[0]), reverse=True)
        return Result

    def Delete(self, Key: str):
        """删除任务"""
        if Key in self.Tasks:
            del self.Tasks[Key]
            self.Save()
