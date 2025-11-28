# 任务管理模块（文件夹驱动）
import json
import time
import shutil
from pathlib import Path
from enum import Enum

from Storage import GetTasksDir, ListTaskDirs
from Download import FetchVideoInfo, DownloadVideo


class TaskStatus(Enum):
    """任务状态"""
    Queued = "queued"
    Downloading = "downloading"
    Extracting = "extracting"
    Recognizing = "recognizing"
    Translating = "translating"
    Dubbing = "dubbing"
    Merging = "merging"
    Ready = "ready"
    Published = "published"
    Failed = "failed"


# 文件名 → 状态映射（根据文件存在推断状态）
FILE_STATUS_MAP = [
    ("output.mp4", TaskStatus.Ready),      # 有最终输出 → 待发布
    ("zh-cn.wav", TaskStatus.Merging),     # 有配音 → 合成中
    ("zh-cn.srt", TaskStatus.Dubbing),     # 有中文字幕 → 配音中
    ("en.srt", TaskStatus.Translating),    # 有英文字幕 → 翻译中
    ("audio.wav", TaskStatus.Recognizing), # 有音频 → 识别中
    ("video.mp4", TaskStatus.Extracting),  # 有视频 → 提取中
]


def InferStatus(TaskDir: Path) -> TaskStatus:
    """根据目录内文件推断任务状态"""
    # 检查是否已发布
    InfoPath = TaskDir / "info.json"
    if InfoPath.exists():
        try:
            with open(InfoPath, "r", encoding="utf-8") as F:
                Info = json.load(F)
                if Info.get("PublishUrl"):
                    return TaskStatus.Published
        except:
            pass

    # 根据文件存在推断
    for FileName, Status in FILE_STATUS_MAP:
        if (TaskDir / FileName).exists():
            return Status

    return TaskStatus.Queued


class TaskManager:
    """任务管理器（文件夹驱动）"""

    def __init__(self):
        self.Tasks = {}  # Key -> Task dict 缓存
        self.Sync()

    def Sync(self):
        """从文件夹同步任务状态"""
        self.Tasks = {}
        for TaskDir in ListTaskDirs():
            Key = TaskDir.name
            Task = self.LoadTask(TaskDir)
            if Task:
                self.Tasks[Key] = Task

    def LoadTask(self, TaskDir: Path) -> dict | None:
        """从目录加载任务"""
        InfoPath = TaskDir / "info.json"
        if not InfoPath.exists():
            return None

        try:
            with open(InfoPath, "r", encoding="utf-8") as F:
                Task = json.load(F)
            # 推断实际状态
            Task["Status"] = InferStatus(TaskDir).value
            Task["Progress"] = 0
            return Task
        except:
            return None

    def SaveTask(self, Key: str):
        """保存任务信息到 info.json"""
        if Key not in self.Tasks:
            return
        Task = self.Tasks[Key].copy()
        # 不保存运行时状态
        Task.pop("Status", None)
        Task.pop("Progress", None)

        TaskDir = self.GetTaskDir(Key)
        InfoPath = TaskDir / "info.json"
        with open(InfoPath, "w", encoding="utf-8") as F:
            json.dump(Task, F, ensure_ascii=False, indent=2)

    def GetTaskDir(self, Key: str) -> Path:
        """获取任务目录"""
        TaskDir = GetTasksDir() / Key
        TaskDir.mkdir(parents=True, exist_ok=True)
        return TaskDir

    def Add(self, Url: str) -> str:
        """添加任务，返回时间戳 Key"""
        Key = str(int(time.time() * 1000))
        self.Tasks[Key] = {
            "Url": Url,
            "Title": "",
            "Author": "",
            "Thumbnail": "",
            "VideoId": "",
            "PublishUrl": "",
            "Error": "",
            "Status": TaskStatus.Queued.value,
            "Progress": 0,
        }
        self.SaveTask(Key)
        return Key

    def FetchInfo(self, Key: str) -> bool:
        """获取视频信息"""
        Task = self.Get(Key)
        if not Task:
            return False

        print(f"FetchInfo: Fetching info for {Task['Url']}")
        Info = FetchVideoInfo(Task["Url"])
        if Info:
            print(f"FetchInfo: Got title '{Info['Title']}', author '{Info['Author']}'")
            self.Update(Key,
                Title=Info["Title"],
                Author=Info["Author"],
                Thumbnail=Info["Thumbnail"],
                VideoId=Info["VideoId"]
            )
            return True
        print("FetchInfo: Failed to get info")
        return False

    def Download(self, Key: str, ProgressCallback=None) -> bool:
        """下载视频"""
        Task = self.Get(Key)
        if not Task:
            return False

        TaskDir = self.GetTaskDir(Key)
        VideoPath = TaskDir / "video.mp4"

        # 已存在则跳过
        if VideoPath.exists():
            return True

        def OnProgress(Percent, Status, Speed):
            self.Tasks[Key]["Progress"] = Percent
            if ProgressCallback:
                ProgressCallback(Percent, Status, Speed)

        Result = DownloadVideo(Task["Url"], TaskDir, OnProgress)
        if Result:
            # 重命名为 video.mp4
            if Result.name != "video.mp4":
                Result.rename(VideoPath)
            return True
        else:
            self.Update(Key, Error="Download failed")
            return False

    def Update(self, Key: str, **Fields):
        """更新任务字段"""
        if Key not in self.Tasks:
            return
        NeedSave = False
        for K, V in Fields.items():
            if K == "Status" and isinstance(V, TaskStatus):
                V = V.value
            self.Tasks[Key][K] = V
            # 持久化字段需要保存
            if K in ["Title", "Author", "Thumbnail", "VideoId", "PublishUrl", "Url"]:
                NeedSave = True
        if NeedSave:
            self.SaveTask(Key)

    def Get(self, Key: str) -> dict | None:
        """获取任务"""
        return self.Tasks.get(Key)

    def FindByUrl(self, Url: str) -> tuple[str, dict] | None:
        """根据 URL 查找任务"""
        for Key, Task in self.Tasks.items():
            if Task["Url"] == Url:
                return (Key, Task)
        return None

    def GetAll(self) -> list[tuple[str, dict]]:
        """获取所有任务（按时间倒序）"""
        Result = list(self.Tasks.items())
        Result.sort(key=lambda X: int(X[0]), reverse=True)
        return Result

    def Delete(self, Key: str):
        """删除任务（包括文件夹）"""
        if Key in self.Tasks:
            del self.Tasks[Key]
        TaskDir = GetTasksDir() / Key
        if TaskDir.exists():
            shutil.rmtree(TaskDir)

    def Archive(self, Key: str, PublishUrl: str):
        """归档任务：设为已发布"""
        self.Update(Key, PublishUrl=PublishUrl)
