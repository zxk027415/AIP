# @AI_GENERATED
# AIP 一键启动脚本（Windows PowerShell 5.1+）
#
# 用法：
#   .\aip.ps1 dev              # 开发模式（后端 8081 有 reload，前端 3001）
#   .\aip.ps1 experiment       # 实验模式（后端 8080 无 reload，前端 3001，worker）
#   .\aip.ps1 stop             # 停止所有 AIP 服务
#   .\aip.ps1 status           # 查看进程状态
#     netstat -ano | findstr :3001
#    Stop-Process -Id <PID> -Force
param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$BACKEND_DIR = Join-Path $ROOT "backend-service"
$FRONTEND_DIR = Join-Path $ROOT "frontend-sevice"

if ($env:AIP_CONDA_ENV) {
    $CONDA_ENV = $env:AIP_CONDA_ENV
} else {
    $CONDA_ENV = "cp_web"
}

# @AI_GENERATED: 光伏 mock 喂数源。
# 默认用「训练集未见过」的盲测源（设备 3Fh2D94S 16 支路 / 2021-11-18~11-24 / 无标签），
# 由 backend-service/scripts/build_pv_unseen_feed_source.py 产出。
# 原来的 pv_mock_feed_source.parquet 与累计训练集 100% 重叠，喂它只能演练链路、
# 无法评估模型效果（预测的都是训练已见过的样本）。
# 切回原喂数源：$env:AIP_PV_MOCK_PARQUET='datasets/pv_mock_feed_source.parquet'
# 路径相对 backend-service/ 解析。
if ($env:AIP_PV_MOCK_PARQUET) {
    $PV_MOCK_PARQUET = $env:AIP_PV_MOCK_PARQUET
} else {
    $PV_MOCK_PARQUET = "datasets/pv_mock_feed_unseen.parquet"
}
# @AI_GENERATED: end

function Start-Dev {
    if ($env:AIP_DEV_BACKEND_PORT) {
        $port = $env:AIP_DEV_BACKEND_PORT
    } else {
        $port = "8081"
    }
    if ($env:AIP_DEV_FRONTEND_PORT) {
        $fport = $env:AIP_DEV_FRONTEND_PORT
    } else {
        $fport = "3001"
    }

    Write-Host "AIP dev mode starting..."
    Write-Host "  Backend: :$port (reload)  Frontend: :$fport"
    Write-Host "  PV mock feed: $PV_MOCK_PARQUET"

    # @AI_GENERATED: 用 conda run 代替 conda activate，确保子进程能正确使用 conda 环境
    # 注意：Windows + conda run 会把带 * 的 --reload-exclude 通配符展开成文件列表，导致 uvicorn 启动失败。
    # 因此只用目录名排除（不要写 datasets/* / *.parquet）。
    $beCmd = "cd '$BACKEND_DIR'; " +
             "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
             "`$env:AUTORESEARCH_DB_READ='1'; " +
             "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
             "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
             "`$env:PV_MOCK_PARQUET_PATH='$PV_MOCK_PARQUET'; " +
             "conda run --no-capture-output -n $CONDA_ENV uvicorn main:app --host 0.0.0.0 --reload --port $port " +
             "--reload-exclude datasets --reload-exclude data --reload-exclude __pycache__ --reload-exclude .pytest_cache"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $beCmd
    # @AI_GENERATED: end

    $feCmd = "cd '$FRONTEND_DIR'; `$env:VITE_API_PROXY_TARGET='http://localhost:$port'; npm run dev -- --host 0.0.0.0 --port $fport"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $feCmd

    Write-Host ""
    Write-Host "Started:"
    Write-Host "   Backend  -> http://localhost:$port (reload)"
    Write-Host "   Frontend -> http://localhost:$fport"
    Write-Host "   API Proxy -> frontend:$fport -> backend:$port"
}

function Start-Experiment {
    if ($env:AIP_BACKEND_PORT) {
        $port = $env:AIP_BACKEND_PORT
    } else {
        $port = "8080"
    }
    if ($env:AIP_FRONTEND_PORT) {
        $fport = $env:AIP_FRONTEND_PORT
    } else {
        $fport = "3001"
    }

    Write-Host "AIP experiment mode starting..."
    Write-Host "  Backend: :$port  Frontend: :$fport  Worker: --loop"
    Write-Host "  PV mock feed: $PV_MOCK_PARQUET"

    # @AI_GENERATED: conda run 代替 conda activate
    $beCmd = "cd '$BACKEND_DIR'; " +
             "`$env:AUTORESEARCH_STORAGE_PROFILE='experiment'; " +
             "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
             "`$env:AUTORESEARCH_DB_READ='1'; " +
             "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
             "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
             "`$env:PV_MOCK_PARQUET_PATH='$PV_MOCK_PARQUET'; " +
             "conda run --no-capture-output -n $CONDA_ENV uvicorn main:app --host 0.0.0.0 --port $port"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $beCmd

    $feCmd = "cd '$FRONTEND_DIR'; `$env:VITE_API_PROXY_TARGET='http://localhost:$port'; npm run dev -- --host 0.0.0.0 --port $fport"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $feCmd

    $wkCmd = "cd '$BACKEND_DIR'; " +
             "`$env:AUTORESEARCH_STORAGE_PROFILE='experiment'; " +
             "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
             "`$env:AUTORESEARCH_DB_READ='1'; " +
             "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
             "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
             "conda run --no-capture-output -n $CONDA_ENV python worker_autoresearch.py --loop"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $wkCmd
    # @AI_GENERATED: end

    Write-Host ""
    Write-Host "Started:"
    Write-Host "   Backend  -> http://localhost:$port (no reload)"
    Write-Host "   Frontend -> http://localhost:$fport"
    Write-Host "   Worker   -> autoresearch loop"
    Write-Host ""
    Write-Host "Stop: close the PowerShell windows or run .\aip.ps1 stop"
}

function Stop-AIP {
    Write-Host "Stopping AIP processes..."
    Get-Process | Where-Object { $_.ProcessName -eq "python" -or $_.ProcessName -eq "node" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Done."
}

function Show-Status {
    Write-Host "AIP process status:"
    $py = Get-Process python -ErrorAction SilentlyContinue
    $nd = Get-Process node -ErrorAction SilentlyContinue
    if ($py) {
        Write-Host "  Python processes: $($py.Count)"
    } else {
        Write-Host "  Python processes: 0"
    }
    if ($nd) {
        Write-Host "  Node processes: $($nd.Count)"
    } else {
        Write-Host "  Node processes: 0"
    }
}

function Show-Usage {
    Write-Host "Usage: .\aip.ps1 <command>"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  dev              Dev mode (backend 8081 reload, frontend 3001)"
    Write-Host "  experiment       Experiment mode (backend 8080, frontend 3001, worker)"
    Write-Host "  stop             Stop all AIP services"
    Write-Host "  status           Show process status"
    Write-Host "  help             Show this help"
    Write-Host ""
    Write-Host "Env overrides:"
    Write-Host "  AIP_PV_MOCK_PARQUET   PV mock feed source (default: datasets/pv_mock_feed_unseen.parquet)"
    Write-Host "                        switch back: datasets/pv_mock_feed_source.parquet"
}

switch ($Command) {
    "dev"        { Start-Dev; break }
    "experiment" { Start-Experiment; break }
    "exp"        { Start-Experiment; break }
    "stop"       { Stop-AIP; break }
    "status"     { Show-Status; break }
    "help"       { Show-Usage; break }
    default      { Write-Host "Unknown command: $Command"; Show-Usage }
}
# @AI_GENERATED: end
