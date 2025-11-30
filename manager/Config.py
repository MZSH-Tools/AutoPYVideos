# 统一配置管理模块
# 在程序启动时加载项目配置，覆盖 videotrans 内部配置
import json
from pathlib import Path


# 项目配置文件路径（跟随版本控制）
CONFIG_PATH = Path(__file__).parent / "config.json"

# 配置缓存
_ProjectConfig = None


def LoadProjectConfig() -> dict:
    """加载项目配置文件"""
    global _ProjectConfig
    if _ProjectConfig is not None:
        return _ProjectConfig

    if not CONFIG_PATH.exists():
        print(f"Config: config.json not found: {CONFIG_PATH}")
        _ProjectConfig = {}
        return _ProjectConfig

    try:
        _ProjectConfig = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        print(f"Config: Loaded {CONFIG_PATH}")
    except (json.JSONDecodeError, OSError) as E:
        print(f"Config: Load failed: {E}")
        _ProjectConfig = {}

    return _ProjectConfig


def ApplyToVideotrans():
    """将项目配置应用到 videotrans 配置"""
    from videotrans.configure import config

    Cfg = LoadProjectConfig()
    if not Cfg:
        print("Config: No config to apply")
        return

    # 映射关系：项目配置（中文键）-> videotrans 配置
    # params: 任务参数（voice_rate, voice_role 等）
    # settings: 高级设置（VAD 参数、字幕长度等）

    ParamsMapping = {
        # 配音
        "配音.声音角色": "voice_role",
        "配音.语速": "voice_rate",
        "配音.音频加速": "voice_autorate",
        "配音.视频慢放": "video_autorate",
        # 语音识别
        "语音识别.模型": "model_name",
        "语音识别.源语言": "source_language_code",
        # 翻译
        "翻译.目标语言": "target_language_code",
        "翻译.翻译引擎": "translate_type",
        # 字幕
        "字幕.字幕类型": "subtitle_type",
    }

    SettingsMapping = {
        # 语音识别 (VAD)
        "语音识别.最短语音持续_毫秒": "min_speech_duration_ms",
        "语音识别.最长语音持续_秒": "max_speech_duration_s",
        "语音识别.最短静音持续_毫秒": "min_silence_duration_ms",
        "语音识别.语音填充_毫秒": "speech_pad_ms",
        "语音识别.阈值": "threshold",
        "语音识别.启用VAD": "vad",
        # 字幕
        "字幕.中日韩每行字数": "cjk_len",
        "字幕.其他每行字数": "other_len",
        # 输出
        "输出.crf": "crf",
        "输出.预设": "preset",
        "输出.视频编码": "video_codec",
    }

    def GetNestedValue(Obj: dict, Path: str):
        """获取嵌套字典值，如 '配音.语速'"""
        Keys = Path.split(".")
        for Key in Keys:
            if not isinstance(Obj, dict) or Key not in Obj:
                return None
            Obj = Obj[Key]
        return Obj

    # 应用到 params
    UpdatedParams = 0
    for SrcPath, DstKey in ParamsMapping.items():
        Val = GetNestedValue(Cfg, SrcPath)
        if Val is not None:
            config.params[DstKey] = Val
            UpdatedParams += 1

    # 应用到 settings
    UpdatedSettings = 0
    for SrcPath, DstKey in SettingsMapping.items():
        Val = GetNestedValue(Cfg, SrcPath)
        if Val is not None:
            config.settings[DstKey] = Val
            UpdatedSettings += 1

    print(f"Config: Applied {UpdatedParams} params, {UpdatedSettings} settings")


def Get(Path: str, Default=None):
    """获取项目配置值

    Args:
        Path: 配置路径，如 '配音.语速'
        Default: 默认值

    Returns:
        配置值或默认值
    """
    Cfg = LoadProjectConfig()
    Keys = Path.split(".")
    for Key in Keys:
        if not isinstance(Cfg, dict) or Key not in Cfg:
            return Default
        Cfg = Cfg[Key]
    return Cfg
