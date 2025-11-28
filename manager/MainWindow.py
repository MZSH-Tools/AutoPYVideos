# 管理界面主窗口
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QFrame, QSplitter, QProgressBar, QApplication
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QCloseEvent, QColor

from Cache import TaskManager, TaskStatus


class FetchInfoThread(QThread):
    """后台获取视频信息的线程"""
    Finished = Signal(str, bool)  # Key, Success

    def __init__(self, TaskMgr: TaskManager, Key: str):
        super().__init__()
        self.TaskMgr = TaskMgr
        self.Key = Key

    def run(self):
        Success = self.TaskMgr.FetchInfo(self.Key)
        self.Finished.emit(self.Key, Success)


class ProcessThread(QThread):
    """后台处理任务的线程（下载 → 识别 → 翻译 → 配音 → 合成）"""
    Progress = Signal(str, int, str)   # Key, Percent, Stage
    StageChanged = Signal(str, str)    # Key, Stage
    Finished = Signal(str, bool)       # Key, Success

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

                def OnDownloadProgress(Percent, Status):
                    self.Progress.emit(self.Key, Percent, "downloading")

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

        # 详情内容
        self.DetailTitle = QLabel("选择一个任务")
        self.DetailTitle.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        self.DetailTitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailTitle.setWordWrap(True)
        DetailLayout.addWidget(self.DetailTitle)

        self.DetailAuthor = QLabel("")
        self.DetailAuthor.setStyleSheet("font-size: 14px; color: #444; padding: 0 10px;")
        self.DetailAuthor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        DetailLayout.addWidget(self.DetailAuthor)

        self.DetailUrl = QLabel("")
        self.DetailUrl.setStyleSheet("color: #666; padding: 5px 10px;")
        self.DetailUrl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailUrl.setWordWrap(True)
        DetailLayout.addWidget(self.DetailUrl)

        self.DetailStatus = QLabel("")
        self.DetailStatus.setStyleSheet("font-size: 14px; padding: 10px;")
        DetailLayout.addWidget(self.DetailStatus)

        self.DetailProgress = QProgressBar()
        self.DetailProgress.setVisible(False)
        DetailLayout.addWidget(self.DetailProgress)

        self.DetailDuration = QLabel("")
        self.DetailDuration.setStyleSheet("color: #888; padding: 5px 10px;")
        DetailLayout.addWidget(self.DetailDuration)

        self.DetailTime = QLabel("")
        self.DetailTime.setStyleSheet("color: #888; padding: 5px 10px;")
        DetailLayout.addWidget(self.DetailTime)

        self.DetailPublishUrl = QLabel("")
        self.DetailPublishUrl.setStyleSheet("color: #0066cc; padding: 5px 10px;")
        self.DetailPublishUrl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailPublishUrl.setWordWrap(True)
        self.DetailPublishUrl.setVisible(False)
        DetailLayout.addWidget(self.DetailPublishUrl)

        self.DetailError = QLabel("")
        self.DetailError.setStyleSheet("color: #cc0000; padding: 10px;")
        self.DetailError.setWordWrap(True)
        self.DetailError.setVisible(False)
        DetailLayout.addWidget(self.DetailError)

        DetailLayout.addStretch()

        # 存储后台线程
        self.FetchThreads = []

        Splitter.setSizes([250, 650])

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
        else:
            Key = self.TaskMgr.Add(Url)
            self.RefreshList()
            self.SelectTask(Key)
            # 后台获取视频信息
            self.StartFetchInfo(Key)

        self.UrlInput.clear()

    def StartFetchInfo(self, Key: str):
        """启动后台获取视频信息"""
        Thread = FetchInfoThread(self.TaskMgr, Key)
        Thread.Finished.connect(self.OnFetchInfoFinished)
        self.FetchThreads.append(Thread)
        Thread.start()

    def OnFetchInfoFinished(self, Key: str, Success: bool):
        """视频信息获取完成"""
        # 刷新列表和详情
        self.RefreshList()
        if self.CurKey == Key:
            Task = self.TaskMgr.Get(Key)
            if Task:
                self.UpdateDetail(Key, Task)
        # 尝试启动自动处理
        self.TryStartProcessing()

    def SelectProcessingTask(self):
        """选中正在处理的任务，如果没有则选中第一个等待的任务"""
        ProcessingStatuses = [
            TaskStatus.Downloading.value,
            TaskStatus.Recognizing.value,
            TaskStatus.Translating.value,
            TaskStatus.Dubbing.value,
            TaskStatus.Merging.value,
        ]
        # 先找正在处理的
        for Key, Task in self.TaskMgr.GetAll():
            if Task["Status"] in ProcessingStatuses:
                self.SelectTask(Key)
                return
        # 再找等待开始的
        for Key, Task in self.TaskMgr.GetAll():
            if Task["Status"] == TaskStatus.Queued.value:
                self.SelectTask(Key)
                return

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

    def OnProcessProgress(self, Key: str, Percent: int, Stage: str):
        """处理进度更新"""
        self.RefreshList()
        if self.CurKey == Key:
            self.DetailProgress.setValue(Percent)

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

    def RefreshList(self):
        """刷新任务列表"""
        self.TaskList.clear()
        Tasks = self.TaskMgr.GetAll()
        for Key, Task in Tasks:
            Item = self.CreateListItem(Key, Task)
            self.TaskList.addItem(Item)

    def CreateListItem(self, Key: str, Task: dict) -> QListWidgetItem:
        """创建列表项"""
        Timestamp = int(Key) / 1000
        TimeStr = datetime.fromtimestamp(Timestamp).strftime("%m-%d %H:%M")

        Status = Task["Status"]
        Color = StatusColors.get(Status, "#666666")

        Item = QListWidgetItem(TimeStr)
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

        Timestamp = int(Key) / 1000
        TimeStr = datetime.fromtimestamp(Timestamp).strftime("%Y-%m-%d %H:%M:%S")

        StatusText = {
            "queued": "等待开始",
            "downloading": "下载中...",
            "recognizing": "识别中...",
            "translating": "翻译中...",
            "dubbing": "配音中...",
            "merging": "合成中...",
            "ready": "待发布",
            "published": "已发布",
        }.get(Status, Status)

        Color = StatusColors.get(Status, "#666666")

        # 标题和作者
        self.DetailTitle.setText(Title)
        self.DetailAuthor.setText(f"作者: {Author}" if Author else "")

        # URL
        self.DetailUrl.setText(f"原链接: {Url}")

        # 状态
        self.DetailStatus.setText(StatusText)
        self.DetailStatus.setStyleSheet(f"font-size: 14px; padding: 10px; color: {Color};")

        # 时长
        if Duration > 0:
            Minutes = Duration // 60
            Seconds = Duration % 60
            self.DetailDuration.setText(f"时长: {Minutes}:{Seconds:02d}")
        else:
            self.DetailDuration.setText("")

        # 添加时间
        self.DetailTime.setText(f"添加时间: {TimeStr}")

        # 进度条（下载、识别、翻译、配音、合成时显示）
        ProcessingStatuses = ["downloading", "recognizing", "translating", "dubbing", "merging"]
        if Status in ProcessingStatuses:
            self.DetailProgress.setVisible(True)
            self.DetailProgress.setValue(Progress)
        else:
            self.DetailProgress.setVisible(False)


        # 发布链接
        if PublishUrl:
            self.DetailPublishUrl.setText(f"发布链接: {PublishUrl}")
            self.DetailPublishUrl.setVisible(True)
        else:
            self.DetailPublishUrl.setText("发布链接: 暂无")
            self.DetailPublishUrl.setVisible(True)

        # 错误信息
        if Error:
            self.DetailError.setText(f"错误: {Error}")
            self.DetailError.setVisible(True)
        else:
            self.DetailError.setVisible(False)

    def ClearDetail(self):
        """清空详情面板"""
        self.CurKey = None
        self.DetailTitle.setText("选择一个任务")
        self.DetailAuthor.setText("")
        self.DetailUrl.setText("")
        self.DetailStatus.setText("")
        self.DetailDuration.setText("")
        self.DetailTime.setText("")
        self.DetailProgress.setVisible(False)
        self.DetailPublishUrl.setVisible(False)
        self.DetailError.setVisible(False)

    def closeEvent(self, Event: QCloseEvent):
        """关闭窗口时隐藏而非退出"""
        Event.ignore()
        self.hide()
        self.Closed.emit()
