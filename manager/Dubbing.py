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
        Log(f"生成对齐字幕: 无字幕内容")
        return None

    OutputPath.write_text("\n".join(Lines), encoding="utf-8")
    Log(f"生成对齐字幕: 完成 -> {OutputPath}")
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
    """
    from videotrans import tts
    from videotrans.configure import config
    from videotrans.util import tools

    if not SrtPath.exists():
        Log(f"配音: 字幕文件不存在: {SrtPath}")
        return None

    if OutputPath is None:
        OutputPath = SrtPath.parent / "zh-cn.wav"

    # 已存在则跳过
    AlignedSrtPath = SrtPath.parent / "aligned.srt"
    if OutputPath.exists():
        Log(f"配音: 跳过，音频已存在: {OutputPath}")
        return (OutputPath, AlignedSrtPath) if AlignedSrtPath.exists() else (OutputPath, None)

    Subtitles = ParseSrt(SrtPath)
    if not Subtitles:
        Log(f"配音: 字幕文件中无字幕内容: {SrtPath}")
        return None

    # 获取 voice ID
    VoiceId = tools.get_edge_rolelist(Voice, "zh-cn")
    if not VoiceId:
        Log(f"配音: 声音 '{Voice}' 未找到，使用默认 zh-CN-XiaoxiaoNeural")
        VoiceId = "zh-CN-XiaoxiaoNeural"

    # 读取配置
    VoiceRate = config.settings.get("voice_rate", "+0%")
    UseProxy = config.proxy if config.proxy else None

    Log(f"配音: {len(Subtitles)} 条字幕, 声音={VoiceId}, 语速={VoiceRate}, 代理={UseProxy}")
    Log(f"配音: 音频加速={VoiceAutorate}, 视频慢放={VideoSlowdown}")

    # 创建缓存目录
    CacheDir = SrtPath.parent / "tts_cache"
    CacheDir.mkdir(exist_ok=True)

    if ProgressCallback:
        ProgressCallback(10, "Generating TTS...")

    # 保存原状态
    OrigBoxTts = config.box_tts

    try:
        config.box_tts = 'ing'

        # 构建 queue_tts
        QueueTts = []
        for I, Sub in enumerate(Subtitles):
            QueueTts.append({
                "text": Sub["text"],
                "role": VoiceId,
                "filename": str(CacheDir / f"seg_{I:04d}.wav"),
                "start_time": int(Sub["start"] * 1000),
                "end_time": int(Sub["end"] * 1000),
                "line": I + 1,
                "rate": VoiceRate,
            })

        Result = None
        try:
            Log(f"配音: 调用 videotrans tts.run...")
            tts.run(
                queue_tts=QueueTts,
                language="zh-cn",
                tts_type=tts.EDGE_TTS
            )

            if ProgressCallback:
                ProgressCallback(50, "Checking audio files...")

            # 检查生成的音频文件
            SuccessCount = sum(1 for Item in QueueTts
                              if Path(Item["filename"]).exists() and Path(Item["filename"]).stat().st_size > 0)
            FailedCount = len(QueueTts) - SuccessCount

            if SuccessCount == 0:
                Log(f"配音: videotrans tts.run 未生成任何音频，切换到备用方案 edge-tts")
                Result = _GenerateDubbingDirect(Subtitles, OutputPath, VoiceId, UseProxy,
                                              CacheDir, VideoPath, VoiceAutorate, VideoSlowdown, ProgressCallback, VoiceRate)
            else:
                Log(f"配音: videotrans tts.run 成功, {SuccessCount} 成功, {FailedCount} 失败")

                if ProgressCallback:
                    ProgressCallback(60, "Aligning audio...")

                Result = _AlignAndMergeAudio(QueueTts, OutputPath, CacheDir, VideoPath,
                                            VoiceAutorate, VideoSlowdown, ProgressCallback)

        except Exception as TtsErr:
            Log(f"配音: videotrans tts.run 异常: {TtsErr}, 切换到备用方案 edge-tts")
            Result = _GenerateDubbingDirect(Subtitles, OutputPath, VoiceId, UseProxy,
                                          CacheDir, VideoPath, VoiceAutorate, VideoSlowdown, ProgressCallback, VoiceRate)

        # 清理缓存
        if CacheDir.exists():
            try:
                shutil.rmtree(CacheDir)
            except:
                pass

        if ProgressCallback:
            ProgressCallback(100, "Done")

        return Result

    except Exception as E:
        import traceback
        Log(f"配音错误: {E}")
        Log(traceback.format_exc())
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
                           ProgressCallback, VoiceRate: str = "+0%") -> Path | None:
    """直接使用 edge-tts 库生成配音（备用方案）"""
    import asyncio
    from edge_tts import Communicate
    from videotrans.util.help_ffmpeg import runffmpeg

    Log(f"备用配音: {len(Subtitles)} 条字幕, 声音={VoiceId}, 语速={VoiceRate}")

    # 构建 queue_tts
    QueueTts = []
    for I, Sub in enumerate(Subtitles):
        QueueTts.append({
            "text": Sub["text"],
            "filename": str(CacheDir / f"seg_{I:04d}.wav"),
            "start_time": int(Sub["start"] * 1000),
            "end_time": int(Sub["end"] * 1000),
            "line": I + 1,
        })

    FailedSegments = []

    async def GenerateAll():
        for I, Sub in enumerate(Subtitles):
            if ProgressCallback:
                Pct = 10 + int(40 * I / len(Subtitles))
                ProgressCallback(Pct, f"TTS [{I+1}/{len(Subtitles)}]")

            OutFile = CacheDir / f"seg_{I:04d}.mp3"
            WavFile = CacheDir / f"seg_{I:04d}.wav"

            if WavFile.exists() and WavFile.stat().st_size > 0:
                continue

            try:
                Comm = Communicate(Sub["text"], voice=VoiceId, proxy=Proxy, rate=VoiceRate)
                await Comm.save(str(OutFile))
                if OutFile.exists() and OutFile.stat().st_size > 0:
                    runffmpeg(["-y", "-i", str(OutFile), "-ar", "44100", "-ac", "2", str(WavFile)])
            except Exception as E:
                FailedSegments.append((I, str(E)))

    try:
        asyncio.run(GenerateAll())
    except Exception as E:
        Log(f"备用配音错误: {E}")
        return None

    # 统计结果
    SuccessCount = sum(1 for Item in QueueTts if Path(Item["filename"]).exists())
    if SuccessCount == 0:
        Log(f"备用配音: 全部失败")
        return None

    if FailedSegments:
        Log(f"备用配音: {len(FailedSegments)} 条失败: {FailedSegments[:3]}...")
    Log(f"备用配音: {SuccessCount}/{len(QueueTts)} 条成功")

    if ProgressCallback:
        ProgressCallback(60, "Aligning audio...")

    return _AlignAndMergeAudio(QueueTts, OutputPath, CacheDir, VideoPath,
                               VoiceAutorate, VideoSlowdown, ProgressCallback)


def _AlignAndMergeAudio(QueueTts: list, OutputPath: Path, CacheDir: Path, VideoPath: Path,
                        VoiceAutorate: bool, VideoSlowdown: bool, ProgressCallback) -> tuple[Path, Path] | None:
    """使用 videotrans 的 SpeedRate 对齐并合并音频"""
    import copy
    from videotrans.task._rate import SpeedRate
    from videotrans.configure import config

    # 统计音频文件
    ExistCount = sum(1 for Item in QueueTts if Path(Item["filename"]).exists())
    MissingCount = len(QueueTts) - ExistCount
    if MissingCount > 0:
        Log(f"音频对齐: {ExistCount} 个文件存在, {MissingCount} 个缺失")
    else:
        Log(f"音频对齐: 全部 {ExistCount} 个文件存在")

    # 深拷贝
    QueueTtsCopy = copy.deepcopy(QueueTts)

    # 计算总时长
    RawTotalTime = QueueTts[-1]["end_time"] if QueueTts else 0

    # 视频慢速需要原视频文件
    NovoiceMp4 = str(VideoPath) if VideoSlowdown and VideoPath and VideoPath.exists() else None
    if VideoSlowdown and not NovoiceMp4:
        Log(f"音频对齐: 请求视频慢放但无视频文件，已禁用")
        VideoSlowdown = False

    Log(f"音频对齐: 总时长={RawTotalTime}ms, 音频加速={VoiceAutorate}, 视频慢放={VideoSlowdown}")

    try:
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

        Log(f"音频对齐: 执行 SpeedRate...")
        UpdatedQueueTts = RateInst.run()

        if OutputPath.exists():
            Size = OutputPath.stat().st_size
            if Size > 1000:
                Log(f"音频对齐: 完成, 输出={Size} 字节")
                NewSrtPath = None
                if VideoSlowdown and UpdatedQueueTts:
                    NewSrtPath = _GenerateNewSrt(UpdatedQueueTts, OutputPath.parent)
                return (OutputPath, NewSrtPath)
            else:
                Log(f"音频对齐: 输出太小 ({Size} 字节), 切换到简单合并")
                OutputPath.unlink()
                return (_MergeAudioSimple(QueueTts, OutputPath, CacheDir), None)
        else:
            Log(f"音频对齐: SpeedRate 未生成输出, 切换到简单合并")
            return (_MergeAudioSimple(QueueTts, OutputPath, CacheDir), None)

    except Exception as E:
        import traceback
        Log(f"音频对齐错误: {E}")
        Log(traceback.format_exc())
        Log(f"音频对齐: 切换到简单合并")
        return (_MergeAudioSimple(QueueTts, OutputPath, CacheDir), None)


def _MergeAudioSimple(QueueTts: list, OutputPath: Path, TempDir: Path) -> Path | None:
    """简单合并音频文件（备用方案，不做加速对齐）"""
    from videotrans.util.help_ffmpeg import runffmpeg

    Log(f"简单合并: 开始...")

    AudioFiles = []
    for Item in QueueTts:
        WavFile = Path(Item["filename"])
        if WavFile.exists() and WavFile.stat().st_size > 0:
            AudioFiles.append((Item["start_time"], WavFile))

    if not AudioFiles:
        Log(f"简单合并: 无音频文件")
        return None

    Log(f"简单合并: {len(AudioFiles)} 个文件")

    AudioFiles.sort(key=lambda X: X[0])
    LastEndTime = QueueTts[-1]["end_time"] / 1000
    SilenceFile = TempDir / "silence.wav"

    # 生成静音底座
    runffmpeg([
        "-y", "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(LastEndTime + 1),
        "-acodec", "pcm_s16le",
        str(SilenceFile)
    ])

    if len(AudioFiles) == 1:
        shutil.copy(AudioFiles[0][1], OutputPath)
    else:
        Inputs = ["-i", str(SilenceFile)]
        FilterParts = []

        for I, (StartMs, WavFile) in enumerate(AudioFiles):
            Inputs.extend(["-i", str(WavFile)])
            FilterParts.append(f"[{I+1}]adelay={StartMs}|{StartMs}[d{I}]")

        NumInputs = len(AudioFiles) + 1
        FilterComplex = "[0]volume=0[s0];" + ";".join(FilterParts) + f";[s0]" + "".join(f"[d{I}]" for I in range(len(AudioFiles))) + f"amix=inputs={NumInputs}:duration=longest:dropout_transition=0:normalize=0[out]"

        Cmd = ["-y"] + Inputs + [
            "-filter_complex", FilterComplex,
            "-map", "[out]",
            "-ar", "44100", "-ac", "2",
            "-acodec", "pcm_s16le",
            str(OutputPath)
        ]

        runffmpeg(Cmd)

    if OutputPath.exists():
        Log(f"简单合并: 完成, 输出={OutputPath.stat().st_size} 字节")
        return OutputPath
    else:
        Log(f"简单合并: 失败，无输出")
        return None
