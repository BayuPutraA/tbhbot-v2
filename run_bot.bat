@echo off
title Task Bar Hero Automation
cd /d "%~dp0"

echo ========================================================
echo        TASK BAR HERO - CHEST & SYNTH AUTOMATOR
echo ========================================================
echo.

:: 1. Verify virtual environment exists and is usable on this PC
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] The virtual environment in .venv is broken or was
        echo           copied from another PC with different paths.
        echo.
        echo Launching automatic setup to rebuild .venv for this machine...
        echo.
        call "%~dp0install_venv.bat"
        if errorlevel 1 (
            echo [ERROR] Setup failed. Exiting...
            pause
            exit /b 1
        )
    )
) else (
    echo [INFO] Virtual environment not found in .venv.
    echo Launching automatic setup to install environment and packages...
    echo.
    call "%~dp0install_venv.bat"
    if errorlevel 1 (
        echo [ERROR] Setup failed. Exiting...
        pause
        exit /b 1
    )
)

echo Starting Task Bar Hero Automation Bot...
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo [INFO] Bot closed or encountered an error.
    pause
)
exit /b 0
