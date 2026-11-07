@echo off
setlocal
cd /d "%~dp0..\frontend"
echo Agentverse Next.js frontend: http://127.0.0.1:3000
call npm.cmd run dev
