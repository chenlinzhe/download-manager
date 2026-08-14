@echo off
cd /d "%~dp0"
start "" http://127.0.0.1:8766
py server.py
pause
