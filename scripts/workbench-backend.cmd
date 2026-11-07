@echo off
setlocal
cd /d "%~dp0.."
echo Agentverse integration backend: http://127.0.0.1:5050
".venv\Scripts\python.exe" -m devils_advocate.server --port 5050
