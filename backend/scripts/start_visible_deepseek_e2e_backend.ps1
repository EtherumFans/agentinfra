[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($env:ICODER_CREDENTIAL_LLM)) {
    throw 'ICODER_CREDENTIAL_LLM is not set in this PowerShell process. Set it in this same visible window before starting the backend.'
}

if ([string]::IsNullOrWhiteSpace($env:ICODER_SECRET_KEY)) {
    throw 'ICODER_SECRET_KEY is not set. Generate a temporary test attestation key before opening the runner PowerShell and starting this backend.'
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $owners = @($existing | Select-Object -ExpandProperty OwningProcess -Unique)
    throw "Port $Port is already listening (PID: $($owners -join ', ')). Stop that process before this controlled test."
}

$python = Get-Command python -ErrorAction Stop
$backendRoot = Split-Path -Parent $PSScriptRoot
$previousTitle = $Host.UI.RawUI.WindowTitle

# This launcher is intentionally specific to the one approved, synthetic
# DeepSeek regression. It keeps the credential process-local, prevents an
# additional live-canary call, and avoids the Windows native ML stack that has
# previously caused access violations on this host.
$env:LLM_PROVIDER = 'deepseek'
$env:ICODER_ALLOW_EXTERNAL_LLM = 'true'
$env:ICODER_REGION = 'cn'
$env:ICODER_EGRESS_POLICY = 'strict'
$env:ICODER_DISABLE_NATIVE_MEDCODER = 'true'
$env:ICODER_ENABLE_LOCAL_STT = 'false'
$env:ICODER_MODEL_LIVE_CANARY_ENABLED = 'false'
$env:ICODER_DEPLOYMENT_MODE = 'local'
$env:APP_ENV = 'local'
$Host.UI.RawUI.WindowTitle = 'iCoDer Backend - controlled DeepSeek E2E'

Push-Location $backendRoot
try {
    Write-Host "Starting controlled iCoDer backend on http://127.0.0.1:$Port"
    Write-Host 'The credential value will not be printed. Keep this window open during the single synthetic regression.'
    & $python.Source -m uvicorn app.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "uvicorn exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    $Host.UI.RawUI.WindowTitle = $previousTitle
}
