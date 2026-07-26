@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul || (echo [ERROR] uv is not installed.& pause & exit /b 1)
where npm >nul 2>nul || (echo [ERROR] Node.js/npm is not installed.& pause & exit /b 1)
start "WildLens API" cmd /k "cd /d %~dp0 && uv sync && uv run python backend/main.py"
start "WildLens Web" cmd /k "cd /d %~dp0frontend && npm install && npm run dev"
echo Backend: http://127.0.0.1:8010/docs
echo Frontend: http://127.0.0.1:5174
endlocal
