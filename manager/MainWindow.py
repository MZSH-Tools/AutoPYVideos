# 管理界面主窗口
import sys
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QFrame, QSplitter, QApplication, QTextEdit
)
from PySide6.QtCore import Signal, Qt, QThread, QObject
from PySide6.QtGui import QCloseEvent, QColor

from pathlib import Path
from Task import TaskManager, TaskStatus
from Extract import ExtractAudio
import Recognize
from Recognize import RecognizeAudio
import Translate
from Translate import TranslateSrt
import Dubbing
from Dubbing import GenerateDubbing
import Merge
from Merge import MergeVideo


# 全局 Debug 标志
DebugMode = False


class LogSignal(QObject):
    """日志信号，用于跨线程发送日志"""
    Message = Signal(str, bool)  # Msg, IsDebug

LogEmitter = LogSignal()


def Log(Msg: str):
    """普通日志"""
    LogEmitter.Message.emit(Msg, False)


def LogDebug(Msg: str):
    """调试日志"""
    LogEmitter.Message.emit(Msg, True)


# 设置模块日志函数
Recognize.SetLogFunc(Log)
Translate.SetLogFunc(Log)
Dubbing.SetLogFunc(Log)
Merge.SetLogFunc(Log)


class LogWriter:
    """重定向stdout到GUI（作为调试日志）"""
    def __init__(self):
        self.Terminal = sys.__stdout__

    def write(self, Msg):
        if Msg.strip():
            LogEmitter.Message.emit(Msg.strip(), True)

    def flush(self):
        pass


class FetchInfoThread(QThread):
    """后台获取视频信息的线程"""
    Finished = Signal(str, bool)  # Key, Success

    def __init__(self, TaskMgr: TaskManager, Key: str, Url: str):
        super().__init__()
        self.TaskMgr = TaskMgr
        self.Key = Key
        self.Url = Url

    def run(self):
        Success = self.TaskMgr.FetchInfo(self.Key)
        self.Finished.emit(self.Key, Success)


class ProcessThread(QThread):
    """后台处理任务的线程（下载 → 识别 → 翻译 → 配音 → 合成）"""
    Progress = Signal(str, int, str, float)   # Key, Percent, Stage, Speed
    StageChanged = Signal(str, str)           # Key, Stage
    Finished = Signal(str, bool)              # Key, Success

    def __init__(self, TaskMgr: TaskManager, Key: str):
        super().__init__()
        self.TaskMgr = TaskMgr
        self.Key = Key

    def run(self):
        """全自动流水线：根据文件存在决定从哪个阶段开始"""
        Task = self.TaskMgr.Get(self.Key)
        if not Task:
            self.Finished.emit(self.Key, False)
            return

        TaskDir = self.TaskMgr.GetTaskDir(self.Key)
        VideoPath = TaskDir / "video.mp4"
        AudioPath = TaskDir / "audio.wav"
        EnSrtPath = TaskDir / "en.srt"
        ZhSrtPath = TaskDir / "zh-cn.srt"
        ZhAudioPath = TaskDir / "zh-cn.wav"
        OutputPath = TaskDir / "output.mp4"

        try:
            # 阶段 1: 下载视频
            if not VideoPath.exists():
                self.StageChanged.emit(self.Key, "downloading")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Downloading, Progress=0)

                def OnDownloadProgress(Percent, Status, Speed):
                    self.Progress.emit(self.Key, Percent, "downloading", Speed or 0)

                try:
                    Success = self.TaskMgr.Download(self.Key, OnDownloadProgress)
                    if not Success:
                        Log(f"Download failed: {Task['Url']}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"Download error: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False)
                    return

            # 阶段 2: 提取音频
            if not AudioPath.exists():
                self.StageChanged.emit(self.Key, "extracting")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Extracting, Progress=0)

                try:
                    Result = ExtractAudio(VideoPath, AudioPath)
                    if not Result:
                        Log(f"Audio extraction failed: {VideoPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"Extraction error: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False)
                    return

                self.TaskMgr.Update(self.Key, Progress=100)

            # 阶段 3: 语音识别
            if not EnSrtPath.exists():
                self.StageChanged.emit(self.Key, "recognizing")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Recognizing, Progress=0)

                def OnRecognizeProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "recognizing", 0)

                try:
                    Result = RecognizeAudio(AudioPath, EnSrtPath, Language="en",
                                            ProgressCallback=OnRecognizeProgress)
                    if not Result:
                        Log(f"Recognition failed: {AudioPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"Recognition error: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False)
                    return

            # 阶段 4: 翻译（英文 → 中文）
            if not ZhSrtPath.exists():
                self.StageChanged.emit(self.Key, "translating")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Translating, Progress=0)

                def OnTranslateProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "translating", 0)

                try:
                    Result = TranslateSrt(EnSrtPath, ZhSrtPath,
                                          SourceLang="en", TargetLang="zh-CN",
                                          ProgressCallback=OnTranslateProgress)
                    if not Result:
                        Log(f"Translation failed: {EnSrtPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"Translation error: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False)
                    return

            # 阶段 5: 配音（中文 TTS）
            if not ZhAudioPath.exists():
                self.StageChanged.emit(self.Key, "dubbing")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Dubbing, Progress=0)

                def OnDubbingProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "dubbing", 0)

                try:
                    Result = GenerateDubbing(ZhSrtPath, ZhAudioPath,
                                             ProgressCallback=OnDubbingProgress)
                    if not Result:
                        Log(f"Dubbing failed: {ZhSrtPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"Dubbing error: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False)
                    return

            # 阶段 6: 合成（音视频合并）
            if not OutputPath.exists():
                self.StageChanged.emit(self.Key, "merging")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Merging, Progress=0)

                def OnMergeProgress(Percent, Text):
                    self.Progress.emit(self.Key, Percent, "merging", 0)

                try:
                    Result = MergeVideo(VideoPath, ZhAudioPath, ZhSrtPath, OutputPath,
                                        ProgressCallback=OnMergeProgress)
                    if not Result:
                        Log(f"Merge failed: {VideoPath}")
                        self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                        self.Finished.emit(self.Key, False)
                        return
                except Exception as E:
                    import traceback
                    Log(f"Merge error: {E}")
                    Log(traceback.format_exc())
                    self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
                    self.Finished.emit(self.Key, False)
                    return

            # 全部完成，标记为待发布
            self.TaskMgr.Update(self.Key, Status=TaskStatus.Ready, Progress=100)
            Log(f"Task completed: {self.Key}")
            self.Finished.emit(self.Key, True)

        except Exception as E:
            import traceback
            Log(f"Process error: {E}")
            Log(traceback.format_exc())
            self.TaskMgr.Update(self.Key, Status=TaskStatus.Failed)
            self.Finished.emit(self.Key, False)


# 状态对应颜色
StatusColors = {
    "queued": "#999999",      # 灰色 - 等待
    "downloading": "#0088ff", # 蓝色 - 下载中
    "extracting": "#ff8800",  # 橙色 - 提取中
    "recognizing": "#ff8800", # 橙色 - 识别中
    "translating": "#ff8800", # 橙色 - 翻译中
    "dubbing": "#ff8800",     # 橙色 - 配音中
    "merging": "#ff8800",     # 橙色 - 合成中
    "ready": "#00aa00",       # 绿色 - 待发布
    "published": "#666666",   # 深灰 - 已发布
    "failed": "#cc0000",      # 红色 - 失败
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
        self.SetupUI()
        Log("Manager started")
        self.RefreshList()
        self.SelectProcessingTask()
        self.TryStartProcessing()

    def SetupUI(self):
        """初始化界面"""
        self.setWindowTitle("AutoPYVideos Manager")
        self.setMinimumSize(900, 600)

        Central = QWidget()
        self.setCentralWidget(Central)
        Layout = QVBoxLayout(Central)

        # 搜索栏
        SearchLayout = QHBoxLayout()
        self.UrlInput = QLineEdit()
        self.UrlInput.setPlaceholderText("输入 YouTube 链接...")
        self.UrlInput.returnPressed.connect(self.OnSearch)
        SearchLayout.addWidget(self.UrlInput)

        self.SearchBtn = QPushButton("🔍")
        self.SearchBtn.setFixedWidth(40)
        self.SearchBtn.clicked.connect(self.OnSearch)
        SearchLayout.addWidget(self.SearchBtn)

        Layout.addLayout(SearchLayout)

        # 分割器：左侧列表 + 右侧详情
        Splitter = QSplitter(Qt.Orientation.Horizontal)
        Layout.addWidget(Splitter)

        # 左侧任务列表
        self.TaskList = QListWidget()
        self.TaskList.setMaximumWidth(250)
        self.TaskList.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.TaskList.currentItemChanged.connect(self.OnTaskSelected)
        Splitter.addWidget(self.TaskList)

        # 右侧详情面板
        DetailPanel = QFrame()
        DetailPanel.setFrameShape(QFrame.Shape.StyledPanel)
        DetailLayout = QVBoxLayout(DetailPanel)
        Splitter.addWidget(DetailPanel)

        # 详情内容样式
        LabelStyle = "font-size: 13px; color: #333; padding: 3px 10px;"
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

        DetailLayout.addStretch()

        # 发布链接（可编辑，贴在底部）
        PublishLayout = QHBoxLayout()
        PublishLabel = QLabel("发布链接:")
        PublishLabel.setStyleSheet(LabelStyle)
        PublishLayout.addWidget(PublishLabel)
        self.PublishUrlEdit = QLineEdit()
        self.PublishUrlEdit.setPlaceholderText("输入发布后的链接...")
        self.PublishUrlEdit.editingFinished.connect(self.OnPublishUrlChanged)
        PublishLayout.addWidget(self.PublishUrlEdit)
        DetailLayout.addLayout(PublishLayout)

        # 打开文件夹按钮（最下面）
        self.OpenFolderBtn = QPushButton("打开文件夹")
        self.OpenFolderBtn.clicked.connect(self.OnOpenFolder)
        DetailLayout.addWidget(self.OpenFolderBtn)

        Splitter.setSizes([250, 650])

        # 底部区域：左侧当前任务流程 + 右侧日志
        BottomLayout = QHBoxLayout()

        # 左侧：当前任务流程
        PipelinePanel = QFrame()
        PipelinePanel.setFrameShape(QFrame.Shape.StyledPanel)
        PipelinePanel.setFixedWidth(200)
        PipelineLayout = QVBoxLayout(PipelinePanel)
        PipelineLayout.setContentsMargins(10, 5, 10, 5)

        # 当前任务标题
        self.PipelineTitle = QLabel("当前任务: 无")
        self.PipelineTitle.setStyleSheet("font-size: 12px; font-weight: bold; color: #333;")
        PipelineLayout.addWidget(self.PipelineTitle)

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
            Label.setStyleSheet("font-size: 11px; color: #999; padding: 1px 5px;")
            PipelineLayout.addWidget(Label)
            self.StageLabels[StageKey] = Label

        PipelineLayout.addStretch()
        BottomLayout.addWidget(PipelinePanel)

        # 右侧：日志
        self.LogText = QTextEdit()
        self.LogText.setReadOnly(True)
        self.LogText.setMaximumHeight(140)
        self.LogText.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; background: #f5f5f5; color: #333;")
        BottomLayout.addWidget(self.LogText)

        Layout.addLayout(BottomLayout)

        # 连接日志信号
        LogEmitter.Message.connect(self.AppendLog)
        sys.stdout = LogWriter()

        # 存储后台线程
        self.FetchThreads = []

    def AppendLog(self, Msg: str, IsDebug: bool = False):
        """添加日志"""
        # Debug 日志只在 Debug 模式下显示
        if IsDebug and not DebugMode:
            return
        TimeStr = datetime.now().strftime("%H:%M:%S")
        Prefix = "[DEBUG] " if IsDebug else ""
        self.LogText.append(f"[{TimeStr}] {Prefix}{Msg}")
        # 滚动到底部
        self.LogText.verticalScrollBar().setValue(self.LogText.verticalScrollBar().maximum())

    def OnSearch(self):
        """搜索/添加链接"""
        Url = self.UrlInput.text().strip()
        if not Url:
            return

        Found = self.TaskMgr.FindByUrl(Url)
        if Found:
            Key, Task = Found
            self.RefreshList()
            self.SelectTask(Key)
            Log(f"Task already exists: {Url[:50]}...")
        else:
            Key = self.TaskMgr.Add(Url)
            self.RefreshList()
            self.SelectTask(Key)
            Log(f"Task added, fetching info...")
            # 后台获取视频信息
            self.StartFetchInfo(Key, Url)

        self.UrlInput.clear()

    def StartFetchInfo(self, Key: str, Url: str):
        """启动后台获取视频信息"""
        Thread = FetchInfoThread(self.TaskMgr, Key, Url)
        Thread.Finished.connect(self.OnFetchInfoFinished)
        self.FetchThreads.append(Thread)
        Thread.start()

    def OnFetchInfoFinished(self, Key: str, Success: bool):
        """视频信息获取完成"""
        Task = self.TaskMgr.Get(Key)
        if Success and Task:
            Log(f"Info fetched: {Task.get('Title', '')[:30]}")
        else:
            Log(f"Failed to fetch info for task {Key}")
        # 刷新列表和详情（保持选中）
        self.RefreshList()
        if self.CurKey == Key and Task:
            self.UpdateDetail(Key, Task)
        # 尝试启动自动处理
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
        # 如果已有任务在处理，不启动新的
        if self.ProcessThread and self.ProcessThread.isRunning():
            return

        # 需要处理的状态（等待中 或 中间状态需要继续）
        PendingStatuses = [
            TaskStatus.Queued.value,
            TaskStatus.Extracting.value,
            TaskStatus.Recognizing.value,
            TaskStatus.Translating.value,
            TaskStatus.Dubbing.value,
            TaskStatus.Merging.value,
        ]

        # 找到第一个需要处理的任务
        for Key, Task in self.TaskMgr.GetAll():
            if Task["Status"] in PendingStatuses:
                self.StartProcessing(Key)
                return

        # 没有任务需要处理，清空流水线显示
        self.ClearPipelineDisplay()

    def StartProcessing(self, Key: str):
        """启动任务处理"""
        self.ProcessThread = ProcessThread(self.TaskMgr, Key)
        self.ProcessThread.Progress.connect(self.OnProcessProgress)
        self.ProcessThread.StageChanged.connect(self.OnStageChanged)
        self.ProcessThread.Finished.connect(self.OnProcessFinished)
        self.ProcessThread.start()
        # 选中这个任务
        self.SelectTask(Key)

    def OnProcessProgress(self, Key: str, Percent: int, Stage: str, Speed: float):
        """处理进度更新"""
        self.RefreshList()
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

    def OnProcessFinished(self, Key: str, Success: bool):
        """处理完成"""
        self.RefreshList()
        Task = self.TaskMgr.Get(Key)
        # 更新详情面板
        if self.CurKey == Key and Task:
            self.UpdateDetail(Key, Task)
        # 尝试处理下一个任务（会自动更新流水线显示）
        self.TryStartProcessing()

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
                Label.setStyleSheet("font-size: 11px; color: #999; padding: 1px 5px;")

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
                Label.setStyleSheet("font-size: 11px; color: #999; padding: 1px 5px;")

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
        """刷新任务列表（保持选中状态）"""
        # 记住当前选中的 Key
        SelectedKey = self.CurKey
        # 阻止信号避免触发 OnTaskSelected
        self.TaskList.blockSignals(True)
        self.TaskList.clear()
        Tasks = self.TaskMgr.GetAll()
        for Key, Task in Tasks:
            Item = self.CreateListItem(Key, Task)
            self.TaskList.addItem(Item)
        # 恢复选中
        if SelectedKey:
            for I in range(self.TaskList.count()):
                Item = self.TaskList.item(I)
                if Item.data(Qt.ItemDataRole.UserRole) == SelectedKey:
                    self.TaskList.setCurrentItem(Item)
                    break
        self.TaskList.blockSignals(False)

    def CreateListItem(self, Key: str, Task: dict) -> QListWidgetItem:
        """创建列表项"""
        Timestamp = int(Key) / 1000
        TimeStr = datetime.fromtimestamp(Timestamp).strftime("%Y-%m-%d %H:%M")

        Status = Task["Status"]
        StatusText = {
            "queued": "等待中",
            "downloading": "下载中...",
            "extracting": "提取中...",
            "recognizing": "识别中...",
            "translating": "翻译中...",
            "dubbing": "配音中...",
            "merging": "合成中...",
            "ready": "待发布",
            "published": "已发布",
            "failed": "失败",
        }.get(Status, Status)
        Color = StatusColors.get(Status, "#666666")

        DisplayText = f"{TimeStr}\n{StatusText}"
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

    def UpdateDetail(self, Key: str, Task: dict):
        """更新详情面板"""
        Title = Task.get("Title") or "加载中..."
        Author = Task.get("Author") or ""
        Url = Task["Url"]
        Status = Task["Status"]
        Progress = Task["Progress"]
        PublishUrl = Task.get("PublishUrl", "")

        StatusText = {
            "queued": "等待中",
            "downloading": "下载中...",
            "extracting": "提取中...",
            "recognizing": "识别中...",
            "translating": "翻译中...",
            "dubbing": "配音中...",
            "merging": "合成中...",
            "ready": "待发布",
            "published": "已发布",
            "failed": "失败",
        }.get(Status, Status)

        Color = StatusColors.get(Status, "#666666")

        # 原作者、原标题、原链接
        self.DetailAuthor.setText(f"原作者: {Author}" if Author else "")
        self.DetailTitle.setText(f"原标题: {Title}")
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

    def OnCopyUrl(self):
        """复制原链接到剪贴板"""
        if hasattr(self, "CurUrl") and self.CurUrl:
            QApplication.clipboard().setText(self.CurUrl)
            Log("链接已复制")

    def OnPublishUrlChanged(self):
        """发布链接编辑完成"""
        if not self.CurKey:
            return
        NewUrl = self.PublishUrlEdit.text().strip()
        self.TaskMgr.Update(self.CurKey, PublishUrl=NewUrl)

    def OnOpenFolder(self):
        """打开任务文件夹"""
        if not self.CurKey:
            return
        import os
        import subprocess
        TaskDir = self.TaskMgr.GetTaskDir(self.CurKey)
        if TaskDir.exists():
            if os.name == "nt":
                subprocess.run(["explorer", str(TaskDir)])
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

    def closeEvent(self, Event: QCloseEvent):
        """关闭窗口时隐藏而非退出"""
        Event.ignore()
        self.hide()
        self.Closed.emit()
