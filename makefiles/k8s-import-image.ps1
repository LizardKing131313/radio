param(
  [Parameter(Mandatory = $true)]
  [string] $ImageTar,

  [string] $Kubectl = "kubectl",

  [string] $Node = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Kubectl
{
  $Arguments = $args

  & $Kubectl @Arguments
  if ($LASTEXITCODE -ne 0)
  {
    throw "kubectl $( $Arguments -join ' ' ) failed with exit code $LASTEXITCODE"
  }
}

function Invoke-KubectlOutput
{
  $Arguments = $args

  $output = & $Kubectl @Arguments 2>&1
  if ($LASTEXITCODE -ne 0)
  {
    throw "kubectl $( $Arguments -join ' ' ) failed with exit code $LASTEXITCODE`n$output"
  }
  return $output
}

$resolvedTarPath = (Resolve-Path -LiteralPath $ImageTar).Path
$cwd = (Resolve-Path -LiteralPath ".").Path
if ( $resolvedTarPath.StartsWith($cwd, [System.StringComparison]::OrdinalIgnoreCase))
{
  $tarPath = "." + $resolvedTarPath.Substring($cwd.Length)
}
else
{
  $tarPath = $resolvedTarPath
}
$tarPath = $tarPath.Replace("\", "/")
$nodeName = $Node
if ($nodeName.Length -eq 0)
{
  $nodeName = (Invoke-KubectlOutput get nodes -o "jsonpath={.items[0].metadata.name}").Trim()
}
if ($nodeName.Length -eq 0)
{
  throw "No Kubernetes node found for image import"
}

$debugPod = $null
$remoteTar = "/tmp/radio-manager-import-$PID.tar"

try
{
  $debugOutput = Invoke-KubectlOutput debug "node/$nodeName" --image=busybox --profile=general "--" sleep 3600
  $match = [regex]::Match(($debugOutput -join "`n"), "Creating debugging pod (?<pod>\S+)")
  if ($match.Success)
  {
    $debugPod = $match.Groups["pod"].Value
  }
  if ($debugPod -eq $null -or $debugPod.Length -eq 0)
  {
    $pods = Invoke-KubectlOutput get pods -o json | ConvertFrom-Json
    $debugPod = @($pods.items |
      Where-Object { $_.metadata.name -like "node-debugger-$nodeName-*" -and $_.status.phase -ne "Succeeded" } |
      Sort-Object { $_.metadata.creationTimestamp } -Descending |
      Select-Object -First 1).metadata.name
  }
  if ($debugPod -eq $null -or $debugPod.Length -eq 0)
  {
    throw "Could not find node debug pod"
  }

  Invoke-Kubectl wait --for=condition=Ready "pod/$debugPod" --timeout=60s
  Invoke-Kubectl cp $tarPath "${debugPod}:/host$remoteTar"
  Invoke-Kubectl exec $debugPod "--" chroot /host ctr -n k8s.io images import $remoteTar
  Invoke-Kubectl exec $debugPod "--" chroot /host rm -f $remoteTar
}
finally
{
  if ($debugPod -ne $null -and $debugPod.Length -gt 0)
  {
    & $Kubectl delete pod $debugPod --ignore-not-found=true | Out-Host
  }
}
