@echo off
setlocal
title MCDEV Revenue QQ Bot
cd /d "%~dp0"

REM ============================================================
REM  Minecraft (China) Developer Revenue QQ Bot - Windows start
REM
REM  Portable: runs on any Windows PC that has Python installed.
REM  Steps: find Python -> prepare .env -> check port ->
REM         build environment -> install deps -> start the bot
REM
REM  If the "venv" module is unavailable (embedded / stripped Python),
REM  it falls back to installing into the system Python automatically.
REM
REM  IMPORTANT: keep this file ASCII-only with CRLF line endings.
REM  Non-ASCII, or LF-only, .bat files break cmd.exe parsing
REM  (cmd may silently SKIP LINES).
REM ============================================================

echo ============================================================
echo  Minecraft Developer Revenue QQ Bot
echo ============================================================
echo.

REM ---------- 1. locate a real Python interpreter ----------
call :find_python
if not defined PY (
    echo [ERROR] Python was not found.
    echo.
    echo   Please install Python 3.9 or newer:
    echo     https://www.python.org/downloads/
    echo   During setup, tick "Add python.exe to PATH".
    echo.
    echo   Note: the Microsoft Store "python" alias does not count.
    echo.
    pause
    exit /b 1
)
echo [1/5] Python found:
echo        %PY%
"%PY%" --version
echo.

REM ---------- 2. configuration file ----------
if exist ".env" (
    echo [2/5] Found .env
) else (
    if not exist ".env.example" (
        echo [ERROR] Neither .env nor .env.example exists in:
        echo        %~dp0
        pause
        exit /b 1
    )
    copy /y ".env.example" ".env" >nul
    echo [2/5] Created .env from .env.example
    echo.
    echo        Please fill in MCDEV_COOKIE ^(and other options^), save, then
    echo        run this script again.
    echo.
    start "" notepad ".env"
    pause
    exit /b 1
)
echo.

REM ---------- 3. port check ----------
netstat -ano | findstr /c:":8080 " | findstr /i "LISTENING" >nul
if not errorlevel 1 (
    echo [ERROR] Port 8080 is already in use - the bot may already be
    echo         running, or another program holds the port.
    echo.
    echo         Close it first, or change HOST / PORT in .env.
    echo.
    pause
    exit /b 1
)
echo [3/5] Port 8080 is free
echo.

REM ---------- 4. build Python environment ----------
set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "USED_VENV=1"

if not exist "%VPY%" (
    echo [4/5] Preparing Python environment ...
    "%PY%" -m venv "%VENV%" >nul 2>&1
)

if exist "%VPY%" (
    echo        Using local virtual environment .venv
) else (
    echo        venv is unavailable - using the system Python instead.
    echo        Reason: this Python has no "venv" module, or venv failed.
    set "USED_VENV=0"
    set "VPY=%PY%"
)

echo        Installing dependencies ^(first run may take a few minutes^) ...
"%VPY%" -m pip install --upgrade pip >nul 2>&1
"%VPY%" -m pip install -r requirements.txt
if not errorlevel 1 goto :deps_ok
if "%USED_VENV%"=="1" goto :deps_fail
echo        Retrying with --user ...
"%VPY%" -m pip install --user -r requirements.txt
if not errorlevel 1 goto :deps_ok

:deps_fail
echo.
echo [ERROR] Failed to install dependencies.
echo         Check your network connection, then run this script again.
pause
exit /b 1

:deps_ok
echo.

REM ---------- 5. start the bot ----------
if not exist "bot.py" (
    echo [ERROR] bot.py not found in %~dp0
    pause
    exit /b 1
)

echo [5/5] Starting the bot ...
echo.
echo   Reverse WebSocket: ws://127.0.0.1:8080/onebot/v11/ws
echo   In NapCat, add a "WebSocket client (reverse)" pointing there.
echo.
echo   Keep this window open while the bot runs.
echo   Press Ctrl+C to stop.
echo.

"%VPY%" bot.py

echo.
echo The bot has exited.
pause
exit /b 0

REM ============================================================
REM  helper: pick the first usable Python interpreter
REM ============================================================
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
REM reject the Microsoft Store alias stub (WindowsApps)
echo %CAND% | findstr /i "WindowsApps" >nul
if errorlevel 1 set "PY=%CAND%"
exit /b
