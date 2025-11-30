# 音频提取模块（调用 videotrans 的 ffmpeg 接口）
from pathlib import Path
from Log import Log


def ExtractAudio(VideoPath: Path, OutputPath: Path = None) -> Path | None:
    """
    从视频提取音频（wav 格式，16kHz 单声道，用于语音识别）
    调用 videotrans 的 runffmpeg 接口
    """
    from videotrans.util.help_ffmpeg import runffmpeg
    from videotrans.util import tools

    if not VideoPath.exists():
        Log(f"提取音频: 视频不存在: {VideoPath}")
        return None

    if OutputPath is None:
        OutputPath = VideoPath.parent / "audio.wav"

    # 已存在则跳过
    if OutputPath.exists():
        Log(f"提取音频: 音频已存在，跳过: {OutputPath}")
        return OutputPath

    try:
        # 先检查视频是否有音频流
        Log(f"提取音频: 检查音频流 {VideoPath.name}...")
        try:
            Duration = tools.get_video_duration(str(VideoPath))
            Log(f"提取音频: 视频时长 = {Duration}ms")
        except Exception as E:
            Log(f"提取音频: 获取视频信息失败: {E}")

        Log(f"提取音频: 从 {VideoPath.name} 提取音频...")
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
        Result = runffmpeg(Cmd)
        Log(f"提取音频: ffmpeg 结果 = {Result}")

        if OutputPath.exists():
            Size = OutputPath.stat().st_size
            Log(f"提取音频: 完成 -> {OutputPath} ({Size} 字节)")
            if Size < 1000:
                Log(f"提取音频: 警告 - 输出文件非常小，视频可能没有音频流")
            return OutputPath
        else:
            Log(f"提取音频: 输出未生成 - 视频可能没有音频流!")
            return None

    except Exception as E:
        import traceback
        Log(f"提取音频: 错误: {E}")
        Log(traceback.format_exc())
        return None
