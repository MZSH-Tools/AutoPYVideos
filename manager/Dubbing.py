# 配音模块（调用 videotrans 的 tts 和 SpeedRate 接口）
import re
import shutil
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


def FormatSrtTime(Ms: int) -> str:
    """将毫秒转换为 SRT 时间格式 HH:MM:SS,mmm"""
    Hours = Ms // 3600000
    Minutes = (Ms % 3600000) // 60000
    Seconds = (Ms % 60000) // 1000
    Millis = Ms % 1000
    return f"{Hours:02d}:{Minutes:02d}:{Seconds:02d},{Millis:03d}"


def _GenerateNewSrt(QueueTts: list, OutputDir: Path) -> Path | None:
    """根据 SpeedRate 返回的新时间轴生成字幕文件"""
    OutputPath = OutputDir / "aligned.srt"

    Lines = []
    for Idx, Item in enumerate(QueueTts):
        Text = Item.get("text", "").strip()
        if not Text:
            continue
        StartTime = FormatSrtTime(Item.get("start_time", 0))
        EndTime = FormatSrtTime(Item.get("end_time", 0))
        Lines.append(str(Idx + 1))
        Lines.append(f"{StartTime} --> {EndTime}")
        Lines.append(Text)
        Lines.append("")

    if not Lines:
        Log(f"_GenerateNewSrt: No subtitles to write")
        return None

    OutputPath.write_text("\n".join(Lines), encoding="utf-8")
    Log(f"_GenerateNewSrt: Generated aligned subtitle -> {OutputPath}")
    return OutputPath


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
                    Voice: str = "晓晓 多语言(Female/CN)", VideoPath: Path = None,
                    VoiceAutorate: bool = False, VideoSlowdown: bool = True,
                    ProgressCallback=None) -> tuple[Path, Path] | None:
    """
    使用 videotrans 的 tts.run 接口根据字幕生成配音音频，并使用 SpeedRate 对齐
    SrtPath: 输入字幕路径
    OutputPath: 输出音频路径，默认为同目录下 zh-cn.wav
    Voice: edge-tts 声音显示名称（如 晓晓 多语言(Female/CN)）
    VideoPath: 原视频路径（视频慢速时需要，会被原地修改为慢速视频）
    VoiceAutorate: 是否启用配音自动加速对齐（默认 False）
    VideoSlowdown: 是否启用视频慢速对齐（默认 True）
    ProgressCallback: 进度回调 (percent, text)
    返回 (音频路径, 对齐后字幕路径) 或 None
    """
    from videotrans import tts
    from videotrans.configure import config
    from videotrans.util import tools

    if not SrtPath.exists():
        Log(f"GenerateDubbing: SRT not found: {SrtPath}")
        return None

    if OutputPath is None:
        OutputPath = SrtPath.parent / "zh-cn.wav"

    # 已存在则跳过（检查对齐字幕是否也存在）
    AlignedSrtPath = SrtPath.parent / "aligned.srt"
    if OutputPath.exists():
        Log(f"GenerateDubbing: Audio already exists: {OutputPath}")
        if AlignedSrtPath.exists():
            return (OutputPath, AlignedSrtPath)
        return (OutputPath, None)

    Log(f"GenerateDubbing: Parsing subtitles...")
    Subtitles = ParseSrt(SrtPath)
    if not Subtitles:
        Log(f"GenerateDubbing: No subtitles found")
        return None

    Log(f"GenerateDubbing: Generating {len(Subtitles)} segments using Edge-TTS...")
    if ProgressCallback:
        ProgressCallback(5, "Initializing TTS...")

    # 获取真正的 voice ID
    VoiceId = tools.get_edge_rolelist(Voice, "zh-cn")
    if not VoiceId:
        Log(f"GenerateDubbing: Voice '{Voice}' not found, using default")
        VoiceId = "zh-CN-XiaoxiaoNeural"  # 晓晓
    Log(f"GenerateDubbing: Voice ID = {VoiceId}")

    # 创建缓存目录
    CacheDir = SrtPath.parent / "tts_cache"
    CacheDir.mkdir(exist_ok=True)

    # 获取全局代理设置
    UseProxy = config.proxy if config.proxy else None
    Log(f"GenerateDubbing: Using proxy: {UseProxy}")
    Log(f"GenerateDubbing: Voice autorate: {VoiceAutorate}, Video slowdown: {VideoSlowdown}")

    if ProgressCallback:
        ProgressCallback(10, "Generating TTS...")

    # 保存原状态
    OrigBoxTts = config.box_tts

    try:
        # 设置状态以绕过 videotrans 的状态检查
        config.box_tts = 'ing'

        # 构建 videotrans tts 格式的 queue_tts
        # 注意：role 要用 VoiceId（如 zh-CN-XiaochenMultilingualNeural），不是显示名称
        # 注意：filename 必须包含 .wav 后缀，因为 SpeedRate 直接使用这个路径加载文件
        # 从配置读取语速设置
        VoiceRate = config.settings.get("voice_rate", "+0%")
        Log(f"GenerateDubbing: Voice rate = {VoiceRate}")

        QueueTts = []
        for I, Sub in enumerate(Subtitles):
            QueueTts.append({
                "text": Sub["text"],
                "role": VoiceId,  # 使用 VoiceId，不是 Voice 显示名称
                "filename": str(CacheDir / f"seg_{I:04d}.wav"),
                "start_time": int(Sub["start"] * 1000),
                "end_time": int(Sub["end"] * 1000),
                "line": I + 1,  # SpeedRate 需要 line 字段
                "rate": VoiceRate,  # 语速设置
            })

        Log(f"GenerateDubbing: Calling tts.run with {len(QueueTts)} items")

        Result = None
        try:
            tts.run(
                queue_tts=QueueTts,
                language="zh-cn",
                tts_type=tts.EDGE_TTS
            )

            if ProgressCallback:
                ProgressCallback(50, "Checking audio files...")

            # 检查生成的音频文件
            SuccessCount = 0
            for I, Item in enumerate(QueueTts):
                WavFile = Path(Item["filename"])
                if WavFile.exists() and WavFile.stat().st_size > 0:
                    SuccessCount += 1

            if SuccessCount == 0:
                Log(f"GenerateDubbing: videotrans produced no audio, falling back...")
                Result = _GenerateDubbingDirect(Subtitles, OutputPath, VoiceId, UseProxy,
                                              CacheDir, VideoPath, VoiceAutorate, VideoSlowdown, ProgressCallback)
            else:
                Log(f"GenerateDubbing: Generated {SuccessCount}/{len(QueueTts)} audio segments")

                if ProgressCallback:
                    ProgressCallback(60, "Aligning audio...")

                # 使用 SpeedRate 进行音频对齐和合并
                Result = _AlignAndMergeAudio(QueueTts, OutputPath, CacheDir, VideoPath,
                                            VoiceAutorate, VideoSlowdown, ProgressCallback)

        except Exception as TtsErr:
            Log(f"GenerateDubbing: tts.run failed: {TtsErr}")
            Log(f"GenerateDubbing: Falling back to direct edge-tts...")
            Result = _GenerateDubbingDirect(Subtitles, OutputPath, VoiceId, UseProxy,
                                          CacheDir, VideoPath, VoiceAutorate, VideoSlowdown, ProgressCallback)

        # 无论成功失败，都清理缓存目录
        if CacheDir.exists():
            try:
                shutil.rmtree(CacheDir)
                Log(f"GenerateDubbing: Cleaned up cache dir")
            except Exception as CleanErr:
                Log(f"GenerateDubbing: Failed to clean cache: {CleanErr}")

        if ProgressCallback:
            ProgressCallback(100, "Done")

        return Result

    except Exception as E:
        import traceback
        Log(f"GenerateDubbing error: {E}")
        Log(traceback.format_exc())
        # 异常时也清理缓存
        if CacheDir.exists():
            try:
                shutil.rmtree(CacheDir)
            except:
                pass
        return None

    finally:
        config.box_tts = OrigBoxTts


def _GenerateDubbingDirect(Subtitles: list, OutputPath: Path, VoiceId: str,
                           Proxy: str, CacheDir: Path, VideoPath: Path,
                           VoiceAutorate: bool, VideoSlowdown: bool,
                           ProgressCallback) -> Path | None:
    """直接使用 edge-tts 库生成配音（备用方案）"""
    import asyncio
    from edge_tts import Communicate
    from videotrans.util.help_ffmpeg import runffmpeg

    Log(f"_GenerateDubbingDirect: Generating {len(Subtitles)} segments...")

    # 构建 queue_tts 格式（filename 必须包含 .wav 后缀）
    QueueTts = []
    for I, Sub in enumerate(Subtitles):
        QueueTts.append({
            "text": Sub["text"],
            "filename": str(CacheDir / f"seg_{I:04d}.wav"),
            "start_time": int(Sub["start"] * 1000),
            "end_time": int(Sub["end"] * 1000),
            "line": I + 1,  # SpeedRate 需要 line 字段
        })

    async def GenerateAll():
        for I, Sub in enumerate(Subtitles):
            if ProgressCallback:
                Pct = 10 + int(40 * I / len(Subtitles))
                ProgressCallback(Pct, f"TTS [{I+1}/{len(Subtitles)}]")

            OutFile = CacheDir / f"seg_{I:04d}.mp3"
            WavFile = CacheDir / f"seg_{I:04d}.wav"

            # 跳过已存在的
            if WavFile.exists() and WavFile.stat().st_size > 0:
                continue

            try:
                Comm = Communicate(Sub["text"], voice=VoiceId, proxy=Proxy)
                await Comm.save(str(OutFile))
                if OutFile.exists() and OutFile.stat().st_size > 0:
                    runffmpeg(["-y", "-i", str(OutFile), "-ar", "44100", "-ac", "2", str(WavFile)])
            except Exception as E:
                Log(f"_GenerateDubbingDirect: Segment {I} failed: {E}")

    try:
        asyncio.run(GenerateAll())
    except Exception as E:
        Log(f"_GenerateDubbingDirect error: {E}")
        return None

    # 检查成功数量
    SuccessCount = sum(1 for Item in QueueTts
                       if Path(Item["filename"]).exists())
    if SuccessCount == 0:
        Log(f"_GenerateDubbingDirect: No audio files generated")
        return None

    Log(f"_GenerateDubbingDirect: Generated {SuccessCount}/{len(QueueTts)} segments")

    if ProgressCallback:
        ProgressCallback(60, "Aligning audio...")

    return _AlignAndMergeAudio(QueueTts, OutputPath, CacheDir, VideoPath,
                               VoiceAutorate, VideoSlowdown, ProgressCallback)


def _AlignAndMergeAudio(QueueTts: list, OutputPath: Path, CacheDir: Path, VideoPath: Path,
                        VoiceAutorate: bool, VideoSlowdown: bool, ProgressCallback) -> Path | None:
    """使用 videotrans 的 SpeedRate 对齐并合并音频"""
    import copy
    from videotrans.task._rate import SpeedRate
    from videotrans.configure import config

    Log(f"_AlignAndMergeAudio: Aligning {len(QueueTts)} segments (audiorate={VoiceAutorate}, videorate={VideoSlowdown})...")

    # 先检查音频文件是否存在
    for I, Item in enumerate(QueueTts):
        WavFile = Path(Item["filename"])
        if WavFile.exists():
            Size = WavFile.stat().st_size
            Log(f"  Segment {I}: {WavFile.name} ({Size} bytes)")
        else:
            Log(f"  Segment {I}: {WavFile.name} NOT FOUND")

    # 深拷贝，因为 SpeedRate 会修改 queue_tts（可能将 filename 设为 None）
    QueueTtsCopy = copy.deepcopy(QueueTts)

    # 计算总时长（最后一个字幕的结束时间，毫秒）
    RawTotalTime = QueueTts[-1]["end_time"] if QueueTts else 0
    Log(f"_AlignAndMergeAudio: Total time = {RawTotalTime}ms")

    # 视频慢速需要原视频文件
    NovoiceMp4 = str(VideoPath) if VideoSlowdown and VideoPath and VideoPath.exists() else None
    if VideoSlowdown and not NovoiceMp4:
        Log(f"_AlignAndMergeAudio: Video slowdown requested but no video file, disabling")

    try:
        # 使用 SpeedRate 进行对齐（使用副本，因为 SpeedRate 会修改 queue_tts）
        RateInst = SpeedRate(
            queue_tts=QueueTtsCopy,
            shoud_audiorate=VoiceAutorate,
            shoud_videorate=VideoSlowdown and NovoiceMp4 is not None,
            raw_total_time=RawTotalTime,
            target_audio=str(OutputPath),
            cache_folder=str(CacheDir),
            novoice_mp4=NovoiceMp4,
            remove_silent_mid=False,
            align_sub_audio=True
        )

        if ProgressCallback:
            ProgressCallback(70, "Processing alignment...")

        # 执行对齐，返回更新后的 queue_tts（包含新时间轴）
        UpdatedQueueTts = RateInst.run()

        if OutputPath.exists():
            Size = OutputPath.stat().st_size
            Log(f"_AlignAndMergeAudio: Output file size = {Size} bytes")
            if Size > 1000:  # 至少 1KB 才算有效
                Log(f"_AlignAndMergeAudio: Done -> {OutputPath}")
                # 如果启用了视频慢速，生成新的字幕文件
                NewSrtPath = None
                if VideoSlowdown and UpdatedQueueTts:
                    NewSrtPath = _GenerateNewSrt(UpdatedQueueTts, OutputPath.parent)
                return (OutputPath, NewSrtPath)
            else:
                Log(f"_AlignAndMergeAudio: Output too small, using fallback...")
                OutputPath.unlink()  # 删除无效文件
                return (_MergeAudioSimple(QueueTts, OutputPath, CacheDir), None)
        else:
            Log(f"_AlignAndMergeAudio: SpeedRate did not produce output, using fallback...")
            return (_MergeAudioSimple(QueueTts, OutputPath, CacheDir), None)

    except Exception as E:
        import traceback
        Log(f"_AlignAndMergeAudio error: {E}")
        Log(traceback.format_exc())
        Log(f"_AlignAndMergeAudio: Falling back to simple merge...")
        return (_MergeAudioSimple(QueueTts, OutputPath, CacheDir), None)


def _MergeAudioSimple(QueueTts: list, OutputPath: Path, TempDir: Path) -> Path | None:
    """简单合并音频文件（备用方案，不做加速对齐）"""
    from videotrans.util.help_ffmpeg import runffmpeg

    Log(f"_MergeAudioSimple: Starting simple merge...")

    AudioFiles = []
    for Item in QueueTts:
        WavFile = Path(Item["filename"])
        if WavFile.exists() and WavFile.stat().st_size > 0:
            AudioFiles.append((Item["start_time"], WavFile))
            Log(f"  Found: {WavFile.name} at {Item['start_time']}ms")

    if not AudioFiles:
        Log(f"_MergeAudioSimple: No audio files found")
        return None

    AudioFiles.sort(key=lambda X: X[0])
    LastEndTime = QueueTts[-1]["end_time"] / 1000
    SilenceFile = TempDir / "silence.wav"

    Log(f"_MergeAudioSimple: Creating {LastEndTime + 1}s silence base...")

    # 生成静音底座
    runffmpeg([
        "-y", "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(LastEndTime + 1),
        "-acodec", "pcm_s16le",
        str(SilenceFile)
    ])

    if len(AudioFiles) == 1:
        Log(f"_MergeAudioSimple: Single file, copying directly...")
        shutil.copy(AudioFiles[0][1], OutputPath)
    else:
        Log(f"_MergeAudioSimple: Merging {len(AudioFiles)} files with overlay...")

        # 使用 overlay 方式而不是 amix（避免音量衰减问题）
        Inputs = ["-i", str(SilenceFile)]
        FilterParts = []

        for I, (StartMs, WavFile) in enumerate(AudioFiles):
            Inputs.extend(["-i", str(WavFile)])
            # adelay 延迟到指定位置
            FilterParts.append(f"[{I+1}]adelay={StartMs}|{StartMs}[d{I}]")

        # 使用 amix 但不要 normalize，并且设置 dropout_transition 避免突然静音
        NumInputs = len(AudioFiles) + 1
        MixInputs = "[0]" + "".join(f"[d{I}]" for I in range(len(AudioFiles)))
        # 用 volume=0 让静音底座真正静音，然后用 amix 混合
        FilterComplex = "[0]volume=0[s0];" + ";".join(FilterParts) + f";[s0]" + "".join(f"[d{I}]" for I in range(len(AudioFiles))) + f"amix=inputs={NumInputs}:duration=longest:dropout_transition=0:normalize=0[out]"

        Cmd = ["-y"] + Inputs + [
            "-filter_complex", FilterComplex,
            "-map", "[out]",
            "-ar", "44100", "-ac", "2",
            "-acodec", "pcm_s16le",
            str(OutputPath)
        ]

        Log(f"_MergeAudioSimple: Running ffmpeg...")
        runffmpeg(Cmd)

    if OutputPath.exists():
        Size = OutputPath.stat().st_size
        Log(f"_MergeAudioSimple: Done -> {OutputPath} ({Size} bytes)")
        return OutputPath
    else:
        Log(f"_MergeAudioSimple: Output not created")
        return None
