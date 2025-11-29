# 配音模块（调用 videotrans 的 tts 接口）
import re
import shutil
import tempfile
import os
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
                    Voice: str = "晓晓(Female/CN)",
                    ProgressCallback=None) -> Path | None:
    """
    使用 videotrans 的 tts.run 接口根据字幕生成配音音频
    SrtPath: 输入字幕路径
    OutputPath: 输出音频路径，默认为同目录下 zh-cn.wav
    Voice: edge-tts 声音显示名称（如 晓晓(Female/CN)）
    ProgressCallback: 进度回调 (percent, text)
    返回生成的音频文件路径
    """
    import asyncio
    from videotrans import tts
    from videotrans.configure import config
    from videotrans.util.help_ffmpeg import runffmpeg
    from videotrans.util import tools

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
        ProgressCallback(5, "Testing Edge-TTS connection...")

    # 获取真正的 voice ID
    VoiceId = tools.get_edge_rolelist(Voice, "zh-cn")
    if not VoiceId:
        Log(f"GenerateDubbing: Voice '{Voice}' not found, using default")
        VoiceId = "zh-CN-XiaoxiaoNeural"
    Log(f"GenerateDubbing: Voice ID = {VoiceId}")

    # 创建临时目录存放音频片段
    TempDir = Path(tempfile.mkdtemp())

    # 获取全局代理设置
    UseProxy = config.proxy if config.proxy else None
    Log(f"GenerateDubbing: Using proxy from config: {UseProxy}")

    if ProgressCallback:
        ProgressCallback(10, "Generating TTS...")

    # 保存原状态
    OrigBoxTts = config.box_tts

    try:
        # 设置状态以绕过 videotrans 的状态检查
        config.box_tts = 'ing'

        # 构建 videotrans tts 格式的 queue_tts
        QueueTts = []
        for I, Sub in enumerate(Subtitles):
            QueueTts.append({
                "text": Sub["text"],
                "role": Voice,
                "filename": str(TempDir / f"seg_{I:04d}"),
                "start_time": int(Sub["start"] * 1000),
                "end_time": int(Sub["end"] * 1000),
            })

        Log(f"GenerateDubbing: Calling tts.run with {len(QueueTts)} items")

        try:
            tts.run(
                queue_tts=QueueTts,
                language="zh-cn",
                tts_type=tts.EDGE_TTS
            )
        except Exception as TtsErr:
            Log(f"GenerateDubbing: tts.run failed: {TtsErr}")
            # 回退到直接使用 edge-tts
            Log(f"GenerateDubbing: Falling back to direct edge-tts...")
            return _GenerateDubbingDirect(Subtitles, OutputPath, VoiceId, UseProxy, TempDir, ProgressCallback)

        if ProgressCallback:
            ProgressCallback(60, "Merging audio...")

        # 检查生成的音频文件并合并
        AudioFiles = []
        for I, Item in enumerate(QueueTts):
            WavFile = Path(Item["filename"] + ".wav")
            if WavFile.exists():
                AudioFiles.append((Item["start_time"], WavFile))

        if not AudioFiles:
            Log(f"GenerateDubbing: videotrans produced no audio, falling back to direct edge-tts...")
            return _GenerateDubbingDirect(Subtitles, OutputPath, VoiceId, UseProxy, TempDir, ProgressCallback)

        Log(f"GenerateDubbing: Generated {len(AudioFiles)} audio segments")

        # 按时间排序
        AudioFiles.sort(key=lambda X: X[0])

        # 合并音频
        Result = _MergeAudioFiles(AudioFiles, Subtitles, OutputPath, TempDir)

        if ProgressCallback:
            ProgressCallback(100, "Done")

        return Result

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


def _GenerateDubbingDirect(Subtitles: list, OutputPath: Path, VoiceId: str,
                           Proxy: str, TempDir: Path, ProgressCallback) -> Path | None:
    """
    直接使用 edge-tts 库生成配音（备用方案）
    """
    import asyncio
    from edge_tts import Communicate
    from videotrans.util.help_ffmpeg import runffmpeg

    Log(f"_GenerateDubbingDirect: Generating {len(Subtitles)} segments...")

    async def GenerateAll():
        AudioFiles = []
        for I, Sub in enumerate(Subtitles):
            if ProgressCallback:
                Pct = 10 + int(50 * I / len(Subtitles))
                ProgressCallback(Pct, f"TTS [{I+1}/{len(Subtitles)}]")

            OutFile = TempDir / f"seg_{I:04d}.mp3"
            try:
                Comm = Communicate(Sub["text"], voice=VoiceId, proxy=Proxy)
                await Comm.save(str(OutFile))
                if OutFile.exists() and OutFile.stat().st_size > 0:
                    # 转换为 wav
                    WavFile = TempDir / f"seg_{I:04d}.wav"
                    runffmpeg(["-y", "-i", str(OutFile), "-ar", "44100", "-ac", "2", str(WavFile)])
                    if WavFile.exists():
                        AudioFiles.append((int(Sub["start"] * 1000), WavFile))
            except Exception as E:
                Log(f"_GenerateDubbingDirect: Segment {I} failed: {E}")

        return AudioFiles

    try:
        AudioFiles = asyncio.run(GenerateAll())
    except Exception as E:
        Log(f"_GenerateDubbingDirect error: {E}")
        return None

    if not AudioFiles:
        Log(f"_GenerateDubbingDirect: No audio files generated")
        return None

    Log(f"_GenerateDubbingDirect: Generated {len(AudioFiles)} segments")

    if ProgressCallback:
        ProgressCallback(70, "Merging audio...")

    Result = _MergeAudioFiles(AudioFiles, Subtitles, OutputPath, TempDir)

    if ProgressCallback:
        ProgressCallback(100, "Done")

    return Result


def _MergeAudioFiles(AudioFiles: list, Subtitles: list, OutputPath: Path, TempDir: Path) -> Path | None:
    """
    合并音频文件（带时间对齐）
    """
    from videotrans.util.help_ffmpeg import runffmpeg

    if not AudioFiles:
        return None

    # 按时间排序
    AudioFiles.sort(key=lambda X: X[0])

    # 使用 ffmpeg 合并音频（带时间对齐）
    LastEndTime = Subtitles[-1]["end"]
    SilenceFile = TempDir / "silence.wav"

    # 生成总时长的静音底座
    runffmpeg([
        "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=16000:cl=mono",
        "-t", str(LastEndTime + 1),
        "-acodec", "pcm_s16le",
        str(SilenceFile)
    ])

    # 使用 amix 混合所有音频
    if len(AudioFiles) == 1:
        shutil.copy(AudioFiles[0][1], OutputPath)
    else:
        Inputs = ["-i", str(SilenceFile)]
        FilterParts = []

        for I, (StartMs, WavFile) in enumerate(AudioFiles):
            Inputs.extend(["-i", str(WavFile)])
            FilterParts.append(f"[{I+1}]adelay={StartMs}|{StartMs}[d{I}]")

        MixInputs = "[0]" + "".join(f"[d{I}]" for I in range(len(AudioFiles)))
        FilterComplex = ";".join(FilterParts) + f";{MixInputs}amix=inputs={len(AudioFiles)+1}:duration=longest[out]"

        Cmd = ["-y"] + Inputs + [
            "-filter_complex", FilterComplex,
            "-map", "[out]",
            "-ar", "16000", "-ac", "1",
            "-acodec", "pcm_s16le",
            str(OutputPath)
        ]
        runffmpeg(Cmd)

    if OutputPath.exists():
        Log(f"_MergeAudioFiles: Done -> {OutputPath}")
        return OutputPath
    else:
        Log(f"_MergeAudioFiles: Output not created")
        return None
