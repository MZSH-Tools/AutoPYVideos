# 字幕翻译模块
import re
import time
import requests
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


def ParseSrt(SrtPath: Path) -> list[dict]:
    """
    解析 SRT 字幕文件
    返回 [{line, start, end, text}, ...]
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

        # 行号
        try:
            LineNum = int(Lines[0].strip())
        except ValueError:
            continue

        # 时间轴
        TimeMatch = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            Lines[1].strip()
        )
        if not TimeMatch:
            continue

        # 字幕文本（可能多行）
        Text = "\n".join(Lines[2:]).strip()

        Result.append({
            "line": LineNum,
            "start": TimeMatch.group(1),
            "end": TimeMatch.group(2),
            "text": Text
        })

    return Result


def WriteSrt(Subtitles: list[dict], OutputPath: Path):
    """
    写入 SRT 字幕文件
    Subtitles: [{line, start, end, text}, ...]
    """
    Lines = []
    for I, Sub in enumerate(Subtitles, 1):
        Lines.append(str(I))
        Lines.append(f"{Sub['start']} --> {Sub['end']}")
        Lines.append(Sub["text"])
        Lines.append("")

    OutputPath.write_text("\n".join(Lines), encoding="utf-8")


def GoogleTranslate(Text: str, SourceLang: str = "zh-CN", TargetLang: str = "en") -> str | None:
    """
    使用 Google Translate 免费 API 翻译文本
    """
    Url = f"https://translate.google.com/m?sl={SourceLang}&tl={TargetLang}&q={requests.utils.quote(Text)}"
    Headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
    }

    try:
        Resp = requests.get(Url, headers=Headers, timeout=30, verify=False)
        Resp.raise_for_status()

        # 提取翻译结果
        Match = re.search(r'<div\s+class="result-container">([^<]+)<', Resp.text)
        if Match:
            return Match.group(1).strip()
        return None
    except Exception as E:
        Log(f"GoogleTranslate error: {E}")
        return None


def TranslateSrt(InputSrt: Path, OutputSrt: Path = None,
                 SourceLang: str = "zh-CN", TargetLang: str = "en",
                 ProgressCallback=None) -> Path | None:
    """
    翻译 SRT 字幕文件
    InputSrt: 输入字幕路径
    OutputSrt: 输出字幕路径，默认为同目录下 {TargetLang}.srt
    SourceLang: 源语言代码
    TargetLang: 目标语言代码
    ProgressCallback: 进度回调 (percent, text)
    返回生成的 srt 文件路径
    """
    if not InputSrt.exists():
        Log(f"TranslateSrt: Input not found: {InputSrt}")
        return None

    if OutputSrt is None:
        OutputSrt = InputSrt.parent / f"{TargetLang}.srt"

    # 已存在则跳过
    if OutputSrt.exists():
        Log(f"TranslateSrt: Output already exists: {OutputSrt}")
        return OutputSrt

    # 解析字幕
    Subtitles = ParseSrt(InputSrt)
    if not Subtitles:
        Log(f"TranslateSrt: No subtitles found in {InputSrt}")
        return None

    Total = len(Subtitles)
    Translated = []

    if ProgressCallback:
        ProgressCallback(0, "Starting translation...")

    for I, Sub in enumerate(Subtitles):
        Text = Sub["text"]

        # 翻译
        Result = GoogleTranslate(Text, SourceLang, TargetLang)
        if Result is None:
            # 翻译失败，保留原文
            Result = Text

        Translated.append({
            "line": Sub["line"],
            "start": Sub["start"],
            "end": Sub["end"],
            "text": Result
        })

        # 进度回调
        if ProgressCallback:
            Percent = int((I + 1) * 100 / Total)
            Preview = Result[:30] + "..." if len(Result) > 30 else Result
            ProgressCallback(Percent, Preview)

        # 避免请求过快被限制
        time.sleep(0.5)

    # 写入文件
    WriteSrt(Translated, OutputSrt)

    if ProgressCallback:
        ProgressCallback(100, "Done")

    return OutputSrt
