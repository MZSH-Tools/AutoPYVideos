# 视频下载模块
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import requests


def GetProxy() -> str | None:
    """从 videotrans 全局配置获取代理"""
    try:
        from videotrans.configure import config
        return config.proxy if config.proxy else None
    except:
        return None


def DownloadThumbnail(Url: str, OutputDir: Path) -> str:
    """下载封面图片到指定目录，返回本地路径（失败返回空字符串）"""
    try:
        OutputDir.mkdir(parents=True, exist_ok=True)
        OutputPath = OutputDir / "thumbnail.jpg"
        Proxy = GetProxy()
        Proxies = {"http": Proxy, "https": Proxy} if Proxy else None
        Resp = requests.get(Url, proxies=Proxies, timeout=30)
        if Resp.status_code == 200:
            with open(OutputPath, "wb") as F:
                F.write(Resp.content)
            return str(OutputPath)
    except Exception as E:
        print(f"DownloadThumbnail error: {E}")
    return ""


def FetchVideoInfo(Url: str) -> dict | None:
    """获取视频信息（标题、作者等）"""
    try:
        import yt_dlp
        Proxy = GetProxy()
        # noplaylist: 确保从播放列表链接中提取单个视频而非播放列表
        Options = {"quiet": True, "no_warnings": True, "noplaylist": True}
        if Proxy:
            Options["proxy"] = Proxy
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Info = Ydl.extract_info(Url, download=False)
            return {
                "Title": Info.get("title", ""),
                "Author": Info.get("uploader") or Info.get("channel", ""),
                "Thumbnail": Info.get("thumbnail", ""),
                "VideoId": Info.get("id", ""),
            }
    except Exception as E:
        print(f"FetchVideoInfo error: {E}")
        return None


class DownloadProgress:
    """下载进度回调包装，合并多流下载为单一进度"""
    def __init__(self, Callback):
        self.Callback = Callback
        self.StreamSizes = {}  # 记录每个流的大小 {filename: total_bytes}
        self.StreamDownloaded = {}  # 记录每个流已下载 {filename: downloaded_bytes}
        self.LastPercent = -1  # 避免重复回调相同进度

    def __call__(self, D: dict):
        if D["status"] == "downloading":
            Filename = D.get("filename", "unknown")
            Total = D.get("total_bytes") or D.get("total_bytes_estimate", 0)
            Downloaded = D.get("downloaded_bytes", 0)
            Speed = D.get("speed", 0)

            # 更新当前流的信息
            if Total > 0:
                self.StreamSizes[Filename] = Total
            self.StreamDownloaded[Filename] = Downloaded

            # 计算总进度
            TotalAll = sum(self.StreamSizes.values())
            DownloadedAll = sum(self.StreamDownloaded.values())
            Percent = int(DownloadedAll * 100 / TotalAll) if TotalAll > 0 else 0

            # 只在进度变化时回调
            if Percent != self.LastPercent:
                self.LastPercent = Percent
                self.Callback(Percent, "downloading", Speed)

        elif D["status"] == "finished":
            # 单个流完成，不触发总完成
            pass

        elif D["status"] == "error":
            self.Callback(self.LastPercent, "error", 0)


def DownloadVideo(Url: str, OutputDir: Path, ProgressCallback=None) -> Path | None:
    """
    下载视频，支持断点续传
    返回下载后的视频文件路径
    """
    import yt_dlp

    OutputDir.mkdir(parents=True, exist_ok=True)
    OutputTemplate = str(OutputDir / "%(id)s.%(ext)s")

    Proxy = GetProxy()
    Options = {
        "outtmpl": OutputTemplate,
        # 只下载单一格式（已包含音视频），避免分流下载合并导致流量翻倍
        # 优先级：1080p带音频 > 720p带音频 > 480p带音频 > 任意带音频
        "format": "best[height<=1080][acodec!=none]/best[height<=720][acodec!=none]/best[height<=480][acodec!=none]/best[acodec!=none]",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,
        "noplaylist": True,  # 确保只下载单个视频而非整个播放列表
    }
    if Proxy:
        Options["proxy"] = Proxy

    if ProgressCallback:
        Options["progress_hooks"] = [DownloadProgress(ProgressCallback)]

    try:
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Info = Ydl.extract_info(Url, download=True)
            VideoId = Info.get("id", "")
            for File in OutputDir.iterdir():
                if File.stem == VideoId and File.suffix == ".mp4":
                    if ProgressCallback:
                        ProgressCallback(100, "finished", 0)
                    return File
            return None
    except Exception as E:
        print(f"Download error: {E}")
        return None


def IsPlaylistUrl(Url: str) -> bool:
    """判断 URL 是否为播放列表（playlist?list=xxx 格式）"""
    try:
        Parsed = urlparse(Url)
        # 只有 /playlist 路径才是播放列表，watch?v=xxx&list=yyy 是单个视频
        return Parsed.path == "/playlist" and "list" in parse_qs(Parsed.query)
    except:
        return False


def CleanVideoUrl(Url: str) -> str:
    """清理视频 URL，只保留 watch?v=xxx，去除 list/index 等参数"""
    try:
        Parsed = urlparse(Url)
        # 只处理 /watch 路径
        if Parsed.path != "/watch":
            return Url
        Query = parse_qs(Parsed.query)
        VideoId = Query.get("v")
        if VideoId:
            return f"https://www.youtube.com/watch?v={VideoId[0]}"
        return Url
    except:
        return Url


def ValidateUrl(Url: str) -> bool:
    """验证链接是否有效（能否被 yt-dlp 识别）"""
    try:
        import yt_dlp
        Proxy = GetProxy()
        Options = {"quiet": True, "no_warnings": True, "extract_flat": True, "noplaylist": True}
        if Proxy:
            Options["proxy"] = Proxy
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Ydl.extract_info(Url, download=False)
            return True
    except:
        return False


def ExtractPlaylistId(Url: str) -> str | None:
    """从 URL 中提取播放列表 ID"""
    try:
        Parsed = urlparse(Url)
        Query = parse_qs(Parsed.query)
        ListIds = Query.get("list")
        return ListIds[0] if ListIds else None
    except:
        return None


def FetchPlaylistUrls(Url: str) -> list[str] | None:
    """获取播放列表中所有视频的 URL，失败返回 None。返回的 URL 都是干净的 watch?v=xxx 格式"""
    try:
        import yt_dlp

        # 如果不是播放列表链接，直接返回清理后的单个 URL
        if not IsPlaylistUrl(Url):
            return [CleanVideoUrl(Url)]

        # 从 URL 提取播放列表 ID，构造纯播放列表链接
        PlaylistId = ExtractPlaylistId(Url)
        if not PlaylistId:
            return [CleanVideoUrl(Url)]
        PlaylistUrl = f"https://www.youtube.com/playlist?list={PlaylistId}"

        Proxy = GetProxy()
        Options = {"quiet": True, "no_warnings": True, "extract_flat": True}
        if Proxy:
            Options["proxy"] = Proxy
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Info = Ydl.extract_info(PlaylistUrl, download=False)
            # 提取播放列表中所有视频，返回干净的 URL
            if Info.get("_type") == "playlist" and "entries" in Info:
                Urls = []
                for Entry in Info["entries"]:
                    if Entry and Entry.get("id"):
                        Urls.append(f"https://www.youtube.com/watch?v={Entry['id']}")
                    elif Entry and Entry.get("url"):
                        Urls.append(CleanVideoUrl(Entry["url"]))
                return Urls if Urls else None
            return None
    except Exception as E:
        print(f"FetchPlaylistUrls error: {E}")
        return None
