# 缓存管理模块
import os
import json
import time
import shutil
from pathlib import Path
from enum import Enum


class TaskStatus(Enum):
    """任务状态（5 阶段断点续传）"""
    Queued = "queued"           # 等待开始
    Downloading = "downloading" # 下载中
    Recognizing = "recognizing" # 识别中（含音频准备）
    Translating = "translating" # 翻译中
    Dubbing = "dubbing"         # 配音中
    Merging = "merging"         # 合成中
    Ready = "ready"             # 处理完成待发布
    Published = "published"     # 已发布


def FetchVideoInfo(Url: str) -> dict | None:
    """获取视频信息（标题、作者等）"""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as Ydl:
            Info = Ydl.extract_info(Url, download=False)
            return {
                "Title": Info.get("title", ""),
                "Author": Info.get("uploader") or Info.get("channel", ""),
                "Duration": Info.get("duration", 0),
                "Description": Info.get("description", ""),
                "Thumbnail": Info.get("thumbnail", ""),
                "VideoId": Info.get("id", ""),
            }
    except Exception as E:
        print(f"FetchVideoInfo error: {E}")
        return None


class DownloadProgress:
    """下载进度回调"""
    def __init__(self, Callback):
        self.Callback = Callback

    def __call__(self, D: dict):
        if D["status"] == "downloading":
            Total = D.get("total_bytes") or D.get("total_bytes_estimate", 0)
            Downloaded = D.get("downloaded_bytes", 0)
            if Total > 0:
                Percent = int(Downloaded * 100 / Total)
                self.Callback(Percent, "downloading")
        elif D["status"] == "finished":
            self.Callback(100, "finished")


def DownloadVideo(Url: str, OutputDir: Path, ProgressCallback=None) -> Path | None:
    """
    下载视频，支持断点续传
    返回下载后的视频文件路径
    """
    import yt_dlp

    OutputDir.mkdir(parents=True, exist_ok=True)
    OutputTemplate = str(OutputDir / "%(id)s.%(ext)s")

    Options = {
        "outtmpl": OutputTemplate,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,  # 断点续传
    }

    if ProgressCallback:
        Options["progress_hooks"] = [DownloadProgress(ProgressCallback)]

    try:
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Info = Ydl.extract_info(Url, download=True)
            VideoId = Info.get("id", "")
            # 查找下载后的文件
            for File in OutputDir.iterdir():
                if File.stem == VideoId and File.suffix == ".mp4":
                    return File
            return None
    except Exception as E:
        print(f"Download error: {E}")
        return None


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
            "VideoPath": "",      # 下载的原始视频
            "OutputPath": "",     # 最终输出视频
            "PublishUrl": "",
            "Error": ""
        }
        self.Save()
        return Key

    def FetchInfo(self, Key: str) -> bool:
        """获取视频信息并更新任务"""
        Task = self.Get(Key)
        if not Task:
            return False

        Info = FetchVideoInfo(Task["Url"])
        if Info:
            self.Update(Key,
                Title=Info["Title"],
                Author=Info["Author"],
                Duration=Info["Duration"],
                Description=Info["Description"],
                Thumbnail=Info["Thumbnail"],
                VideoId=Info["VideoId"]
            )
            return True
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

        def OnProgress(Percent, Status):
            self.Update(Key, Progress=Percent)
            if ProgressCallback:
                ProgressCallback(Percent, Status)

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

        # 删除视频缓存
        if Task.get("OutputPath"):
            OutputPath = Path(Task["OutputPath"])
            if OutputPath.exists():
                if OutputPath.is_dir():
                    shutil.rmtree(OutputPath)
                else:
                    OutputPath.unlink()

        # 更新状态
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
            # 同步更新 info.txt
            self.WriteInfoFile(Key)

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
