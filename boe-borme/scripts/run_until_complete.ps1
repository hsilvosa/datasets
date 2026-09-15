# Drives the full BOE/BORME pipeline to completion.
# It waits for any run already in progress, then re-runs `run` until it exits 0
# (download complete, quality pass, staged) or the attempt budget is exhausted.
# Every run is resumable and append-only, so retries only fetch missing units.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = Join-Path $root "src"
$python = Join-Path $root ".venv\Scripts\python.exe"
$log = Join-Path $root "full_run.err.log"

"[supervisor] start $(Get-Date -Format o) pid=$PID" | Out-File -Append -Encoding utf8 $log

# Wait for any pipeline process that is already running (e.g. the initial launch).
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try { $_.WaitForExit() } catch { }
}
"[supervisor] previous processes finished $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log

for ($attempt = 1; $attempt -le 50; $attempt++) {
    "[supervisor] attempt $attempt $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log
    & $python -m boe_borme run --config configs/default.json *>> $log
    $code = $LASTEXITCODE
    "[supervisor] attempt $attempt exit=$code $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log
    if ($code -eq 0) {
        "[supervisor] COMPLETE $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log
        break
    }
    Start-Sleep -Seconds 60
}
"[supervisor] stop $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $log
