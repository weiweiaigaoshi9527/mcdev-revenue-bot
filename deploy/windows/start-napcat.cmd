@echo off
REM ============================================================
REM  Start NapCat (Windows)
REM
REM  Why this wrapper exists:
REM   1) Clears Electron / VS Code environment variables inherited
REM      from AI / editor sessions. If they leak into QQ (also an
REM      Electron app), QQ exits right after launch and NapCat
REM      prints "Process exited.".
REM   2) Kills leftover QQ / NapCat processes.
REM   3) Starts NapCat with ABSOLUTE paths, so it works no matter
REM      what the current working directory is.
REM
REM  Usage: double-click this file (it will ask for a dmin rights).
REM
REM  IMPORTANT: keep this file ASCII-only. cmd.exe mis-parses UTF-8
REM  batch files when "chcp 65001" is used and may SKIP LINES.
REM ============================================================

setlocal

set "NAPCAT_DIR=F:\NapCat"
set "QQ_EXE=F:\QQNT\QQ.exe"
set "HOOK_DLL=%NAPCAT_DIR%\NapCatWinBootHook.dll"
set "BOOT_MAIN=%NAPCAT_DIR%\NapCatWinBootMain.exe"
set "LOAD_JS=%NAPCAT_DIR%\loadNapCat.js"

REM ---- 1. clear inherited Electron / VS Code environment ----
for %%V in (
  VSCODE_IPC_HOOK VSCODE_PID VSCODE_CODE_CACHE_PATH VSCODE_CRASH_REPORTER_PROCESS_TYPE
  VSCODE_CWD VSCODE_NLS_CONFIG VSCODE_LOGS
  AHA_CHROME_CRASHPAD_PIPE_NAME AHA_IPC_SERVICE_NAME CHROME_CRASHPAD_PIPE_NAME
  ELECTRON_RUN_AS_NODE ELECTRON_NO_ATTACH_CONSOLE NODE_OPTIONS NODE_ENV NPM_CONFIG_YES
  ICUBE_ELECTRON_PATH ICUBE_APP_ROOT ICUBE_USER_DATA_DIR ICUBE_MAIN_PPID ICUBE_APP_SETTINGS_HOME
  CFS_IPC_NAME CFS_TOKEN CFS_TRANSPORT CKG_PORT CKG_USE_AHA_IPC
  ENABLE_IPC_SERVER ENABLE_TOOLHOST AI_NATIVE_ENV
) do set "%%V="

REM ---- 2. require administrator ----
net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================================
echo  Starting NapCat
echo ============================================================
echo.

echo [1/4] Checking paths...
if not exist "%BOOT_MAIN%" (
    echo ERROR: not found - "%BOOT_MAIN%"
    echo Edit NAPCAT_DIR in this file.
    pause
    exit /b 1
)
if not exist "%QQ_EXE%" (
    echo ERROR: not found - "%QQ_EXE%"
    echo Edit QQ_EXE in this file.
    pause
    exit /b 1
)
if not exist "%HOOK_DLL%" (
    echo ERROR: not found - "%HOOK_DLL%"
    pause
    exit /b 1
)

echo [2/4] Killing leftover QQ / NapCat processes...
taskkill /f /im NapCatWinBootMain.exe >nul 2>&1
taskkill /f /im QQ.exe >nul 2>&1
timeout /t 5 /nobreak >nul

echo [3/4] Starting NapCat...
echo        (scan the QR code with mobile QQ if the login expired)
echo.
REM Enter NapCat dir first: the official launcher derives its paths
REM (qqnt.json / loadNapCat.js / hook dll) from the CURRENT directory,
REM and it also exports the NAPCAT_* env vars the boot main needs.
pushd "%NAPCAT_DIR%" || (
    echo ERROR: cannot enter "%NAPCAT_DIR%"
    pause
    exit /b 1
)
call "%NAPCAT_DIR%\launcher-win10.bat"
popd

echo.
echo NapCat has exited.
pause
