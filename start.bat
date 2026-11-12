@echo off
chcp 65001 >nul
title MLogger
cd /d "%~dp0"

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 (
    py -3 start.py %*
    goto done
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 (
    python start.py %*
    goto done
)

echo.
echo   Python 3.9 or newer was not found.
echo.
echo   1. Download the installer: https://www.python.org/downloads/
echo   2. During setup tick "Add python.exe to PATH".
echo   3. Run start.bat again.
echo.
echo   Не найден Python 3.9 или новее.
echo.
echo   1. Скачайте установщик: https://www.python.org/downloads/
echo   2. При установке отметьте галочку "Add python.exe to PATH".
echo   3. Запустите start.bat ещё раз.
echo.

:done
if errorlevel 1 pause
