param(
    [string]$ConfigPath = 'configs/archive-pilot.json'
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$resolvedConfig = if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
    [System.IO.Path]::GetFullPath($ConfigPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $projectRoot $ConfigPath))
}
$settings = Get-Content -LiteralPath $resolvedConfig -Raw | ConvertFrom-Json
$archiveRoot = if ([System.IO.Path]::IsPathRooted($settings.root)) {
    [System.IO.Path]::GetFullPath($settings.root)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $projectRoot $settings.root))
}
if (Test-Path -LiteralPath (Join-Path $archiveRoot 'run.lock')) {
    throw 'Existe run.lock. Comprueba el proceso o ejecuta recover antes de reanudar.'
}
$logDirectory = Join-Path $archiveRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdoutPath = Join-Path $logDirectory "$stamp.out.log"
$stderrPath = Join-Path $logDirectory "$stamp.err.log"
$arguments = @('-u', '-m', 'boe_borme.archive', 'run', '--config', ('"' + $resolvedConfig + '"'))
$taskProcess = Start-Process -FilePath $pythonPath -ArgumentList $arguments `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
[pscustomobject]@{
    ProcessId = $taskProcess.Id
    Config = $resolvedConfig
    Archive = $archiveRoot
    StandardOutput = $stdoutPath
    StandardError = $stderrPath
}
