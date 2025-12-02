# 存储路径管理模块
import os
import json
from pathlib import Path


def GetDataDir() -> Path:
    """获取数据目录"""
    # 优先使用外置硬盘缓存目录
    ExternalCache = Path("/Volumes/MyNas/Cache/AutoPYVideos")
    if ExternalCache.exists() or (ExternalCache.parent.exists() and ExternalCache.parent.parent.exists()):
        ExternalCache.mkdir(parents=True, exist_ok=True)
        return ExternalCache

    # 回退到本地目录
    if os.name == "nt":
        Base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        Base = Path.home() / ".local" / "share"

    DataDir = Base / "AutoPYVideos"
    DataDir.mkdir(parents=True, exist_ok=True)
    return DataDir


def GetTasksDir() -> Path:
    """获取任务存储目录"""
    TasksDir = GetDataDir() / "Tasks"
    TasksDir.mkdir(parents=True, exist_ok=True)
    return TasksDir


def GetLogsDir() -> Path:
    """获取日志目录"""
    LogsDir = GetDataDir() / "logs"
    LogsDir.mkdir(parents=True, exist_ok=True)
    return LogsDir


def GetModelsDir() -> Path:
    """获取模型缓存目录"""
    ModelsDir = GetDataDir() / "models"
    ModelsDir.mkdir(parents=True, exist_ok=True)
    return ModelsDir


def GetTempDir() -> Path:
    """获取临时文件目录（按进程 ID 隔离）"""
    import os
    TempDir = GetDataDir() / f"tmp{os.getpid()}"
    TempDir.mkdir(parents=True, exist_ok=True)
    return TempDir


def GetOutputDir() -> Path:
    """获取输出目录"""
    OutputDir = GetDataDir() / "output"
    OutputDir.mkdir(parents=True, exist_ok=True)
    return OutputDir


def ListTaskDirs() -> list[Path]:
    """遍历所有任务目录，按时间戳倒序"""
    TasksDir = GetTasksDir()
    Dirs = [D for D in TasksDir.iterdir() if D.is_dir() and D.name.isdigit()]
    Dirs.sort(key=lambda D: int(D.name), reverse=True)
    return Dirs


def GetSettingsPath() -> Path:
    """获取全局设置文件路径"""
    return GetDataDir() / "settings.json"


def LoadSettings() -> dict:
    """从项目配置文件读取发布设置"""
    from manager.Config import Get

    return {
        "TitlePrefix": Get("发布.标题前缀", ""),
        "TitleSuffix": Get("发布.标题后缀", ""),
        "DescriptionExtra": Get("发布.简介附加", ""),
    }


def SaveSettings(Settings: dict):
    """保存发布设置到项目配置文件"""
    from manager.Config import CONFIG_PATH, LoadProjectConfig, ClearCache

    Cfg = LoadProjectConfig()

    # 确保发布节点存在
    if "发布" not in Cfg:
        Cfg["发布"] = {}

    # 更新值
    Cfg["发布"]["标题前缀"] = Settings.get("TitlePrefix", "")
    Cfg["发布"]["标题后缀"] = Settings.get("TitleSuffix", "")
    Cfg["发布"]["简介附加"] = Settings.get("DescriptionExtra", "")

    # 写回文件
    with open(CONFIG_PATH, "w", encoding="utf-8") as F:
        json.dump(Cfg, F, ensure_ascii=False, indent=2)

    # 清除缓存以便下次读取最新值
    ClearCache()
