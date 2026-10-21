$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first; this script does not modify global Python.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) { uv venv .venv --python 3.12; if ($LASTEXITCODE) { throw 'venv failed' } }
uv pip sync requirements.lock --python .venv/Scripts/python.exe
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
& .venv/Scripts/python.exe -m playwright install chromium
if ($LASTEXITCODE) { throw 'Browser installation failed' }
Write-Output 'Ready. Run start.ps1.'
