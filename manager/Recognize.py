# 语音识别模块（Faster-Whisper）
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


def RecognizeAudio(AudioPath: Path, OutputSrt: Path = None, Language: str = "zh",
                   Model: str = "large-v3", UseCuda: bool = True,
                   ProgressCallback=None) -> Path | None:
    """
    使用 Faster-Whisper 识别音频生成字幕
    AudioPath: 音频文件路径（16kHz wav）
    OutputSrt: 输出字幕路径，默认为音频同目录下 {Language}.srt
    Language: 语言代码，如 zh, en, ja
    Model: 模型名称，如 tiny, base, small, medium, large-v3
    UseCuda: 是否使用 GPU 加速
    ProgressCallback: 进度回调 (percent, text)
    返回生成的 srt 文件路径
    """
    if not AudioPath.exists():
        Log(f"RecognizeAudio: Audio not found: {AudioPath}")
        return None

    if OutputSrt is None:
        OutputSrt = AudioPath.parent / f"{Language}.srt"

    # 已存在则跳过
    if OutputSrt.exists():
        Log(f"RecognizeAudio: SRT already exists: {OutputSrt}")
        return OutputSrt

    try:
        from faster_whisper import WhisperModel

        Log(f"RecognizeAudio: Loading model {Model}...")
        if ProgressCallback:
            ProgressCallback(0, "Loading model...")

        # 加载模型
        Device = "cuda" if UseCuda else "cpu"
        ComputeType = "float16" if UseCuda else "int8"
        ModelObj = WhisperModel(Model, device=Device, compute_type=ComputeType)

        if ProgressCallback:
            ProgressCallback(10, "Transcribing...")

        # 识别
        Segments, Info = ModelObj.transcribe(
            str(AudioPath),
            language=Language,
            beam_size=5,
            word_timestamps=True
        )

        # 生成 SRT
        SrtLines = []
        Index = 1
        for Seg in Segments:
            StartTime = FormatSrtTime(Seg.start)
            EndTime = FormatSrtTime(Seg.end)
            Text = Seg.text.strip()
            if Text:
                SrtLines.append(f"{Index}")
                SrtLines.append(f"{StartTime} --> {EndTime}")
                SrtLines.append(Text)
                SrtLines.append("")
                Index += 1

            if ProgressCallback:
                # 估算进度（基于时间）
                Progress = min(90, 10 + int(Seg.end / Info.duration * 80))
                ProgressCallback(Progress, Text[:30] + "..." if len(Text) > 30 else Text)

        # 写入文件
        with open(OutputSrt, "w", encoding="utf-8") as F:
            F.write("\n".join(SrtLines))

        if ProgressCallback:
            ProgressCallback(100, "Done")

        return OutputSrt

    except Exception as E:
        import traceback
        Log(f"RecognizeAudio error: {E}")
        Log(traceback.format_exc())
        return None
