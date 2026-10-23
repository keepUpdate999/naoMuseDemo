param([string]$OutputDirectory = "$PSScriptRoot\dist", [string]$PythonArchive = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildArgs = @('-m','desktop.build_portable','--output',$OutputDirectory)
if ($PythonArchive) { $buildArgs += @('--python-archive',$PythonArchive) }
& .venv/Scripts/python.exe @buildArgs
if ($LASTEXITCODE) { throw 'Portable build failed. Inspect its output; no local configuration is included.' }
