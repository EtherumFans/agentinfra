[CmdletBinding()]
param(
    [string]$BackendPython,
    [string]$BackendScript,
    [string]$FrontendDirectory,
    [string]$WorkingDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..')),
    [string]$LogDirectory,
    [ValidateRange(1024,65535)][int]$BackendPort = 18000,
    [ValidateRange(1024,65535)][int]$FrontendPort = 13000,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
if ($BackendPort -eq $FrontendPort) { throw 'Frontend and backend must use different ports.' }
$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"
if (-not $LogDirectory) { $LogDirectory = Join-Path $WorkingDirectory '.data/local-service-logs' }

function Test-Port([int]$Port) {
    $client = [Net.Sockets.TcpClient]::new()
    try { $client.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}
function Wait-Ready([string]$Url, [string]$Label, [int]$Seconds = 40) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        try {
            $response = Invoke-RestMethod "$Url/api/health/ready" -TimeoutSec 4
            if ($response.schema -eq 'icoder.readiness/v1' -and $response.ready -eq $true) { return }
        } catch { }
        if ([DateTime]::UtcNow -ge $deadline) { break }
        Start-Sleep -Milliseconds 500
    } while ($true)
    throw "$Label is not ready. Check service logs and database connectivity. URL: $Url/api/health/ready"
}

if (-not $CheckOnly) {
    # Validate dependencies before starting either service. Never install or migrate here.
    if (-not $BackendPython -or -not (Test-Path -LiteralPath $BackendPython -PathType Leaf)) { throw 'Provide an existing BackendPython executable.' }
    if (-not $BackendScript -or -not (Test-Path -LiteralPath $BackendScript -PathType Leaf)) { throw 'Provide an existing BackendScript; it must bind the requested loopback port.' }
    if (-not $FrontendDirectory -or -not (Test-Path -LiteralPath (Join-Path $FrontendDirectory 'node_modules/vite/bin/vite.js'))) { throw 'Frontend Vite dependencies are missing.' }
    $nodePath = (Get-Command node.exe -ErrorAction Stop).Source
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    $env:VITE_API_TARGET = $backendUrl
    if (-not (Test-Port $BackendPort)) {
        Start-Process -FilePath $BackendPython -ArgumentList ('"'+$BackendScript+'"') -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDirectory 'backend.out.log') -RedirectStandardError (Join-Path $LogDirectory 'backend.err.log') | Out-Null
    }
}
Wait-Ready $backendUrl 'Backend' $(if ($CheckOnly) { 0 } else { 40 })
if (-not $CheckOnly -and -not (Test-Port $FrontendPort)) {
    Start-Process -FilePath $nodePath -ArgumentList 'node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',"$FrontendPort",'--strictPort' -WorkingDirectory $FrontendDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDirectory 'frontend.out.log') -RedirectStandardError (Join-Path $LogDirectory 'frontend.err.log') | Out-Null
}
Wait-Ready $frontendUrl 'Frontend API proxy' $(if ($CheckOnly) { 0 } else { 40 })
$login = Invoke-WebRequest "$frontendUrl/login" -TimeoutSec 5
if ($login.StatusCode -ne 200 -or $login.Content -notmatch '(?i)<html') { throw 'Login page did not return HTML.' }
Write-Output "Ready: $frontendUrl/login (backend database check and frontend API proxy passed)."
