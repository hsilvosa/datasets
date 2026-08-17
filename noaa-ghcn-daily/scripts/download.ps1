param([string]$Config = "configs/default.json")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content (Join-Path $root $Config) -Raw | ConvertFrom-Json
$raw = Join-Path $root "data/raw/$($cfg.snapshot_date)"
New-Item -ItemType Directory -Force -Path $raw | Out-Null
$items = @($cfg.archive.name) + @($cfg.metadata)
foreach ($name in $items) {
  $target = Join-Path $raw $name
  if (Test-Path $target) { continue }
  $partial = "$target.part"
  & curl.exe --fail --location --retry 10 --retry-all-errors --continue-at - --silent --show-error --output $partial "$($cfg.base_url)/$name"
  if ($LASTEXITCODE -ne 0) { throw "Download failed: $name" }
  if ($name -eq $cfg.archive.name -and (Get-Item $partial).Length -ne [int64]$cfg.archive.bytes) { throw "Unexpected archive size" }
  Move-Item -Force $partial $target
}
$files = Get-ChildItem $raw -File | ForEach-Object { [ordered]@{name=$_.Name; bytes=$_.Length; sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()} }
[ordered]@{snapshot_date=$cfg.snapshot_date; completed_at=(Get-Date).ToUniversalTime().ToString('o'); files=$files} | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $raw 'manifest.json') -Encoding utf8
