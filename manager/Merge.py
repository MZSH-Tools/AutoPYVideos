# 音视频合成模块（调用 videotrans 的 ffmpeg 接口）
import os
import shutil
import tempfile
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


def MergeWithHardSubtitle(VideoPath: Path, AudioPath: Path, SubtitlePath: Path,
                          OutputPath: Path, ProgressCallback=None) -> bool:
    """
    将视频、音频和字幕合并（硬字幕，烧录到视频画面）
    调用 videotrans 的 runffmpeg 接口
    """
    from videotrans.util.help_ffmpeg import runffmpeg
    from videotrans.configure import config

    if not VideoPath.exists():
        Log(f"硬字幕合成: 视频不存在: {VideoPath}")
        return False

    if not AudioPath.exists():
        Log(f"硬字幕合成: 音频不存在: {AudioPath}")
        return False

    if not SubtitlePath.exists():
        Log(f"硬字幕合成: 字幕不存在: {SubtitlePath}")
        return False

    Log(f"硬字幕合成: 烧录字幕到视频...")
    if ProgressCallback:
        ProgressCallback(10, "编码中...")

    # 保存原工作目录
    OrigCwd = os.getcwd()
    TempDir = None

    try:
        # 复制字幕到临时目录，然后 chdir 到该目录（避免路径问题）
        TempDir = Path(tempfile.mkdtemp())
        TempSrt = TempDir / "sub.srt"
        shutil.copy(SubtitlePath, TempSrt)

        # 切换到临时目录，字幕用相对路径（videotrans 的做法）
        os.chdir(TempDir)

        # 构建 ffmpeg 参数（不包含 ffmpeg 本身，runffmpeg 会自动添加）
        Cmd = [
            "-y",
            "-i", Path(VideoPath).as_posix(),
            "-i", Path(AudioPath).as_posix(),
            "-map", "0:v",
            "-map", "1:a",
            "-vf", "subtitles=sub.srt:charenc=utf-8",
            "-c:v", f"libx{config.settings.get('video_codec', '264')}",
            "-c:a", "aac",
            "-b:a", "192k",
            "-crf", f"{config.settings.get('crf', 23)}",
            "-preset", config.settings.get('preset', 'fast'),
            "-movflags", "+faststart",
            "-shortest",
            Path(OutputPath).as_posix()
        ]

        Log(f"硬字幕合成: 执行 ffmpeg (视频重编码)...")

        # 调用 videotrans 的 runffmpeg（自动处理硬件编码器和回退）
        Result = runffmpeg(Cmd)

        if ProgressCallback:
            ProgressCallback(100, "完成")

        if OutputPath.exists():
            Log(f"硬字幕合成: 完成 -> {OutputPath}")
            return True
        else:
            Log(f"硬字幕合成: 输出未生成")
            return False

    except Exception as E:
        import traceback
        Log(f"硬字幕合成: 错误: {E}")
        Log(traceback.format_exc())
        return False

    finally:
        # 恢复工作目录
        os.chdir(OrigCwd)
        # 清理临时文件
        if TempDir and TempDir.exists():
            shutil.rmtree(TempDir, ignore_errors=True)


def MergeVideoAudio(VideoPath: Path, AudioPath: Path, OutputPath: Path,
                    ProgressCallback=None) -> bool:
    """
    将视频和音频合并，替换原视频的音频轨道（无字幕）
    调用 videotrans 的 runffmpeg 接口
    """
    from videotrans.util.help_ffmpeg import runffmpeg

    if not VideoPath.exists():
        Log(f"音视频合成: 视频不存在: {VideoPath}")
        return False

    if not AudioPath.exists():
        Log(f"音视频合成: 音频不存在: {AudioPath}")
        return False

    Log(f"音视频合成: 合并视频和音频...")
    if ProgressCallback:
        ProgressCallback(10, "合并中...")

    try:
        # 构建 ffmpeg 参数
        Cmd = [
            "-y",
            "-i", Path(VideoPath).as_posix(),
            "-i", Path(AudioPath).as_posix(),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            Path(OutputPath).as_posix()
        ]

        # 调用 videotrans 的 runffmpeg
        Result = runffmpeg(Cmd)

        if ProgressCallback:
            ProgressCallback(100, "完成")

        if OutputPath.exists():
            Log(f"音视频合成: 完成 -> {OutputPath}")
            return True
        else:
            Log(f"音视频合成: 输出未生成")
            return False

    except Exception as E:
        import traceback
        Log(f"音视频合成: 错误: {E}")
        Log(traceback.format_exc())
        return False


def MergeVideo(VideoPath: Path, AudioPath: Path, SubtitlePath: Path = None,
               OutputPath: Path = None, HardSubtitle: bool = True,
               ProgressCallback=None) -> Path | None:
    """
    合成最终视频
    VideoPath: 原视频路径
    AudioPath: 配音音频路径
    SubtitlePath: 字幕路径（可选）
    OutputPath: 输出视频路径，默认为同目录下 output.mp4
    HardSubtitle: 是否烧录硬字幕（默认 True）
    ProgressCallback: 进度回调 (percent, text)
    返回生成的视频文件路径
    """
    if OutputPath is None:
        OutputPath = VideoPath.parent / "output.mp4"

    # 已存在则跳过
    if OutputPath.exists():
        Log(f"视频合成: 输出已存在，跳过: {OutputPath}")
        return OutputPath

    if HardSubtitle and SubtitlePath and SubtitlePath.exists():
        # 烧录硬字幕（字幕永久嵌入画面）
        Success = MergeWithHardSubtitle(VideoPath, AudioPath, SubtitlePath, OutputPath, ProgressCallback)
        if Success:
            return OutputPath
        else:
            return None
    else:
        # 只替换音频（无字幕）
        Success = MergeVideoAudio(VideoPath, AudioPath, OutputPath, ProgressCallback)
        if Success:
            return OutputPath
        else:
            return None
