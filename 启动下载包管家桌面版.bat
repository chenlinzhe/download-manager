@echo off
cd /d "%~dp0"
rem Launch with pythonw so no black console window stays on screen.
where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw.exe "%~dp0desktop.py"
  exit /b
)
where pyw.exe >nul 2>nul
if %errorlevel%==0 (
  start "" pyw.exe -3 "%~dp0desktop.py"
  exit /b
)
echo pythonw.exe not found, falling back to python.exe (a console window will appear)
start "" python.exe "%~dp0desktop.py"
