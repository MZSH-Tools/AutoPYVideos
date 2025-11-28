# 视频下载模块
from pathlib import Path


PROXY = "http://127.0.0.1:7890"


def FetchVideoInfo(Url: str) -> dict | None:
    """获取视频信息（标题、作者等）"""
    try:
        import yt_dlp
        Options = {"quiet": True, "no_warnings": True, "proxy": PROXY}
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Info = Ydl.extract_info(Url, download=False)
            return {
                "Title": Info.get("title", ""),
                "Author": Info.get("uploader") or Info.get("channel", ""),
                "Duration": Info.get("duration", 0),
                "Description": Info.get("description", ""),
                "Thumbnail": Info.get("thumbnail", ""),
                "VideoId": Info.get("id", ""),
            }
    except Exception as E:
        print(f"FetchVideoInfo error: {E}")
        return None


class DownloadProgress:
    """下载进度回调包装"""
    def __init__(self, Callback):
        self.Callback = Callback

    def __call__(self, D: dict):
        if D["status"] == "downloading":
            Total = D.get("total_bytes") or D.get("total_bytes_estimate", 0)
            Downloaded = D.get("downloaded_bytes", 0)
            Speed = D.get("speed", 0)
            Percent = int(Downloaded * 100 / Total) if Total > 0 else 0
            self.Callback(Percent, "downloading", Speed)
        elif D["status"] == "finished":
            self.Callback(100, "finished", 0)


def DownloadVideo(Url: str, OutputDir: Path, ProgressCallback=None) -> Path | None:
    """
    下载视频，支持断点续传
    返回下载后的视频文件路径
    """
    import yt_dlp

    OutputDir.mkdir(parents=True, exist_ok=True)
    OutputTemplate = str(OutputDir / "%(id)s.%(ext)s")

    Options = {
        "outtmpl": OutputTemplate,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,
        "proxy": PROXY,
    }

    if ProgressCallback:
        Options["progress_hooks"] = [DownloadProgress(ProgressCallback)]

    try:
        with yt_dlp.YoutubeDL(Options) as Ydl:
            Info = Ydl.extract_info(Url, download=True)
            VideoId = Info.get("id", "")
            for File in OutputDir.iterdir():
                if File.stem == VideoId and File.suffix == ".mp4":
                    return File
            return None
    except Exception as E:
        print(f"Download error: {E}")
        return None
