$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run setup.ps1 first.' }
$demoUrl = 'http://127.0.0.1:18889'
try {
    $health = Invoke-RestMethod "$demoUrl/health" -TimeoutSec 2
    if ($health.app -ne 'nanomuse-browser-demo') { throw 'Port belongs to another service.' }
    Start-Process $demoUrl
    exit
} catch {
    if (Get-NetTCPConnection -LocalPort 18889 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 18889 is occupied. Existing service preserved.' }
}
New-Item -ItemType Directory -Path '.local' -Force | Out-Null
$proc = Start-Process -FilePath $pythonExe -ArgumentList 'server.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput '.local\server.out.log' -RedirectStandardError '.local\server.err.log'
$proc.Id | Set-Content '.local\server.pid'
for ($attempt=0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    try { $health=Invoke-RestMethod "$demoUrl/health" -TimeoutSec 1; if ($health.app -eq 'nanomuse-browser-demo') { Start-Process $demoUrl; exit } } catch {}
}
throw 'Startup failed. See .local/server.err.log.'
