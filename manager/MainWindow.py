# 管理界面主窗口
import sys
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QFrame, QSplitter, QProgressBar, QApplication, QTextEdit
)
from PySide6.QtCore import Signal, Qt, QThread, QObject
from PySide6.QtGui import QCloseEvent, QColor

from Cache import TaskManager, TaskStatus


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

    def __init__(self, Key: str, Url: str):
        super().__init__()
        self.Key = Key
        self.Url = Url
        self.TaskMgr = TaskManager()  # 独立实例

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
        Task = self.TaskMgr.Get(self.Key)
        if not Task:
            self.Finished.emit(self.Key, False)
            return

        try:
            # 阶段 1: 下载
            if Task["Status"] == TaskStatus.Queued.value:
                self.StageChanged.emit(self.Key, "downloading")
                self.TaskMgr.Update(self.Key, Status=TaskStatus.Downloading, Progress=0)

                def OnDownloadProgress(Percent, Status, Speed):
                    self.Progress.emit(self.Key, Percent, "downloading", Speed or 0)

                Success = self.TaskMgr.Download(self.Key, OnDownloadProgress)
                if not Success:
                    self.Finished.emit(self.Key, False)
                    return

            # 阶段 2-5: 识别、翻译、配音、合成（待实现）
            # 暂时直接标记为待发布
            self.TaskMgr.Update(self.Key, Status=TaskStatus.Ready, Progress=100)
            self.Finished.emit(self.Key, True)

        except Exception as E:
            self.TaskMgr.Update(self.Key, Error=str(E))
            self.Finished.emit(self.Key, False)


# 状态对应颜色
StatusColors = {
    "queued": "#999999",      # 灰色 - 等待
    "downloading": "#0088ff", # 蓝色 - 下载中
    "recognizing": "#ff8800", # 橙色 - 识别中
    "translating": "#ff8800", # 橙色 - 翻译中
    "dubbing": "#ff8800",     # 橙色 - 配音中
    "merging": "#ff8800",     # 橙色 - 合成中
    "ready": "#00aa00",       # 绿色 - 待发布
    "published": "#666666",   # 深灰 - 已发布
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

        # 详情内容（普通正文样式）
        LabelStyle = "font-size: 13px; color: #333; padding: 3px 10px;"

        # 状态（第一行）
        self.DetailStatus = QLabel("")
        self.DetailStatus.setStyleSheet("font-size: 13px; padding: 3px 10px;")
        DetailLayout.addWidget(self.DetailStatus)

        self.DetailAuthor = QLabel("")
        self.DetailAuthor.setStyleSheet(LabelStyle)
        self.DetailAuthor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        DetailLayout.addWidget(self.DetailAuthor)

        self.DetailTitle = QLabel("")
        self.DetailTitle.setStyleSheet(LabelStyle)
        self.DetailTitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailTitle.setWordWrap(True)
        DetailLayout.addWidget(self.DetailTitle)

        # 原链接 + 复制按钮
        UrlLayout = QHBoxLayout()
        self.DetailUrl = QLabel("")
        self.DetailUrl.setStyleSheet(LabelStyle)
        self.DetailUrl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailUrl.setWordWrap(True)
        UrlLayout.addWidget(self.DetailUrl, 1)
        self.CopyUrlBtn = QPushButton("复制")
        self.CopyUrlBtn.setFixedWidth(50)
        self.CopyUrlBtn.clicked.connect(self.OnCopyUrl)
        self.CopyUrlBtn.setVisible(False)
        UrlLayout.addWidget(self.CopyUrlBtn)
        DetailLayout.addLayout(UrlLayout)

        self.DetailDuration = QLabel("")
        self.DetailDuration.setStyleSheet(LabelStyle)
        DetailLayout.addWidget(self.DetailDuration)

        self.DetailProgress = QProgressBar()
        self.DetailProgress.setVisible(False)
        DetailLayout.addWidget(self.DetailProgress)

        self.DetailSpeed = QLabel("")
        self.DetailSpeed.setStyleSheet("color: #0088ff; padding: 3px 10px;")
        self.DetailSpeed.setVisible(False)
        DetailLayout.addWidget(self.DetailSpeed)

        self.DetailError = QLabel("")
        self.DetailError.setStyleSheet("color: #cc0000; padding: 3px 10px;")
        self.DetailError.setWordWrap(True)
        self.DetailError.setVisible(False)
        DetailLayout.addWidget(self.DetailError)

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

        # 底部日志区域
        self.LogText = QTextEdit()
        self.LogText.setReadOnly(True)
        self.LogText.setMaximumHeight(120)
        self.LogText.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; background: #f5f5f5; color: #333;")
        Layout.addWidget(self.LogText)

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
        Thread = FetchInfoThread(Key, Url)
        Thread.Finished.connect(self.OnFetchInfoFinished)
        self.FetchThreads.append(Thread)
        Thread.start()

    def OnFetchInfoFinished(self, Key: str, Success: bool):
        """视频信息获取完成"""
        # 重新加载任务数据
        self.TaskMgr.Load()
        Task = self.TaskMgr.Get(Key)
        if Success and Task:
            Log(f"Info fetched: {Task.get('Title', '')[:30]}")
        else:
            Log(f"Failed to fetch info for task {Key}")
        # 刷新列表和详情（保持选中）
        self.RefreshList()
        if self.CurKey == Key and Task:
            self.UpdateDetail(Key, Task)
        # 注意：信息获取完成后不自动开始下载，等用户确认

    def SelectProcessingTask(self):
        """选中正在处理的任务，如果没有则选中第一个任务"""
        ProcessingStatuses = [
            TaskStatus.Downloading.value,
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

        # 找到第一个等待处理的任务
        for Key, Task in self.TaskMgr.GetAll():
            if Task["Status"] == TaskStatus.Queued.value:
                self.StartProcessing(Key)
                return

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
        if self.CurKey == Key:
            self.DetailProgress.setValue(Percent)
            self.CurSpeed = Speed
            self.UpdateSpeedDisplay()

    def OnStageChanged(self, Key: str, Stage: str):
        """处理阶段变化"""
        self.RefreshList()
        if self.CurKey == Key:
            Task = self.TaskMgr.Get(Key)
            if Task:
                self.UpdateDetail(Key, Task)

    def OnProcessFinished(self, Key: str, Success: bool):
        """处理完成"""
        self.RefreshList()
        if self.CurKey == Key:
            Task = self.TaskMgr.Get(Key)
            if Task:
                self.UpdateDetail(Key, Task)
        # 尝试处理下一个任务
        self.TryStartProcessing()

    def UpdateSpeedDisplay(self):
        """更新速度显示"""
        if self.CurSpeed > 0:
            if self.CurSpeed >= 1024 * 1024:
                SpeedStr = f"{self.CurSpeed / 1024 / 1024:.1f} MB/s"
            elif self.CurSpeed >= 1024:
                SpeedStr = f"{self.CurSpeed / 1024:.1f} KB/s"
            else:
                SpeedStr = f"{self.CurSpeed:.0f} B/s"
            self.DetailSpeed.setText(f"速度: {SpeedStr}")
            self.DetailSpeed.setVisible(True)
        else:
            self.DetailSpeed.setVisible(False)

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
            "recognizing": "识别中...",
            "translating": "翻译中...",
            "dubbing": "配音中...",
            "merging": "合成中...",
            "ready": "待发布",
            "published": "已发布",
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
        Duration = Task.get("Duration", 0)
        PublishUrl = Task.get("PublishUrl", "")
        Error = Task.get("Error", "")

        StatusText = {
            "queued": "等待中",
            "downloading": "下载中...",
            "recognizing": "识别中...",
            "translating": "翻译中...",
            "dubbing": "配音中...",
            "merging": "合成中...",
            "ready": "待发布",
            "published": "已发布",
        }.get(Status, Status)

        Color = StatusColors.get(Status, "#666666")

        # 原作者、原标题、原链接
        self.DetailAuthor.setText(f"原作者: {Author}" if Author else "")
        self.DetailTitle.setText(f"原标题: {Title}")
        self.DetailUrl.setText(f"原链接: {Url}")
        self.CurUrl = Url  # 保存用于复制
        self.CopyUrlBtn.setVisible(True)

        # 视频时长
        if Duration > 0:
            Minutes = Duration // 60
            Seconds = Duration % 60
            self.DetailDuration.setText(f"视频时长: {Minutes}:{Seconds:02d}")
        else:
            self.DetailDuration.setText("")

        # 状态
        self.DetailStatus.setText(f"状态: {StatusText}")
        self.DetailStatus.setStyleSheet(f"font-size: 13px; padding: 3px 10px; color: {Color};")

        # 进度条和速度
        ProcessingStatuses = ["downloading", "recognizing", "translating", "dubbing", "merging"]
        if Status in ProcessingStatuses:
            self.DetailProgress.setVisible(True)
            self.DetailProgress.setValue(Progress)
            if Status == "downloading":
                self.UpdateSpeedDisplay()
            else:
                self.DetailSpeed.setVisible(False)
        else:
            self.DetailProgress.setVisible(False)
            self.DetailSpeed.setVisible(False)

        # 发布链接（可编辑）
        self.PublishUrlEdit.setText(PublishUrl)

        # 错误信息
        if Error:
            self.DetailError.setText(f"错误: {Error}")
            self.DetailError.setVisible(True)
        else:
            self.DetailError.setVisible(False)

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
        self.DetailAuthor.setText("")
        self.DetailTitle.setText("")
        self.DetailUrl.setText("")
        self.DetailDuration.setText("")
        self.DetailProgress.setVisible(False)
        self.DetailSpeed.setVisible(False)
        self.CopyUrlBtn.setVisible(False)
        self.PublishUrlEdit.setText("")
        self.DetailError.setVisible(False)

    def closeEvent(self, Event: QCloseEvent):
        """关闭窗口时隐藏而非退出"""
        Event.ignore()
        self.hide()
        self.Closed.emit()
