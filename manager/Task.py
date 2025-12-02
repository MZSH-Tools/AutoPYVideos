# 任务管理模块（文件夹驱动）
import json
import time
import shutil
from pathlib import Path
from enum import Enum

from Storage import GetTasksDir, ListTaskDirs
from Download import FetchVideoInfo, DownloadVideo, DownloadThumbnail


class TaskStatus(Enum):
    """任务状态"""
    Queued = "queued"
    Validating = "validating"  # 校验/修复任务信息中
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
    Excluded = "excluded"  # 已排除（不再处理）


def InferStatus(TaskDir: Path) -> TaskStatus:
    """根据目录内文件推断任务状态（只区分已完成/未完成）"""
    InfoPath = TaskDir / "info.json"
    if InfoPath.exists():
        try:
            with open(InfoPath, "r", encoding="utf-8") as F:
                Info = json.load(F)
                # 检查是否已排除
                if Info.get("Status") == TaskStatus.Excluded.value:
                    return TaskStatus.Excluded
                # 检查是否已发布
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
        self.UrlIndex = {}  # Url -> Key 索引
        self.Sync()

    def Sync(self):
        """从文件夹同步任务状态"""
        self.Tasks = {}
        self.UrlIndex = {}
        for TaskDir in ListTaskDirs():
            Key = TaskDir.name
            Task = self.LoadTask(TaskDir)
            if Task:
                self.Tasks[Key] = Task
                if Task.get("Url"):
                    self.UrlIndex[Task["Url"]] = Key

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
        # 不保存运行时状态（但保留 excluded 状态）
        Status = Task.pop("Status", None)
        if Status == TaskStatus.Excluded.value:
            Task["Status"] = Status
        Task.pop("Progress", None)

        TaskDir = self.GetTaskDir(Key)
        InfoPath = TaskDir / "info.json"
        with open(InfoPath, "w", encoding="utf-8") as F:
            json.dump(Task, F, ensure_ascii=False, indent=2)
        # 已排除任务不创建日志文件
        if Status != TaskStatus.Excluded.value:
            LogPath = TaskDir / "log.txt"
            if not LogPath.exists():
                LogPath.touch()

    def GetTaskDir(self, Key: str) -> Path:
        """获取任务目录"""
        TaskDir = GetTasksDir() / Key
        TaskDir.mkdir(parents=True, exist_ok=True)
        return TaskDir

    def GenerateKey(self) -> str:
        """生成唯一时间戳 Key，如果冲突则 +1 秒"""
        Key = str(int(time.time() * 1000))
        while Key in self.Tasks:
            Key = str(int(Key) + 1000)  # +1 秒
        return Key

    def Add(self, Url: str) -> str:
        """添加任务，返回时间戳 Key"""
        Key = self.GenerateKey()
        self.Tasks[Key] = {
            "Url": Url,
            "Title": "",
            "TitleZh": "",  # 翻译后的中文标题
            "Author": "",
            "Thumbnail": "",
            "VideoId": "",
            "PublishUrl": "",
            "Priority": False,  # 优先处理标记
            "Error": "",
            "Status": TaskStatus.Queued.value,
            "Progress": 0,
        }
        self.UrlIndex[Url] = Key
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
            # 下载封面到任务目录
            ThumbnailPath = ""
            if Info["Thumbnail"]:
                TaskDir = self.GetTaskDir(Key)
                ThumbnailPath = DownloadThumbnail(Info["Thumbnail"], TaskDir)
            self.Update(Key,
                Title=Info["Title"],
                Author=Info["Author"],
                Thumbnail=ThumbnailPath,  # 存本地路径而非 URL
                VideoId=Info["VideoId"]
            )
            return True
        print("获取信息: 获取失败")
        return False

    def CheckInfo(self, Key: str) -> dict:
        """检测任务信息问题，返回 {MissingTitle, MissingThumbnail, MissingTitleZh, ThumbnailPathInvalid}"""
        Task = self.Get(Key)
        if not Task:
            return {}

        TaskDir = self.GetTaskDir(Key)
        ThumbnailPath = TaskDir / "thumbnail.jpg"
        Thumb = Task.get("Thumbnail", "")
        Title = Task.get("Title", "")
        TitleZh = Task.get("TitleZh", "")

        return {
            "MissingTitle": not Title,
            "MissingThumbnail": not ThumbnailPath.exists(),
            "ThumbnailPathInvalid": ThumbnailPath.exists() and (not Thumb or Thumb.startswith("http")),
            # 中文标题缺失或与英文标题相同（翻译失败）
            "MissingTitleZh": Title and (not TitleZh or TitleZh == Title),
        }

    def CleanupPublishedTask(self, Key: str) -> int:
        """清理已发布任务的所有文件（保留 info.json），返回清理文件数"""
        TaskDir = self.GetTaskDir(Key)
        Count = 0
        for File in TaskDir.iterdir():
            if File.name != "info.json":
                try:
                    File.unlink()
                    Count += 1
                except Exception:
                    pass
        return Count

    def ValidateInfo(self, Key: str, TranslateFunc=None) -> dict:
        """校验并修复任务信息，返回修复结果 {Fixed: [...], Failed: [], Cleaned: int}"""
        Task = self.Get(Key)
        if not Task:
            return {"Fixed": [], "Failed": ["Task not found"], "Cleaned": 0}

        # 已发布/已排除任务：清理所有文件（保留 info.json）
        if Task.get("Status") in [TaskStatus.Published.value, TaskStatus.Excluded.value]:
            Count = self.CleanupPublishedTask(Key)
            return {"Fixed": [], "Failed": [], "Cleaned": Count}

        # 先检测问题
        Problems = self.CheckInfo(Key)
        if not any(Problems.values()):
            return {"Fixed": [], "Failed": [], "Cleaned": 0}

        # 设置校验状态
        OldStatus = Task.get("Status")
        self.Tasks[Key]["Status"] = TaskStatus.Validating.value

        Result = {"Fixed": [], "Failed": [], "Cleaned": 0}
        TaskDir = self.GetTaskDir(Key)
        ThumbnailPath = TaskDir / "thumbnail.jpg"
        NeedSave = False
        ThumbnailUrl = ""

        try:
            # 1. 修复基础信息（仅在缺失时获取）
            if Problems["MissingTitle"]:
                Info = FetchVideoInfo(Task["Url"])
                if Info:
                    if Info["Title"]:
                        self.Tasks[Key]["Title"] = Info["Title"]
                        Result["Fixed"].append("Title")
                        NeedSave = True
                    if Info["Author"] and not Task.get("Author"):
                        self.Tasks[Key]["Author"] = Info["Author"]
                        Result["Fixed"].append("Author")
                        NeedSave = True
                    if Info["VideoId"] and not Task.get("VideoId"):
                        self.Tasks[Key]["VideoId"] = Info["VideoId"]
                        Result["Fixed"].append("VideoId")
                        NeedSave = True
                    ThumbnailUrl = Info.get("Thumbnail", "")
                else:
                    Result["Failed"].append("FetchVideoInfo")

            # 2. 修复封面（仅在文件缺失时下载）
            if Problems["MissingThumbnail"]:
                # 优先从已有 Thumbnail 字段获取 URL
                if not ThumbnailUrl:
                    Thumb = Task.get("Thumbnail", "")
                    if Thumb.startswith("http"):
                        ThumbnailUrl = Thumb
                if ThumbnailUrl:
                    LocalPath = DownloadThumbnail(ThumbnailUrl, TaskDir)
                    if LocalPath:
                        self.Tasks[Key]["Thumbnail"] = LocalPath
                        Result["Fixed"].append("Thumbnail")
                        NeedSave = True
                    else:
                        Result["Failed"].append("DownloadThumbnail")
                else:
                    Result["Failed"].append("NoThumbnailUrl")
            elif Problems["ThumbnailPathInvalid"]:
                # 封面文件存在但路径字段无效，直接修正
                self.Tasks[Key]["Thumbnail"] = str(ThumbnailPath)
                Result["Fixed"].append("ThumbnailPath")
                NeedSave = True

            # 3. 修复中文标题（仅在缺失或与英文相同时翻译）
            if Problems["MissingTitleZh"] and TranslateFunc:
                # 重新获取最新 Title（可能刚修复）
                Title = self.Tasks[Key].get("Title", "")
                if Title:
                    try:
                        TitleZh = TranslateFunc(Title, "en", "zh-cn")
                        if TitleZh and TitleZh != Title:
                            self.Tasks[Key]["TitleZh"] = TitleZh
                            Result["Fixed"].append("TitleZh")
                            NeedSave = True
                        elif TitleZh == Title:
                            Result["Failed"].append("TranslateSameAsOriginal")
                    except Exception:
                        Result["Failed"].append("TranslateTitle")

            if NeedSave:
                self.SaveTask(Key)
        finally:
            # 恢复原状态
            self.Tasks[Key]["Status"] = OldStatus

        return Result

    def GetTasksNeedValidation(self) -> list[str]:
        """获取需要校验的任务列表（已发布/已排除需清理，未发布需检测信息）"""
        Keys = []
        for Key, Task in self.Tasks.items():
            Status = Task.get("Status")
            # 已发布/已排除任务：检查是否需要清理文件
            if Status in [TaskStatus.Published.value, TaskStatus.Excluded.value]:
                TaskDir = self.GetTaskDir(Key)
                # 如果目录中有除 info.json 外的文件，需要清理
                HasFiles = any(F.name != "info.json" for F in TaskDir.iterdir() if F.is_file())
                if HasFiles:
                    Keys.append(Key)
                continue
            # 未发布任务：检测信息问题
            Problems = self.CheckInfo(Key)
            if any(Problems.values()):
                Keys.append(Key)
        return Keys

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
            # 更新 Url 时同步更新索引
            if K == "Url":
                OldUrl = self.Tasks[Key].get("Url")
                if OldUrl and OldUrl in self.UrlIndex:
                    del self.UrlIndex[OldUrl]
                if V:
                    self.UrlIndex[V] = Key
            self.Tasks[Key][K] = V
            # 持久化字段需要保存
            if K in ["Title", "TitleZh", "Author", "Thumbnail", "VideoId", "PublishUrl", "Url", "Priority", "Status"]:
                NeedSave = True
        if NeedSave:
            self.SaveTask(Key)

    def Get(self, Key: str) -> dict | None:
        """获取任务"""
        return self.Tasks.get(Key)

    def FindByUrl(self, Url: str) -> tuple[str, dict] | None:
        """根据 URL 查找任务（O(1) 索引查找）"""
        Key = self.UrlIndex.get(Url)
        if Key and Key in self.Tasks:
            return (Key, self.Tasks[Key])
        return None

    def GetAll(self) -> list[tuple[str, dict]]:
        """获取所有任务（按时间倒序）"""
        Result = list(self.Tasks.items())
        Result.sort(key=lambda X: int(X[0]), reverse=True)
        return Result

    def Delete(self, Key: str):
        """删除任务（包括文件夹）"""
        if Key in self.Tasks:
            Url = self.Tasks[Key].get("Url")
            if Url and Url in self.UrlIndex:
                del self.UrlIndex[Url]
            del self.Tasks[Key]
        TaskDir = GetTasksDir() / Key
        if TaskDir.exists():
            shutil.rmtree(TaskDir)

    def Archive(self, Key: str, PublishUrl: str) -> tuple[bool, str]:
        """归档任务：验证链接、保存、清理缓存，返回 (成功, 消息)"""
        from Publish import ValidateUrl, CleanupTaskCache

        Valid, Error, ExtractedUrl = ValidateUrl(PublishUrl)
        if not Valid:
            return False, f"链接验证失败: {Error}"

        # 只保存提取出的纯 URL，同时更新状态
        self.Update(Key, PublishUrl=ExtractedUrl, Status=TaskStatus.Published)
        Count = CleanupTaskCache(self.GetTaskDir(Key))
        return True, f"已发布，清理 {Count} 个缓存文件"

    def SetPriority(self, Key: str, IsPriority: bool):
        """设置任务优先级"""
        self.Update(Key, Priority=IsPriority)

    def IsPriority(self, Key: str) -> bool:
        """检查任务是否在优先队列"""
        Task = self.Get(Key)
        return Task.get("Priority", False) if Task else False

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
        PriorityTasks = [K for K in PendingTasks if self.IsPriority(K)]
        NormalTasks = [K for K in PendingTasks if not self.IsPriority(K)]

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

            # 重置任务信息，保留 Url 和 Priority
            Priority = self.Tasks[Key].get("Priority", False)
            self.Tasks[Key] = {
                "Url": Url,
                "Title": "",
                "TitleZh": "",
                "Author": "",
                "Thumbnail": "",
                "VideoId": "",
                "PublishUrl": "",
                "Priority": Priority,
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

            # 更新状态为等待中，清除发布链接
            self.Tasks[Key]["Status"] = TaskStatus.Queued.value
            self.Tasks[Key]["Progress"] = 0
            self.Tasks[Key]["Error"] = ""
            self.Tasks[Key]["PublishUrl"] = ""  # 重置时清除发布链接
            self.SaveTask(Key)

        return True
