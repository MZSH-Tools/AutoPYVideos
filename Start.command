#!/bin/bash
# AutoPYVideos Launcher for macOS

cd "$(dirname "$0")"

# Initialize conda
source /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh

# Activate environment and run
conda activate AutoPYVideos
python RunManager.py
