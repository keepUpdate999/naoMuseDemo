$ErrorActionPreference = 'Stop'
$demoUrl = 'http://127.0.0.1:18889'
try { $health = Invoke-RestMethod "$demoUrl/health" -TimeoutSec 2 } catch { Write-Output 'Demo is not running.'; exit }
if ($health.app -ne 'nanomuse-browser-demo') { throw 'Different service, nothing stopped.' }
$page = Invoke-WebRequest "$demoUrl/" -UseBasicParsing
$token = [regex]::Match($page.Content, 'name="demo-token" content="([^"]+)"').Groups[1].Value
Invoke-RestMethod "$demoUrl/api/shutdown" -Method Post -ContentType 'application/json' -Headers @{'X-Demo-Token'=$token} -Body '{}' | Out-Null
Write-Output 'Demo shutting down safely.'
