Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

function Get-SaasRepositoryRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Import-SaasEnvironmentFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Environment file not found: $Path. Copy .env.windows-local.example to .env.windows-local and fill required values."
    }

    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $separator = $trimmed.IndexOf("=")
        if ($separator -lt 1) { throw "Invalid environment entry in $Path." }
        $name = $trimmed.Substring(0, $separator).Trim()
        if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw "Invalid environment entry in $Path." }

        $rawValue = $trimmed.Substring($separator + 1).Trim()
        if ($rawValue.StartsWith('"') -or $rawValue.StartsWith("'")) {
            $quote = $rawValue.Substring(0, 1)
            $closing = $rawValue.IndexOf($quote, 1)
            if ($closing -lt 0) { throw "Invalid environment entry in $Path." }
            $tail = $rawValue.Substring($closing + 1).Trim()
            if ($tail -and -not $tail.StartsWith("#")) { throw "Invalid environment entry in $Path." }
            $value = $rawValue.Substring(1, $closing - 1)
        } else {
            $comment = $rawValue.IndexOf("#")
            if ($comment -ge 0) { $rawValue = $rawValue.Substring(0, $comment) }
            $value = $rawValue.Trim()
        }

        if ([Environment]::GetEnvironmentVariable($name, 'Process') -eq $null) {
            Set-Item -Path ("Env:{0}" -f $name) -Value $value
        }
    }
}

function Resolve-SaasPython {
    foreach ($candidate in @("py", "python")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            & $candidate --version *> $null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    throw "Python was not found. Install Python and ensure py.exe or python.exe is on PATH."
}

function Assert-SaasChromeExecutable {
    if (-not (Test-Path -LiteralPath $env:SAAS_CHROME_EXECUTABLE -PathType Leaf)) {
        throw "SAAS_CHROME_EXECUTABLE does not identify the exact Chrome executable path."
    }
    $item = Get-Item -LiteralPath $env:SAAS_CHROME_EXECUTABLE
    if ($item.Extension -ne ".exe" -or $item.VersionInfo.FileDescription -notmatch "Chrome") {
        throw "SAAS_CHROME_EXECUTABLE must identify the Chrome executable."
    }
}

function Assert-SaasRequiredEnvironment {
    $required = @(
        "SAAS_ENV",
        "SAAS_DEPLOYMENT_MODE",
        "SAAS_RUNTIME_HOST",
        "DATABASE_URL",
        "SESSION_SECRET",
        "SAAS_ALLOWED_ORIGINS",
        "SAAS_CHROME_EXECUTABLE",
        "SAAS_BROWSER_PROFILE_ROOT"
    )
    foreach ($name in $required) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ([string]::IsNullOrWhiteSpace($value)) { throw "$name is required." }
    }
    if ($env:SAAS_ENV -ne "production") { throw "SAAS_ENV must be production for the Windows-local launcher." }
    if ($env:SAAS_DEPLOYMENT_MODE -ne "windows-local") { throw "SAAS_DEPLOYMENT_MODE must be windows-local." }
    if ($env:SAAS_RUNTIME_HOST -ne "local") { throw "SAAS_RUNTIME_HOST must be local." }
    if ($env:SESSION_SECRET.Length -lt 32) { throw "SESSION_SECRET must contain at least 32 characters." }
    Assert-SaasChromeExecutable
}

function Get-SaasDatabaseTarget {
    try { $uri = [Uri]$env:DATABASE_URL } catch { throw "DATABASE_URL must be a valid PostgreSQL connection URL with a host and database name." }
    if ($uri.Scheme -notin @("postgresql", "postgresql+psycopg") -or [string]::IsNullOrWhiteSpace($uri.Host) -or [string]::IsNullOrWhiteSpace($uri.AbsolutePath.Trim('/'))) {
        throw "DATABASE_URL must use postgresql or postgresql+psycopg and include a host and database name."
    }
    $explicitPort = [regex]::Match($env:DATABASE_URL, '^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/?#]*@)?(?:\[[^\]]+\]|[^:/?#]+):([0-9]+)(?:[/?#]|$)')
    if ($explicitPort.Success) {
        $port = [Int64]$explicitPort.Groups[1].Value
        if ($port -lt 1 -or $port -gt 65535) { throw "DATABASE_URL must specify a port between 1 and 65535." }
    } else {
        $port = 5432
    }
    return @{ Host = $uri.Host; Port = $port }
}

function Test-SaasPostgresReachability {
    $target = Get-SaasDatabaseTarget
    $result = Test-NetConnection -ComputerName $target.Host -Port $target.Port -WarningAction SilentlyContinue
    return [bool]$result.TcpTestSucceeded
}

function Assert-SaasPostgresReachability {
    if (-not (Test-SaasPostgresReachability)) { throw "PostgreSQL is not reachable at the configured DATABASE_URL host and port. Verify the database service and network access." }
}

function Stop-SaasProcessTree {
    param(
        [Parameter(ParameterSetName = "ByProcess", Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(ParameterSetName = "ByIdentity", Mandatory = $true)][int]$ProcessId,
        [Parameter(ParameterSetName = "ByIdentity", Mandatory = $true)][datetime]$ExpectedStartTime
    )

    if ($Process) {
        $ProcessId = $Process.Id
        $ExpectedStartTime = $Process.StartTime
    }

    try { $current = Get-Process -Id $ProcessId -ErrorAction Stop } catch { return }
    if ($current.StartTime -ne $ExpectedStartTime) { return }

    $taskkill = Get-Command taskkill -ErrorAction SilentlyContinue
    if ($taskkill) {
        & taskkill /PID $ProcessId /T /F *> $null
        if ($LASTEXITCODE -eq 0) { return }
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function ConvertFrom-SaasAlembicOutput {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Output)

    $revisions = @()
    foreach ($line in ($Output -split "`r?`n")) {
        if ($line -match '^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*(?:\([^\r\n]*\))?\s*$') { $revisions += $Matches[1] }
    }
    return @($revisions | Sort-Object -Unique)
}

function Test-SaasRevisionSetsEqual {
    param([string[]]$Expected, [string[]]$Actual)

    $expectedSet = @($Expected | Sort-Object -Unique)
    $actualSet = @($Actual | Sort-Object -Unique)
    if ($expectedSet.Count -ne $actualSet.Count) { return $false }
    for ($index = 0; $index -lt $expectedSet.Count; $index++) {
        if ($expectedSet[$index] -ne $actualSet[$index]) { return $false }
    }
    return $true
}

function Assert-SaasAlembicRevisionSets {
    param(
        [Parameter(Mandatory = $true)][string]$HeadsOutput,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$CurrentOutput
    )

    $headRevisions = @(ConvertFrom-SaasAlembicOutput -Output $HeadsOutput)
    if ($headRevisions.Count -eq 0) { throw "No Alembic head revision was found." }
    $currentRevisions = @(ConvertFrom-SaasAlembicOutput -Output $CurrentOutput)
    if ($currentRevisions.Count -eq 0) { throw "Unable to read the current Alembic revision." }
    if (-not (Test-SaasRevisionSetsEqual -Expected $headRevisions -Actual $currentRevisions)) {
        throw "Database schema is not at the current Alembic revision. Run migrations first."
    }
}

function Assert-SaasAlembicCurrent {
    param([Parameter(Mandatory = $true)][string]$Python)

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $heads = (& $Python -m alembic heads 2>&1 | Out-String).Trim()
        $headsExitCode = $LASTEXITCODE
        $current = (& $Python -m alembic current 2>&1 | Out-String).Trim()
        $currentExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($headsExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($heads)) { throw "Unable to read the Alembic head revision." }
    if ($currentExitCode -ne 0) { throw "Unable to read the current Alembic revision." }
    Assert-SaasAlembicRevisionSets -HeadsOutput $heads -CurrentOutput $current
}

function Initialize-SaasWindowsEnvironment {
    param(
        [string]$EnvFile = ".env.windows-local",
        [switch]$SkipServiceChecks
    )

    $root = Get-SaasRepositoryRoot
    Set-Location -LiteralPath $root
    $resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $root $EnvFile }
    Import-SaasEnvironmentFile -Path $resolvedEnvFile
    Assert-SaasRequiredEnvironment
    $python = Resolve-SaasPython
    if (-not $SkipServiceChecks) {
        Assert-SaasPostgresReachability
        Assert-SaasAlembicCurrent -Python $python
    }
    return $python
}
