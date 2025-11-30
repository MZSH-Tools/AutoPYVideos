# 配音模块（调用 videotrans 的 tts 和 SpeedRate 接口）
import re
import shutil
import copy
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


def _GenerateAlignedSrt(QueueTts: list, OutputDir: Path) -> Path | None:
    """根据 SpeedRate 返回的新时间轴生成对齐字幕文件"""
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
        Log("生成对齐字幕: 无内容")
        return None

    OutputPath.write_text("\n".join(Lines), encoding="utf-8")
    Log(f"生成对齐字幕: {OutputPath}")
    return OutputPath


def GenerateDubbing(SrtPath: Path, OutputPath: Path = None,
                    Voice: str = "晓晓 多语言(Female/CN)", VideoPath: Path = None,
                    VoiceAutorate: bool = False, VideoSlowdown: bool = True,
                    RemoveSilentMid: bool = False, AlignSubAudio: bool = True,
                    ProgressCallback=None) -> tuple[Path, Path] | None:
    """
    使用 videotrans 的 tts.run 接口生成配音音频，并使用 SpeedRate 对齐时间轴
    完全依赖 videotrans 接口，有错误直接抛出
    """
    from videotrans import tts
    from videotrans.configure import config
    from videotrans.util import tools
    from videotrans.task._rate import SpeedRate

    # 检查字幕文件
    if not SrtPath.exists():
        raise FileNotFoundError(f"字幕文件不存在: {SrtPath}")

    if OutputPath is None:
        OutputPath = SrtPath.parent / "zh-cn.wav"

    # 已存在则跳过
    AlignedSrtPath = SrtPath.parent / "aligned.srt"
    if OutputPath.exists():
        Log(f"配音: 音频已存在，跳过: {OutputPath}")
        return (OutputPath, AlignedSrtPath) if AlignedSrtPath.exists() else (OutputPath, None)

    # 解析字幕
    Subtitles = ParseSrt(SrtPath)
    if not Subtitles:
        raise ValueError(f"字幕文件无内容: {SrtPath}")

    # 验证声音名称是否有效
    VoiceId = tools.get_edge_rolelist(Voice, "zh-cn")
    if not VoiceId:
        raise ValueError(f"无效的声音名称: {Voice}")

    # 读取配置（voice_rate 在 params 中，不在 settings 中）
    VoiceRate = config.params.get("voice_rate", "+0%")
    UseProxy = config.proxy if config.proxy else None

    Log(f"配音: {len(Subtitles)} 条字幕")
    Log(f"配音: 声音={Voice}, 语速={VoiceRate} (from config.params)")
    Log(f"配音: 音频加速={VoiceAutorate}, 视频慢放={VideoSlowdown}")

    # 创建缓存目录
    CacheDir = SrtPath.parent / "tts_cache"
    CacheDir.mkdir(exist_ok=True)

    # 保存原状态
    OrigBoxTts = config.box_tts

    try:
        config.box_tts = 'ing'

        if ProgressCallback:
            ProgressCallback(10, "生成配音...")

        # 构建 queue_tts
        # role 使用原始中文名称，EdgeTTS 内部会调用 get_edge_rolelist 转换
        QueueTts = []
        for I, Sub in enumerate(Subtitles):
            QueueTts.append({
                "text": Sub["text"],
                "role": Voice,
                "filename": str(CacheDir / f"seg_{I:04d}.wav"),
                "start_time": int(Sub["start"] * 1000),
                "end_time": int(Sub["end"] * 1000),
                "line": I + 1,
                "rate": VoiceRate,
            })

        # 调用 videotrans tts.run 生成配音
        Log("配音: 调用 videotrans tts.run...")
        tts.run(
            queue_tts=QueueTts,
            language="zh-cn",
            tts_type=tts.EDGE_TTS
        )

        if ProgressCallback:
            ProgressCallback(50, "检查音频...")

        # 检查生成结果
        SuccessCount = sum(1 for Item in QueueTts
                          if Path(Item["filename"]).exists() and Path(Item["filename"]).stat().st_size > 0)
        FailedCount = len(QueueTts) - SuccessCount

        if SuccessCount == 0:
            raise RuntimeError("videotrans tts.run 未生成任何音频")

        Log(f"配音: tts.run 完成, 成功={SuccessCount}, 失败={FailedCount}")

        if ProgressCallback:
            ProgressCallback(60, "对齐音频...")

        # 使用 SpeedRate 对齐音频和视频
        QueueTtsCopy = copy.deepcopy(QueueTts)
        RawTotalTime = QueueTts[-1]["end_time"] if QueueTts else 0

        # 视频慢放需要原视频文件
        NovoiceMp4 = None
        if VideoSlowdown:
            if VideoPath and VideoPath.exists():
                NovoiceMp4 = str(VideoPath)
            else:
                Log("配音: 视频慢放需要视频文件，已禁用")
                VideoSlowdown = False

        Log(f"配音: 调用 SpeedRate, 总时长={RawTotalTime}ms")

        RateInst = SpeedRate(
            queue_tts=QueueTtsCopy,
            shoud_audiorate=VoiceAutorate,
            shoud_videorate=VideoSlowdown,
            raw_total_time=RawTotalTime,
            target_audio=str(OutputPath),
            cache_folder=str(CacheDir),
            novoice_mp4=NovoiceMp4,
            remove_silent_mid=RemoveSilentMid,
            align_sub_audio=AlignSubAudio
        )

        if ProgressCallback:
            ProgressCallback(70, "处理对齐...")

        UpdatedQueueTts = RateInst.run()

        # 检查输出
        if not OutputPath.exists():
            raise RuntimeError("SpeedRate 未生成输出音频")

        Size = OutputPath.stat().st_size
        if Size < 1000:
            raise RuntimeError(f"SpeedRate 输出音频太小: {Size} 字节")

        Log(f"配音: SpeedRate 完成, 输出={Size} 字节")

        # 视频慢放时生成对齐字幕
        NewSrtPath = None
        if VideoSlowdown and UpdatedQueueTts:
            NewSrtPath = _GenerateAlignedSrt(UpdatedQueueTts, OutputPath.parent)

        if ProgressCallback:
            ProgressCallback(100, "完成")

        Log(f"配音: 完成 -> {OutputPath}")
        return (OutputPath, NewSrtPath)

    finally:
        config.box_tts = OrigBoxTts
        # 清理缓存
        if CacheDir.exists():
            try:
                shutil.rmtree(CacheDir)
            except:
                pass
