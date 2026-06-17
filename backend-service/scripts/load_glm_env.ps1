# PowerShell 版 GLM 环境变量加载（用法对齐 load_glm_env.sh）
#
#   cd backend-service
#   .\scripts\load_glm_env.ps1
#   .\scripts\load_glm_env.ps1 -ApiKey "your_key"
#
# 或在当前会话手动设置（仅此终端生效）：
#   $env:GLM_API_KEY = "..."
#
# 注意：不要用 bash 的 `source`，PowerShell 里没有该命令。

param(
    [string]$ApiKey = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Resolve-Path (Join-Path $ScriptDir "..")
$EnvLocal = Join-Path $BackendRoot ".env.local"

if (Test-Path $EnvLocal) {
    Get-Content $EnvLocal -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $name = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $val, "Process")
    }
}

if ($ApiKey) {
    $env:GLM_API_KEY = $ApiKey
}

# 可选：与 .sh 一样在此处填默认 key（请勿提交真实密钥到公开仓库）
# $env:GLM_API_KEY = "paste_here_if_needed"

if (-not $env:GLM_API_KEY) {
    Write-Host "[load_glm_env] GLM_API_KEY is NOT set." -ForegroundColor Yellow
    Write-Host "[load_glm_env] Use .env.local, -ApiKey, or `$env:GLM_API_KEY = '...'"
} else {
    Write-Host "[load_glm_env] GLM_API_KEY is set (hidden)."
}

if (-not $env:GLM_ENABLE) { $env:GLM_ENABLE = "true" }
if (-not $env:GLM_RESEARCH_QUESTIONS_ENABLE) { $env:GLM_RESEARCH_QUESTIONS_ENABLE = "true" }
if (-not $env:GLM_BASE_URL) { $env:GLM_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4" }
if (-not $env:GLM_MODEL) { $env:GLM_MODEL = "glm-5.1" }
if (-not $env:GLM_TIMEOUT_S) { $env:GLM_TIMEOUT_S = "120" }

Write-Host "[load_glm_env] Loaded:"
Write-Host "  GLM_ENABLE=$env:GLM_ENABLE"
Write-Host "  GLM_RESEARCH_QUESTIONS_ENABLE=$env:GLM_RESEARCH_QUESTIONS_ENABLE"
Write-Host "  GLM_BASE_URL=$env:GLM_BASE_URL"
Write-Host "  GLM_MODEL=$env:GLM_MODEL"
Write-Host "  GLM_TIMEOUT_S=$env:GLM_TIMEOUT_S"
