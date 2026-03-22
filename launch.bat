@echo off
setlocal

set VENV=%~dp0.venv

if not exist "%VENV%\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo Failed to create virtual environment. Is Python installed?
        pause & exit /b 1
    )
)

if not exist "%VENV%\Scripts\activate.bat" (
    echo Virtual environment looks broken. Delete .venv and try again.
    pause & exit /b 1
)

call "%VENV%\Scripts\activate.bat"

python -c "import PyQt5, stl, numpy" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo Dependency installation failed.
        pause & exit /b 1
    )
)

python "%~dp0main.py"
if errorlevel 1 pause
