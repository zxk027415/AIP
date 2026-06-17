@echo off
REM @AI_GENERATED
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 启动前端开发服务器
echo ========================================
echo.

REM 将 Node.js 加入 PATH
set "PATH=C:\Program Files\nodejs;%APPDATA%\npm;%PATH%"

echo 检查 Node.js...
node --version
if %errorLevel% neq 0 (
    echo [错误] 找不到 Node.js
    pause
    exit /b 1
)

echo.
echo 前端开发服务器启动中...
echo URL: http://localhost:3001
echo.

npm run dev
REM @AI_GENERATED: end
