@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>nul || (echo [ERROR] Docker Desktop is not installed or not running.& pause & exit /b 1)
docker compose up --build -d
if errorlevel 1 (echo [ERROR] Docker startup failed.& pause & exit /b 1)
echo Frontend: http://127.0.0.1:5174
echo API docs: http://127.0.0.1:8010/docs
docker compose ps
pause
endlocal
