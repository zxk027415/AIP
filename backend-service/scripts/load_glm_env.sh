#!/usr/bin/env bash
# NOTE:
# This file is usually "sourced" in an interactive shell (bash/zsh).
# Do NOT use `set -u` / `set -e` here; they would leak into the current shell
# and can break prompts or other scripts.

# Usage:
#   source ./scripts/load_glm_env.sh
#   source ./scripts/load_glm_env.sh "your_api_key"
#   GLM_API_KEY="your_api_key" source ./scripts/load_glm_env.sh
#
# Windows PowerShell（没有 source 命令）请用：
#   cd backend-service
#   .\scripts\load_glm_env.ps1
#   .\scripts\load_glm_env.ps1 -ApiKey "your_api_key"
# 或已安装 Git Bash 时：
#   bash -lc "source backend-service/scripts/load_glm_env.sh"
#
# Then start backend in the SAME terminal:
#   python run.py --reload
#
# Notes:
# - Do NOT commit real API keys into git.
# - Prefer setting GLM_API_KEY in your shell profile or pass it temporarily:
#     export GLM_API_KEY="..."
#
# 优先级：命令行参数 $1 > 当前环境里的 GLM_API_KEY > .env.local
# 不要把真实 key 写进这个脚本；服务器部署用 EnvironmentFile 或 backend-service/.env.local。

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
elif [[ -n "${ZSH_VERSION-}" ]]; then
  # In zsh, ${(%):-%x} expands to the current script path when sourced.
  SCRIPT_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"
else
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

ENV_LOCAL_FILE="$(cd "$SCRIPT_DIR/.." && pwd)/.env.local"
if [[ -f "$ENV_LOCAL_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_LOCAL_FILE"
  set +a
fi

if [[ -n "${1:-}" ]]; then
  export GLM_API_KEY="$1"
fi

export GLM_ENABLE="${GLM_ENABLE:-true}"
export GLM_RESEARCH_QUESTIONS_ENABLE="${GLM_RESEARCH_QUESTIONS_ENABLE:-true}"
export GLM_BASE_URL="${GLM_BASE_URL:-https://open.bigmodel.cn/api/coding/paas/v4}"
export GLM_MODEL="${GLM_MODEL:-glm-5.1}"
export GLM_TIMEOUT_S="${GLM_TIMEOUT_S:-120}"

if [[ -z "${GLM_API_KEY:-}" ]]; then
  echo "[load_glm_env] GLM_API_KEY is NOT set."
  echo "[load_glm_env] Use .env.local, EnvironmentFile, or: export GLM_API_KEY=\"...\""
else
  echo "[load_glm_env] GLM_API_KEY is set (hidden)."
fi



echo "[load_glm_env] Loaded:"
echo "  GLM_ENABLE=$GLM_ENABLE"
echo "  GLM_RESEARCH_QUESTIONS_ENABLE=$GLM_RESEARCH_QUESTIONS_ENABLE"
echo "  GLM_BASE_URL=$GLM_BASE_URL"
echo "  GLM_MODEL=$GLM_MODEL"
echo "  GLM_TIMEOUT_S=$GLM_TIMEOUT_S"
