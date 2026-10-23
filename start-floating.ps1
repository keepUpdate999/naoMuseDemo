$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pythonWindowless = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
& $pythonExe -c 'import PySide6'
if ($LASTEXITCODE) { throw 'Run setup-desktop.ps1 first to install the pinned desktop dependencies.' }
New-Item -ItemType Directory -Path '.local\desktop' -Force | Out-Null
# Start the assistant first so service preparation has a visible status.
Start-Process -FilePath $pythonWindowless -ArgumentList '-m','desktop.main' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput '.local\desktop\assistant.out.log' -RedirectStandardError '.local\desktop\assistant.err.log'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-real.ps1') -NoWorkbench
if ($LASTEXITCODE) { throw 'Workspace startup failed. Check .local/business/server.err.log.' }
