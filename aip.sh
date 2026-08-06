#!/usr/bin/env bash
# AIP 一键启动脚本（macOS / Linux）
#
# 用法：
#   bash aip.sh dev              # 开发模式，后台 nohup（服务器）
#   bash aip.sh dev -mac         # 开发模式，打开 Terminal 窗口（macOS）
#   bash aip.sh experiment       # 实验模式，后台 nohup（服务器）
#   bash aip.sh experiment -mac  # 实验模式，打开 Terminal 窗口（macOS）
#   bash aip.sh stop             # 停止所有 AIP 服务
#   bash aip.sh status           # 查看进程状态
#   bash aip.sh logs [service]   # 查看日志（仅后台模式）
#
# 自定义配置：在项目根目录创建 .aip.local.env，例如：
#   export AIP_CONDA_ENV=cp_web_forecast
#   export AIP_BACKEND_PORT=8080

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend-service"
FRONTEND_DIR="$ROOT/frontend-sevice"
GLM_ENV_SCRIPT="$BACKEND_DIR/scripts/load_glm_env.sh"
LOG_DIR="$ROOT/logs"
PID_DIR="$ROOT/.pids"

# 加载本地配置覆盖
if [ -f "$ROOT/.aip.local.env" ]; then
  source "$ROOT/.aip.local.env"
fi

CONDA_ENV="${AIP_CONDA_ENV:-cp_web}"

cmd="${1:-}"
# 检测 -mac 标志
USE_MAC=false
for arg in "$@"; do
  if [ "$arg" = "-mac" ]; then
    USE_MAC=true
  fi
done

# ── 工具函数 ──────────────────────────────────────────────────────────────

usage() {
  echo "用法: bash aip.sh <子命令> [-mac]"
  echo ""
  echo "子命令："
  echo "  dev              开发模式（后端 8081 有 reload，前端 3001）"
  echo "  experiment|exp   实验模式（后端 8080 无 reload，前端 3001，worker）"
  echo "  stop             停止所有 AIP 服务"
  echo "  status           查看各进程运行状态"
  echo "  logs [service]   查看后台日志（backend / frontend / worker / all）"
  echo "  -h|--help        显示此帮助"
  echo ""
  echo "选项："
  echo "  -mac             在 macOS Terminal 新窗口中启动（可看实时日志）"
  echo "                   不加则后台运行，日志写入 logs/ 目录"
  exit "${1:-0}"
}

# macOS: 在新 Terminal 窗口中执行命令
open_terminal() {
  local title="$1"
  local cmd_str="$2"
  # 转义双引号，防止打断 AppleScript 字符串
  cmd_str="${cmd_str//\"/\\\"}"
  osascript <<EOF
tell application "Terminal"
  activate
  do script "echo '=== $title ===' && $cmd_str"
end tell
EOF
}

# 后台模式: 初始化 conda 环境（在当前 shell）
init_conda() {
  local CONDA_BASE
  CONDA_BASE="$(conda info --base 2>/dev/null || echo '/opt/miniconda3')"
  source "$CONDA_BASE/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
  echo "  ✔ Conda 环境: $CONDA_ENV"
}

load_glm() {
  if [ -f "$GLM_ENV_SCRIPT" ]; then
    source "$GLM_ENV_SCRIPT"
    echo "  ✔ GLM 环境已加载"
  fi
}

# ── macOS Terminal 模式 ───────────────────────────────────────────────────

do_dev_mac() {
  local BACKEND_PORT="${AIP_DEV_BACKEND_PORT:-8081}"
  local FRONTEND_PORT="${AIP_DEV_FRONTEND_PORT:-3001}"

  echo "▶ AIP 开发模式启动（macOS Terminal）"
  echo "  后端: :$BACKEND_PORT (reload)  前端: :$FRONTEND_PORT"
  echo ""

  open_terminal "AIP 后端 - 开发模式 :$BACKEND_PORT" \
    "cd '$BACKEND_DIR' && source \"\$(conda info --base)/etc/profile.d/conda.sh\" && conda activate $CONDA_ENV && [ -f '$GLM_ENV_SCRIPT' ] && source '$GLM_ENV_SCRIPT'; AUTORESEARCH_STORAGE_PROFILE=dev uvicorn main:app --host 0.0.0.0 --reload --port $BACKEND_PORT"

  open_terminal "AIP 前端 - 开发模式 :$FRONTEND_PORT" \
    "cd '$FRONTEND_DIR' && VITE_API_PROXY_TARGET='http://localhost:$BACKEND_PORT' npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT"

  echo "✅ 已启动："
  echo "   后端 → http://localhost:$BACKEND_PORT（有 reload）"
  echo "   前端 → http://localhost:$FRONTEND_PORT"
  echo "   停止: 关闭 Terminal 窗口或 Ctrl+C"
}

do_experiment_mac() {
  local BACKEND_PORT="${AIP_BACKEND_PORT:-8080}"
  local FRONTEND_PORT="${AIP_FRONTEND_PORT:-3001}"

  echo "▶ AIP 实验模式启动（macOS Terminal）"
  echo "  后端: :$BACKEND_PORT  前端: :$FRONTEND_PORT  Worker: --loop"
  echo ""

  open_terminal "AIP 后端 - 实验模式 :$BACKEND_PORT" \
    "cd '$BACKEND_DIR' && source \"\$(conda info --base)/etc/profile.d/conda.sh\" && conda activate $CONDA_ENV && [ -f '$GLM_ENV_SCRIPT' ] && source '$GLM_ENV_SCRIPT'; AUTORESEARCH_STORAGE_PROFILE=experiment uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT"

  open_terminal "AIP 前端 - 实验模式 :$FRONTEND_PORT" \
    "cd '$FRONTEND_DIR' && VITE_API_PROXY_TARGET='http://localhost:$BACKEND_PORT' npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT"

  open_terminal "AIP Worker - AutoResearch" \
    "cd '$BACKEND_DIR' && source \"\$(conda info --base)/etc/profile.d/conda.sh\" && conda activate $CONDA_ENV && [ -f '$GLM_ENV_SCRIPT' ] && source '$GLM_ENV_SCRIPT'; AUTORESEARCH_STORAGE_PROFILE=experiment python worker_autoresearch.py --loop"

  echo "✅ 已启动："
  echo "   后端   → http://localhost:$BACKEND_PORT（无 reload）"
  echo "   前端   → http://localhost:$FRONTEND_PORT"
  echo "   Worker → 自动轮询 job queue"
  echo "   停止: 关闭 Terminal 窗口或 Ctrl+C"
}

# ── 后台 nohup 模式（服务器） ────────────────────────────────────────────

do_dev_bg() {
  local BACKEND_PORT="${AIP_DEV_BACKEND_PORT:-8081}"
  local FRONTEND_PORT="${AIP_DEV_FRONTEND_PORT:-3001}"

  mkdir -p "$LOG_DIR" "$PID_DIR"

  echo "▶ AIP 开发模式启动（后台）"
  echo "  后端: :$BACKEND_PORT (reload)  前端: :$FRONTEND_PORT"
  echo ""

  init_conda
  load_glm
  echo ""

  cd "$BACKEND_DIR"
  nohup env AUTORESEARCH_STORAGE_PROFILE=dev \
    uvicorn main:app --host 0.0.0.0 --reload --port "$BACKEND_PORT" \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$PID_DIR/backend.pid"
  echo "  后端 PID: $! | 日志: logs/backend.log"

  cd "$FRONTEND_DIR"
  nohup env VITE_API_PROXY_TARGET="http://localhost:$BACKEND_PORT" \
    npx vite --host 0.0.0.0 --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
  echo $! > "$PID_DIR/frontend.pid"
  echo "  前端 PID: $! | 日志: logs/frontend.log"

  echo ""
  echo "✅ 已启动（后台）："
  echo "   后端 → http://localhost:$BACKEND_PORT（有 reload）"
  echo "   前端 → http://localhost:$FRONTEND_PORT"
  echo "   日志: bash aip.sh logs backend"
  echo "   停止: bash aip.sh stop"
}

do_experiment_bg() {
  local BACKEND_PORT="${AIP_BACKEND_PORT:-8080}"
  local FRONTEND_PORT="${AIP_FRONTEND_PORT:-3001}"

  mkdir -p "$LOG_DIR" "$PID_DIR"

  echo "▶ AIP 实验模式启动（后台）"
  echo "  后端: :$BACKEND_PORT  前端: :$FRONTEND_PORT  Worker: --loop"
  echo ""

  init_conda
  load_glm
  echo ""

  cd "$BACKEND_DIR"
  nohup env AUTORESEARCH_STORAGE_PROFILE=experiment \
    uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$PID_DIR/backend.pid"
  echo "  后端 PID: $! | 日志: logs/backend.log"

  cd "$FRONTEND_DIR"
  nohup env VITE_API_PROXY_TARGET="http://localhost:$BACKEND_PORT" \
    npx vite --host 0.0.0.0 --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
  echo $! > "$PID_DIR/frontend.pid"
  echo "  前端 PID: $! | 日志: logs/frontend.log"

  cd "$BACKEND_DIR"
  nohup env AUTORESEARCH_STORAGE_PROFILE=experiment \
    python worker_autoresearch.py --loop \
    > "$LOG_DIR/worker.log" 2>&1 &
  echo $! > "$PID_DIR/worker.pid"
  echo "  Worker PID: $! | 日志: logs/worker.log"

  echo ""
  echo "✅ 已启动（后台）："
  echo "   后端   → http://localhost:$BACKEND_PORT（无 reload）"
  echo "   前端   → http://localhost:$FRONTEND_PORT"
  echo "   Worker → 自动轮询 job queue"
  echo "   日志: bash aip.sh logs backend"
  echo "   停止: bash aip.sh stop"
}

# ── 通用子命令 ────────────────────────────────────────────────────────────

do_stop() {
  echo "🛑 停止 AIP 相关进程..."

  # 先试 PID 文件
  if [ -d "$PID_DIR" ]; then
    for pidfile in "$PID_DIR"/*.pid; do
      [ -f "$pidfile" ] || continue
      local name pid
      name=$(basename "$pidfile" .pid)
      pid=$(cat "$pidfile")
      if kill -0 "$pid" 2>/dev/null; then
        echo "  停止 $name (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
      fi
      rm -f "$pidfile"
    done
  fi

  # 再 pgrep 兜底
  for pattern in "uvicorn main:app" "vite.*frontend-sevice" "npm run dev.*frontend-sevice" "worker_autoresearch.py"; do
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      echo "  停止: $pattern (PID: $pids)"
      echo "$pids" | xargs kill 2>/dev/null || true
    fi
  done

  # 等进程退出后清理 SQLite WAL 残留
  sleep 1
  local db_file="$BACKEND_DIR/data/autoresearch/jobs.sqlite"
  if [ -f "$db_file" ]; then
    rm -f "$db_file" "$db_file-journal" "$db_file-wal" "$db_file-shm" 2>/dev/null
    echo "  ✔ 清理 jobs.sqlite"
  fi

  echo ""
  echo "✅ 完成"
}

do_status() {
  echo "📊 AIP 进程状态："
  for pattern in "uvicorn main:app" "vite.*frontend-sevice" "worker_autoresearch"; do
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      echo "  ✅ $pattern 运行中 (PID: $pids)"
    else
      echo "  ⚪ $pattern 未运行"
    fi
  done
}

do_logs() {
  local service="${1:-backend}"
  if [ ! -d "$LOG_DIR" ]; then
    echo "❌ 日志目录不存在（仅后台模式产生日志）"
    exit 1
  fi
  case "$service" in
    backend|be)   exec tail -f "$LOG_DIR/backend.log" ;;
    frontend|fe)  exec tail -f "$LOG_DIR/frontend.log" ;;
    worker|w)     exec tail -f "$LOG_DIR/worker.log" ;;
    all)          exec tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log" "$LOG_DIR/worker.log" ;;
    *)            echo "未知服务: $service（可选: backend, frontend, worker, all）"; exit 1 ;;
  esac
}

# ── 主入口 ────────────────────────────────────────────────────────────────

case "$cmd" in
  dev)
    if [ "$USE_MAC" = true ]; then do_dev_mac; else do_dev_bg; fi
    ;;
  experiment|exp)
    if [ "$USE_MAC" = true ]; then do_experiment_mac; else do_experiment_bg; fi
    ;;
  stop)               do_stop ;;
  status|st)          do_status ;;
  logs)               shift; do_logs "$@" ;;
  -h|--help|help|"")  usage 0 ;;
  *)
    echo "未知子命令: $cmd"
    echo ""
    usage 1
    ;;
esac
