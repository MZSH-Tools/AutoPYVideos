# 音频处理模块
import subprocess
from pathlib import Path


def ExtractAudio(VideoPath: Path, OutputPath: Path = None) -> Path | None:
    """
    从视频提取音频（wav 格式，16kHz 单声道，用于语音识别）
    """
    if not VideoPath.exists():
        print(f"ExtractAudio: Video not found: {VideoPath}")
        return None

    if OutputPath is None:
        OutputPath = VideoPath.parent / "audio.wav"

    # 已存在则跳过
    if OutputPath.exists():
        return OutputPath

    try:
        # ffmpeg 提取音频：16kHz 单声道 wav（Whisper 最佳格式）
        Cmd = [
            "ffmpeg", "-y",
            "-i", str(VideoPath),
            "-vn",                    # 不要视频
            "-acodec", "pcm_s16le",   # 16-bit PCM
            "-ar", "16000",           # 16kHz 采样率
            "-ac", "1",               # 单声道
            str(OutputPath)
        ]
        Result = subprocess.run(Cmd, capture_output=True, text=True)
        if Result.returncode == 0 and OutputPath.exists():
            return OutputPath
        else:
            print(f"ExtractAudio error: {Result.stderr}")
            return None
    except Exception as E:
        print(f"ExtractAudio exception: {E}")
        return None
