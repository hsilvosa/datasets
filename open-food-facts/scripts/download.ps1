param([string]$Config = "configs/default.json")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content (Join-Path $root $Config) -Raw | ConvertFrom-Json
$raw = Join-Path $root "data/raw/$($cfg.snapshot_date)"
New-Item -ItemType Directory -Force -Path $raw | Out-Null
$target = Join-Path $raw $cfg.filename
if (-not (Test-Path $target)) {
  $partial = "$target.part"
  & curl.exe --fail --location --retry 10 --retry-all-errors --continue-at - --silent --show-error --output $partial $cfg.url
  if ($LASTEXITCODE -ne 0) { throw "Download failed" }
  if ((Get-Item $partial).Length -ne [int64]$cfg.bytes) { throw "Unexpected snapshot size" }
  Move-Item -Force $partial $target
}
[ordered]@{snapshot_date=$cfg.snapshot_date; bytes=(Get-Item $target).Length; sha256=(Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant(); completed_at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $raw 'manifest.json') -Encoding utf8
