@echo off
setlocal enabledelayedexpansion
title Task Bar Hero - Virtual Environment Setup
cd /d "%~dp0"

echo ========================================================
echo        TASK BAR HERO - VIRTUAL ENVIRONMENT SETUP
echo ========================================================
echo.

:: 1. Check if existing .venv is broken or copied from another machine
if exist ".venv\Scripts\python.exe" (
    echo [CHECK] Testing existing .venv environment...
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [WARNING] The existing .venv cannot run on this PC.
        echo           (Detected invalid paths or copied from another PC)
        echo [CLEANUP] Removing broken .venv folder...
        rmdir /s /q ".venv"
        echo [CLEANUP] Done.
    ) else (
        echo [INFO] Existing .venv is working.
        set /p REINSTALL="Do you want to reinstall/refresh dependencies? (y/N): "
        if /i "!REINSTALL!"=="y" (
            echo [CLEANUP] Removing existing .venv...
            rmdir /s /q ".venv"
        ) else (
            echo.
            echo Skipping venv creation. Updating packages...
            goto install_deps
        )
    )
)

:: 2. Find Python interpreter
echo.
echo [SEARCH] Finding Python installation on this PC...
set "PYTHON_CMD="

:: Check uv first (if available on this machine)
where uv >nul 2>&1
if not errorlevel 1 (
    echo [FOUND] 'uv' package manager found.
    goto create_venv_uv
)

:: Check standard python
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto found_python
)

:: Check Windows Python Launcher (py)
py --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    goto found_python
)

:: If no python found
echo.
echo ========================================================
echo [ERROR] Python was not found on this PC!
echo.
echo Please install Python (3.10, 3.11, or 3.12 recommended)
echo from: https://www.python.org/downloads/
echo.
echo IMPORTANT: During Python installation, make sure to check:
echo   [x] "Add Python to PATH"
echo ========================================================
echo.
pause
exit /b 1

:found_python
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PY_VER=%%v"
echo [FOUND] %PY_VER% using '%PYTHON_CMD%'

:: 3. Create .venv using standard Python
echo.
echo [STEP 1/2] Creating fresh virtual environment in .venv...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment using '%PYTHON_CMD% -m venv .venv'.
    pause
    exit /b 1
)
echo [SUCCESS] Virtual environment created.

:install_deps
echo.
echo [STEP 2/2] Installing requirements into .venv...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found!
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)
goto verify_env

:create_venv_uv
echo.
echo [STEP 1/2] Creating fresh virtual environment using uv...
uv venv .venv
if errorlevel 1 (
    echo [WARNING] uv venv failed, falling back to standard python...
    goto found_python
)
echo [SUCCESS] Virtual environment created with uv.
echo.
echo [STEP 2/2] Installing requirements using uv pip...
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
if errorlevel 1 (
    echo [WARNING] uv pip install failed, falling back to standard pip...
    goto install_deps
)

:verify_env
echo.
echo [VERIFY] Verifying core modules (PySide6, cv2, numpy, pyautogui, pynput)...
".venv\Scripts\python.exe" -c "import PySide6, cv2, numpy, mss, pyautogui, pynput; print('[OK] All required modules loaded successfully!')"
if errorlevel 1 (
    echo [WARNING] Some modules failed to import. Please check output above.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   [SUCCESS] SETUP COMPLETED SUCCESSFULLY!
echo ========================================================
echo You can now launch the bot anytime by running 'run_bot.bat'.
echo.
pause
exit /b 0