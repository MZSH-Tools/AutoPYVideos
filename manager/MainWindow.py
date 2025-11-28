# 管理界面主窗口
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QFrame, QSplitter, QProgressBar
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QCloseEvent, QColor

from Cache import TaskManager, TaskStatus


# 状态对应颜色
StatusColors = {
    "queued": "#999999",      # 灰色 - 等待
    "downloading": "#0088ff", # 蓝色 - 下载中
    "processing": "#ff8800",  # 橙色 - 处理中
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
        self.SetupUI()
        self.RefreshList()

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
        self.UrlInput.setPlaceholderText("Enter YouTube URL...")
        self.UrlInput.returnPressed.connect(self.OnSearch)
        SearchLayout.addWidget(self.UrlInput)

        self.SearchBtn = QPushButton("Search")
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
        self.DetailTitle = QLabel("Select a task")
        self.DetailTitle.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        DetailLayout.addWidget(self.DetailTitle)

        self.DetailUrl = QLabel("")
        self.DetailUrl.setStyleSheet("color: #666; padding: 0 10px;")
        self.DetailUrl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.DetailUrl.setWordWrap(True)
        DetailLayout.addWidget(self.DetailUrl)

        self.DetailStatus = QLabel("")
        self.DetailStatus.setStyleSheet("font-size: 14px; padding: 10px;")
        DetailLayout.addWidget(self.DetailStatus)

        self.DetailProgress = QProgressBar()
        self.DetailProgress.setVisible(False)
        DetailLayout.addWidget(self.DetailProgress)

        self.DetailTime = QLabel("")
        self.DetailTime.setStyleSheet("color: #888; padding: 10px;")
        DetailLayout.addWidget(self.DetailTime)

        self.DetailError = QLabel("")
        self.DetailError.setStyleSheet("color: #cc0000; padding: 10px;")
        self.DetailError.setWordWrap(True)
        self.DetailError.setVisible(False)
        DetailLayout.addWidget(self.DetailError)

        DetailLayout.addStretch()

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

        self.UrlInput.clear()

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
        Title = Task["Title"] or "Untitled"
        Url = Task["Url"]
        Status = Task["Status"]
        Progress = Task["Progress"]
        Error = Task.get("Error", "")

        Timestamp = int(Key) / 1000
        TimeStr = datetime.fromtimestamp(Timestamp).strftime("%Y-%m-%d %H:%M:%S")

        StatusText = {
            "queued": "Queued for download",
            "downloading": "Downloading...",
            "processing": "Processing...",
            "ready": "Ready to publish",
            "published": "Published",
        }.get(Status, Status)

        Color = StatusColors.get(Status, "#666666")

        self.DetailTitle.setText(Title)
        self.DetailUrl.setText(Url)
        self.DetailStatus.setText(StatusText)
        self.DetailStatus.setStyleSheet(f"font-size: 14px; padding: 10px; color: {Color};")
        self.DetailTime.setText(f"Added: {TimeStr}")

        if Status in ["downloading", "processing"]:
            self.DetailProgress.setVisible(True)
            self.DetailProgress.setValue(Progress)
        else:
            self.DetailProgress.setVisible(False)

        if Error:
            self.DetailError.setText(f"Error: {Error}")
            self.DetailError.setVisible(True)
        else:
            self.DetailError.setVisible(False)

    def ClearDetail(self):
        """清空详情面板"""
        self.CurKey = None
        self.DetailTitle.setText("Select a task")
        self.DetailUrl.setText("")
        self.DetailStatus.setText("")
        self.DetailTime.setText("")
        self.DetailProgress.setVisible(False)
        self.DetailError.setVisible(False)

    def closeEvent(self, Event: QCloseEvent):
        """关闭窗口时隐藏而非退出"""
        Event.ignore()
        self.hide()
        self.Closed.emit()
