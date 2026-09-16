param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$serverRoot = Split-Path -Parent $PSScriptRoot

if (-not $OutputPath) {
    $OutputPath = Join-Path $serverRoot "dist\xiaozhi-hospice-deploy.tar.gz"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDir = Split-Path -Parent $OutputPath
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "xiaozhi-hospice-deploy-$PID"

$requiredBuilds = @(
    "apps\patient\index.html",
    "apps\family\index.html",
    "apps\clinician\index.html"
)
foreach ($relative in $requiredBuilds) {
    if (-not (Test-Path (Join-Path $serverRoot $relative))) {
        throw "缺少前端构建产物：$relative。请先运行三个前端的 npm run build。"
    }
}

$directories = @(
    "apps",
    "config",
    "core",
    "music",
    "plugins_func",
    "test\js",
    "models\snakers4_silero-vad",
    "models\bge-small-zh-v1.5"
)

$rootFiles = @(
    "agent-base-prompt.txt",
    "app.py",
    "config.yaml",
    "config_from_api.yaml",
    "mcp_server_settings.json",
    "requirements.txt"
)

try {
    New-Item -ItemType Directory -Force -Path $stage, $outputDir | Out-Null

    foreach ($relative in $directories) {
        $source = Join-Path $serverRoot $relative
        if (Test-Path $source) {
            $destination = Join-Path $stage $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
            Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
        }
    }

    foreach ($relative in $rootFiles) {
        Copy-Item -LiteralPath (Join-Path $serverRoot $relative) -Destination $stage -Force
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $stage "data") | Out-Null
    Copy-Item -LiteralPath (Join-Path $serverRoot "config.yaml") `
        -Destination (Join-Path $stage "data\.config.yaml") -Force
    Copy-Item -LiteralPath (Join-Path $serverRoot "data\.config_hospice.example.yaml") `
        -Destination (Join-Path $stage "data\.config_hospice.example.yaml") -Force

    Get-ChildItem -LiteralPath $stage -Recurse -Force -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $stage -Recurse -Force -File -Include "*.pyc", "*.log" |
        Remove-Item -Force

    if (Test-Path $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }
    & tar.exe -czf $OutputPath -C $stage .
    if ($LASTEXITCODE -ne 0) {
        throw "tar 打包失败，退出码：$LASTEXITCODE"
    }

    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $OutputPath
    $sizeMB = [math]::Round((Get-Item -LiteralPath $OutputPath).Length / 1MB, 1)
    Write-Host "发布包：$OutputPath"
    Write-Host "大小：$sizeMB MB"
    Write-Host "SHA256：$($hash.Hash)"
}
finally {
    if (Test-Path $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
