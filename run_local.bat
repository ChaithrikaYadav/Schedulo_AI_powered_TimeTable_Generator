@echo off
REM ============================================================
REM  Schedulo — One-command local startup for Windows
REM  Usage: Double-click run_local.bat  OR  run from Command Prompt
REM  Prerequisites: Python 3.11+  (https://www.python.org/downloads/)
REM ============================================================
echo.
echo  =====================================================
echo   Schedulo - AI-Powered Timetable Generator
echo  =====================================================
echo.

REM Step 1: Check Python
python --version 2>NUL
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Install from https://www.python.org/downloads/
    echo         Make sure "Add Python to PATH" is checked.
    pause & exit /b 1
)

REM Step 2: Create virtual environment if missing
if not exist ".venv" (
    echo [Setup] Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

REM Step 3: Install or update dependencies
echo [Setup] Checking dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.local.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check the output above.
    pause & exit /b 1
)

REM Step 4: Copy .env if missing
if not exist ".env" (
    echo [Setup] Creating .env from template...
    copy .env.local.example .env > NUL
    echo         .env created. Set GROQ_API_KEY or HF_API_TOKEN for AI features.
)

REM Step 5: Create required directories
if not exist "outputs"  mkdir outputs
if not exist "ml_models" mkdir ml_models
if not exist "logs"     mkdir logs
if not exist "data\postgres" mkdir data\postgres
if not exist "data\redis"    mkdir data\redis

REM Step 6: Start the application (auto-seeds DB on first run)
echo.
echo  =====================================================
echo   Backend  : http://localhost:8000
echo   API Docs : http://localhost:8000/docs
echo   Press Ctrl+C to stop
echo  =====================================================
echo.
python run.py --seed
pause
