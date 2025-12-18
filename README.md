# AutoPYVideos

自动化英转中视频本地化工具。下载 YouTube 视频并自动完成语音识别、翻译、配音和视频合成。

基于 [pyvideotrans](https://github.com/jianchang512/pyvideotrans) 开发。

## 功能特性

### 核心功能
- **YouTube 下载**：支持代理下载视频（yt-dlp），支持单个视频链接和播放列表链接
- **播放列表支持**：自动解析播放列表，为每个视频创建独立任务
- **语音识别**：英语语音转文字（Faster-Whisper）
- **翻译**：英译中字幕翻译（Google 翻译 / DeepL / OpenAI）
- **配音**：中文语音合成（Edge TTS - 微软免费 TTS）
- **配音对齐**：配音时长超过字幕时长时自动视频慢放对齐
- **视频合成**：合并音频、视频和硬编码双语字幕（FFmpeg）
- **多模式运行**：支持纯 CPU 运行，也支持 CUDA 加速

### 任务管理
- **任务队列**：支持优先级的自动处理队列，同时只处理一个任务
- **任务控制**：支持暂停、重启、延迟执行、关闭、排除等操作
- **状态筛选**：按状态筛选任务列表，快速查找特定状态的任务
- **黑名单**：可设置频道或视频黑名单，自动跳过不需要处理的内容
- **断点续传**：基于文件的检查点恢复，程序重启后自动继续

### 界面功能
- **系统托盘**：后台常驻运行，托盘图标显示，右键菜单操作
- **单实例管理**：重复启动时唤醒已有窗口，不会重复运行
- **视频封面**：自动下载视频缩略图，任务详情显示封面预览
- **启动校验**：启动时自动检测并修复任务信息（标题、封面等）
- **延迟退出**：支持设置延迟时间后自动关闭程序
- **后台运行**：支持 Windows 和 macOS 后台静默运行

## 工作流程

```
YouTube 链接
    ↓
下载（yt-dlp，最高 1080p）
    ↓
提取音频（FFmpeg，16kHz 单声道 WAV）
    ↓
语音识别（Faster-Whisper）→ en.srt
    ↓
翻译（Google 翻译）→ zh-cn.srt
    ↓
配音（Edge TTS）→ zh-cn.wav
    ↓
合成（FFmpeg，硬编码双语字幕）→ output.mp4
```

## 环境要求

- Python 3.10
- FFmpeg
- uv（推荐）或 conda

## 安装步骤

### Windows

```bash
# 安装 FFmpeg
winget install Gyan.FFmpeg

# 克隆仓库
git clone https://github.com/MZSH-Tools/AutoPYVideos.git
cd AutoPYVideos

# 使用 uv 安装依赖
uv sync
```

### macOS

```bash
# 安装 FFmpeg
brew install ffmpeg

# 克隆仓库
git clone https://github.com/MZSH-Tools/AutoPYVideos.git
cd AutoPYVideos

# 创建 conda 环境
conda create -n AutoPYVideos python=3.10
conda activate AutoPYVideos

# 安装 PyTorch（macOS CPU 版本）
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

### 启动应用

**Windows：**
```bash
# 使用 uv 运行
uv run python RunManager.py

# 或使用隐藏窗口启动器（双击）
StartManager.vbs
```

**macOS：**
```bash
# 使用 conda 运行
conda run -n AutoPYVideos python RunManager.py

# 或双击启动器
Start.command
```

### 基本操作

1. **添加任务**：在输入框粘贴 YouTube 链接后按回车（支持单个视频或播放列表链接）
2. **查看进度**：在左侧面板选择任务查看详情和日志
3. **状态筛选**：点击顶部状态标签筛选显示特定状态的任务
4. **设置优先级**：右键任务 → 设置优先级（星标图标标记）
5. **重新执行阶段**：右键任务 → 重新执行 → 选择阶段
6. **暂停/重启**：右键任务 → 暂停任务 / 重启任务
7. **延迟执行**：右键任务 → 延迟执行，设置延迟时间
8. **排除任务**：右键任务 → 排除任务，从处理队列中移除
9. **黑名单管理**：右键任务 → 加入黑名单，可按频道或视频设置
10. **打开文件夹**：点击"打开文件夹"按钮查看输出文件
11. **发布验证**：上传视频后输入发布链接，点击验证按钮，自动标记为已发布并清理缓存文件

### 托盘操作

- **双击托盘图标**：打开管理界面
- **右键托盘图标**：显示菜单（打开管理界面 / 延迟退出 / 退出）
- **关闭窗口**：隐藏到托盘继续后台运行

### 任务状态

| 状态 | 颜色 | 说明 |
|------|------|------|
| 排队中 | 灰色 | 等待开始 |
| 下载中 | 蓝色 | 正在下载视频 |
| 提取中 | 紫色 | 正在提取音频 |
| 识别中 | 橙色 | 正在语音识别 |
| 翻译中 | 青色 | 正在翻译字幕 |
| 配音中 | 靛蓝 | 正在生成语音 |
| 合成中 | 棕色 | 正在合成视频 |
| 待发布 | 绿色 | 准备发布 |
| 已发布 | 浅灰 | 已发布 |
| 已暂停 | 黄色 | 任务已暂停 |
| 已延迟 | 橙黄 | 延迟执行中 |
| 已排除 | 深灰 | 已从队列排除 |
| 失败 | 红色 | 发生错误 |

### 输出文件

每个任务文件夹包含：

```
{task_folder}/
├── info.json          # 任务元数据（链接、标题、作者）
├── thumbnail.jpg      # 视频封面缩略图
├── video.mp4          # 原始视频
├── video_slow.mp4     # 慢放后的视频（配音对齐时生成）
├── audio.wav          # 提取的音频
├── en.srt             # 英文字幕
├── zh-cn.srt          # 中文字幕
├── bilingual.srt      # 双语字幕
├── aligned.srt        # 对齐后的中文字幕（配音对齐时生成）
├── zh-cn.wav          # 中文配音音频
└── output.mp4         # 带硬字幕的最终视频
```

### 数据位置

- **Windows**：`%LOCALAPPDATA%\AutoPYVideos\Tasks\`
- **macOS**：`~/.local/share/AutoPYVideos/Tasks/`

## 配置

编辑 `manager/config.json` 可自定义：

- 语音识别模型和参数
- 翻译引擎
- TTS 声音和语速
- 视频编码设置

## 开机自启

### Windows

将 `StartManager.vbs` 的快捷方式放入启动文件夹：

1. 按 `Win + R` 打开运行
2. 输入 `shell:startup` 回车打开启动文件夹
3. 将 `StartManager.vbs` 的快捷方式复制到该文件夹

### macOS

```bash
# 启用
launchctl load ~/Library/LaunchAgents/com.autopyvideos.plist

# 禁用
launchctl unload ~/Library/LaunchAgents/com.autopyvideos.plist
```

## 常见问题

### Edge TTS "NoAudioReceived" 错误

Edge-tts 7.2.2+ 存在导致 TTS 失败的 bug。本项目已锁定 edge-tts 版本为 7.2.1。

如遇此错误，请重新安装：
```bash
pip install edge-tts==7.2.1
```

### 未检测到 CUDA

应用默认使用 CPU 模式。启用 CUDA：
1. 安装 CUDA toolkit 和 cuDNN
2. 在 `manager/config.json` 中设置 `"Processing.EnableCUDA": true`

### 代理配置

应用默认使用 `http://127.0.0.1:7890` 作为代理。如需修改请编辑 `manager/Config.py`。

## 许可证

GPL-3.0
