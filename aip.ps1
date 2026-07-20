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

    # @AI_GENERATED: 用 conda run 代替 conda activate，确保子进程能正确使用 conda 环境
    # 环境变量通过 PowerShell 在同一窗口设置后再调 conda run
    $beCmd = "cd '$BACKEND_DIR'; " +
             "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
             "`$env:AUTORESEARCH_DB_READ='1'; " +
             "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
             "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
             "conda run --no-capture-output -n $CONDA_ENV uvicorn main:app --host 0.0.0.0 --reload --port $port"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $beCmd
    # @AI_GENERATED: end

    $feCmd = "cd '$FRONTEND_DIR'; npm run dev -- --host 0.0.0.0 --port $fport"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $feCmd

    Write-Host ""
    Write-Host "Started:"
    Write-Host "   Backend  -> http://localhost:$port (reload)"
    Write-Host "   Frontend -> http://localhost:$fport"
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

    # @AI_GENERATED: conda run 代替 conda activate
    $beCmd = "cd '$BACKEND_DIR'; " +
             "`$env:AUTORESEARCH_STORAGE_PROFILE='experiment'; " +
             "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
             "`$env:AUTORESEARCH_DB_READ='1'; " +
             "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
             "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
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
