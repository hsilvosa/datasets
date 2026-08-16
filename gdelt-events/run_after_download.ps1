param(
    [Parameter(Mandatory = $true)]
    [int]$DownloadPid
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
Wait-Process -Id $DownloadPid
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"
python -m gdelt_events verify --config configs/default.json
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
