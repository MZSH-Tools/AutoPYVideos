# 音频提取模块（调用 videotrans 的 ffmpeg 接口）
from pathlib import Path

# 日志回调（由 MainWindow 设置）
LogFunc = None

def SetLogFunc(Func):
    """设置日志函数"""
    global LogFunc
    LogFunc = Func

def Log(Msg: str):
    """输出日志"""
    if LogFunc:
        LogFunc(Msg)
    else:
        print(Msg)


def ExtractAudio(VideoPath: Path, OutputPath: Path = None) -> Path | None:
    """
    从视频提取音频（wav 格式，16kHz 单声道，用于语音识别）
    调用 videotrans 的 runffmpeg 接口
    """
    from videotrans.util.help_ffmpeg import runffmpeg

    if not VideoPath.exists():
        Log(f"ExtractAudio: Video not found: {VideoPath}")
        return None

    if OutputPath is None:
        OutputPath = VideoPath.parent / "audio.wav"

    # 已存在则跳过
    if OutputPath.exists():
        Log(f"ExtractAudio: Audio already exists: {OutputPath}")
        return OutputPath

    try:
        Log(f"ExtractAudio: Extracting audio from {VideoPath.name}...")
        # ffmpeg 提取音频：16kHz 单声道 wav（Whisper 最佳格式）
        Cmd = [
            "-y",
            "-i", Path(VideoPath).as_posix(),
            "-vn",                    # 不要视频
            "-acodec", "pcm_s16le",   # 16-bit PCM
            "-ar", "16000",           # 16kHz 采样率
            "-ac", "1",               # 单声道
            Path(OutputPath).as_posix()
        ]
        runffmpeg(Cmd)

        if OutputPath.exists():
            Log(f"ExtractAudio: Done -> {OutputPath}")
            return OutputPath
        else:
            Log(f"ExtractAudio: Output not created")
            return None

    except Exception as E:
        import traceback
        Log(f"ExtractAudio error: {E}")
        Log(traceback.format_exc())
        return None
