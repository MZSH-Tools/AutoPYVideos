# AutoPYVideos

英文视频中文化工具：自动将英文视频转换为中文字幕和配音

## 功能

### 已实现

- [x] 系统托盘常驻运行
- [x] YouTube 视频下载（支持代理）
- [x] 音频提取（ffmpeg）
- [x] 英文语音识别（Faster-Whisper，CPU 模式）
- [x] 字幕翻译（Google Translate）
- [x] 中文配音（edge-tts 微软免费 TTS）
- [x] 音视频合成（ffmpeg）
- [x] 任务队列管理（自动处理，同时只处理一个）
- [x] 断点续传（基于文件夹状态推断）

### 待实现

- [ ] 发布功能

## 处理流程

```
YouTube 链接 → 下载视频 → 提取音频 → 英文识别 → 翻译中文 → 中文配音 → 合成视频
```

## 运行

```bash
# 激活环境
conda activate AutoPYVideos

# 启动
python RunManager.py

# Windows 隐藏窗口启动
双击 StartManager.vbs
```
