# 发布模块
import re
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from Log import Log


def ExtractUrl(Text: str) -> str:
    """从文本中提取 URL，返回第一个匹配的 URL 或原文本"""
    if not Text:
        return ""
    # 匹配 http/https 开头的 URL
    Match = re.search(r'https?://[^\s<>"\']+', Text)
    if not Match:
        return Text.strip()
    Url = Match.group(0)
    # bilibili 链接只保留到 BV 号
    BiliMatch = re.match(r'(https?://www\.bilibili\.com/video/BV[a-zA-Z0-9]+)', Url)
    if BiliMatch:
        return BiliMatch.group(1)
    return Url


def ValidateUrl(Text: str) -> tuple[bool, str, str]:
    """验证链接是否可访问，返回 (成功, 错误信息, 提取的URL)"""
    if not Text or not Text.strip():
        return False, "链接为空", ""

    Url = ExtractUrl(Text)
    if not Url.startswith("http"):
        return False, "无效的 URL 格式", ""

    try:
        Req = urllib.request.Request(
            Url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(Req, timeout=10) as Resp:
            return True, "", Url
    except urllib.error.HTTPError as E:
        # 403/401 等表示链接存在，只是需要权限
        if E.code in [403, 401]:
            return True, "", Url
        return False, f"HTTP {E.code}", Url
    except urllib.error.URLError as E:
        return False, str(E.reason), Url
    except Exception as E:
        return False, str(E), Url


def CleanupTaskCache(TaskDir: Path) -> int:
    """清理任务缓存文件，只保留 info.json、log.txt 和 thumbnail.jpg，返回删除数量"""
    if not TaskDir.exists():
        return 0

    KeepFiles = {"info.json", "log.txt", "thumbnail.jpg"}
    Count = 0

    for Item in TaskDir.iterdir():
        if Item.name in KeepFiles:
            continue
        try:
            if Item.is_file():
                Item.unlink()
            else:
                shutil.rmtree(Item)
            Count += 1
        except Exception as E:
            Log(f"删除失败: {Item.name} - {E}")

    return Count
