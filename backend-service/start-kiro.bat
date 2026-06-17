@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 启动后端服务器
echo ========================================
echo.

REM 检查 conda 是否可用
where conda >nul 2>&1
if %errorLevel% neq 0 (
    echo [错误] 找不到 conda 命令
    echo.
    echo 请确保：
    echo 1. Anaconda/Miniconda 已安装
    echo 2. 已将 Anaconda 添加到系统 PATH
    echo 3. 或在 Anaconda Prompt 中运行此脚本
    echo.
    pause
    exit /b 1
)

REM 激活 aip_web 环境
echo 激活 aip_web 环境...
call conda activate aip_web
if %errorLevel% neq 0 (
    echo [错误] 无法激活 aip_web 环境
    echo 请先创建环境: conda create -n aip_web python=3.10 -y
    pause
    exit /b 1
)

echo.
echo 后端服务器启动中...
echo URL: http://localhost:8080
echo API 文档: http://localhost:8080/docs
echo.
echo 按 Ctrl+C 停止服务器
echo.

REM 启动服务器
uvicorn main:app --reload --port 8080
