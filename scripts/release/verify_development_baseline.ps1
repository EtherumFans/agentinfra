[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [string]$DotNet = "dotnet",
    [string]$Docker = "docker",
    [switch]$Full,
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Scratch = Join-Path ([System.IO.Path]::GetTempPath()) (
    "icoder-baseline-verify-" + [guid]::NewGuid().ToString("N")
)
New-Item -ItemType Directory -Path $Scratch | Out-Null

function Invoke-Checked {
    param(
        [Parameter(Mandatory)] [string]$Label,
        [Parameter(Mandatory)] [string]$Executable,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [Parameter(Mandatory)] [string]$WorkingDirectory
    )

    Write-Host "==> $Label"
    Push-Location $WorkingDirectory
    try {
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Label failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Assert-Command {
    param([Parameter(Mandatory)] [string]$Command)

    if ((Test-Path -LiteralPath $Command) -or (Get-Command $Command -ErrorAction SilentlyContinue)) {
        return
    }
    throw "Required command is unavailable: $Command"
}

try {
    Assert-Command $Python
    Assert-Command $Npm
    Assert-Command $DotNet
    if ($Full) {
        Assert-Command $Docker
    }

    $BaselineManifest = "reports/development-baseline/baseline-2026-08-31.json"
    Invoke-Checked "development baseline manifest" $Python @(
        "scripts/release/build_development_baseline.py",
        "--output", $BaselineManifest,
        "--verify", $BaselineManifest
    ) $RepoRoot

    $VenvRoot = Join-Path $RepoRoot "backend/.venv"
    $VenvPython = if ($IsWindows) {
        Join-Path $VenvRoot "Scripts/python.exe"
    }
    else {
        Join-Path $VenvRoot "bin/python"
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Invoke-Checked "create Python virtual environment" $Python @(
            "-m", "venv", $VenvRoot
        ) $RepoRoot
    }
    if (-not $SkipInstall) {
        Invoke-Checked "install backend dependencies" $VenvPython @(
            "-m", "pip", "install", "--disable-pip-version-check",
            "-r", "requirements.txt"
        ) (Join-Path $RepoRoot "backend")
        Invoke-Checked "install Python SDK build tool" $VenvPython @(
            "-m", "pip", "install", "--disable-pip-version-check", "build==1.6.0"
        ) $RepoRoot
    }

    Invoke-Checked "baseline governance tests" $VenvPython @(
        "-m", "pytest", "-q",
        "tests/test_development_baseline.py",
        "tests/test_release_candidate_validator.py"
    ) $RepoRoot
    Invoke-Checked "backend PR unit tests" $VenvPython @(
        "-m", "pytest", "tests", "-q",
        "--ignore=tests/integration",
        "--ignore=tests/e2e",
        "--ignore=tests/e2e_product",
        "--ignore=tests/regression",
        "-k", "not test_mcp_client_pubmed_search"
    ) (Join-Path $RepoRoot "backend")
    Invoke-Checked "fresh SQLite migration tests" $VenvPython @(
        "-m", "pytest", "-q",
        "tests/test_api/test_a1a_gate3r_5_migration_portability.py",
        "tests/unit/scripts/test_schema_drift.py"
    ) (Join-Path $RepoRoot "backend")
    Invoke-Checked "release version contract" $VenvPython @(
        "scripts/release/validate_release_candidate.py",
        "--output", (Join-Path $Scratch "version-manifest.json")
    ) $RepoRoot
    Invoke-Checked "OpenAPI drift check" $VenvPython @(
        "scripts/export_openapi.py", "--check"
    ) (Join-Path $RepoRoot "backend")
    Invoke-Checked "deployment preflight" $VenvPython @(
        "scripts/corti_parity/validate_deployment_candidate.py",
        "--output-dir", (Join-Path $Scratch "deployment")
    ) (Join-Path $RepoRoot "backend")

    $Frontend = Join-Path $RepoRoot "frontend"
    if (-not $SkipInstall) {
        Invoke-Checked "frontend npm ci" $Npm @("ci") $Frontend
    }
    Invoke-Checked "frontend dependency audit" $Npm @(
        "audit", "--audit-level=high"
    ) $Frontend
    Invoke-Checked "frontend typecheck" $Npm @(
        "exec", "--", "tsc", "--noEmit"
    ) $Frontend
    Invoke-Checked "frontend build" $Npm @(
        "exec", "--", "vite", "build"
    ) $Frontend

    $JsSdk = Join-Path $RepoRoot "packages/icoder-sdk"
    if (-not $SkipInstall) {
        Invoke-Checked "JavaScript SDK npm ci" $Npm @("ci") $JsSdk
    }
    Invoke-Checked "JavaScript SDK dependency audit" $Npm @(
        "audit", "--audit-level=high"
    ) $JsSdk
    Invoke-Checked "JavaScript SDK tests" $Npm @("test") $JsSdk

    $WebSdk = Join-Path $RepoRoot "packages/icoder-web"
    if (-not $SkipInstall) {
        Invoke-Checked "Web Components npm ci" $Npm @("ci") $WebSdk
    }
    Invoke-Checked "Web Components typecheck" $Npm @(
        "exec", "--", "tsc", "--noEmit"
    ) $WebSdk

    $PythonSdk = Join-Path $RepoRoot "packages/icoder-python"
    Invoke-Checked "Python SDK tests" $VenvPython @(
        "-m", "pytest", "-q"
    ) $PythonSdk
    Invoke-Checked "Python SDK wheel" $VenvPython @(
        "-m", "build", "--wheel",
        "--outdir", (Join-Path $Scratch "python-sdk")
    ) $PythonSdk

    $SdkList = (& $DotNet --list-sdks) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $SdkList -notmatch "(?m)^8\." -or $SdkList -notmatch "(?m)^10\.") {
        throw ".NET 8 and .NET 10 SDKs are both required"
    }
    $DotNetRoot = Join-Path $RepoRoot "packages/icoder-dotnet"
    Invoke-Checked ".NET SDK tests" $DotNet @(
        "test", "tests/Icoder.Sdk.Tests/Icoder.Sdk.Tests.csproj", "-c", "Release"
    ) $DotNetRoot
    Invoke-Checked ".NET netstandard2.0 consumer" $DotNet @(
        "build", "tests/Icoder.Sdk.NetStandard20Consumer/Icoder.Sdk.NetStandard20Consumer.csproj",
        "-c", "Release"
    ) $DotNetRoot
    Invoke-Checked ".NET net462 consumer" $DotNet @(
        "build", "tests/Icoder.Sdk.Net462Consumer/Icoder.Sdk.Net462Consumer.csproj",
        "-c", "Release"
    ) $DotNetRoot
    Invoke-Checked ".NET package" $DotNet @(
        "pack", "src/Icoder.Sdk/Icoder.Sdk.csproj", "-c", "Release",
        "-o", (Join-Path $Scratch "dotnet-sdk")
    ) $DotNetRoot

    if ($Full) {
        $Compose = Join-Path $RepoRoot "docker-compose.local-dev.yml"
        try {
            Invoke-Checked "start integration services" $Docker @(
                "compose", "-f", $Compose, "up", "-d", "db", "redis"
            ) $RepoRoot
            Invoke-Checked "PostgreSQL migrations" $Docker @(
                "compose", "-f", $Compose, "run", "--rm", "backend",
                "python", "-m", "alembic", "upgrade", "head"
            ) $RepoRoot
            foreach ($Suite in @("integration", "regression", "e2e", "e2e_product")) {
                Invoke-Checked "backend $Suite tests" $Docker @(
                    "compose", "-f", $Compose, "run", "--rm", "backend",
                    "python", "-m", "pytest", "tests/$Suite", "-v", "--tb=short"
                ) $RepoRoot
            }
        }
        finally {
            & $Docker compose -f $Compose down --remove-orphans
        }
    }

    Write-Host "DEVELOPMENT_BASELINE_SUPPORTED_VALIDATION_PASSED"
}
finally {
    if (Test-Path -LiteralPath $Scratch) {
        Remove-Item -LiteralPath $Scratch -Recurse -Force
    }
}
