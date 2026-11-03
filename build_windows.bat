@echo off
setlocal
cd /d "%~dp0"
py -m pip install -r windows_client\requirements.txt
py -m PyInstaller --noconfirm --clean --onefile --windowed --name RQAZ-DONATE windows_client\app.py
if errorlevel 1 exit /b 1
echo.
echo Готово: dist\RQAZ-DONATE.exe
pause
