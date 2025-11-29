# 字幕翻译模块（调用 videotrans 的 translator 接口）
import re
from pathlib import Path

# 代理设置（与 Download.py 保持一致）
PROXY = "http://127.0.0.1:7890"

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


def TranslateSrt(InputSrt: Path, OutputSrt: Path = None,
                 SourceLang: str = "en", TargetLang: str = "zh-cn",
                 ProgressCallback=None) -> Path | None:
    """
    翻译 SRT 字幕文件
    调用 videotrans 的 translator.run 接口
    InputSrt: 输入字幕路径
    OutputSrt: 输出字幕路径，默认为同目录下 {TargetLang}.srt
    SourceLang: 源语言代码（如 en, zh-cn）
    TargetLang: 目标语言代码（如 zh-cn, en）
    ProgressCallback: 进度回调 (percent, text)
    返回生成的 srt 文件路径
    """
    from videotrans import translator
    from videotrans.translator import GOOGLE_INDEX
    from videotrans.configure import config

    # 设置代理（Google 翻译需要）
    config.proxy = PROXY

    # 保存原状态
    OrigBoxTrans = config.box_trans

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

    Log(f"TranslateSrt: Translating {len(Subtitles)} subtitles ({SourceLang} -> {TargetLang})...")
    if ProgressCallback:
        ProgressCallback(10, "Translating...")

    try:
        # 设置状态以绕过 videotrans 的状态检查
        config.box_trans = 'ing'

        # 转换为 videotrans 格式：[{"text": "...", "line": 1}, ...]
        TextList = [{"text": Sub["text"], "line": Sub["line"]} for Sub in Subtitles]

        # 调用 videotrans 翻译接口（默认 Google，失败自动回退 Microsoft）
        Log(f"TranslateSrt: Using proxy {config.proxy}")
        try:
            Result = translator.run(
                translate_type=GOOGLE_INDEX,
                text_list=TextList,
                source_code=SourceLang,
                target_code=TargetLang
            )
        except Exception as TransErr:
            Log(f"TranslateSrt: translator.run exception: {TransErr}")
            import traceback
            Log(traceback.format_exc())
            return None

        if not Result:
            Log(f"TranslateSrt: Translation returned empty result")
            return None

        Log(f"TranslateSrt: Got {len(Result)} results")

        # 合并翻译结果
        # Result 格式可能是 [str, ...] 或 [{"text": str}, ...]
        Translated = []
        for I, Sub in enumerate(Subtitles):
            if I < len(Result):
                Item = Result[I]
                TransText = Item["text"] if isinstance(Item, dict) else str(Item)
            else:
                TransText = Sub["text"]
            Translated.append({
                "line": Sub["line"],
                "start": Sub["start"],
                "end": Sub["end"],
                "text": TransText
            })

        # 写入文件
        WriteSrt(Translated, OutputSrt)

        if ProgressCallback:
            ProgressCallback(100, "Done")

        Log(f"TranslateSrt: Done -> {OutputSrt}")
        return OutputSrt

    except Exception as E:
        import traceback
        Log(f"TranslateSrt error: {E}")
        Log(traceback.format_exc())
        return None

    finally:
        # 恢复原状态
        config.box_trans = OrigBoxTrans
