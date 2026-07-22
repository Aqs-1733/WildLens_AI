@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 同步依赖...
uv sync
if errorlevel 1 goto :error
echo [2/3] 升级数据库、清理预设图鉴并转码旧视频...
uv run python scripts\maintenance\upgrade_v3.py --transcode-all
if errorlevel 1 goto :error
echo [3/3] 运行测试...
uv run pytest -q
if errorlevel 1 goto :error
echo.
echo 升级完成。现在可启动 backend/main.py 和 frontend。
pause
exit /b 0
:error
echo.
echo 升级失败，请保留当前窗口中的完整错误信息。
pause
exit /b 1
