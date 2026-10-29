@echo off
REM Build HamzziCapture.exe  (run after extracting the zip)
cd /d "%~dp0"

set PY=python
where py >nul 2>nul && set PY=py

echo [1/3] Installing packages...
%PY% -m pip install -r requirements.txt "pyinstaller>=6.0"
if errorlevel 1 goto fail

echo [2/3] Building exe...
%PY% -m PyInstaller --noconsole --onefile --name HamzziCapture --icon hamzzi.ico app.py
if errorlevel 1 goto fail

echo [3/3] SHA-256 of the exe (write this in your release notes):
certutil -hashfile dist\HamzziCapture.exe SHA256

echo.
echo Done: dist\HamzziCapture.exe
pause
exit /b 0

:fail
echo.
echo Build failed. Check that Python is installed and added to PATH.
pause
exit /b 1
