# AutoPYVideos Manager

A background management tool for automated YouTube video downloading, translation, and dubbing.

## Features

- System tray application (runs in background)
- YouTube video download via yt-dlp
- Automatic translation and dubbing using pyVideoTrans
- Task queue management
- History tracking

## Usage

```bash
python run_manager.py
```

Or use the batch file:

```bash
start_manager.bat
```

## Structure

```
manager/
├── App.py          # Application entry
├── Tray.py         # System tray module
└── MainWindow.py   # Manager UI window
```
