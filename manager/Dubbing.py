# 配音模块（调用 videotrans 的 tts 接口）
import re
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


def ParseSrtTime(TimeStr: str) -> float:
    """将 SRT 时间格式转换为秒数"""
    Match = re.match(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", TimeStr)
    if not Match:
        return 0.0
    Hours, Minutes, Seconds, Millis = Match.groups()
    return int(Hours) * 3600 + int(Minutes) * 60 + int(Seconds) + int(Millis) / 1000


def ParseSrt(SrtPath: Path) -> list[dict]:
    """解析 SRT 字幕文件，返回 [{start, end, text}, ...]"""
    if not SrtPath.exists():
        return []

    Content = SrtPath.read_text(encoding="utf-8")
    Blocks = re.split(r"\n\s*\n", Content.strip())
    Result = []

    for Block in Blocks:
        Lines = Block.strip().split("\n")
        if len(Lines) < 3:
            continue

        TimeMatch = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            Lines[1].strip()
        )
        if not TimeMatch:
            continue

        Text = " ".join(Lines[2:]).strip()
        Result.append({
            "start": ParseSrtTime(TimeMatch.group(1)),
            "end": ParseSrtTime(TimeMatch.group(2)),
            "text": Text
        })

    return Result


def GenerateDubbing(SrtPath: Path, OutputPath: Path = None,
                    Voice: str = "zh-CN-XiaoxiaoNeural",
                    ProgressCallback=None) -> Path | None:
    """
    使用 videotrans 的 tts.run 接口根据字幕生成配音音频
    SrtPath: 输入字幕路径
    OutputPath: 输出音频路径，默认为同目录下 zh-cn.wav
    Voice: edge-tts 声音名称
    ProgressCallback: 进度回调 (percent, text)
    返回生成的音频文件路径
    """
    from videotrans import tts
    from videotrans.configure import config
    from videotrans.util.help_ffmpeg import runffmpeg

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

    Log(f"GenerateDubbing: Generating {len(Subtitles)} segments using Edge-TTS...")
    if ProgressCallback:
        ProgressCallback(10, "Generating TTS...")

    # 保存原状态
    OrigBoxTts = config.box_tts

    TempDir = None
    try:
        # 设置状态以绕过 videotrans 的状态检查
        config.box_tts = 'ing'

        # 创建临时目录存放音频片段
        TempDir = Path(tempfile.mkdtemp())

        # 构建 videotrans tts 格式的 queue_tts
        # 格式: [{"text": "...", "role": "角色名", "filename": "输出路径(不含扩展名)"}, ...]
        QueueTts = []
        for I, Sub in enumerate(Subtitles):
            QueueTts.append({
                "text": Sub["text"],
                "role": Voice,
                "filename": str(TempDir / f"seg_{I:04d}"),
                "start_time": int(Sub["start"] * 1000),  # 毫秒
                "end_time": int(Sub["end"] * 1000),
            })

        # 调用 videotrans TTS 接口
        tts.run(
            queue_tts=QueueTts,
            language="zh-cn",
            tts_type=tts.EDGE_TTS
        )

        if ProgressCallback:
            ProgressCallback(60, "Merging audio...")

        # 检查生成的音频文件并合并
        AudioFiles = []
        for I, Item in enumerate(QueueTts):
            WavFile = Path(Item["filename"] + ".wav")
            if WavFile.exists():
                AudioFiles.append((Item["start_time"], WavFile))

        if not AudioFiles:
            Log(f"GenerateDubbing: No audio files generated")
            return None

        # 按时间排序
        AudioFiles.sort(key=lambda X: X[0])

        # 使用 ffmpeg 合并音频（带时间对齐）
        # 创建静音填充的完整音频
        LastEndTime = Subtitles[-1]["end"]
        SilenceFile = TempDir / "silence.wav"

        # 生成总时长的静音底座
        runffmpeg([
            "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=16000:cl=mono",
            "-t", str(LastEndTime + 1),
            "-acodec", "pcm_s16le",
            SilenceFile.as_posix()
        ])

        # 使用 amix 混合所有音频
        if len(AudioFiles) == 1:
            # 只有一个音频，直接复制
            shutil.copy(AudioFiles[0][1], OutputPath)
        else:
            # 构建 ffmpeg filter_complex
            Inputs = ["-i", SilenceFile.as_posix()]
            FilterParts = ["[0]"]

            for I, (StartMs, WavFile) in enumerate(AudioFiles):
                Inputs.extend(["-i", WavFile.as_posix()])
                DelayMs = StartMs
                FilterParts.append(f"[{I+1}]adelay={DelayMs}|{DelayMs}[d{I}]")

            # 混合所有延迟后的音频
            MixInputs = "[0]" + "".join(f"[d{I}]" for I in range(len(AudioFiles)))
            FilterComplex = ";".join(FilterParts[1:]) + f";{MixInputs}amix=inputs={len(AudioFiles)+1}:duration=longest[out]"

            Cmd = ["-y"] + Inputs + [
                "-filter_complex", FilterComplex,
                "-map", "[out]",
                "-ar", "16000", "-ac", "1",
                "-acodec", "pcm_s16le",
                OutputPath.as_posix()
            ]
            runffmpeg(Cmd)

        if ProgressCallback:
            ProgressCallback(100, "Done")

        if OutputPath.exists():
            Log(f"GenerateDubbing: Done -> {OutputPath}")
            return OutputPath
        else:
            Log(f"GenerateDubbing: Output not created")
            return None

    except Exception as E:
        import traceback
        Log(f"GenerateDubbing error: {E}")
        Log(traceback.format_exc())
        return None

    finally:
        # 恢复原状态
        config.box_tts = OrigBoxTts
        # 清理临时文件
        if TempDir and TempDir.exists():
            shutil.rmtree(TempDir, ignore_errors=True)
