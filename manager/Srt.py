# 公共 SRT 字幕处理模块
import re
from pathlib import Path


def ParseTime(TimeStr: str) -> float:
    """将 SRT 时间格式转换为秒数"""
    Match = re.match(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", TimeStr)
    if not Match:
        return 0.0
    Hours, Minutes, Seconds, Millis = Match.groups()
    return int(Hours) * 3600 + int(Minutes) * 60 + int(Seconds) + int(Millis) / 1000


def FormatTime(Seconds: float) -> str:
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    Hours = int(Seconds // 3600)
    Minutes = int((Seconds % 3600) // 60)
    Secs = int(Seconds % 60)
    Millis = int((Seconds % 1) * 1000)
    return f"{Hours:02d}:{Minutes:02d}:{Secs:02d},{Millis:03d}"


def FormatTimeMs(Ms: int) -> str:
    """将毫秒转换为 SRT 时间格式 HH:MM:SS,mmm"""
    Hours = Ms // 3600000
    Minutes = (Ms % 3600000) // 60000
    Seconds = (Ms % 60000) // 1000
    Millis = Ms % 1000
    return f"{Hours:02d}:{Minutes:02d}:{Seconds:02d},{Millis:03d}"


def Parse(SrtPath: Path) -> list[dict]:
    """解析 SRT 字幕文件，返回 [{line, start, end, text, start_sec, end_sec}, ...]"""
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
            r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})",
            Lines[1].strip()
        )
        if not TimeMatch:
            continue

        StartStr = TimeMatch.group(1)
        EndStr = TimeMatch.group(2)
        Text = "\n".join(Lines[2:]).strip()

        Result.append({
            "line": LineNum,
            "start": StartStr,
            "end": EndStr,
            "text": Text,
            "start_sec": ParseTime(StartStr),
            "end_sec": ParseTime(EndStr),
        })

    return Result


def Write(Subtitles: list[dict], OutputPath: Path):
    """写入 SRT 字幕文件，Subtitles: [{start, end, text}, ...]"""
    Lines = []
    for I, Sub in enumerate(Subtitles, 1):
        Lines.append(str(I))
        Lines.append(f"{Sub['start']} --> {Sub['end']}")
        Lines.append(Sub["text"])
        Lines.append("")

    OutputPath.write_text("\n".join(Lines), encoding="utf-8")
