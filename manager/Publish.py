# 发布模块
import shutil
import urllib.request
import urllib.error
from pathlib import Path
from Log import Log


def ValidateUrl(Url: str) -> tuple[bool, str]:
    """验证链接是否可访问，返回 (成功, 错误信息)"""
    if not Url or not Url.strip():
        return False, "链接为空"

    try:
        Req = urllib.request.Request(
            Url.strip(),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(Req, timeout=10) as Resp:
            return True, ""
    except urllib.error.HTTPError as E:
        # 403/401 等表示链接存在，只是需要权限
        if E.code in [403, 401]:
            return True, ""
        return False, f"HTTP {E.code}"
    except urllib.error.URLError as E:
        return False, str(E.reason)
    except Exception as E:
        return False, str(E)


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
