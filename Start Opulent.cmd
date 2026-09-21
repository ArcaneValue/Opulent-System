@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.13 or newer is required. Install it and select Add Python to PATH.
  pause
  exit /b 1
)
echo Open http://localhost:8765 in Microsoft Edge after the server starts.
echo Leave this window open. Press Ctrl+C here to stop Opulent.
python server.py
pause
