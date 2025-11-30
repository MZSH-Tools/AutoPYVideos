# AutoPYVideos

English video to Chinese - auto subtitle, translation and dubbing.

## Features

- YouTube video download (with proxy support)
- Speech recognition (Faster-Whisper)
- Subtitle translation (Google Translate / DeepL / OpenAI)
- Chinese dubbing (Edge TTS)
- Video composition (FFmpeg)
- Task queue with priority support
- Resume from breakpoint
- Cross-platform (Windows / macOS)

## Workflow

```
YouTube URL → Download → Extract Audio → Speech Recognition → Translation → Dubbing → Compose Video
```

## Requirements

- Python 3.10
- FFmpeg
- uv (recommended) or conda

## Installation

### Windows

```bash
# Install FFmpeg via winget
winget install Gyan.FFmpeg

# Install dependencies
uv sync
```

### macOS (with Conda)

```bash
# Install FFmpeg via Homebrew
brew install ffmpeg

# Create conda environment
conda create -n AutoPYVideos python=3.10
conda activate AutoPYVideos

# Install PyTorch (CPU version)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install dependencies
pip install PySide6 faster-whisper edge-tts yt-dlp ffmpeg-python srt pydub \
    openai deepl requests httpx aiohttp numpy scipy librosa soundfile \
    pillow pygame qdarkstyle sherpa-onnx sounddevice gtts zhconv jieba \
    plyer psutil openai-whisper anthropic google-genai \
    google-cloud-texttospeech google-api-python-client dashscope \
    transformers accelerate safetensors
```

## Usage

### Windows

```bash
# Run with uv
uv run python RunManager.py

# Or activate venv first
.venv\Scripts\activate
python RunManager.py

# Hidden window (double-click)
StartManager.vbs
```

### macOS

```bash
# Run with conda
conda run -n AutoPYVideos python RunManager.py

# Or activate environment first
conda activate AutoPYVideos
python RunManager.py

# Double-click launcher
Start.command
```

### Auto-start on Login (macOS)

```bash
# Enable
launchctl load ~/Library/LaunchAgents/com.autopyvideos.plist

# Disable
launchctl unload ~/Library/LaunchAgents/com.autopyvideos.plist
```

## Task Management

- **Add Task**: Paste YouTube URL in the input box
- **Priority**: Right-click → Set Priority (⚡ mark)
- **Re-execute**: Right-click → Re-execute → Select stage
- **Delete**: Right-click → Delete

## Output

Processed videos are saved in the task folder:
- `video.mp4` - Original video
- `en.srt` - English subtitle
- `zh-cn.srt` - Chinese subtitle
- `output.mp4` - Final video with Chinese dubbing

## License

GPL-3.0
