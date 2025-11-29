# 配音模块（edge-tts）
import asyncio
import re
import tempfile
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


def ParseSrtTime(TimeStr: str) -> float:
    """将 SRT 时间格式转换为秒数"""
    # 格式: HH:MM:SS,mmm 或 HH:MM:SS.mmm
    Match = re.match(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", TimeStr)
    if not Match:
        return 0.0
    Hours, Minutes, Seconds, Millis = Match.groups()
    return int(Hours) * 3600 + int(Minutes) * 60 + int(Seconds) + int(Millis) / 1000


def ParseSrt(SrtPath: Path) -> list[dict]:
    """
    解析 SRT 字幕文件
    返回 [{start, end, text}, ...]
    """
    if not SrtPath.exists():
        return []

    Content = SrtPath.read_text(encoding="utf-8")
    Blocks = re.split(r"\n\s*\n", Content.strip())
    Result = []

    for Block in Blocks:
        Lines = Block.strip().split("\n")
        if len(Lines) < 3:
            continue

        # 时间轴
        TimeMatch = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            Lines[1].strip()
        )
        if not TimeMatch:
            continue

        # 字幕文本（可能多行）
        Text = " ".join(Lines[2:]).strip()

        Result.append({
            "start": ParseSrtTime(TimeMatch.group(1)),
            "end": ParseSrtTime(TimeMatch.group(2)),
            "text": Text
        })

    return Result


async def GenerateTTS(Text: str, OutputPath: Path, Voice: str = "zh-CN-XiaoxiaoNeural") -> bool:
    """使用 edge-tts 生成单条语音"""
    try:
        import edge_tts
        Communicate = edge_tts.Communicate(Text, Voice)
        await Communicate.save(str(OutputPath))
        return OutputPath.exists()
    except Exception as E:
        Log(f"TTS error: {E}")
        return False


def GetAudioDuration(AudioPath: Path) -> float:
    """获取音频时长（秒）"""
    try:
        Result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(AudioPath)],
            capture_output=True, text=True
        )
        return float(Result.stdout.strip())
    except:
        return 0.0


def GenerateSilence(Duration: float, OutputPath: Path, SampleRate: int = 16000) -> bool:
    """生成指定时长的静音音频"""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={SampleRate}:cl=mono",
             "-t", str(Duration), "-acodec", "pcm_s16le", str(OutputPath)],
            capture_output=True
        )
        return OutputPath.exists()
    except:
        return False


def ConcatAudios(AudioPaths: list[Path], OutputPath: Path) -> bool:
    """合并多个音频文件"""
    if not AudioPaths:
        return False

    try:
        # 创建文件列表
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as F:
            for P in AudioPaths:
                # ffmpeg concat 需要转义路径
                F.write(f"file '{str(P).replace(chr(92), '/')}'\n")
            ListFile = Path(F.name)

        # 合并
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(ListFile),
             "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(OutputPath)],
            capture_output=True
        )

        ListFile.unlink()
        return OutputPath.exists()
    except Exception as E:
        Log(f"Concat error: {E}")
        return False


async def GenerateDubbingAsync(Subtitles: list[dict], OutputPath: Path,
                                Voice: str = "zh-CN-XiaoxiaoNeural",
                                ProgressCallback=None) -> bool:
    """异步生成配音音频"""
    if not Subtitles:
        return False

    TempDir = Path(tempfile.mkdtemp())
    AudioSegments = []
    CurTime = 0.0
    Total = len(Subtitles)

    try:
        for I, Sub in enumerate(Subtitles):
            StartTime = Sub["start"]
            EndTime = Sub["end"]
            Text = Sub["text"]

            # 填充前面的静音
            if StartTime > CurTime:
                SilencePath = TempDir / f"silence_{I}.wav"
                GenerateSilence(StartTime - CurTime, SilencePath)
                if SilencePath.exists():
                    AudioSegments.append(SilencePath)

            # 生成语音
            TtsPath = TempDir / f"tts_{I}.mp3"
            Success = await GenerateTTS(Text, TtsPath, Voice)

            if Success:
                # 转换为 wav
                WavPath = TempDir / f"tts_{I}.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(TtsPath), "-ar", "16000", "-ac", "1",
                     "-acodec", "pcm_s16le", str(WavPath)],
                    capture_output=True
                )
                if WavPath.exists():
                    AudioSegments.append(WavPath)
                    # 更新当前时间
                    Duration = GetAudioDuration(WavPath)
                    CurTime = StartTime + Duration
                else:
                    CurTime = EndTime
            else:
                # TTS 失败，用静音代替
                SilencePath = TempDir / f"fail_{I}.wav"
                GenerateSilence(EndTime - StartTime, SilencePath)
                if SilencePath.exists():
                    AudioSegments.append(SilencePath)
                CurTime = EndTime

            # 进度回调
            if ProgressCallback:
                Percent = int((I + 1) * 100 / Total)
                Preview = Text[:20] + "..." if len(Text) > 20 else Text
                ProgressCallback(Percent, Preview)

        # 合并所有音频
        if AudioSegments:
            ConcatAudios(AudioSegments, OutputPath)

        return OutputPath.exists()

    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(TempDir, ignore_errors=True)


def GenerateDubbing(SrtPath: Path, OutputPath: Path = None,
                    Voice: str = "zh-CN-XiaoxiaoNeural",
                    ProgressCallback=None) -> Path | None:
    """
    根据字幕生成配音音频
    SrtPath: 输入字幕路径
    OutputPath: 输出音频路径，默认为同目录下 zh-cn.wav
    Voice: edge-tts 声音名称
    ProgressCallback: 进度回调 (percent, text)
    返回生成的音频文件路径
    """
    if not SrtPath.exists():
        Log(f"GenerateDubbing: SRT not found: {SrtPath}")
        return None

    if OutputPath is None:
        OutputPath = SrtPath.parent / "zh-cn.wav"

    # 已存在则跳过
    if OutputPath.exists():
        Log(f"GenerateDubbing: Audio already exists: {OutputPath}")
        return OutputPath

    Log(f"GenerateDubbing: Parsing subtitles...")
    Subtitles = ParseSrt(SrtPath)
    if not Subtitles:
        Log(f"GenerateDubbing: No subtitles found")
        return None

    Log(f"GenerateDubbing: Generating {len(Subtitles)} segments...")

    # 运行异步任务
    try:
        Loop = asyncio.new_event_loop()
        asyncio.set_event_loop(Loop)
        Success = Loop.run_until_complete(
            GenerateDubbingAsync(Subtitles, OutputPath, Voice, ProgressCallback)
        )
        Loop.close()

        if Success:
            Log(f"GenerateDubbing: Done -> {OutputPath}")
            return OutputPath
        else:
            Log(f"GenerateDubbing: Failed")
            return None

    except Exception as E:
        import traceback
        Log(f"GenerateDubbing error: {E}")
        Log(traceback.format_exc())
        return None
