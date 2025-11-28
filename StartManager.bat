@echo off
cd /d "%~dp0"
REM 激活 conda 环境
call conda activate AutoPYVideos
python RunManager.py
pause
