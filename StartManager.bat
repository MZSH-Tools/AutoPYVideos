@echo off
cd /d "%~dp0"
powershell -Command "if (Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*RunManager.py*' }) { exit 1 } else { exit 0 }"
if %errorlevel%==1 (
    REM Already running, just show window
    powershell -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Manager is already running. Check the system tray.', 'AutoPYVideos')"
) else (
    start /b pythonw RunManager.py
)
