@echo off
cd /d "%~dp0"
echo Killing Edge processes...
taskkill /f /im msedge.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo === Step 1: Unsubscribe from all channels ===
.venv\Scripts\python -m yt_feed.cli unsub --yes

echo.
echo === Step 2: Subscribe to azan_kz1 ===
.venv\Scripts\python -m yt_feed.cli sub https://www.youtube.com/@azan_kz1 --yes

echo.
echo Done!
