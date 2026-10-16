@echo off
setlocal
title MCDEV Revenue QQ Bot (Official)
cd /d "%~dp0"

REM ============================================================
REM  Minecraft (China) Developer Revenue QQ Bot
REM  Official QQ Bot mode (qq-botpy) - NO QQ client required
REM
REM  Requires QQ_BOT_APPID / QQ_BOT_SECRET in .env
REM  Get them at https://q.qq.com/
REM
REM  IMPORTANT: keep this file ASCII-only with CRLF line endings.
REM ============================================================

echo ============================================================
echo  Minecraft Developer Revenue QQ Bot - Official mode
echo ============================================================
echo.

call :find_python
if not defined PY (
    echo [ERROR] Python was not found.
    echo   Install Python 3.9+ from https://www.python.org/downloads/
    echo   and tick "Add python.exe to PATH".
    pause
    exit /b 1
)
echo [1/4] Python: %PY%
"%PY%" --version

if not exist ".env" (
    if not exist ".env.example" (
        echo [ERROR] .env not found.
        pause
        exit /b 1
    )
    copy /y ".env.example" ".env" >nul
    echo [2/4] Created .env - please fill QQ_BOT_APPID / QQ_BOT_SECRET / MCDEV_COOKIE
    start "" notepad ".env"
    pause
    exit /b 1
)
echo [2/4] Found .env

set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (
    echo [3/4] Creating virtual environment ...
    "%PY%" -m venv "%VENV%" >nul 2>&1
)
if not exist "%VPY%" (
    echo        venv unavailable - using system Python
    set "VPY=%PY%"
) else (
    echo [3/4] Virtual environment OK
)

echo        Installing dependencies ^(first run may take a while^) ...
"%VPY%" -m pip install --upgrade pip >nul 2>&1
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

if not exist "bot_qq.py" (
    echo [ERROR] bot_qq.py not found in %~dp0
    pause
    exit /b 1
)

echo [4/4] Starting official QQ bot ...
echo.
echo   In a group: @the bot and send a command.
echo   Private chat: send a command directly.
echo   Keep this window open. Press Ctrl+C to stop.
echo.
"%VPY%" bot_qq.py

echo.
echo The bot has exited.
pause
exit /b 0

:find_python
set "PY="
call :probe "py -3"
if not defined PY call :probe "python"
if not defined PY call :probe "python3"
exit /b

:probe
set "CAND="
for /f "delims=" %%P in ('%~1 -c "import sys;print(sys.executable)" 2^>nul') do set "CAND=%%P"
if not defined CAND exit /b
echo %CAND% | findstr /i "WindowsApps" >nul
if errorlevel 1 set "PY=%CAND%"
exit /b
