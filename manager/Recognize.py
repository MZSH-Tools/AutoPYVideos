# 语音识别模块（调用 videotrans 的 recognition 接口）
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


def FormatSrtTime(Seconds: float) -> str:
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    Hours = int(Seconds // 3600)
    Minutes = int((Seconds % 3600) // 60)
    Secs = int(Seconds % 60)
    Millis = int((Seconds % 1) * 1000)
    return f"{Hours:02d}:{Minutes:02d}:{Secs:02d},{Millis:03d}"


def RecognizeAudio(AudioPath: Path, OutputSrt: Path = None, Language: str = "en",
                   Model: str = "small.en", UseCuda: bool = False,
                   SplitType: int = 0, AutoFix: bool = True,
                   ProgressCallback=None) -> Path | None:
    """
    使用 videotrans 的 recognition.run 接口识别音频生成字幕
    AudioPath: 音频文件路径（16kHz wav）
    OutputSrt: 输出字幕路径，默认为音频同目录下 {Language}.srt
    Language: 语言代码，如 zh, en, ja
    Model: 模型名称，如 tiny, base, small, small.en, medium, large-v3
    UseCuda: 是否使用 GPU 加速（默认 False，使用 CPU）
    SplitType: 分割方式，0=整体识别，1=均等分割（默认 0）
    AutoFix: 是否启用自动修正字幕（默认 True）
    ProgressCallback: 进度回调 (percent, text)
    返回生成的 srt 文件路径
    """
    from videotrans import recognition
    from videotrans.configure import config
    from videotrans.util import tools

    if not AudioPath.exists():
        Log(f"RecognizeAudio: Audio not found: {AudioPath}")
        return None

    if OutputSrt is None:
        OutputSrt = AudioPath.parent / f"{Language}.srt"

    # 已存在则跳过
    if OutputSrt.exists():
        Log(f"RecognizeAudio: SRT already exists: {OutputSrt}")
        return OutputSrt

    Log(f"RecognizeAudio: Using {'CUDA' if UseCuda else 'CPU'} mode")
    Log(f"RecognizeAudio: Model={Model}, Language={Language}, SplitType={SplitType}, AutoFix={AutoFix}")

    if ProgressCallback:
        ProgressCallback(10, f"Loading {Model}...")

    # 保存原状态
    OrigBoxRecogn = config.box_recogn
    OrigRephrase = config.settings.get('rephrase', 0)

    try:
        # 设置状态以绕过 videotrans 的状态检查
        config.box_recogn = 'ing'
        # 关闭 LLM 重新断句（使用整体识别的原始断句）
        config.settings['rephrase'] = 0

        # 创建临时缓存目录
        CacheFolder = Path(tempfile.mkdtemp())

        Log(f"RecognizeAudio: Calling recognition.run...")

        # 调用 videotrans 识别接口
        Result = recognition.run(
            recogn_type=recognition.FASTER_WHISPER,
            audio_file=str(AudioPath),
            cache_folder=str(CacheFolder),
            model_name=Model,
            detect_language=Language,
            is_cuda=UseCuda,
            split_type=SplitType,  # 0=整体识别，1=均等分割
            subtitle_type=0  # 0=普通字幕
        )

        if not Result:
            Log(f"RecognizeAudio: Recognition failed, no result")
            return None

        Log(f"RecognizeAudio: Got {len(Result)} segments")

        if ProgressCallback:
            ProgressCallback(70, "Processing results...")

        # 自动修正字幕（如果启用）
        if AutoFix and Result:
            Log(f"RecognizeAudio: Applying auto fix...")
            if ProgressCallback:
                ProgressCallback(80, "Auto fixing...")
            Result = tools.auto_fix_srtdict(Result, Language)
            Log(f"RecognizeAudio: After auto fix: {len(Result)} segments")

        if ProgressCallback:
            ProgressCallback(90, "Writing SRT...")

        # Result 格式: [{"start_time": ms, "end_time": ms, "text": "..."}, ...]
        # 转换为 SRT 格式
        SrtLines = []
        for I, Item in enumerate(Result, 1):
            StartMs = Item.get("start_time", 0)
            EndMs = Item.get("end_time", 0)
            Text = Item.get("text", "").strip()
            if Text:
                StartTime = FormatSrtTime(StartMs / 1000)
                EndTime = FormatSrtTime(EndMs / 1000)
                SrtLines.append(str(I))
                SrtLines.append(f"{StartTime} --> {EndTime}")
                SrtLines.append(Text)
                SrtLines.append("")

        # 写入文件
        OutputSrt.write_text("\n".join(SrtLines), encoding="utf-8")

        if ProgressCallback:
            ProgressCallback(100, "Done")

        Log(f"RecognizeAudio: Done -> {OutputSrt}")
        return OutputSrt

    except Exception as E:
        import traceback
        Log(f"RecognizeAudio error: {E}")
        Log(traceback.format_exc())
        return None

    finally:
        # 恢复原状态
        config.box_recogn = OrigBoxRecogn
        config.settings['rephrase'] = OrigRephrase
