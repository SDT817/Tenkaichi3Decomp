[CmdletBinding()]
param(
    [string]$InstallDir = 'C:\BT3Lobby',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'package-manifest.json') -Raw | ConvertFrom-Json
function Get-PackageSHA256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
foreach ($entry in $manifest.files.PSObject.Properties) {
    $item = Join-Path $packageRoot $entry.Name
    if (-not (Test-Path -LiteralPath $item -PathType Leaf)) { throw "Missing package file: $($entry.Name)" }
    if ((Get-PackageSHA256 $item) -ne $entry.Value) { throw "Package checksum failed: $($entry.Name)" }
}
if ($CheckOnly) { Write-Host 'Deployment package checksums: OK. No installation performed.'; return }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Open PowerShell as Administrator on the SERVER.' }
if ([Environment]::OSVersion.Version.Build -lt 14393) { throw 'Windows Server 2016 / Windows 10 or later is required by the portable services.' }
$target = [IO.Path]::GetFullPath($InstallDir)
if ($target.TrimEnd('\') -eq [IO.Path]::GetPathRoot($target).TrimEnd('\')) { throw 'Choose a dedicated installation folder.' }
if (Test-Path -LiteralPath $target) { throw "Destination already exists: $target. Preserve it and choose a new InstallDir; this installer does not overwrite an existing server." }
$taskNames = @('BT3-Rooms','BT3-Directory','BT3-TURN','BT3-HTTPS')
foreach ($name in $taskNames) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw "Task already exists: $name. Preserve the existing installation first." }
}
$busyTCP = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @(80,443,8787,8788) })
$busyUDP = @(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @(3478,8787) })
if ($busyTCP.Count -or $busyUDP.Count) { throw 'One of the required TCP 80/443/8787/8788 or UDP 3478/8787 ports is already in use. Preserve the existing service and resolve the conflict first.' }
New-Item -ItemType Directory -Path $target | Out-Null
& icacls.exe $target /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict server configuration permissions.' }
Get-ChildItem -LiteralPath (Join-Path $packageRoot 'payload') | Copy-Item -Destination $target -Recurse
foreach ($dir in @('data','logs')) { New-Item -ItemType Directory -Path (Join-Path $target $dir) -Force | Out-Null }
# The embedded runtime isolates sys.path. Add only the application's own code.
$pth = Get-ChildItem -LiteralPath (Join-Path $target 'python') -Filter 'python*._pth' | Select-Object -First 1
Add-Content -LiteralPath $pth.FullName -Value '..\app' -Encoding Ascii
$publicIP = $manifest.public_ipv4
$domain = $manifest.domain
try {
    $resolved = @(Resolve-DnsName -Name $domain -Type A -ErrorAction Stop | Where-Object Type -eq 'A' | ForEach-Object IPAddress)
    if ($publicIP -notin $resolved) { Write-Host "DNS is not pointing to $publicIP yet. HTTPS will be pending." -ForegroundColor Yellow }
} catch { Write-Host 'DNS lookup is unavailable. HTTPS will retry after DNS becomes reachable.' -ForegroundColor Yellow }
New-NetFirewallRule -DisplayName 'BT3Lobby HTTPS and certificate renewal' -Group 'BT3Lobby' -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort 80,443 -Program (Join-Path $target 'caddy\caddy.exe') | Out-Null
New-NetFirewallRule -DisplayName 'BT3Lobby UDP player RTT' -Group 'BT3Lobby' -Direction Inbound -Action Allow -Profile Any -Protocol UDP -LocalPort 8787 -Program (Join-Path $target 'python\python.exe') | Out-Null
New-NetFirewallRule -DisplayName 'BT3Lobby TURN listener and relay range' -Group 'BT3Lobby' -Direction Inbound -Action Allow -Profile Any -Protocol UDP -LocalPort 3478,'49160-49259' -Program (Join-Path $target 'bt3-turn.exe') | Out-Null
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$trigger = New-ScheduledTaskTrigger -AtStartup
$components = @{'BT3-Rooms'='rooms';'BT3-Directory'='directory';'BT3-TURN'='turn';'BT3-HTTPS'='https'}
foreach ($name in $taskNames) {
    $runner = Join-Path $target 'Run-Component.ps1'
    $argument = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$runner+'" -Component '+$components[$name]
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $target
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $taskPrincipal -Description 'Private BT3 room/directory/TURN service' | Out-Null
    Start-ScheduledTask -TaskName $name
}
Start-Sleep -Seconds 3
foreach ($port in @(8787,8788)) {
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 5
        if (-not $status.ok) { throw 'Service not healthy' }
        Write-Host "Local API $port : OK" -ForegroundColor Green
    } catch { Write-Host "Local API $port : pending, inspect $target\logs" -ForegroundColor Yellow }
}
Write-Host "Installed in $target. Four startup tasks run without an RDP session."
Write-Host 'In the cloud console SECURITY GROUP, allow TCP 80,443 and UDP 3478,8787,49160-49259.'
Write-Host "Public endpoint: https://$domain/healthz"
Write-Host 'A successful HTTPS check does not yet prove remote UDP gameplay; test with both players.'
