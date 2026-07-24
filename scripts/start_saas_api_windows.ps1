param(
    [string]$EnvFile = ".env.windows-local",
    [switch]$SkipServiceChecks
)
. (Join-Path $PSScriptRoot "saas_windows_common.ps1")
$python = Initialize-SaasWindowsEnvironment -EnvFile $EnvFile -SkipServiceChecks:$SkipServiceChecks
& $python -m uvicorn "src.facebook_leads.saas.api:app" --host "0.0.0.0" --port "8000" --workers "1"
exit $LASTEXITCODE
