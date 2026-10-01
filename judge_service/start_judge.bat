@echo off
cd /d "%~dp0"
echo Starting SQL Judge Service...

REM 用 docker compose 创建并启动判题数据库容器（跨请求复用）
docker compose up -d
if errorlevel 1 (
    echo [ERROR] Failed to start judge database container via docker compose.
    pause
    exit /b 1
)

python judge_service_new.py
pause
