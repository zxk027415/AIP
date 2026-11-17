# @AI_GENERATED
# AIP 一键启动脚本（Windows PowerShell 5.1+）
#
# 用法：
#   .\aip.ps1 dev                # 开发模式：缺失服务才启动，健康服务直接复用
#   .\aip.ps1 restart-dev        # 只重启 AIP 的 8081/3001，加载最新代码
#   .\aip.ps1 experiment         # 实验模式（后端 8080、前端 3001、worker）
#   .\aip.ps1 restart-experiment # 清理 AIP 进程后重启实验栈
#   .\aip.ps1 stop               # 只停止 AIP 端口和 worker，不误杀其它 Python/Node
#   .\aip.ps1 status             # 查看 AIP 端口所有者和 worker
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

# @AI_GENERATED: AIP 进程/端口守卫。
# 目的：重复执行 dev 时不再启动第二套服务；stop 也只结束 AIP 自己的进程。
function Get-PortOwnerInfo {
    param([int]$Port)

    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        return $null
    }

    try {
        return Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)"
    } catch {
        return [PSCustomObject]@{
            ProcessId = $connection.OwningProcess
            Name = "unknown"
            CommandLine = ""
        }
    }
}

function Test-AipBackendProcess {
    param($ProcessInfo)
    if (-not $ProcessInfo) { return $false }
    $line = [string]$ProcessInfo.CommandLine
    return $line -match '(?i)(-m\s+uvicorn\s+main:app|uvicorn(?:\.exe)?"?\s+main:app)'
}

function Test-AipFrontendProcess {
    param($ProcessInfo)
    if (-not $ProcessInfo) { return $false }
    $line = [string]$ProcessInfo.CommandLine
    return ($line -match '(?i)vite(?:\.js)?') -and
        ($line -match ([regex]::Escape($FRONTEND_DIR)))
}

function Test-HttpReady {
    param([string]$Url)
    $previousProgressPreference = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    } finally {
        $ProgressPreference = $previousProgressPreference
    }
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-HttpReady -Url $Url) { return $true }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Stop-AipListener {
    param(
        [int]$Port,
        [ValidateSet('backend', 'frontend')]
        [string]$Kind
    )

    $owner = Get-PortOwnerInfo -Port $Port
    if (-not $owner) { return }

    $isAip = if ($Kind -eq 'backend') {
        Test-AipBackendProcess $owner
    } else {
        Test-AipFrontendProcess $owner
    }

    if (-not $isAip) {
        Write-Warning "Skip port ${Port}: PID $($owner.ProcessId) is not recognized as an AIP $Kind process."
        return
    }

    Stop-Process -Id $owner.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "  Stopped AIP $Kind on :$Port (PID $($owner.ProcessId))"
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

    # @AI_GENERATED: 先检查端口；识别到健康的 AIP 服务时复用，未知进程占用时明确报 PID。
    $backendOwner = Get-PortOwnerInfo -Port ([int]$port)
    $frontendOwner = Get-PortOwnerInfo -Port ([int]$fport)

    if ($backendOwner -and -not (Test-AipBackendProcess $backendOwner)) {
        Write-Host "Cannot start AIP backend: port $port is used by PID $($backendOwner.ProcessId)." -ForegroundColor Red
        Write-Host "Command: $($backendOwner.CommandLine)"
        return
    }
    if ($frontendOwner -and -not (Test-AipFrontendProcess $frontendOwner)) {
        Write-Host "Cannot start AIP frontend: port $fport is used by PID $($frontendOwner.ProcessId)." -ForegroundColor Red
        Write-Host "Command: $($frontendOwner.CommandLine)"
        return
    }
    if ($backendOwner -and -not (Test-HttpReady -Url "http://localhost:$port/api/health")) {
        Write-Host "AIP backend PID $($backendOwner.ProcessId) owns port $port but health check failed." -ForegroundColor Red
        Write-Host "Run '.\aip.ps1 restart-dev' to replace the stale process."
        return
    }
    if ($frontendOwner -and -not (Test-HttpReady -Url "http://localhost:$fport")) {
        Write-Host "AIP frontend PID $($frontendOwner.ProcessId) owns port $fport but HTTP check failed." -ForegroundColor Red
        Write-Host "Run '.\aip.ps1 restart-dev' to replace the stale process."
        return
    }

    if (-not $backendOwner) {
        # Windows + conda run 会把带 * 的 --reload-exclude 通配符展开成文件列表，
        # 因此这里只传目录名，不传 datasets/* 或 *.parquet。
        $beCmd = "Set-Location -LiteralPath '$BACKEND_DIR'; " +
                 "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
                 "`$env:AUTORESEARCH_DB_READ='1'; " +
                 "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
                 "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
                 "`$env:PV_MOCK_PARQUET_PATH='$PV_MOCK_PARQUET'; " +
                 "conda run --no-capture-output -n $CONDA_ENV uvicorn main:app --host 0.0.0.0 --reload --port $port " +
                 "--reload-exclude datasets --reload-exclude data --reload-exclude __pycache__ --reload-exclude .pytest_cache"
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $beCmd
        Write-Host "  Starting backend on :$port ..."
    } else {
        Write-Host "  Reusing healthy AIP backend on :$port (PID $($backendOwner.ProcessId))"
        if ([string]$backendOwner.CommandLine -notmatch '(?i)--reload') {
            Write-Warning "Existing backend was started without --reload. Use '.\aip.ps1 restart-dev' to load new Python code."
        }
    }

    if (-not $frontendOwner) {
        $feCmd = "Set-Location -LiteralPath '$FRONTEND_DIR'; `$env:VITE_API_PROXY_TARGET='http://localhost:$port'; npm run dev -- --host 0.0.0.0 --port $fport"
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $feCmd
        Write-Host "  Starting frontend on :$fport ..."
    } else {
        Write-Host "  Reusing healthy AIP frontend on :$fport (PID $($frontendOwner.ProcessId))"
    }

    $backendReady = Wait-HttpReady -Url "http://localhost:$port/api/health" -TimeoutSeconds 60
    $frontendReady = Wait-HttpReady -Url "http://localhost:$fport" -TimeoutSeconds 45

    Write-Host ""
    if ($backendReady -and $frontendReady) {
        Write-Host "AIP dev is ready:" -ForegroundColor Green
    } else {
        Write-Warning "AIP processes were launched/reused, but one health check timed out. Check the service PowerShell windows."
    }
    Write-Host "   Backend  -> http://localhost:$port (health=$backendReady)"
    Write-Host "   Frontend -> http://localhost:$fport (health=$frontendReady)"
    Write-Host "   API Proxy -> frontend:$fport -> backend:$port"
    # @AI_GENERATED: end
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

    # @AI_GENERATED: experiment 需要独占 8080/3001 和 worker，避免复用 dev 前端时代理仍指向 8081。
    $backendOwner = Get-PortOwnerInfo -Port ([int]$port)
    $frontendOwner = Get-PortOwnerInfo -Port ([int]$fport)
    $existingWorker = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -match '(?i)worker_autoresearch\.py\s+--loop' } |
        Select-Object -First 1

    if ($backendOwner -or $frontendOwner -or $existingWorker) {
        Write-Host "Experiment mode needs exclusive AIP ports/processes." -ForegroundColor Yellow
        if ($backendOwner) { Write-Host "  Backend port $port -> PID $($backendOwner.ProcessId)" }
        if ($frontendOwner) { Write-Host "  Frontend port $fport -> PID $($frontendOwner.ProcessId)" }
        if ($existingWorker) { Write-Host "  Worker -> PID $($existingWorker.ProcessId)" }
        Write-Host "Run '.\aip.ps1 restart-experiment' for a clean experiment stack."
        return
    }

    $beCmd = "Set-Location -LiteralPath '$BACKEND_DIR'; " +
             "`$env:AUTORESEARCH_STORAGE_PROFILE='experiment'; " +
             "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
             "`$env:AUTORESEARCH_DB_READ='1'; " +
             "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
             "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
             "`$env:PV_MOCK_PARQUET_PATH='$PV_MOCK_PARQUET'; " +
             "conda run --no-capture-output -n $CONDA_ENV uvicorn main:app --host 0.0.0.0 --port $port"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $beCmd

    $feCmd = "Set-Location -LiteralPath '$FRONTEND_DIR'; `$env:VITE_API_PROXY_TARGET='http://localhost:$port'; npm run dev -- --host 0.0.0.0 --port $fport"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $feCmd

    $wkCmd = "Set-Location -LiteralPath '$BACKEND_DIR'; " +
             "`$env:AUTORESEARCH_STORAGE_PROFILE='experiment'; " +
             "`$env:AUTORESEARCH_DB_DUAL_WRITE='1'; " +
             "`$env:AUTORESEARCH_DB_READ='1'; " +
             "`$env:AUTORESEARCH_JOB_QUEUE_BACKEND='mysql'; " +
             "`$env:AIP_SKIP_ALEMBIC_MIGRATION='1'; " +
             "conda run --no-capture-output -n $CONDA_ENV python worker_autoresearch.py --loop"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $wkCmd

    $backendReady = Wait-HttpReady -Url "http://localhost:$port/api/health" -TimeoutSeconds 60
    $frontendReady = Wait-HttpReady -Url "http://localhost:$fport" -TimeoutSeconds 45
    # @AI_GENERATED: end

    Write-Host ""
    if ($backendReady -and $frontendReady) {
        Write-Host "AIP experiment is ready:" -ForegroundColor Green
    } else {
        Write-Warning "Experiment processes started, but one health check timed out. Check the service PowerShell windows."
    }
    Write-Host "   Backend  -> http://localhost:$port (health=$backendReady)"
    Write-Host "   Frontend -> http://localhost:$fport (health=$frontendReady)"
    Write-Host "   Worker   -> autoresearch loop"
    Write-Host ""
    Write-Host "Stop: close the PowerShell windows or run .\aip.ps1 stop"
}

function Stop-AIP {
    Write-Host "Stopping AIP-owned processes only..."

    $backendPorts = @(8080, 8081)
    if ($env:AIP_BACKEND_PORT) { $backendPorts += [int]$env:AIP_BACKEND_PORT }
    if ($env:AIP_DEV_BACKEND_PORT) { $backendPorts += [int]$env:AIP_DEV_BACKEND_PORT }

    $frontendPorts = @(3001)
    if ($env:AIP_FRONTEND_PORT) { $frontendPorts += [int]$env:AIP_FRONTEND_PORT }
    if ($env:AIP_DEV_FRONTEND_PORT) { $frontendPorts += [int]$env:AIP_DEV_FRONTEND_PORT }

    $backendPorts | Sort-Object -Unique | ForEach-Object {
        Stop-AipListener -Port $_ -Kind 'backend'
    }
    $frontendPorts | Sort-Object -Unique | ForEach-Object {
        Stop-AipListener -Port $_ -Kind 'frontend'
    }

    $workers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -match '(?i)worker_autoresearch\.py\s+--loop' }
    foreach ($worker in $workers) {
        Stop-Process -Id $worker.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  Stopped AutoResearch worker (PID $($worker.ProcessId))"
    }
    Write-Host "Done. Non-AIP Python/Node processes were left untouched."
}

function Restart-Dev {
    Stop-AIP
    Start-Sleep -Seconds 2
    Start-Dev
}

function Restart-Experiment {
    Stop-AIP
    Start-Sleep -Seconds 2
    Start-Experiment
}

function Show-Status {
    Write-Host "AIP service status:"
    foreach ($item in @(
        @{ Port = 8081; Kind = 'dev backend' },
        @{ Port = 8080; Kind = 'experiment backend' },
        @{ Port = 3001; Kind = 'frontend' }
    )) {
        $owner = Get-PortOwnerInfo -Port $item.Port
        if ($owner) {
            Write-Host "  $($item.Kind) :$($item.Port) -> PID $($owner.ProcessId) [$($owner.Name)]"
        } else {
            Write-Host "  $($item.Kind) :$($item.Port) -> stopped"
        }
    }
    $workers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -match '(?i)worker_autoresearch\.py\s+--loop' }
    Write-Host "  AutoResearch workers -> $(@($workers).Count)"
}

function Show-Usage {
    Write-Host "Usage: .\aip.ps1 <command>"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  dev                Start missing dev services; reuse healthy AIP ports"
    Write-Host "  restart-dev        Safely restart AIP dev backend/frontend only"
    Write-Host "  experiment         Start experiment stack when AIP ports are free"
    Write-Host "  restart-experiment Safely restart backend/frontend/worker in experiment mode"
    Write-Host "  stop               Stop AIP-owned ports and worker only"
    Write-Host "  status             Show AIP port owners and worker count"
    Write-Host "  help               Show this help"
    Write-Host ""
    Write-Host "Env overrides:"
    Write-Host "  AIP_PV_MOCK_PARQUET   PV mock feed source (default: datasets/pv_mock_feed_unseen.parquet)"
    Write-Host "                        switch back: datasets/pv_mock_feed_source.parquet"
}

switch ($Command) {
    "dev"                { Start-Dev; break }
    "restart-dev"        { Restart-Dev; break }
    "experiment"         { Start-Experiment; break }
    "restart-experiment" { Restart-Experiment; break }
    "exp"                { Start-Experiment; break }
    "stop"               { Stop-AIP; break }
    "status"             { Show-Status; break }
    "help"               { Show-Usage; break }
    default               { Write-Host "Unknown command: $Command"; Show-Usage }
}
# @AI_GENERATED: end
