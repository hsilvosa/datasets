$root = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content (Join-Path $root 'configs/default.json') -Raw | ConvertFrom-Json
$raw = Join-Path $root "data/raw/$($cfg.snapshot_date)"
Get-ChildItem $raw -File -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime
