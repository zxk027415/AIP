#!/usr/bin/env bash
# 一键启动长实验环境
# 用法：bash start-experiment.sh
#
# 后端：禁用 --reload，固定 8080，适合长时间 AutoResearch。
# 前端：固定代理到 8080。

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend-service"
FRONTEND_DIR="$PROJECT_DIR/frontend-sevice"
GLM_ENV_SCRIPT="$BACKEND_DIR/scripts/load_glm_env.sh"

echo "▶ 项目根目录: $PROJECT_DIR"
echo "▶ 后端目录:   $BACKEND_DIR"
echo "▶ 前端目录:   $FRONTEND_DIR"
echo "▶ 模式:       实验模式（后端禁用 reload，适合长任务）"
echo "▶ 存储:       backend-service/data/autoresearch"
echo ""

echo "▶ 启动实验后端 8080（新 Terminal 窗口）..."
osascript <<EOF
tell application "Terminal"
  activate
  do script "
    echo '=== 后端启动：实验模式，无 reload ===' &&
    cd '$BACKEND_DIR' &&
    source \"\$(conda info --base)/etc/profile.d/conda.sh\" &&
    conda activate cp_web &&
    source '$GLM_ENV_SCRIPT' &&
    AUTORESEARCH_STORAGE_PROFILE=experiment uvicorn main:app --port 8080
  "
end tell
EOF

echo "▶ 启动前端 3001，代理到 8080（新 Terminal 窗口）..."
osascript <<EOF
tell application "Terminal"
  activate
  do script "
    echo '=== 前端启动：实验模式，API -> 8080 ===' &&
    cd '$FRONTEND_DIR' &&
    VITE_API_PROXY_TARGET='http://localhost:8080' npm run dev
  "
end tell
EOF

echo "▶ 启动 AutoResearch Worker（新 Terminal 窗口）..."
osascript <<EOF
tell application "Terminal"
  activate
  do script "
    echo '=== AutoResearch Worker 启动 ===' &&
    cd '$BACKEND_DIR' &&
    source \"\$(conda info --base)/etc/profile.d/conda.sh\" &&
    conda activate cp_web &&
    source '$GLM_ENV_SCRIPT' &&
    AUTORESEARCH_STORAGE_PROFILE=experiment python worker_autoresearch.py --loop
  "
end tell
EOF

echo ""
echo "✅ 实验环境已启动："
echo "   后端   → http://localhost:8080（无 reload）"
echo "   前端   → http://localhost:3001"
echo "   Worker → 自动轮询 job queue（后端重启不影响）"
