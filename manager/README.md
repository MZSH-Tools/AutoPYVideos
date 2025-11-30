# AutoPYVideos Manager

English YouTube videos to Chinese - auto subtitle, translation and dubbing.

## Workflow

```
YouTube URL → Download → Extract Audio → Speech Recognition → Translation → Dubbing → Compose Video
```

## Features

| Feature | Tool | Status |
|---------|------|--------|
| Video Download | yt-dlp | Done |
| Audio Extract | FFmpeg | Done |
| Speech Recognition | Faster-Whisper | Done |
| Translation | Google Translate | Done |
| Dubbing | Edge-TTS | Done |
| Video Compose | FFmpeg (hard subtitle) | Done |

## Run

### Windows

```bash
conda activate AutoPYVideos
python RunManager.py
```

### macOS

```bash
conda run -n AutoPYVideos python RunManager.py

# Or double-click Start.command
```
