$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup.ps1')
if ($LASTEXITCODE) { throw 'Core setup failed.' }
uv pip install --python .venv/Scripts/python.exe -r requirements-desktop.lock
if ($LASTEXITCODE) { throw 'Desktop dependency installation failed.' }
Write-Output 'Ready. Run start-floating.ps1.'
