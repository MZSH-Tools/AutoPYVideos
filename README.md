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

### macOS

```bash
# Install FFmpeg via Homebrew
brew install ffmpeg

# Install dependencies
uv sync
```

## Usage

```bash
# Run with uv
uv run python RunManager.py

# Or activate venv first
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows
python RunManager.py
```

### Windows (Hidden Window)

Double-click `StartManager.vbs`

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
