# AutoPYVideos

Automated English-to-Chinese video localization tool. Downloads YouTube videos and automatically processes them through speech recognition, translation, dubbing, and video composition.

Based on [pyvideotrans](https://github.com/jianchang512/pyvideotrans).

## Features

- **YouTube Download**: Download videos with proxy support (yt-dlp)
- **Speech Recognition**: English speech to text (Faster-Whisper, CPU/CUDA)
- **Translation**: English to Chinese subtitle translation (Google Translate / DeepL / OpenAI)
- **Dubbing**: Chinese voice synthesis (Edge TTS - Microsoft free TTS)
- **Video Composition**: Merge audio, video, and hardcoded subtitles (FFmpeg)
- **Task Queue**: Priority queue with automatic processing
- **Resume Support**: File-based checkpoint recovery
- **Cross-platform**: Windows and macOS support

## Workflow

```
YouTube URL
    ↓
Download (yt-dlp, max 1080p)
    ↓
Extract Audio (FFmpeg, 16kHz mono WAV)
    ↓
Speech Recognition (Faster-Whisper) → en.srt
    ↓
Translation (Google Translate) → zh-cn.srt
    ↓
Dubbing (Edge TTS) → zh-cn.wav
    ↓
Composition (FFmpeg, hardcoded bilingual subtitles) → output.mp4
```

## Requirements

- Python 3.10
- FFmpeg
- uv (recommended) or conda

## Installation

### Windows

```bash
# Install FFmpeg
winget install Gyan.FFmpeg

# Clone repository
git clone https://github.com/MZSH-Tools/AutoPYVideos.git
cd AutoPYVideos

# Install dependencies with uv
uv sync
```

### macOS

```bash
# Install FFmpeg
brew install ffmpeg

# Clone repository
git clone https://github.com/MZSH-Tools/AutoPYVideos.git
cd AutoPYVideos

# Create conda environment
conda create -n AutoPYVideos python=3.10
conda activate AutoPYVideos

# Install PyTorch (CPU version for macOS)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Start the Application

**Windows:**
```bash
# Run with uv
uv run python RunManager.py

# Or use hidden window launcher (double-click)
StartManager.vbs
```

**macOS:**
```bash
# Run with conda
conda run -n AutoPYVideos python RunManager.py

# Or double-click launcher
Start.command
```

### Basic Operations

1. **Add Task**: Paste YouTube URL in the input box and press Enter
2. **View Progress**: Select task in the left panel to see details and logs
3. **Set Priority**: Right-click task → Set Priority (marked with star icon)
4. **Re-execute Stage**: Right-click task → Re-execute → Select stage
5. **Open Folder**: Click "Open Folder" button to view output files
6. **Publish**: Enter publish URL after uploading the output video

### Task States

| State | Color | Description |
|-------|-------|-------------|
| Queued | Gray | Waiting to start |
| Downloading | Blue | Downloading video |
| Extracting | Purple | Extracting audio |
| Recognizing | Orange | Speech recognition |
| Translating | Cyan | Translating subtitles |
| Dubbing | Indigo | Generating voice |
| Merging | Brown | Composing video |
| Ready | Green | Ready to publish |
| Published | Light Gray | Published |
| Failed | Red | Error occurred |

### Output Files

Each task folder contains:

```
{task_folder}/
├── info.json          # Task metadata (URL, title, author)
├── video.mp4          # Original video
├── audio.wav          # Extracted audio
├── en.srt             # English subtitles
├── zh-cn.srt          # Chinese subtitles
├── bilingual.srt      # Bilingual subtitles
├── zh-cn.wav          # Chinese dubbing audio
└── output.mp4         # Final video with hardcoded subtitles
```

### Data Location

- **Windows**: `%LOCALAPPDATA%\AutoPYVideos\Tasks\`
- **macOS**: `~/.local/share/AutoPYVideos/Tasks/`

## Configuration

Edit `manager/config.json` to customize:

- Speech recognition model and parameters
- Translation engine
- TTS voice and speed
- Video encoding settings

## Auto-start on Login (macOS)

```bash
# Enable
launchctl load ~/Library/LaunchAgents/com.autopyvideos.plist

# Disable
launchctl unload ~/Library/LaunchAgents/com.autopyvideos.plist
```

## Troubleshooting

### Edge TTS "NoAudioReceived" Error

Edge-tts 7.2.2+ has a bug causing TTS failures. The project locks edge-tts to version 7.2.1.

If you encounter this error, reinstall:
```bash
pip install edge-tts==7.2.1
```

### CUDA Not Detected

The application defaults to CPU mode. To enable CUDA:
1. Install CUDA toolkit and cuDNN
2. Set `"Processing.EnableCUDA": true` in `manager/config.json`

### Proxy Configuration

The application uses `http://127.0.0.1:7890` as default proxy. Modify in `manager/Config.py` if needed.

## License

GPL-3.0
