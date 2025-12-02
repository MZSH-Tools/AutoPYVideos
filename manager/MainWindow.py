# 管理界面主窗口
import sys
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QFrame, QSplitter, QApplication, QTextEdit, QMenu, QMessageBox
)
from PySide6.QtCore import Signal, Qt, QThread, QObject, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QAction

from pathlib import Path
from Task import TaskManager, TaskStatus
from Storage import LoadSettings, SaveSettings
from Download import FetchPlaylistUrls
import Log as LogModule
from Extract import ExtractAudio
import Config
from Recognize import RecognizeAudio
from Translate import TranslateSrt, MergeBilingualSrt, TranslateText
from Dubbing import GenerateDubbing
from Merge import MergeVideo


# 全局 Debug 标志
DebugMode = False


class LogSignal(QObject):
    """日志信号，用于跨线程发送日志"""
    Message = Signal(str, str, bool)  # Key, Msg, IsDebug

LogEmitter = LogSignal()

# 当前处理任务的Key（由ProcessThread设置）
CurrentProcessingKey = None

# 暂停状态（暂停后当前阶段会完成，但不会进入下一阶段）
IsPaused = False

# 延迟重启状态（当前流程完成后重启）
IsDelayedRestart = False

# 暂停状态变化信号
class PauseSignal(QObject):
    Changed = Signal(bool)  # IsPaused
PauseEmitter = PauseSignal()

# 延迟重启状态变化信号
class DelayedRestartSignal(QObject):
    Changed = Signal(bool)  # IsDelayedRestart
    DoRestart = Signal()    # 触发实际重启
DelayedRestartEmitter = DelayedRestartSignal()


def SetPaused(Paused: bool):
    """设置延迟暂停状态（全局操作，不记录到任务日志）"""
    global IsPaused
    IsPaused = Paused
    PauseEmitter.Changed.emit(Paused)


def SetDelayedRestart(DelayedRestart: bool):
    """设置延迟重启状态"""
    global IsDelayedRestart
    IsDelayedRestart = DelayedRestart
    DelayedRestartEmitter.Changed.emit(DelayedRestart)


def Log(Msg: str, Key: str = None):
    """普通日志（Key为None时使用当前处理任务的Key）"""
    ActualKey = Key if Key is not None else (CurrentProcessingKey or "")
    LogEmitter.Message.emit(ActualKey, Msg, False)


def LogDebug(Msg: str):
    """调试日志（不写入任务日志文件）"""
    LogEmitter.Message.emit("", Msg, True)


# 设置公共日志模块的回调函数
LogModule.SetLogFunc(Log)


class LogWriter:
    """重定向stdout到GUI（作为调试日志）"""
    def __init__(self):
        self.Terminal = sys.__stdout__

    def write(self, Msg):
        if Msg.strip():
            LogEmitter.Message.emit(CurrentProcessingKey or "", Msg.strip(), True)

    def flush(self):
        pass


class ValidateInfoThread(QThread):
    """启动时后台校验任务信息的线程（逐个校验，非并发）"""
    Started = Signal(int)  # Total count
    TaskStarted = Signal(str)  # Key（开始校验某任务）
    TaskFixed = Signal(str, list, list, int)  # Key, Fixed, Failed, Cleaned
    Finished = Signal(int, int, int)  # FixedCount, FailedCount, CleanedCount

    def __init__(self, TaskMgr: TaskManager):
        super().__init__()
        self.TaskMgr = TaskMgr

    def run(self):
        Keys = self.TaskMgr.GetTasksNeedValidation()
        Total = len(Keys)
        if Total == 0:
            self.Finished.emit(0, 0, 0)
            return

        self.Started.emit(Total)
        FixedCount = 0
        FailedCount = 0
        CleanedCount = 0

        for Key in Keys:
            self.TaskStarted.emit(Key)
            Result = self.TaskMgr.ValidateInfo(Key, TranslateFunc=TranslateText)
            if Result["Fixed"]:
                FixedCount += len(Result["Fixed"])
            if Result["Failed"]:
                FailedCount += len(Result["Failed"])
            CleanedCount += Result.get("Cleaned", 0)
            self.TaskFixed.emit(Key, Result["Fixed"], Result["Failed"], Result.get("Cleaned", 0))

        self.Finished.emit(FixedCount, FailedCount, CleanedCount)


class FetchPlaylistThread(QThread):
    """后台获取播放列表的线程"""
    Finished = Signal(list)  # Urls (空列表表示失败)

    def __init__(self, Url: str):
        super().__init__()
        self.Url = Url

    def run(self):
        Urls = FetchPlaylistUrls(self.Url)
        self.Finished.emit(Urls if Urls else [])


class ProcessThread(QThread):
    """后台处理任务的线程（下载 → 识别 → 翻译 → 配音 → 合成）"""
    Progress = Signal(str, int, str, float)   # Key, Percent, Stage, Speed
    StageChanged = Signal(str, str)           # Key, Stage
    Finished = Signal(str, bool, bool)        # Key, Success, Preempted（是否被抢占）

    def __init__(self, TaskMgr: TaskManager, Key: str):
        super().__init__()
        self.TaskMgr = TaskMgr
        self.Key = Key

    def run(self):
        """全自动流水线：根据文件存在决定从哪个阶段开始"""
        global CurrentProcessingKey
        CurrentProcessingKey = self.Key

        try:
            self._DoRun()
        finally:
            CurrentProcessingKey = None

    def _ShouldPreempt(self) -> bool:
        """检查是否应该被抢占（有更高优先级任务等待）"""
        # 当前任务是优先任务，不被抢占
        if self.TaskMgr.IsPriority(self.Key):
            return False
        # 检查是否有优先任务在等待
        NextKey = self.TaskMgr.GetNextTask()
        if NextKey and NextKey != self.Key and self.TaskMgr.IsPriority(NextKey):
            return True
        return False

    def _DoRun(self):
        """实际执行处理逻辑"""
        Task = self.TaskMgr.Get(self.Key)
        if not Task:
            self.Finished.emit(self.Key, False, False)
            return

        # 兜底：检测并修复任务信息（正常情况下启动时已校验过）
        Problems = self.TaskMgr.CheckInfo(self.Key)
        if any(Problems.values()):
            Log(f"Validating task info...")
            Result = self.TaskMgr.ValidateInfo(self.Key, TranslateFunc=TranslateText)
            if Result["Fixed"]:
                Log(f"Fixed: {', '.join(Result['Fixed'])}")
            if Result["Failed"]:
                Log(f"Failed to fix: {', '.join(Result['Failed'])}")
            Task = self.TaskMgr.Get(self.Key)  # 重新获取更新后的任务

        TaskDir = self.TaskMgr.GetTaskDir(self.Key)
        VideoPath = TaskDir / "video.mp4"
        AudioPath = TaskDir / "audio.wav"
        EnSrtPath = TaskDir / "en.srt"
        ZhSrtPath = TaskDir / "zh-cn.srt"
        BilingualSrtPath = TaskDir / "bilingual.srt"
        ZhAudioPath = TaskDir / "zh-cn.wav"
        OutputPath = TaskDir / "output.mp4"

        try:
            # 阶段 1: 下载视频
            if not VideoPath.exists():
                if IsPaused or IsDelayedRestart:
                    Log(f"任务在下载前{'暂停' if IsPaused else '等待重启'}")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Paused)
                    self.Finished.emit(self.Key, False, False)
                    return
                # 下载前检查抢占
                if self._ShouldPreempt():
                    Log(f"任务被优先任务抢占，暂停等待")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Queued)
                    self.Finished.emit(self.Key, False, True)
                    return
                self.StageChanged.emit(self.Key, "downloading")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Downloading, Progress=0)

                def OnDownloadProgress(Percent, Status, Speed):
                    self.Progress.emit(self.Key, Percent, "downloading", Speed or 0)

                try:
                    Success = self.TaskMgr.Download(self.Key, OnDownloadProgress)
                    if not Success:
                        Log(f"下载失败: {Task['Url']}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"下载错误: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False, False)
                    return

            # 阶段 2: 提取音频
            if not AudioPath.exists():
                if IsPaused or IsDelayedRestart:
                    Log(f"任务在提取前{'暂停' if IsPaused else '等待重启'}")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Paused)
                    self.Finished.emit(self.Key, False, False)
                    return
                # 提取前检查抢占
                if self._ShouldPreempt():
                    Log(f"任务被优先任务抢占，暂停等待")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Queued)
                    self.Finished.emit(self.Key, False, True)
                    return
                self.StageChanged.emit(self.Key, "extracting")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Extracting, Progress=0)

                try:
                    Result = ExtractAudio(VideoPath, AudioPath)
                    if not Result:
                        Log(f"音频提取失败: {VideoPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"提取错误: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False, False)
                    return

                self.TaskMgr.Update(self.Key, Progress=100)

            # 阶段 3: 语音识别
            if not EnSrtPath.exists():
                if IsPaused or IsDelayedRestart:
                    Log(f"任务在识别前{'暂停' if IsPaused else '等待重启'}")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Paused)
                    self.Finished.emit(self.Key, False, False)
                    return
                # 识别前检查抢占
                if self._ShouldPreempt():
                    Log(f"任务被优先任务抢占，暂停等待")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Queued)
                    self.Finished.emit(self.Key, False, True)
                    return
                self.StageChanged.emit(self.Key, "recognizing")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Recognizing, Progress=0)

                def OnRecognizeProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "recognizing", 0)

                try:
                    Model = Config.Get("语音识别.模型", "medium.en")
                    Language = Config.Get("语音识别.源语言", "en")
                    AutoFix = Config.Get("语音识别.自动修正", False)
                    UseCuda = Config.Get("处理.启用CUDA", False)
                    Result = RecognizeAudio(AudioPath, EnSrtPath, Language=Language,
                                            Model=Model, AutoFix=AutoFix, UseCuda=UseCuda,
                                            ProgressCallback=OnRecognizeProgress)
                    if not Result:
                        Log(f"识别失败: {AudioPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"识别错误: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False, False)
                    return

            # 阶段 4: 翻译（英文 → 中文）
            if not ZhSrtPath.exists():
                if IsPaused or IsDelayedRestart:
                    Log(f"任务在翻译前{'暂停' if IsPaused else '等待重启'}")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Paused)
                    self.Finished.emit(self.Key, False, False)
                    return
                # 翻译前检查抢占
                if self._ShouldPreempt():
                    Log(f"任务被优先任务抢占，暂停等待")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Queued)
                    self.Finished.emit(self.Key, False, True)
                    return
                self.StageChanged.emit(self.Key, "translating")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Translating, Progress=0)

                def OnTranslateProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "translating", 0)

                try:
                    Result = TranslateSrt(EnSrtPath, ZhSrtPath,
                                          SourceLang="en", TargetLang="zh-cn",
                                          ProgressCallback=OnTranslateProgress)
                    if not Result:
                        Log(f"翻译失败: {EnSrtPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"翻译错误: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False, False)
                    return

            # 翻译完成后生成双语字幕（中文在上，英文在下）
            if not BilingualSrtPath.exists() and ZhSrtPath.exists() and EnSrtPath.exists():
                Log(f"生成双语字幕...")
                MergeBilingualSrt(ZhSrtPath, EnSrtPath, BilingualSrtPath,
                                  TargetLang="zh-cn", SourceLang="en")

            # 阶段 5: 配音（中文 TTS）
            AlignedSrtPath = TaskDir / "aligned.srt"  # 对齐后的字幕（视频慢速时生成）
            if not ZhAudioPath.exists():
                if IsPaused or IsDelayedRestart:
                    Log(f"任务在配音前{'暂停' if IsPaused else '等待重启'}")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Paused)
                    self.Finished.emit(self.Key, False, False)
                    return
                # 配音前检查抢占
                if self._ShouldPreempt():
                    Log(f"任务被优先任务抢占，暂停等待")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Queued)
                    self.Finished.emit(self.Key, False, True)
                    return
                self.StageChanged.emit(self.Key, "dubbing")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Dubbing, Progress=0)

                def OnDubbingProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "dubbing", 0)

                try:
                    Voice = Config.Get("配音.声音角色", "晓晓 多语言(Female/CN)")
                    VoiceAutorate = Config.Get("配音.音频加速", False)
                    VideoSlowdown = Config.Get("配音.视频慢放", True)
                    RemoveSilentMid = Config.Get("处理.删除间隙静音", False)
                    AlignSubAudio = Config.Get("处理.对齐字幕音频", True)
                    Log(f"配置: 声音={Voice}, 音频加速={VoiceAutorate}, 视频慢放={VideoSlowdown}")
                    Log(f"配置: 删除间隙静音={RemoveSilentMid}, 对齐字幕音频={AlignSubAudio}")
                    DubbingResult = GenerateDubbing(ZhSrtPath, ZhAudioPath, VideoPath=VideoPath,
                                                    Voice=Voice,
                                                    VoiceAutorate=VoiceAutorate,
                                                    VideoSlowdown=VideoSlowdown,
                                                    RemoveSilentMid=RemoveSilentMid,
                                                    AlignSubAudio=AlignSubAudio,
                                                    ProgressCallback=OnDubbingProgress)
                    if not DubbingResult:
                        Log(f"配音失败: {ZhSrtPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False, False)
                        return
                    # 解包结果：(音频路径, 对齐后字幕路径)
                    _, AlignedSrtPath = DubbingResult
                    if AlignedSrtPath:
                        Log(f"配音生成对齐字幕: {AlignedSrtPath}")
                except Exception as E:
                    import traceback
                    Log(f"配音错误: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False, False)
                    return
            else:
                # 配音已存在，检查对齐字幕是否存在
                if not AlignedSrtPath.exists():
                    AlignedSrtPath = None

            # 如果有对齐字幕，生成对齐版双语字幕
            AlignedBilingualSrtPath = TaskDir / "aligned_bilingual.srt"
            if AlignedSrtPath and AlignedSrtPath.exists() and EnSrtPath.exists():
                if not AlignedBilingualSrtPath.exists():
                    Log(f"生成对齐版双语字幕...")
                    MergeBilingualSrt(AlignedSrtPath, EnSrtPath, AlignedBilingualSrtPath,
                                      TargetLang="zh-cn", SourceLang="en")

            # 阶段 6: 合成（音视频合并）
            if not OutputPath.exists():
                if IsPaused or IsDelayedRestart:
                    Log(f"任务在合成前{'暂停' if IsPaused else '等待重启'}")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Paused)
                    self.Finished.emit(self.Key, False, False)
                    return
                # 合成前检查抢占
                if self._ShouldPreempt():
                    Log(f"任务被优先任务抢占，暂停等待")
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Queued)
                    self.Finished.emit(self.Key, False, True)
                    return
                self.StageChanged.emit(self.Key, "merging")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Merging, Progress=0)

                def OnMergeProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "merging", 0)

                try:
                    # 优先使用对齐版双语字幕（视频慢速后时间轴正确+双语）
                    # 其次使用普通双语字幕，最后使用中文字幕
                    if AlignedBilingualSrtPath.exists():
                        SubtitlePath = AlignedBilingualSrtPath
                        Log(f"使用对齐版双语字幕: {SubtitlePath}")
                    elif BilingualSrtPath.exists():
                        SubtitlePath = BilingualSrtPath
                        Log(f"使用双语字幕: {SubtitlePath}")
                    else:
                        SubtitlePath = ZhSrtPath
                        Log(f"使用中文字幕: {SubtitlePath}")

                    # 优先使用慢速后的视频（如果存在）
                    SlowVideoPath = TaskDir / "video_slow.mp4"
                    MergeVideoPath = SlowVideoPath if SlowVideoPath.exists() else VideoPath
                    Log(f"使用视频: {MergeVideoPath}")

                    Result = MergeVideo(MergeVideoPath, ZhAudioPath, SubtitlePath, OutputPath,
                                        HardSubtitle=True, ProgressCallback=OnMergeProgress)
                    if not Result:
                        Log(f"合成失败: {VideoPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"合成错误: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False, False)
                    return

            # 全部完成，标记为待发布
            self.TaskMgr.Update(self.Key, Status=TaskStatus.Ready, Progress=100)
            Log(f"任务完成: {self.Key}")
            self.Finished.emit(self.Key, True, False)

        except Exception as E:
            import traceback
            Log(f"处理错误: {E}")
            Log(traceback.format_exc())
            self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
            self.Finished.emit(self.Key, False, False)


# 状态对应颜色
StatusColors = {
    "queued": "#888888",      # 灰色 - 等待中
    "validating": "#607D8B",  # 蓝灰 - 校验中
    "downloading": "#2196F3", # 蓝色 - 下载中
    "extracting": "#9C27B0",  # 紫色 - 提取中
    "recognizing": "#FF9800", # 橙色 - 识别中
    "translating": "#00BCD4", # 青色 - 翻译中
    "dubbing": "#3F51B5",     # 靛蓝 - 配音中
    "merging": "#795548",     # 棕色 - 合成中
    "paused": "#FFC107",      # 黄色 - 已暂停
    "ready": "#4CAF50",       # 绿色 - 待发布
    "published": "#9E9E9E",   # 浅灰 - 已发布
    "failed": "#F44336",      # 红色 - 失败
}


class MainWindow(QMainWindow):
    """管理界面主窗口"""

    Closed = Signal()

    def __init__(self):
        super().__init__()
        self.TaskMgr = TaskManager()
        self.CurKey = None
        self.CurSpeed = 0  # 当前下载速度 bytes/s
        self.ProcessThread = None  # 当前处理线程（同时只处理一个）
        self.LogFilePos = 0  # 日志文件读取位置
        self.SetupUI()
        # 监听暂停状态变化
        PauseEmitter.Changed.connect(self.OnPauseChanged)
        # 监听延迟重启状态变化
        DelayedRestartEmitter.Changed.connect(self.OnDelayedRestartChanged)
        # 定时刷新日志显示
        self.LogTimer = QTimer(self)
        self.LogTimer.timeout.connect(self.RefreshLogDisplay)
        self.LogTimer.start(500)  # 每500ms刷新
        self.RefreshList()
        self.SelectProcessingTask()
        self.TryStartProcessing()

    def CenterOnScreen(self):
        """将窗口居中到屏幕中央"""
        Screen = QApplication.primaryScreen().geometry()
        X = (Screen.width() - self.width()) // 2
        Y = (Screen.height() - self.height()) // 2
        self.move(X, Y)

    def SetupUI(self):
        """初始化界面"""
        self.setWindowTitle("AutoPYVideos Manager")
        self.setMinimumSize(1200, 900)
        self.resize(1200, 900)
        self.CenterOnScreen()

        Central = QWidget()
        self.setCentralWidget(Central)
        Layout = QVBoxLayout(Central)

        # 顶部区域：搜索栏 + 全局设置
        TopContainer = QVBoxLayout()
        TopLayout = QHBoxLayout()

        # 搜索栏
        self.UrlInput = QLineEdit()
        self.UrlInput.setPlaceholderText("输入 YouTube 链接...")
        self.UrlInput.returnPressed.connect(self.OnSearch)
        self.UrlInput.textChanged.connect(self.OnUrlInputChanged)
        TopLayout.addWidget(self.UrlInput)

        # 清除按钮
        self.ClearBtn = QPushButton("✕")
        self.ClearBtn.setFixedWidth(30)
        self.ClearBtn.clicked.connect(self.OnClearSearch)
        self.ClearBtn.setVisible(False)
        TopLayout.addWidget(self.ClearBtn)

        self.SearchBtn = QPushButton("🔍")
        self.SearchBtn.setFixedWidth(40)
        self.SearchBtn.clicked.connect(self.OnSearch)
        TopLayout.addWidget(self.SearchBtn)

        TopLayout.addSpacing(20)

        # 全局设置
        TopLayout.addWidget(QLabel("标题前缀:"))
        self.TitlePrefixEdit = QLineEdit()
        self.TitlePrefixEdit.setFixedWidth(60)
        self.TitlePrefixEdit.setPlaceholderText("【中字】")
        self.TitlePrefixEdit.editingFinished.connect(self.OnSettingsChanged)
        TopLayout.addWidget(self.TitlePrefixEdit)

        TopLayout.addWidget(QLabel("后缀:"))
        self.TitleSuffixEdit = QLineEdit()
        self.TitleSuffixEdit.setFixedWidth(60)
        self.TitleSuffixEdit.setPlaceholderText("(配音)")
        self.TitleSuffixEdit.editingFinished.connect(self.OnSettingsChanged)
        TopLayout.addWidget(self.TitleSuffixEdit)

        TopContainer.addLayout(TopLayout)

        # 错误提示标签
        self.UrlErrorLabel = QLabel()
        self.UrlErrorLabel.setStyleSheet("color: #cc0000; font-size: 12px; padding-left: 5px;")
        self.UrlErrorLabel.setVisible(False)
        TopContainer.addWidget(self.UrlErrorLabel)

        Layout.addLayout(TopContainer)

        # 筛选状态
        self.FilterKeys = None  # None=不筛选, list=筛选指定 Key

        # 第二行：简介附加（多行输入，全局设置）
        DescExtraLayout = QHBoxLayout()
        DescExtraLayout.addWidget(QLabel("简介附加:"))
        self.DescExtraEdit = QTextEdit()
        self.DescExtraEdit.setPlaceholderText("发布时附加的简介内容（多行）...")
        self.DescExtraEdit.setMaximumHeight(50)
        self.DescExtraEdit.setStyleSheet("font-size: 12px;")
        self.DescExtraEdit.textChanged.connect(self.OnSettingsChanged)
        DescExtraLayout.addWidget(self.DescExtraEdit)
        Layout.addLayout(DescExtraLayout)

        # 分割器：左侧列表 + 右侧详情
        Splitter = QSplitter(Qt.Orientation.Horizontal)
        Layout.addWidget(Splitter)

        # 左侧任务列表
        self.TaskList = QListWidget()
        self.TaskList.setMaximumWidth(250)
        self.TaskList.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.TaskList.currentItemChanged.connect(self.OnTaskSelected)
        self.TaskList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.TaskList.customContextMenuRequested.connect(self.OnTaskContextMenu)
        Splitter.addWidget(self.TaskList)

        # 右侧详情面板
        DetailPanel = QFrame()
        DetailPanel.setFrameShape(QFrame.Shape.StyledPanel)
        DetailLayout = QVBoxLayout(DetailPanel)
        Splitter.addWidget(DetailPanel)

        # 详情内容样式
        LabelStyle = "font-size: 13px; padding: 3px 10px;"
        HeaderStyle = LabelStyle + "font-weight: bold;"

        # 状态行
        StatusLayout = QHBoxLayout()
        self.DetailStatus = QLabel("")
        self.DetailStatus.setStyleSheet("font-size: 13px; padding: 3px 10px;")
        StatusLayout.addWidget(self.DetailStatus)
        StatusLayout.addStretch()
        self.DetailProgressLabel = QLabel("")
        self.DetailProgressLabel.setStyleSheet("font-size: 13px; padding: 3px 10px; color: #0088ff;")
        StatusLayout.addWidget(self.DetailProgressLabel)
        DetailLayout.addLayout(StatusLayout)

        DetailLayout.addSpacing(10)

        # 视频信息
        InfoHeader = QLabel("视频信息:")
        InfoHeader.setStyleSheet(HeaderStyle)
        DetailLayout.addWidget(InfoHeader)

        self.DetailAuthor = QLabel("")
        self.DetailAuthor.setStyleSheet(LabelStyle + "padding-left: 20px;")
        self.DetailAuthor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        DetailLayout.addWidget(self.DetailAuthor)

        self.DetailTitle = QLabel("")
        self.DetailTitle.setStyleSheet(LabelStyle + "padding-left: 20px;")
        self.DetailTitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailTitle.setWordWrap(True)
        DetailLayout.addWidget(self.DetailTitle)

        # 原链接 + 复制按钮
        UrlLayout = QHBoxLayout()
        self.DetailUrl = QLabel("")
        self.DetailUrl.setStyleSheet(LabelStyle + "padding-left: 20px;")
        self.DetailUrl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailUrl.setWordWrap(True)
        UrlLayout.addWidget(self.DetailUrl, 1)
        self.CopyUrlBtn = QPushButton("复制")
        self.CopyUrlBtn.setFixedWidth(50)
        self.CopyUrlBtn.clicked.connect(self.OnCopyUrl)
        self.CopyUrlBtn.setVisible(False)
        UrlLayout.addWidget(self.CopyUrlBtn)
        DetailLayout.addLayout(UrlLayout)

        DetailLayout.addSpacing(10)

        # 预览信息
        PreviewHeader = QLabel("发布预览:")
        PreviewHeader.setStyleSheet(HeaderStyle)
        DetailLayout.addWidget(PreviewHeader)

        # 标题预览 + 复制按钮
        TitlePreviewLayout = QHBoxLayout()
        TitlePreviewLayout.addWidget(QLabel("标题:"))
        self.TitlePreview = QLineEdit()
        self.TitlePreview.setReadOnly(True)
        TitlePreviewLayout.addWidget(self.TitlePreview)
        self.CopyTitleBtn = QPushButton("复制")
        self.CopyTitleBtn.setFixedWidth(50)
        self.CopyTitleBtn.clicked.connect(self.OnCopyTitle)
        TitlePreviewLayout.addWidget(self.CopyTitleBtn)
        DetailLayout.addLayout(TitlePreviewLayout)

        # 简介预览 + 复制按钮
        DescPreviewLayout = QHBoxLayout()
        DescPreviewLayout.addWidget(QLabel("简介:"))
        self.DescPreview = QTextEdit()
        self.DescPreview.setReadOnly(True)
        self.DescPreview.setMinimumHeight(100)
        self.DescPreview.setStyleSheet("font-size: 12px;")
        DescPreviewLayout.addWidget(self.DescPreview)
        self.CopyDescBtn = QPushButton("复制")
        self.CopyDescBtn.setFixedWidth(50)
        self.CopyDescBtn.clicked.connect(self.OnCopyDesc)
        DescPreviewLayout.addWidget(self.CopyDescBtn)
        DetailLayout.addLayout(DescPreviewLayout)

        # 发布链接（可编辑，贴在底部）
        PublishLayout = QHBoxLayout()
        PublishLabel = QLabel("发布链接:")
        PublishLabel.setStyleSheet(LabelStyle)
        PublishLayout.addWidget(PublishLabel)
        self.PublishUrlEdit = QLineEdit()
        self.PublishUrlEdit.setPlaceholderText("输入发布后的链接...")
        PublishLayout.addWidget(self.PublishUrlEdit)
        self.PublishBtn = QPushButton("发布")
        self.PublishBtn.setFixedWidth(50)
        self.PublishBtn.clicked.connect(self.OnPublish)
        PublishLayout.addWidget(self.PublishBtn)
        DetailLayout.addLayout(PublishLayout)

        # 打开文件夹按钮（最下面）
        self.OpenFolderBtn = QPushButton("打开文件夹")
        self.OpenFolderBtn.clicked.connect(self.OnOpenFolder)
        DetailLayout.addWidget(self.OpenFolderBtn)

        Splitter.setSizes([250, 850])

        # 底部区域：左侧任务流程 + 右侧日志
        BottomLayout = QHBoxLayout()

        # 左侧面板：任务流程
        LeftPanel = QFrame()
        LeftPanel.setFrameShape(QFrame.Shape.StyledPanel)
        LeftPanel.setFixedWidth(200)
        LeftLayout = QVBoxLayout(LeftPanel)
        LeftLayout.setContentsMargins(10, 5, 10, 5)
        LeftLayout.setSpacing(3)

        # 当前任务标题
        self.PipelineTitle = QLabel("当前任务: 无")
        self.PipelineTitle.setStyleSheet("font-size: 12px; font-weight: bold;")
        LeftLayout.addWidget(self.PipelineTitle)

        # 流水线阶段
        self.StageLabels = {}
        StageNames = [
            ("downloading", "下载视频"),
            ("extracting", "提取音频"),
            ("recognizing", "语音识别"),
            ("translating", "字幕翻译"),
            ("dubbing", "语音合成"),
            ("merging", "视频合成"),
        ]
        for StageKey, StageName in StageNames:
            Label = QLabel(f"○ {StageName}")
            Label.setStyleSheet("font-size: 11px; color: #888; padding: 1px 5px;")
            LeftLayout.addWidget(Label)
            self.StageLabels[StageKey] = Label

        LeftLayout.addStretch()

        # 运行状态标签（放大居中，与流程拉开距离）
        self.StatusLabel = QLabel("● 运行中")
        self.StatusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.StatusLabel.setStyleSheet("font-size: 14px; font-weight: bold; color: #4CAF50; padding: 10px 5px;")
        LeftLayout.addWidget(self.StatusLabel)
        self.UpdateStatusLabel()

        BottomLayout.addWidget(LeftPanel)

        # 右侧：日志
        self.LogText = QTextEdit()
        self.LogText.setReadOnly(True)
        self.LogText.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        BottomLayout.addWidget(self.LogText)

        Layout.addLayout(BottomLayout)

        # 加载全局设置
        self.LoadGlobalSettings()

        # 连接日志信号
        LogEmitter.Message.connect(self.AppendLog)
        sys.stdout = LogWriter()

        # 存储后台线程
        self.ValidateThread = None

        # 启动时先校验任务信息，校验完成后再启动正常处理
        self.StartValidation()

    def AppendLog(self, Key: str, Msg: str, IsDebug: bool = False):
        """添加日志（Key为任务Key，空表示全局日志）- 只写入文件"""
        # Debug 日志只在 Debug 模式下显示（不写文件）
        if IsDebug and not DebugMode:
            return
        TimeStr = datetime.now().strftime("%H:%M:%S")
        Prefix = "[DEBUG] " if IsDebug else ""
        LogLine = f"[{TimeStr}] {Prefix}{Msg}"

        # 保存到任务日志文件（非Debug且有Key时）
        if Key and not IsDebug:
            self.SaveTaskLog(Key, LogLine)

    def SaveTaskLog(self, Key: str, LogLine: str):
        """保存日志到任务目录"""
        TaskDir = self.TaskMgr.GetTaskDir(Key)
        LogPath = TaskDir / "log.txt"
        try:
            with open(LogPath, "a", encoding="utf-8") as F:
                F.write(LogLine + "\n")
        except:
            pass

    def LoadTaskLog(self, Key: str):
        """加载任务日志到日志面板（完整加载并记录位置）"""
        self.LogText.clear()
        self.LogFilePos = 0
        TaskDir = self.TaskMgr.GetTaskDir(Key)
        LogPath = TaskDir / "log.txt"
        if LogPath.exists():
            try:
                Content = LogPath.read_text(encoding="utf-8")
                self.LogFilePos = len(Content.encode("utf-8"))
                if Content.strip():
                    self.LogText.setPlainText(Content.rstrip())
                    self.LogText.verticalScrollBar().setValue(self.LogText.verticalScrollBar().maximum())
            except:
                pass

    def RefreshLogDisplay(self):
        """定时刷新日志显示（增量读取）"""
        if not self.CurKey:
            return
        TaskDir = self.TaskMgr.GetTaskDir(self.CurKey)
        LogPath = TaskDir / "log.txt"
        if not LogPath.exists():
            return
        try:
            with open(LogPath, "rb") as F:
                F.seek(self.LogFilePos)
                NewData = F.read()
                if NewData:
                    self.LogFilePos += len(NewData)
                    NewText = NewData.decode("utf-8", errors="ignore").rstrip()
                    if NewText:
                        self.LogText.append(NewText)
                        self.LogText.verticalScrollBar().setValue(self.LogText.verticalScrollBar().maximum())
        except:
            pass

    def OnSearch(self):
        """搜索/添加链接"""
        Url = self.UrlInput.text().strip()
        if not Url:
            return

        # 隐藏错误提示
        self.UrlErrorLabel.setVisible(False)

        # 禁用搜索栏，启动超时计时器
        self.SetSearchEnabled(False)
        self.SearchTimeout = QTimer()
        self.SearchTimeout.setSingleShot(True)
        self.SearchTimeout.timeout.connect(self.OnSearchTimeout)
        self.SearchTimeout.start(10000)  # 10 秒超时
        self.SearchCancelled = False  # 标记是否已取消

        # 启动后台解析
        self.PlaylistThread = FetchPlaylistThread(Url)
        self.PlaylistThread.Finished.connect(self.OnPlaylistFetched)
        self.PlaylistThread.start()

    def OnSearchTimeout(self):
        """搜索超时"""
        self.SearchCancelled = True  # 标记已取消，忽略后续回调
        self.SetSearchEnabled(True)
        self.ShowUrlError("网络超时，请检查网络后重试")

    def OnPlaylistFetched(self, Urls: list):
        """播放列表解析完成"""
        # 停止超时计时器
        if hasattr(self, "SearchTimeout") and self.SearchTimeout:
            self.SearchTimeout.stop()

        # 如果已超时取消，忽略此次回调
        if getattr(self, "SearchCancelled", False):
            return

        # 恢复搜索栏
        self.SetSearchEnabled(True)

        # 解析失败
        if not Urls:
            self.ShowUrlError("输入链接无效，请重新输入")
            return

        # 添加任务并筛选
        AddedKeys = []
        ExistingKeys = []
        for Url in Urls:
            Found = self.TaskMgr.FindByUrl(Url)
            if Found:
                ExistingKeys.append(Found[0])
            else:
                Key = self.TaskMgr.Add(Url)
                AddedKeys.append(Key)

        # 有新任务则启动后台校验（单线程逐个校验）
        if AddedKeys:
            self.StartValidation()

        # 设置筛选并刷新
        self.FilterKeys = AddedKeys + ExistingKeys
        self.ClearBtn.setVisible(True)
        self.RefreshList()

        # 选中第一个任务
        if AddedKeys:
            self.SelectTask(AddedKeys[0])
        elif ExistingKeys:
            self.SelectTask(ExistingKeys[0])

    def SetSearchEnabled(self, Enabled: bool):
        """启用/禁用搜索栏"""
        self.UrlInput.setEnabled(Enabled)
        self.SearchBtn.setEnabled(Enabled)
        self.ClearBtn.setEnabled(Enabled)

    def ShowUrlError(self, Msg: str):
        """显示 URL 错误提示"""
        self.UrlErrorLabel.setText(f"⚠ {Msg}")
        self.UrlErrorLabel.setVisible(True)

    def OnUrlInputChanged(self, Text: str):
        """输入框内容变化时隐藏错误提示"""
        self.UrlErrorLabel.setVisible(False)

    def OnClearSearch(self):
        """清除搜索并取消筛选"""
        self.UrlInput.clear()
        self.FilterKeys = None
        self.ClearBtn.setVisible(False)
        self.UrlErrorLabel.setVisible(False)
        self.RefreshList()

    def StartValidation(self):
        """启动后台信息校验（单线程逐个校验）"""
        # 如果正在校验，不重复启动
        if hasattr(self, "ValidateThread") and self.ValidateThread and self.ValidateThread.isRunning():
            return
        # 如果正在处理任务，不启动校验
        if self.ProcessThread and self.ProcessThread.isRunning():
            return

        self.ValidateThread = ValidateInfoThread(self.TaskMgr)
        self.ValidateThread.Started.connect(self.OnValidateStarted)
        self.ValidateThread.TaskStarted.connect(self.OnValidateTaskStarted)
        self.ValidateThread.TaskFixed.connect(self.OnTaskFixed)
        self.ValidateThread.Finished.connect(self.OnValidateFinished)
        self.ValidateThread.start()

    def OnValidateStarted(self, Total: int):
        """校验流程开始"""
        Log(f"Validating {Total} tasks...")

    def OnValidateTaskStarted(self, Key: str):
        """开始校验某个任务"""
        # 刷新列表以显示 Validating 状态
        self.RefreshList()
        Task = self.TaskMgr.Get(Key)
        if self.CurKey == Key and Task:
            self.UpdateDetail(Key, Task)

    def OnTaskFixed(self, Key: str, Fixed: list, Failed: list, Cleaned: int):
        """单个任务校验完成"""
        # 已发布任务清理后不记录日志（避免重新创建刚删除的日志文件）
        Task = self.TaskMgr.Get(Key)
        IsPublished = Task and Task.get("Status") == TaskStatus.Published.value
        if Fixed:
            Log(f"Fixed: {', '.join(Fixed)}", Key)
        if Failed:
            Log(f"Failed to fix: {', '.join(Failed)}", Key)
        if Cleaned > 0 and not IsPublished:
            Log(f"Cleaned {Cleaned} cache files", Key)
        # 刷新列表和详情
        self.RefreshList()
        Task = self.TaskMgr.Get(Key)
        if self.CurKey == Key and Task:
            self.UpdateDetail(Key, Task)

    def OnValidateFinished(self, FixedCount: int, FailedCount: int, CleanedCount: int):
        """全部校验完成"""
        if FixedCount > 0 or FailedCount > 0 or CleanedCount > 0:
            Log(f"Validation complete: {FixedCount} fixed, {FailedCount} failed, {CleanedCount} files cleaned")
        # 校验完成后尝试启动正常处理流程
        self.TryStartProcessing()

    def SelectProcessingTask(self):
        """选中正在处理的任务，如果没有则选中第一个任务"""
        ProcessingStatuses = [
            TaskStatus.Downloading.value,
            TaskStatus.Extracting.value,
            TaskStatus.Recognizing.value,
            TaskStatus.Translating.value,
            TaskStatus.Dubbing.value,
            TaskStatus.Merging.value,
        ]
        AllTasks = self.TaskMgr.GetAll()
        # 先找正在处理的
        for Key, Task in AllTasks:
            if Task["Status"] in ProcessingStatuses:
                self.SelectTask(Key)
                return
        # 没有正在处理的，选中第一个
        if AllTasks:
            self.SelectTask(AllTasks[0][0])

    def TryStartProcessing(self):
        """尝试启动下一个任务的处理（如果当前没有在处理）"""
        # 如果正在校验任务信息，等校验完成再启动
        if self.ValidateThread and self.ValidateThread.isRunning():
            return

        # 如果已有任务在处理，不启动新的
        if self.ProcessThread and self.ProcessThread.isRunning():
            return

        # 检查延迟重启：没有任务在处理时触发重启
        if IsDelayedRestart:
            DelayedRestartEmitter.DoRestart.emit()
            return

        # 如果暂停中，不启动新任务
        if IsPaused:
            return

        # 使用 TaskManager 的优先队列逻辑获取下一个任务
        NextKey = self.TaskMgr.GetNextTask()
        if NextKey:
            self.StartProcessing(NextKey)
            return

        # 没有任务需要处理，清空流水线显示
        self.ClearPipelineDisplay()

    def StartProcessing(self, Key: str):
        """启动任务处理（不改变用户当前选中的任务）"""
        self.ProcessThread = ProcessThread(self.TaskMgr, Key)
        self.ProcessThread.Progress.connect(self.OnProcessProgress)
        self.ProcessThread.StageChanged.connect(self.OnStageChanged)
        self.ProcessThread.Finished.connect(self.OnProcessFinished)
        self.ProcessThread.start()

    def OnProcessProgress(self, Key: str, Percent: int, Stage: str, Speed: float):
        """处理进度更新"""
        self.CurSpeed = Speed
        # 更新流水线显示（当前处理任务）
        Task = self.TaskMgr.Get(Key)
        if Task:
            self.UpdatePipelineDisplay(Key, Task["Status"], Percent)
        # 更新详情面板进度
        if self.CurKey == Key:
            self.UpdateProgressDisplay(Percent, Stage)

    def OnStageChanged(self, Key: str, Stage: str):
        """处理阶段变化"""
        self.RefreshList()
        # 更新流水线显示
        Task = self.TaskMgr.Get(Key)
        if Task:
            self.UpdatePipelineDisplay(Key, Task["Status"], Task["Progress"])
        # 更新详情面板
        if self.CurKey == Key and Task:
            self.UpdateDetail(Key, Task)

    def OnProcessFinished(self, Key: str, Success: bool, Preempted: bool):
        """处理完成"""
        self.RefreshList()
        Task = self.TaskMgr.Get(Key)
        # 更新详情面板
        if self.CurKey == Key and Task:
            self.UpdateDetail(Key, Task)
        # 尝试处理下一个任务（会自动更新流水线显示）
        # 如果是被抢占的，下一个任务会是优先任务
        # 优先任务完成后，被抢占的任务会继续执行
        self.TryStartProcessing()

    def OnPauseChanged(self, Paused: bool):
        """暂停状态变化"""
        self.UpdateStatusLabel()
        self.RefreshList()
        if not Paused:
            # 恢复后尝试继续处理
            self.TryStartProcessing()

    def OnDelayedRestartChanged(self, DelayedRestart: bool):
        """延迟重启状态变化"""
        self.UpdateStatusLabel()
        if DelayedRestart:
            # 如果没有任务在处理，立即触发重启
            if not (self.ProcessThread and self.ProcessThread.isRunning()):
                DelayedRestartEmitter.DoRestart.emit()

    def UpdateStatusLabel(self):
        """更新运行状态标签"""
        if IsDelayedRestart:
            self.StatusLabel.setText("● 待重启")
            self.StatusLabel.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF5722; padding: 10px 5px;")
        elif IsPaused:
            self.StatusLabel.setText("● 待暂停")
            self.StatusLabel.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFC107; padding: 10px 5px;")
        else:
            self.StatusLabel.setText("● 运行中")
            self.StatusLabel.setStyleSheet("font-size: 14px; font-weight: bold; color: #4CAF50; padding: 10px 5px;")

    def LoadGlobalSettings(self):
        """加载全局设置到UI"""
        Settings = LoadSettings()
        self.TitlePrefixEdit.setText(Settings.get("TitlePrefix", ""))
        self.TitleSuffixEdit.setText(Settings.get("TitleSuffix", ""))
        self.DescExtraEdit.setPlainText(Settings.get("DescriptionExtra", ""))

    def OnSettingsChanged(self):
        """设置变化时保存并刷新预览"""
        Settings = {
            "TitlePrefix": self.TitlePrefixEdit.text(),
            "TitleSuffix": self.TitleSuffixEdit.text(),
            "DescriptionExtra": self.DescExtraEdit.toPlainText(),
        }
        SaveSettings(Settings)
        # 刷新当前任务预览
        if self.CurKey:
            Task = self.TaskMgr.Get(self.CurKey)
            if Task:
                TitleZh = Task.get("TitleZh") or ""
                RawTitle = Task.get("Title") or ""
                Author = Task.get("Author") or ""
                Url = Task.get("Url") or ""
                self.UpdatePreview(TitleZh or RawTitle, RawTitle, Author, Url)

    def UpdatePipelineDisplay(self, Key: str, Status: str, Progress: int):
        """更新流水线阶段显示（显示当前处理任务）"""
        Stages = ["downloading", "extracting", "recognizing", "translating", "dubbing", "merging"]
        StageNames = {
            "downloading": "下载视频",
            "extracting": "提取音频",
            "recognizing": "语音识别",
            "translating": "字幕翻译",
            "dubbing": "语音合成",
            "merging": "视频合成",
        }

        # 更新标题（显示任务时间）
        if Key:
            Timestamp = int(Key) / 1000
            TimeStr = datetime.fromtimestamp(Timestamp).strftime("%Y-%m-%d %H:%M")
            self.PipelineTitle.setText(f"当前任务: {TimeStr}")
        else:
            self.PipelineTitle.setText("当前任务: 无")

        # 找到当前阶段的索引
        CurIndex = -1
        if Status in Stages:
            CurIndex = Stages.index(Status)
        elif Status in ["ready", "published"]:
            CurIndex = len(Stages)  # 全部完成

        for I, Stage in enumerate(Stages):
            Label = self.StageLabels.get(Stage)
            if not Label:
                continue

            Name = StageNames[Stage]
            if I < CurIndex:
                # 已完成
                Label.setText(f"✓ {Name}")
                Label.setStyleSheet("font-size: 11px; color: #00aa00; padding: 1px 5px;")
            elif I == CurIndex:
                # 进行中
                if Progress > 0:
                    Label.setText(f"◉ {Name} ({Progress}%)")
                else:
                    Label.setText(f"◉ {Name}...")
                Label.setStyleSheet("font-size: 11px; color: #0088ff; padding: 1px 5px; font-weight: bold;")
            else:
                # 等待中
                Label.setText(f"○ {Name}")
                Label.setStyleSheet("font-size: 11px; color: #888; padding: 1px 5px;")

    def ClearPipelineDisplay(self):
        """清空流水线显示（无任务时）"""
        self.PipelineTitle.setText("当前任务: 无")
        StageNames = {
            "downloading": "下载视频",
            "extracting": "提取音频",
            "recognizing": "语音识别",
            "translating": "字幕翻译",
            "dubbing": "语音合成",
            "merging": "视频合成",
        }
        for Stage, Name in StageNames.items():
            Label = self.StageLabels.get(Stage)
            if Label:
                Label.setText(f"○ {Name}")
                Label.setStyleSheet("font-size: 11px; color: #888; padding: 1px 5px;")

    def UpdateProgressDisplay(self, Percent: int, Stage: str):
        """更新进度显示（状态行右侧）"""
        if Stage == "downloading" and self.CurSpeed > 0:
            # 下载时显示：进度 + 速度
            if self.CurSpeed >= 1024 * 1024:
                SpeedStr = f"{self.CurSpeed / 1024 / 1024:.1f} MB/s"
            elif self.CurSpeed >= 1024:
                SpeedStr = f"{self.CurSpeed / 1024:.1f} KB/s"
            else:
                SpeedStr = f"{self.CurSpeed:.0f} B/s"
            self.DetailProgressLabel.setText(f"{Percent}% ({SpeedStr})")
        else:
            # 其他阶段只显示进度
            self.DetailProgressLabel.setText(f"{Percent}%")

    def RefreshList(self):
        """刷新任务列表（保持选中状态和滚动位置，支持筛选）"""
        # 记住当前选中的 Key 和滚动位置
        SelectedKey = self.CurKey
        ScrollPos = self.TaskList.verticalScrollBar().value()
        # 阻止信号避免触发 OnTaskSelected
        self.TaskList.blockSignals(True)
        self.TaskList.clear()
        Tasks = self.TaskMgr.GetAll()
        for Key, Task in Tasks:
            # 筛选逻辑
            if self.FilterKeys is not None and Key not in self.FilterKeys:
                continue
            Item = self.CreateListItem(Key, Task)
            self.TaskList.addItem(Item)
        # 恢复选中和滚动位置
        if SelectedKey:
            for I in range(self.TaskList.count()):
                Item = self.TaskList.item(I)
                if Item.data(Qt.ItemDataRole.UserRole) == SelectedKey:
                    self.TaskList.setCurrentItem(Item)
                    break
        self.TaskList.verticalScrollBar().setValue(ScrollPos)
        self.TaskList.blockSignals(False)

    def CreateListItem(self, Key: str, Task: dict) -> QListWidgetItem:
        """创建列表项"""
        Timestamp = int(Key) / 1000
        TimeStr = datetime.fromtimestamp(Timestamp).strftime("%Y-%m-%d %H:%M")

        Status = Task["Status"]
        StatusText = {
            "queued": "等待中",
            "validating": "校验中...",
            "downloading": "下载中...",
            "extracting": "提取中...",
            "recognizing": "识别中...",
            "translating": "翻译中...",
            "dubbing": "配音中...",
            "merging": "合成中...",
            "paused": "已暂停",
            "ready": "待发布",
            "published": "已发布",
            "failed": "失败",
        }.get(Status, Status)
        Color = StatusColors.get(Status, "#666666")

        # 优先任务标记
        PriorityMark = "⚡ " if self.TaskMgr.IsPriority(Key) else ""

        DisplayText = f"{PriorityMark}{TimeStr}\n{StatusText}"
        Item = QListWidgetItem(DisplayText)
        Item.setData(Qt.ItemDataRole.UserRole, Key)
        Item.setForeground(QColor(Color))
        return Item

    def SelectTask(self, Key: str):
        """选中指定任务"""
        for I in range(self.TaskList.count()):
            Item = self.TaskList.item(I)
            if Item.data(Qt.ItemDataRole.UserRole) == Key:
                self.TaskList.setCurrentItem(Item)
                break

    def OnTaskSelected(self, Current: QListWidgetItem, Previous: QListWidgetItem):
        """任务选中时更新详情"""
        if not Current:
            self.ClearDetail()
            return

        Key = Current.data(Qt.ItemDataRole.UserRole)
        self.CurKey = Key
        Task = self.TaskMgr.Get(Key)
        if not Task:
            self.ClearDetail()
            return

        self.UpdateDetail(Key, Task)
        # 加载任务日志
        self.LoadTaskLog(Key)

    def UpdateDetail(self, Key: str, Task: dict):
        """更新详情面板"""
        RawTitle = Task.get("Title") or ""
        TitleZh = Task.get("TitleZh") or ""
        RawAuthor = Task.get("Author") or ""
        Url = Task["Url"]
        Status = Task["Status"]
        Progress = Task["Progress"]
        PublishUrl = Task.get("PublishUrl", "")

        StatusText = {
            "queued": "等待中",
            "validating": "校验中...",
            "downloading": "下载中...",
            "extracting": "提取中...",
            "recognizing": "识别中...",
            "translating": "翻译中...",
            "dubbing": "配音中...",
            "merging": "合成中...",
            "paused": "已暂停",
            "ready": "待发布",
            "published": "已发布",
            "failed": "失败",
        }.get(Status, Status)

        Color = StatusColors.get(Status, "#666666")

        # 显示用的标题（空则显示加载中）
        DisplayTitle = RawTitle or "加载中..."

        # 原作者、原标题、原链接
        self.DetailAuthor.setText(f"原作者: {RawAuthor}" if RawAuthor else "原作者: 加载中...")
        self.DetailTitle.setText(f"原标题: {DisplayTitle}")
        self.DetailUrl.setText(f"原链接: {Url}")
        self.CurUrl = Url  # 保存用于复制
        self.CopyUrlBtn.setVisible(True)

        # 状态
        self.DetailStatus.setText(f"状态: {StatusText}")
        self.DetailStatus.setStyleSheet(f"font-size: 13px; padding: 3px 10px; color: {Color};")

        # 进度显示（状态行右侧）
        ProcessingStatuses = ["downloading", "extracting", "recognizing", "translating", "dubbing", "merging"]
        if Status in ProcessingStatuses and Progress > 0:
            self.UpdateProgressDisplay(Progress, Status)
        else:
            self.DetailProgressLabel.setText("")

        # 发布链接（可编辑）
        self.PublishUrlEdit.setText(PublishUrl)

        # 更新发布预览（标题用翻译后的，简介中的原标题用英文原标题）
        self.UpdatePreview(TitleZh or RawTitle, RawTitle, RawAuthor, Url)

    def OnCopyUrl(self):
        """复制原链接到剪贴板"""
        if hasattr(self, "CurUrl") and self.CurUrl:
            QApplication.clipboard().setText(self.CurUrl)

    def UpdatePreview(self, TitleZh: str, RawTitle: str, Author: str, Url: str):
        """更新发布预览
        TitleZh: 翻译后的中文标题（用于标题预览）
        RawTitle: 英文原标题（用于简介中的原标题）
        """
        Settings = LoadSettings()
        Prefix = Settings.get("TitlePrefix", "")
        Suffix = Settings.get("TitleSuffix", "")
        DescExtra = Settings.get("DescriptionExtra", "")

        # 标题预览：前缀 + 中文标题 + 后缀
        if TitleZh:
            PreviewTitle = f"{Prefix}{TitleZh}{Suffix}"
        else:
            PreviewTitle = "(标题加载中...)"
        self.TitlePreview.setText(PreviewTitle)

        # 简介预览：原标题（英文）、原作者、原链接 + 简介附加
        DescLines = []
        if RawTitle:
            DescLines.append(f"原标题: {RawTitle}")
        else:
            DescLines.append("原标题: (加载中...)")
        if Author:
            DescLines.append(f"原作者: {Author}")
        else:
            DescLines.append("原作者: (加载中...)")
        if Url:
            DescLines.append(f"原链接: {Url}")
        # 简介附加：直接使用用户输入的内容
        if DescExtra:
            DescLines.append("")
            DescLines.append(DescExtra)
        self.DescPreview.setPlainText("\n".join(DescLines))

    def OnCopyTitle(self):
        """复制标题预览到剪贴板"""
        Text = self.TitlePreview.text()
        if Text:
            QApplication.clipboard().setText(Text)

    def OnCopyDesc(self):
        """复制简介预览到剪贴板"""
        Text = self.DescPreview.toPlainText()
        if Text:
            QApplication.clipboard().setText(Text)

    def OnPublish(self):
        """点击发布按钮：验证链接并清理缓存"""
        if not self.CurKey:
            return
        Url = self.PublishUrlEdit.text().strip()
        if not Url:
            Log("请输入发布链接", self.CurKey)
            return

        Log(f"验证链接: {Url}", self.CurKey)
        Success, Msg = self.TaskMgr.Archive(self.CurKey, Url)
        Log(Msg, "")  # 传空Key，避免清理后又创建日志文件

        if Success:
            self.RefreshList()
            Task = self.TaskMgr.Get(self.CurKey)
            if Task:
                self.UpdateDetail(self.CurKey, Task)

    def OnOpenFolder(self):
        """打开任务文件夹"""
        if not self.CurKey:
            return
        import os
        import subprocess
        import sys
        TaskDir = self.TaskMgr.GetTaskDir(self.CurKey)
        if TaskDir.exists():
            if sys.platform == "win32":
                subprocess.run(["explorer", str(TaskDir)])
            elif sys.platform == "darwin":
                subprocess.run(["open", str(TaskDir)])
            else:
                subprocess.run(["xdg-open", str(TaskDir)])

    def ClearDetail(self):
        """清空详情面板"""
        self.CurKey = None
        self.CurSpeed = 0
        self.CurUrl = ""
        self.DetailStatus.setText("无任务")
        self.DetailProgressLabel.setText("")
        self.DetailAuthor.setText("")
        self.DetailTitle.setText("")
        self.DetailUrl.setText("")
        self.CopyUrlBtn.setVisible(False)
        self.PublishUrlEdit.setText("")
        self.TitlePreview.setText("")
        self.DescPreview.setPlainText("")

    def OnTaskContextMenu(self, Pos):
        """任务列表右键菜单"""
        Item = self.TaskList.itemAt(Pos)
        if not Item:
            return

        Key = Item.data(Qt.ItemDataRole.UserRole)
        Task = self.TaskMgr.Get(Key)
        if not Task:
            return

        Menu = QMenu(self)

        # 优先处理/取消优先
        IsPriority = self.TaskMgr.IsPriority(Key)
        if IsPriority:
            CancelPriorityAction = Menu.addAction("取消优先")
            CancelPriorityAction.triggered.connect(lambda: self.OnCancelPriority(Key))
        else:
            PriorityAction = Menu.addAction("优先处理")
            PriorityAction.triggered.connect(lambda: self.OnSetPriority(Key))

        Menu.addSeparator()

        # 重新执行子菜单
        ResetMenu = Menu.addMenu("重新执行")

        # 检测任务实际进度（根据文件存在判断）
        TaskDir = self.TaskMgr.GetTaskDir(Key)
        HasVideo = (TaskDir / "video.mp4").exists()
        HasAudio = (TaskDir / "audio.wav").exists()
        HasEnSrt = (TaskDir / "en.srt").exists()
        HasZhSrt = (TaskDir / "zh-cn.srt").exists()
        HasZhAudio = (TaskDir / "zh-cn.wav").exists()
        HasOutput = (TaskDir / "output.mp4").exists()

        ResetAllAction = ResetMenu.addAction("全部重新执行")
        ResetAllAction.triggered.connect(lambda: self.OnResetTask(Key, "all"))

        ResetMenu.addSeparator()

        # 各阶段选项（只有已完成的阶段才能重新开始）
        ResetDownloadAction = ResetMenu.addAction("从下载开始")
        ResetDownloadAction.triggered.connect(lambda: self.OnResetTask(Key, "download"))
        ResetDownloadAction.setEnabled(HasVideo)  # 有视频才能重新下载

        ResetExtractAction = ResetMenu.addAction("从提取音频开始")
        ResetExtractAction.triggered.connect(lambda: self.OnResetTask(Key, "extract"))
        ResetExtractAction.setEnabled(HasAudio)  # 有音频才能重新提取

        ResetRecognizeAction = ResetMenu.addAction("从语音识别开始")
        ResetRecognizeAction.triggered.connect(lambda: self.OnResetTask(Key, "recognize"))
        ResetRecognizeAction.setEnabled(HasEnSrt)  # 有英文字幕才能重新识别

        ResetTranslateAction = ResetMenu.addAction("从翻译开始")
        ResetTranslateAction.triggered.connect(lambda: self.OnResetTask(Key, "translate"))
        ResetTranslateAction.setEnabled(HasZhSrt)  # 有中文字幕才能重新翻译

        ResetDubAction = ResetMenu.addAction("从配音开始")
        ResetDubAction.triggered.connect(lambda: self.OnResetTask(Key, "dub"))
        ResetDubAction.setEnabled(HasZhAudio)  # 有中文音频才能重新配音

        ResetMergeAction = ResetMenu.addAction("从合成开始")
        ResetMergeAction.triggered.connect(lambda: self.OnResetTask(Key, "merge"))
        ResetMergeAction.setEnabled(HasOutput)  # 有输出视频才能重新合成

        Menu.addSeparator()

        # 清理日志
        ClearLogAction = Menu.addAction("清理日志")
        ClearLogAction.triggered.connect(lambda: self.OnClearLog(Key))

        # 删除
        DeleteAction = Menu.addAction("删除任务")
        DeleteAction.triggered.connect(lambda: self.OnDeleteTask(Key))

        Menu.exec(self.TaskList.mapToGlobal(Pos))

    def OnSetPriority(self, Key: str):
        """设置任务优先处理"""
        self.TaskMgr.SetPriority(Key, True)
        Log(f"已设为优先处理", Key)
        self.RefreshList()

    def OnCancelPriority(self, Key: str):
        """取消任务优先处理"""
        self.TaskMgr.SetPriority(Key, False)
        Log(f"已取消优先处理", Key)
        self.RefreshList()

    def OnResetTask(self, Key: str, FromStage: str):
        """重置任务"""
        StageNames = {
            "all": "全部",
            "download": "下载",
            "extract": "提取音频",
            "recognize": "语音识别",
            "translate": "翻译",
            "dub": "配音",
            "merge": "合成",
        }
        StageName = StageNames.get(FromStage, FromStage)

        # 确认对话框
        Reply = QMessageBox.question(
            self, "确认重置",
            f"确定要从 [{StageName}] 开始重新执行吗？\n这将删除该阶段及后续的所有缓存文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if Reply != QMessageBox.StandardButton.Yes:
            return

        # 如果正在处理这个任务，需要先停止
        if CurrentProcessingKey == Key and self.ProcessThread and self.ProcessThread.isRunning():
            Log(f"任务正在处理中，尝试停止...", Key)
            # 设置 videotrans 退出标志，让识别/配音等操作尽快退出
            from videotrans.configure import config
            config.box_recogn = 'stop'
            config.box_tts = 'stop'
            # 清理可能残留的锁文件
            import glob
            LockFiles = glob.glob(config.TEMP_DIR + '/*.lock')
            for LockFile in LockFiles:
                try:
                    Path(LockFile).unlink(missing_ok=True)
                except Exception:
                    pass
            config.model_process = None
            # 等待线程结束（最多等待2秒）
            self.ProcessThread.wait(2000)
            if self.ProcessThread.isRunning():
                Log(f"警告：无法正常停止任务，将强制终止", Key)
                self.ProcessThread.terminate()
                self.ProcessThread.wait(1000)

        Success = self.TaskMgr.Reset(Key, FromStage)
        if Success:
            Log(f"任务已重置，从 [{StageName}] 开始重新执行", Key)
            self.RefreshList()
            # 更新详情
            Task = self.TaskMgr.Get(Key)
            if Task and self.CurKey == Key:
                self.UpdateDetail(Key, Task)
                self.LoadTaskLog(Key)
            # 尝试开始处理
            self.TryStartProcessing()
        else:
            Log(f"任务重置失败", Key)

    def OnDeleteTask(self, Key: str):
        """删除任务"""
        Task = self.TaskMgr.Get(Key)
        if not Task:
            return

        # 确认对话框
        Reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除该任务吗？\n这将删除任务文件夹及所有相关文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if Reply != QMessageBox.StandardButton.Yes:
            return

        # 从优先队列移除
        self.TaskMgr.SetPriority(Key, False)
        # 删除任务
        self.TaskMgr.Delete(Key)

        # 如果当前选中的就是被删除的任务，清空详情
        if self.CurKey == Key:
            self.CurKey = None
            self.ClearDetail()
            self.LogText.clear()

        self.RefreshList()

        # 选中第一个任务
        if self.TaskList.count() > 0:
            self.TaskList.setCurrentRow(0)

    def OnClearLog(self, Key: str):
        """清理任务日志"""
        TaskDir = self.TaskMgr.GetTaskDir(Key)
        LogPath = TaskDir / "log.txt"
        if LogPath.exists():
            LogPath.write_text("", encoding="utf-8")
            # 如果当前显示的是这个任务，刷新日志显示
            if self.CurKey == Key:
                self.LogText.clear()
            Log(f"日志已清理", Key)

    def closeEvent(self, Event: QCloseEvent):
        """关闭窗口时隐藏而非退出"""
        Event.ignore()
        self.hide()
        self.Closed.emit()
