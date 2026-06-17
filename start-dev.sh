#!/usr/bin/env bash
# 一键启动前后端开发环境
# 用法：bash start-dev.sh
#
# 后端：conda activate aip_web → source load_glm_env.sh → uvicorn --reload --port 8081
# 前端：npm run dev，代理到 8081
# Worker：不自动启动；需要验证 AutoResearch 主循环时手动开 dev worker
#
# 注意：该脚本用于开发调试，不适合长时间 AutoResearch。
# 长实验请使用：bash start-experiment.sh
#
# 每个服务在独立的 Terminal 窗口中运行，方便查看各自日志。

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend-service"
FRONTEND_DIR="$PROJECT_DIR/frontend-sevice"
GLM_ENV_SCRIPT="$BACKEND_DIR/scripts/load_glm_env.sh"

echo "▶ 项目根目录: $PROJECT_DIR"
echo "▶ 后端目录:   $BACKEND_DIR"
echo "▶ 前端目录:   $FRONTEND_DIR"
echo "▶ 模式:       开发模式（后端启用 reload，不用于长任务）"
echo "▶ 存储:       backend-service/data/autoresearch_dev"
echo ""

# ── 后端 ──────────────────────────────────────────────────────────────────
echo "▶ 启动开发后端 8081（新 Terminal 窗口）..."
osascript <<EOF
tell application "Terminal"
  activate
  do script "
    echo '=== 后端启动：开发模式，有 reload ===' &&
	    cd '$BACKEND_DIR' &&
	    source \"\$(conda info --base)/etc/profile.d/conda.sh\" &&
	    conda activate aip_web &&
	    source '$GLM_ENV_SCRIPT' &&
	    AUTORESEARCH_STORAGE_PROFILE=dev uvicorn main:app --reload --port 8081
	  "
end tell
EOF

# ── 前端 ──────────────────────────────────────────────────────────────────
echo "▶ 启动前端 3001，代理到 8081（新 Terminal 窗口）..."
osascript <<EOF
tell application "Terminal"
  activate
  do script "
    echo '=== 前端启动：开发模式，API -> 8081 ===' &&
    cd '$FRONTEND_DIR' &&
    VITE_API_PROXY_TARGET='http://localhost:8081' npm run dev
  "
end tell
EOF

echo ""
echo "✅ 已在两个 Terminal 窗口中分别启动："
echo "   后端 → http://localhost:8081（有 reload）"
echo "   前端 → http://localhost:3001"
echo ""
echo "▶ 如需验证 dev AutoResearch，请手动开 worker："
echo "   cd backend-service && conda activate aip_web && source scripts/load_glm_env.sh && AUTORESEARCH_STORAGE_PROFILE=dev python worker_autoresearch.py --loop"
echo ""
echo "⚠ 长时间 AutoResearch 请使用：bash start-experiment.sh"
