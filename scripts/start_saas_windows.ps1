param(
    [string]$EnvFile = ".env.windows-local",
    [switch]$WithScheduler,
    [int]$StartupTimeoutSeconds = 60
)
. (Join-Path $PSScriptRoot "saas_windows_common.ps1")
$null = Initialize-SaasWindowsEnvironment -EnvFile $EnvFile
$root = Get-SaasRepositoryRoot
$resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
$shell = (Get-Process -Id $PID).Path

function Start-SaasChild {
    param([Parameter(Mandatory = $true)][string]$ScriptName)
    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    $process = Start-Process -FilePath $shell -ArgumentList @("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $scriptPath), "-EnvFile", ('"{0}"' -f $resolvedEnvFile), "-SkipServiceChecks") -WorkingDirectory $root -PassThru
    return [pscustomobject]@{ ProcessId = $process.Id; StartTime = $process.StartTime }
}

function Stop-SaasChildren {
    param([object[]]$Children)
    foreach ($child in @($Children)) {
        if ($child) {
            Stop-SaasProcessTree -ProcessId $child.ProcessId -ExpectedStartTime $child.StartTime
        }
    }
}

function Test-SaasChildExited {
    param([Parameter(Mandatory = $true)]$Child)
    try { return (Get-Process -Id $Child.ProcessId -ErrorAction Stop).StartTime -ne $Child.StartTime } catch { return $true }
}

function Test-SaasHttpEndpoint {
    param([Parameter(Mandatory = $true)][string]$Uri)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    } catch { return $false }
}

$apiProcess = $null
$workerProcess = $null
$schedulerProcess = $null
$startupSucceeded = $false
try {
    $apiProcess = Start-SaasChild -ScriptName "start_saas_api_windows.ps1"
    $workerProcess = Start-SaasChild -ScriptName "start_saas_worker_windows.ps1"
    if ($WithScheduler) { $schedulerProcess = Start-SaasChild -ScriptName "start_saas_scheduler_windows.ps1" }

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $health = $false
    $ready = $false
    do {
        if ((Test-SaasChildExited -Child $apiProcess) -or (Test-SaasChildExited -Child $workerProcess) -or ($WithScheduler -and (Test-SaasChildExited -Child $schedulerProcess))) { break }
        $health = Test-SaasHttpEndpoint -Uri "http://127.0.0.1:8000/api/health"
        if ($health) { $ready = Test-SaasHttpEndpoint -Uri "http://127.0.0.1:8000/api/ready" }
        if ($health -and $ready) { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    $frontend = Test-SaasHttpEndpoint -Uri "http://127.0.0.1:8080/"
    $postgres = Test-SaasPostgresReachability
    $apiRunning = $health -and -not (Test-SaasChildExited -Child $apiProcess)
    $workerRunning = -not (Test-SaasChildExited -Child $workerProcess)
    $schedulerRunning = -not $WithScheduler -or ($schedulerProcess -and -not (Test-SaasChildExited -Child $schedulerProcess))
    $runtimeConfigured = ($env:SAAS_RUNTIME_HOST -eq "local") -and (Test-Path -LiteralPath $env:SAAS_CHROME_EXECUTABLE -PathType Leaf)

    Write-Host ("Frontend: {0} (http://127.0.0.1:8080)" -f $(if ($frontend) { "responding" } else { "not responding" }))
    Write-Host ("API: {0} (http://127.0.0.1:8000)" -f $(if ($apiRunning) { "healthy" } else { "not healthy" }))
    Write-Host ("Ready: {0}" -f $(if ($ready) { "ready" } else { "not ready" }))
    Write-Host ("PostgreSQL: {0}" -f $(if ($postgres) { "reachable" } else { "not reachable" }))
    Write-Host ("Worker: process {0}; authenticated status endpoint requires login" -f $(if ($workerRunning) { "running" } else { "exited" }))
    Write-Host ("Runtime: configuration {0}; authenticated capability endpoint requires login" -f $(if ($runtimeConfigured) { "valid" } else { "invalid" }))
    if ($WithScheduler) {
        Write-Host ("Scheduler: process {0}; authenticated status endpoint requires login" -f $(if ($schedulerRunning) { "running" } else { "exited" }))
    }

    if (-not $apiRunning -or -not $ready -or -not $postgres -or -not $workerRunning -or -not $schedulerRunning) {
        throw "SaaS child startup failed; stopped all child processes."
    }

    $startupSucceeded = $true
    # This launcher verifies startup and exits successfully. The API, worker, and optional scheduler remain running independently.
    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
} finally {
    if (-not $startupSucceeded) {
        Stop-SaasChildren -Children @($apiProcess, $workerProcess, $schedulerProcess)
    }
}
