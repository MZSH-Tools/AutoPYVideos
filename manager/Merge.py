# 音视频合成模块（ffmpeg）
import subprocess
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


def GetVideoDuration(VideoPath: Path) -> float:
    """获取视频时长（秒）"""
    try:
        Result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(VideoPath)],
            capture_output=True, text=True
        )
        return float(Result.stdout.strip())
    except:
        return 0.0


def MergeVideoAudio(VideoPath: Path, AudioPath: Path, OutputPath: Path,
                    ProgressCallback=None) -> bool:
    """
    将视频和音频合并，替换原视频的音频轨道
    VideoPath: 原视频路径
    AudioPath: 配音音频路径
    OutputPath: 输出视频路径
    ProgressCallback: 进度回调 (percent, text)
    返回是否成功
    """
    if not VideoPath.exists():
        Log(f"MergeVideoAudio: Video not found: {VideoPath}")
        return False

    if not AudioPath.exists():
        Log(f"MergeVideoAudio: Audio not found: {AudioPath}")
        return False

    Log(f"MergeVideoAudio: Merging video and audio...")
    if ProgressCallback:
        ProgressCallback(10, "Merging...")

    try:
        # 获取视频时长用于进度估算
        Duration = GetVideoDuration(VideoPath)

        # ffmpeg 命令：替换音频
        # -map 0:v 取第一个输入的视频流
        # -map 1:a 取第二个输入的音频流
        # -c:v copy 视频流直接复制（不重新编码）
        # -c:a aac 音频编码为 AAC
        # -shortest 以较短的流为准
        Cmd = [
            "ffmpeg", "-y",
            "-i", str(VideoPath),
            "-i", str(AudioPath),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(OutputPath)
        ]

        # 运行 ffmpeg
        Process = subprocess.Popen(
            Cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # 读取输出（ffmpeg 输出到 stderr）
        _, Stderr = Process.communicate()

        if Process.returncode != 0:
            Log(f"MergeVideoAudio: ffmpeg error: {Stderr[-500:]}")
            return False

        if ProgressCallback:
            ProgressCallback(100, "Done")

        if OutputPath.exists():
            Log(f"MergeVideoAudio: Done -> {OutputPath}")
            return True
        else:
            Log(f"MergeVideoAudio: Output not created")
            return False

    except Exception as E:
        import traceback
        Log(f"MergeVideoAudio error: {E}")
        Log(traceback.format_exc())
        return False


def MergeWithSubtitle(VideoPath: Path, AudioPath: Path, SubtitlePath: Path,
                      OutputPath: Path, ProgressCallback=None) -> bool:
    """
    将视频、音频和字幕合并（软字幕，可切换）
    VideoPath: 原视频路径
    AudioPath: 配音音频路径
    SubtitlePath: 字幕路径（.srt）
    OutputPath: 输出视频路径（.mkv 支持软字幕）
    ProgressCallback: 进度回调 (percent, text)
    返回是否成功
    """
    if not VideoPath.exists():
        Log(f"MergeWithSubtitle: Video not found: {VideoPath}")
        return False

    if not AudioPath.exists():
        Log(f"MergeWithSubtitle: Audio not found: {AudioPath}")
        return False

    if not SubtitlePath.exists():
        Log(f"MergeWithSubtitle: Subtitle not found: {SubtitlePath}")
        return False

    Log(f"MergeWithSubtitle: Merging video, audio and subtitle...")
    if ProgressCallback:
        ProgressCallback(10, "Merging...")

    try:
        # ffmpeg 命令：合并视频、音频和软字幕
        Cmd = [
            "ffmpeg", "-y",
            "-i", str(VideoPath),
            "-i", str(AudioPath),
            "-i", str(SubtitlePath),
            "-map", "0:v",
            "-map", "1:a",
            "-map", "2:s",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-c:s", "srt",
            "-shortest",
            str(OutputPath)
        ]

        Process = subprocess.Popen(
            Cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        _, Stderr = Process.communicate()

        if Process.returncode != 0:
            Log(f"MergeWithSubtitle: ffmpeg error: {Stderr[-500:]}")
            return False

        if ProgressCallback:
            ProgressCallback(100, "Done")

        if OutputPath.exists():
            Log(f"MergeWithSubtitle: Done -> {OutputPath}")
            return True
        else:
            Log(f"MergeWithSubtitle: Output not created")
            return False

    except Exception as E:
        import traceback
        Log(f"MergeWithSubtitle error: {E}")
        Log(traceback.format_exc())
        return False


def MergeVideo(VideoPath: Path, AudioPath: Path, SubtitlePath: Path = None,
               OutputPath: Path = None, EmbedSubtitle: bool = False,
               ProgressCallback=None) -> Path | None:
    """
    合成最终视频
    VideoPath: 原视频路径
    AudioPath: 配音音频路径
    SubtitlePath: 字幕路径（可选）
    OutputPath: 输出视频路径，默认为同目录下 output.mp4
    EmbedSubtitle: 是否嵌入软字幕（需要 .mkv 格式）
    ProgressCallback: 进度回调 (percent, text)
    返回生成的视频文件路径
    """
    if OutputPath is None:
        OutputPath = VideoPath.parent / "output.mp4"

    # 已存在则跳过
    if OutputPath.exists():
        Log(f"MergeVideo: Output already exists: {OutputPath}")
        return OutputPath

    if EmbedSubtitle and SubtitlePath and SubtitlePath.exists():
        # 嵌入软字幕（输出 mkv）
        MkvPath = OutputPath.with_suffix(".mkv")
        Success = MergeWithSubtitle(VideoPath, AudioPath, SubtitlePath, MkvPath, ProgressCallback)
        if Success:
            return MkvPath
        else:
            return None
    else:
        # 只替换音频
        Success = MergeVideoAudio(VideoPath, AudioPath, OutputPath, ProgressCallback)
        if Success:
            return OutputPath
        else:
            return None
