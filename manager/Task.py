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
    Paused = "paused"  # 暂停（阶段完成后暂停）
    Ready = "ready"
    Published = "published"
    Failed = "failed"


def InferStatus(TaskDir: Path) -> TaskStatus:
    """根据目录内文件推断任务状态（只区分已完成/未完成）"""
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

    # 有最终输出 → 待发布
    if (TaskDir / "output.mp4").exists():
        return TaskStatus.Ready

    # 其他情况都是等待中（具体处理阶段由 MainWindow 在处理时设置）
    return TaskStatus.Queued


class TaskManager:
    """任务管理器（文件夹驱动）"""

    def __init__(self):
        self.Tasks = {}  # Key -> Task dict 缓存
        self.PriorityKeys = set()  # 优先处理队列（Key 集合）
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
        """保存任务信息到 info.json（同时创建 log.txt）"""
        if Key not in self.Tasks:
            return
        Task = self.Tasks[Key].copy()
        # 不保存运行时状态
        Task.pop("Status", None)
        Task.pop("Progress", None)

        TaskDir = self.GetTaskDir(Key)
        InfoPath = TaskDir / "info.json"
        LogPath = TaskDir / "log.txt"
        with open(InfoPath, "w", encoding="utf-8") as F:
            json.dump(Task, F, ensure_ascii=False, indent=2)
        # 同步创建 log.txt（如不存在）
        if not LogPath.exists():
            LogPath.touch()

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
            "TitleZh": "",  # 翻译后的中文标题
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

        print(f"获取信息: 获取视频信息 {Task['Url']}")
        Info = FetchVideoInfo(Task["Url"])
        if Info:
            print(f"获取信息: 标题='{Info['Title']}', 作者='{Info['Author']}'")
            self.Update(Key,
                Title=Info["Title"],
                Author=Info["Author"],
                Thumbnail=Info["Thumbnail"],
                VideoId=Info["VideoId"]
            )
            return True
        print("获取信息: 获取失败")
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
            if K in ["Title", "TitleZh", "Author", "Thumbnail", "VideoId", "PublishUrl", "Url"]:
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

    def Archive(self, Key: str, PublishUrl: str) -> tuple[bool, str]:
        """归档任务：验证链接、保存、清理缓存，返回 (成功, 消息)"""
        from Publish import ValidateUrl, CleanupTaskCache

        Valid, Error = ValidateUrl(PublishUrl)
        if not Valid:
            return False, f"链接验证失败: {Error}"

        self.Update(Key, PublishUrl=PublishUrl)
        Count = CleanupTaskCache(self.GetTaskDir(Key))
        return True, f"已发布，清理 {Count} 个缓存文件"

    def SetPriority(self, Key: str, IsPriority: bool):
        """设置任务优先级"""
        if IsPriority:
            self.PriorityKeys.add(Key)
        else:
            self.PriorityKeys.discard(Key)

    def IsPriority(self, Key: str) -> bool:
        """检查任务是否在优先队列"""
        return Key in self.PriorityKeys

    def GetNextTask(self) -> str | None:
        """获取下一个待处理任务（优先队列优先，再按时间正序）"""
        # 收集等待中或已暂停的任务
        PendingTasks = []
        for Key, Task in self.Tasks.items():
            if Task["Status"] in [TaskStatus.Queued.value, TaskStatus.Paused.value]:
                PendingTasks.append(Key)

        if not PendingTasks:
            return None

        # 分成优先和普通两组
        PriorityTasks = [K for K in PendingTasks if K in self.PriorityKeys]
        NormalTasks = [K for K in PendingTasks if K not in self.PriorityKeys]

        # 优先队列按时间正序（Key 越小越早）
        if PriorityTasks:
            PriorityTasks.sort(key=lambda X: int(X))
            return PriorityTasks[0]

        # 普通队列按时间正序
        if NormalTasks:
            NormalTasks.sort(key=lambda X: int(X))
            return NormalTasks[0]

        return None

    def Reset(self, Key: str, FromStage: str = "all") -> bool:
        """重置任务：从指定阶段开始重新执行
        FromStage: all=全部重置, download=从下载开始, extract=从提取开始,
                   recognize=从识别开始, translate=从翻译开始, dub=从配音开始, merge=从合成开始
        """
        Task = self.Get(Key)
        if not Task:
            return False

        Url = Task.get("Url", "")
        if not Url:
            return False

        TaskDir = self.GetTaskDir(Key)
        if not TaskDir.exists():
            return False

        # 各阶段对应的文件（按流程顺序）
        # 删除某阶段意味着删除该阶段及后续所有文件
        StageFiles = {
            "download": ["video.mp4", "video_slow.mp4"],  # 下载阶段
            "extract": ["audio.wav"],  # 提取阶段
            "recognize": ["en.srt"],  # 识别阶段
            "translate": ["zh-cn.srt", "bilingual.srt"],  # 翻译阶段
            "dub": ["zh-cn.wav", "aligned.srt", "aligned_bilingual.srt"],  # 配音阶段
            "merge": ["output.mp4"],  # 合成阶段
        }
        StageOrder = ["download", "extract", "recognize", "translate", "dub", "merge"]

        if FromStage == "all":
            # 全部重置：删除所有文件
            FilesToDelete = []
            for Files in StageFiles.values():
                FilesToDelete.extend(Files)
            FilesToDelete.extend(["info.json", "log.txt"])  # 也删除信息和日志

            for FileName in FilesToDelete:
                FilePath = TaskDir / FileName
                if FilePath.exists():
                    try:
                        FilePath.unlink()
                    except Exception:
                        pass

            # 重置任务信息，只保留 Url
            self.Tasks[Key] = {
                "Url": Url,
                "Title": "",
                "TitleZh": "",
                "Author": "",
                "Thumbnail": "",
                "VideoId": "",
                "PublishUrl": "",
                "Error": "",
                "Status": TaskStatus.Queued.value,
                "Progress": 0,
            }
            self.SaveTask(Key)
        else:
            # 从指定阶段开始重置
            if FromStage not in StageOrder:
                return False

            StartIndex = StageOrder.index(FromStage)
            FilesToDelete = []
            for I in range(StartIndex, len(StageOrder)):
                Stage = StageOrder[I]
                FilesToDelete.extend(StageFiles[Stage])

            for FileName in FilesToDelete:
                FilePath = TaskDir / FileName
                if FilePath.exists():
                    try:
                        FilePath.unlink()
                    except Exception:
                        pass

            # 更新状态为等待中
            self.Tasks[Key]["Status"] = TaskStatus.Queued.value
            self.Tasks[Key]["Progress"] = 0
            self.Tasks[Key]["Error"] = ""

        return True
