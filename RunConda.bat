@echo off
REM 启动 pyvideotrans 原项目的 GUI 界面
REM 用于功能对比

call conda activate AutoPYVideos
cd /d "%~dp0"
python sp.py
pause
