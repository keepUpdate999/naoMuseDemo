$ErrorActionPreference = 'Stop'
$demoUrl = 'http://127.0.0.1:18892'
$health = Invoke-RestMethod "$demoUrl/health" -TimeoutSec 3
if ($health.app -ne 'nanomuse-real-apps') { throw 'Service identity mismatch.' }
$html = (Invoke-WebRequest $demoUrl -UseBasicParsing).Content
$controlToken = [regex]::Match($html, 'name="demo-token" content="([^"]+)"').Groups[1].Value
Invoke-RestMethod "$demoUrl/api/shutdown" -Method Post -ContentType 'application/json' -Headers @{'X-Demo-Token'=$controlToken} -Body '{}' | Out-Null
