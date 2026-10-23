param([switch]$NoWorkbench)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$demoUrl = 'http://127.0.0.1:18892'
try {
    $health = Invoke-RestMethod "$demoUrl/health" -TimeoutSec 2
    if ($health.app -eq 'nanomuse-real-apps') { if (-not $NoWorkbench) { Start-Process $demoUrl }; exit }
} catch {}
if (Get-NetTCPConnection -LocalPort 18892 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 18892 is occupied. Existing service preserved.' }
New-Item -ItemType Directory -Path '.local\business' -Force | Out-Null
$proc = Start-Process -FilePath $pythonExe -ArgumentList 'real_server.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.local\business\server.out.log' -RedirectStandardError '.local\business\server.err.log'
$proc.Id | Set-Content '.local\business\server.pid'
for ($attempt = 0; $attempt -lt 900; $attempt++) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { throw 'Real applications startup failed. See .local/business/server.err.log.' }
    try { $health = Invoke-RestMethod "$demoUrl/health" -TimeoutSec 1; if ($health.app -eq 'nanomuse-real-apps') { if (-not $NoWorkbench) { Start-Process $demoUrl }; exit } } catch {}
}
throw 'Applications are still starting. Check .local/business/server.out.log.'
