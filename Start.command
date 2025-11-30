#!/bin/bash

# 获取脚本所在目录
cd "$(dirname "$0")"

# 设置 PATH
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:$PATH"

# 激活 conda 并后台运行
source /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh
conda activate AutoPYVideos
nohup python RunManager.py > /dev/null 2>&1 &

# 关闭终端窗口
osascript -e 'tell application "Terminal" to close first window' &
