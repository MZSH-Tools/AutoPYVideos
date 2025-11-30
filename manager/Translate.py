# 字幕翻译模块（调用 videotrans 的 translator 接口）
import re
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


def MergeBilingualSrt(TargetSrtPath: Path, SourceSrtPath: Path, OutputPath: Path = None,
                       TargetLang: str = "zh-cn", SourceLang: str = "en") -> Path | None:
    """
    合并双语字幕（调用 videotrans 的 help_srt 工具函数）
    TargetSrtPath: 目标语言字幕路径（中文，显示在上）
    SourceSrtPath: 源语言字幕路径（英文，显示在下）
    OutputPath: 输出路径，默认为同目录下 bilingual.srt
    TargetLang: 目标语言代码
    SourceLang: 源语言代码
    返回生成的双语字幕路径
    """
    from videotrans.util.help_srt import get_subtitle_from_srt, textwrap
    from videotrans.configure import config

    if not TargetSrtPath.exists():
        Log(f"MergeBilingualSrt: Target SRT not found: {TargetSrtPath}")
        return None

    if not SourceSrtPath.exists():
        Log(f"MergeBilingualSrt: Source SRT not found: {SourceSrtPath}")
        return None

    if OutputPath is None:
        OutputPath = TargetSrtPath.parent / "bilingual.srt"

    # 已存在则跳过
    if OutputPath.exists():
        Log(f"MergeBilingualSrt: Output already exists: {OutputPath}")
        return OutputPath

    Log(f"MergeBilingualSrt: Loading subtitles...")

    try:
        TargetSubList = get_subtitle_from_srt(str(TargetSrtPath))
        SourceSubList = get_subtitle_from_srt(str(SourceSrtPath))
    except Exception as E:
        Log(f"MergeBilingualSrt: Failed to load subtitles: {E}")
        return None

    if not TargetSubList or not SourceSubList:
        Log(f"MergeBilingualSrt: Empty subtitles")
        return None

    Log(f"MergeBilingualSrt: Merging {len(TargetSubList)} + {len(SourceSubList)} subtitles...")

    # 硬字幕时单行字符数（参考 trans_create.py:893-896）
    MaxlenTarget = int(config.settings.get('cjk_len', 15) if TargetLang[:2] in ["zh", "ja", "jp", "ko", "yu"]
                       else config.settings.get('other_len', 60))
    MaxlenSource = int(config.settings.get('cjk_len', 15) if SourceLang[:2] in ["zh", "ja", "jp", "ko", "yu"]
                       else config.settings.get('other_len', 60))

    SourceLength = len(SourceSubList)
    SrtString = ""

    # 双语字幕组装（参考 trans_create.py:912-924）
    # 目标字幕在上，源字幕在下
    for I, Item in enumerate(TargetSubList):
        # 硬字幕换行
        TargetText = textwrap(Item['text'].strip(), MaxlenTarget)
        SrtString += f"{Item['line']}\n{Item['time']}\n{TargetText}"
        if SourceLength > 0 and I < SourceLength:
            SourceText = textwrap(SourceSubList[I]['text'].strip(), MaxlenSource)
            SrtString += "\n" + SourceText
        SrtString += "\n\n"

    OutputPath.write_text(SrtString.strip(), encoding="utf-8")
    Log(f"MergeBilingualSrt: Done -> {OutputPath}")
    return OutputPath


def TranslateText(Text: str, SourceLang: str = "en", TargetLang: str = "zh-cn",
                  TranslateType: int = None) -> str | None:
    """
    翻译单个文本
    Text: 要翻译的文本
    SourceLang: 源语言代码
    TargetLang: 目标语言代码
    TranslateType: 翻译引擎类型（默认 GOOGLE_INDEX）
    返回翻译后的文本，失败返回 None
    """
    from videotrans import translator
    from videotrans.translator import GOOGLE_INDEX
    from videotrans.configure import config

    if not Text or not Text.strip():
        return None

    if TranslateType is None:
        TranslateType = GOOGLE_INDEX

    OrigBoxTrans = config.box_trans

    try:
        config.box_trans = 'ing'
        TextList = [{"text": Text, "line": 1}]

        Result = translator.run(
            translate_type=TranslateType,
            text_list=TextList,
            source_code=SourceLang,
            target_code=TargetLang
        )

        if Result and len(Result) > 0:
            Item = Result[0]
            return Item["text"] if isinstance(Item, dict) else str(Item)
        return None

    except Exception as E:
        Log(f"TranslateText error: {E}")
        return None

    finally:
        config.box_trans = OrigBoxTrans


def TranslateSrt(InputSrt: Path, OutputSrt: Path = None,
                 SourceLang: str = "en", TargetLang: str = "zh-cn",
                 TranslateType: int = None,
                 ProgressCallback=None) -> Path | None:
    """
    翻译 SRT 字幕文件
    调用 videotrans 的 translator.run 接口
    InputSrt: 输入字幕路径
    OutputSrt: 输出字幕路径，默认为同目录下 {TargetLang}.srt
    SourceLang: 源语言代码（如 en, zh-cn）
    TargetLang: 目标语言代码（如 zh-cn, en）
    TranslateType: 翻译引擎类型（默认 GOOGLE_INDEX）
    ProgressCallback: 进度回调 (percent, text)
    返回生成的 srt 文件路径
    """
    from videotrans import translator
    from videotrans.translator import GOOGLE_INDEX
    from videotrans.configure import config

    # 默认使用 Google 翻译
    if TranslateType is None:
        TranslateType = GOOGLE_INDEX

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
    Log(f"TranslateSrt: Using translate_type={TranslateType}, proxy={config.proxy}")
    if ProgressCallback:
        ProgressCallback(10, "Translating...")

    try:
        # 设置状态以绕过 videotrans 的状态检查
        config.box_trans = 'ing'

        # 转换为 videotrans 格式：[{"text": "...", "line": 1}, ...]
        TextList = [{"text": Sub["text"], "line": Sub["line"]} for Sub in Subtitles]

        # 调用 videotrans 翻译接口（带重试机制，无限重试）
        import time
        RetryDelay = 2  # 秒
        MaxDelay = 10  # 最大间隔
        Attempt = 0
        Result = None

        while True:
            Attempt += 1
            try:
                Result = translator.run(
                    translate_type=TranslateType,
                    text_list=TextList,
                    source_code=SourceLang,
                    target_code=TargetLang
                )
                if Result:
                    break
            except Exception as TransErr:
                Log(f"TranslateSrt: Attempt {Attempt} failed: {TransErr}")
                Log(f"TranslateSrt: Retrying in {RetryDelay} seconds...")
                time.sleep(RetryDelay)
                RetryDelay = min(RetryDelay * 2, MaxDelay)  # 指数退避，最大60秒

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
