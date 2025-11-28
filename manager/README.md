# AutoPYVideos Manager

将英文 YouTube 视频自动转换为中文语音中文字幕的视频。

## 处理流程

```
英文视频 → 语音识别 → 英文字幕 → 翻译 → 中文字幕 → 配音 → 中文视频
```

## 已实现

| 功能 | 工具/模型 | 说明 |
|------|-----------|------|
| 视频下载 | yt-dlp | 支持断点续传 |
| 语音识别 | Faster-Whisper large-v3 | 英文语音 → 英文字幕 |
| 字幕翻译 | Google Translate | 英文 → 中文 |

## 待实现

| 功能 | 说明 |
|------|------|
| 配音 | 中文 TTS 语音合成 |
| 合成 | 替换原音轨，生成最终视频 |

## 运行

```bash
conda activate AutoPYVideos
cd manager
python App.py
```
