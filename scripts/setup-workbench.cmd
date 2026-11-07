@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r devils_advocate/requirements.txt -r backend/requirements.txt
if errorlevel 1 exit /b 1
cd frontend
call npm.cmd ci
if errorlevel 1 exit /b 1
echo Setup complete. Run workbench-backend.cmd and workbench-frontend.cmd in two terminals.
