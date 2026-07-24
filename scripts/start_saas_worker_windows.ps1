param(
    [string]$EnvFile = ".env.windows-local",
    [switch]$SkipServiceChecks
)
. (Join-Path $PSScriptRoot "saas_windows_common.ps1")
$python = Initialize-SaasWindowsEnvironment -EnvFile $EnvFile -SkipServiceChecks:$SkipServiceChecks
& $python "scripts/saas_worker.py"
exit $LASTEXITCODE
