# 视频下载模块
from pathlib import Path


def GetProxy() -> str | None:
    """从 videotrans 全局配置获取代理"""
    try:
        from videotrans.configure import config
        return config.proxy if config.proxy else None
    except:
        return None


def FetchVideoInfo(Url: str) -> dict | None:
    """获取视频信息（标题、作者等）"""
    try:
        import yt_dlp
        Proxy = GetProxy()
        Options = {"quiet": True, "no_warnings": True}
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
        self.TotalBytes = 0  # 累计总大小
        self.DownloadedBytes = 0  # 累计已下载
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


def ValidateUrl(Url: str) -> bool:
    """验证链接是否有效（能否被 yt-dlp 识别）"""
    try:
        import yt_dlp
        Proxy = GetProxy()
        Options = {"quiet": True, "no_warnings": True, "extract_flat": True}
        if Proxy:
            Options["proxy"] = Proxy
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Ydl.extract_info(Url, download=False)
            return True
    except:
        return False


def FetchPlaylistUrls(Url: str) -> list[str] | None:
    """获取播放列表中所有视频的 URL，失败返回 None"""
    try:
        import yt_dlp
        Proxy = GetProxy()
        Options = {"quiet": True, "no_warnings": True, "extract_flat": True}
        if Proxy:
            Options["proxy"] = Proxy
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Info = Ydl.extract_info(Url, download=False)
            # 判断是否为播放列表
            if Info.get("_type") == "playlist" and "entries" in Info:
                Urls = []
                for Entry in Info["entries"]:
                    if Entry and Entry.get("url"):
                        Urls.append(Entry["url"])
                    elif Entry and Entry.get("id"):
                        Urls.append(f"https://www.youtube.com/watch?v={Entry['id']}")
                return Urls
            # 单个视频返回包含该视频的列表
            elif Info.get("id"):
                return [Url]
            return None
    except Exception as E:
        print(f"FetchPlaylistUrls error: {E}")
        return None
