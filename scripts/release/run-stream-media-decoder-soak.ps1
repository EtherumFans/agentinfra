[CmdletBinding()]
param(
    [string]$PythonPath = "python",
    [ValidateRange(10, 500)]
    [int]$Cases = 100,
    [string]$OutputPath = "reports/sdk_stream_media_soak_phase_20260824/decoder_soak_evidence.json"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$backendRoot = Join-Path $repositoryRoot "backend"
$resolvedOutput = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $OutputPath))
$environmentNames = @(
    "ICODER_CREDENTIAL_LLM", "DEEPSEEK_API_KEY",
    "ICODER_STREAM_MEDIA_VALIDATION_MODE", "ICODER_STREAM_MEDIA_DECODER_PATH",
    "ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS",
    "ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY",
    "ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS"
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    Remove-Item Env:ICODER_CREDENTIAL_LLM -ErrorAction SilentlyContinue
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    $ffmpegPath = (& $PythonPath -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($ffmpegPath) -or -not (Test-Path -LiteralPath $ffmpegPath)) {
        throw "Bundled ffmpeg executable was not found."
    }

    Push-Location $backendRoot
    try {
        & $PythonPath scripts/stream_media_decoder_soak.py `
            --ffmpeg $ffmpegPath `
            --cases $Cases `
            --output $resolvedOutput
        if ($LASTEXITCODE -ne 0) { throw "Streams media decoder soak failed." }
    }
    finally { Pop-Location }

    $remaining = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ExecutablePath -and
                [System.IO.Path]::GetFullPath($_.ExecutablePath).Equals(
                    [System.IO.Path]::GetFullPath($ffmpegPath),
                    [System.StringComparison]::OrdinalIgnoreCase
                )
            }
    )
    if ($remaining.Count -ne 0) {
        throw "Streams media decoder soak left ffmpeg processes running."
    }
}
finally {
    foreach ($name in $environmentNames) {
        $value = $previousEnvironment[$name]
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}
