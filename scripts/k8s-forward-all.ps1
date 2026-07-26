param(
  [string]$Namespace = "radio",
  [string]$Deployment = "radio",
  [int]$HttpPort = 30080,
  [int]$ApiPort = 18000,
  [int]$DbPort = 15432
)

$ErrorActionPreference = "Stop"
$jobs = @(
  Start-Job -ScriptBlock { param($ns, $port) kubectl -n $ns port-forward svc/radio "$port`:80" } -ArgumentList $Namespace, $HttpPort
  Start-Job -ScriptBlock { param($ns, $name, $port) kubectl -n $ns port-forward deployment/$name "$port`:8000" } -ArgumentList $Namespace, $Deployment, $ApiPort
  Start-Job -ScriptBlock { param($ns, $port) kubectl -n $ns port-forward svc/postgres "$port`:5432" } -ArgumentList $Namespace, $DbPort
)

Write-Host "HTTP/player/admin/API/HLS: http://127.0.0.1:$HttpPort"
Write-Host "Direct FastAPI: http://127.0.0.1:$ApiPort"
Write-Host "PostgreSQL: 127.0.0.1:$DbPort"

try
{
  Receive-Job -Job $jobs -Wait
}
finally
{
  Stop-Job -Job $jobs -ErrorAction SilentlyContinue
  Remove-Job -Job $jobs -Force -ErrorAction SilentlyContinue
}
