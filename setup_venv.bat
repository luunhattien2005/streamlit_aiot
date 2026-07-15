@echo off
set "VENV_NAME=.venv"

if not exist "%VENV_NAME%\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv "%VENV_NAME%"
)

echo Activating environment...
call "%VENV_NAME%\Scripts\activate.bat"

echo Updating pip...
python -m pip install --upgrade pip

if exist requirements.txt (
    echo Installing requirements...
    pip install -r requirements.txt
) else (
    echo requirements.txt not found, skipping.
)

echo.
echo ====================================
echo Python version in active environment:
python --version
echo ====================================
echo.

echo Done!
pause