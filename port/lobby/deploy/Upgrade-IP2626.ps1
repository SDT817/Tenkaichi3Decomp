[CmdletBinding()]
param([string]$InstallDir = 'C:\BT3Lobby', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
function Get-SHA256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $manifest.files.PSObject.Properties) {
    if ((Get-SHA256 (Join-Path $packageRoot $entry.Name)) -ne $entry.Value) { throw "Package checksum failed: $($entry.Name)" }
}
if ($CheckOnly) { Write-Host 'IP2626 update checksums: OK. No server changes performed.'; return }
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator on the SERVER.' }
$root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
if ($root -eq [IO.Path]::GetPathRoot($root).TrimEnd('\')) { throw 'Expected an existing dedicated BT3Lobby installation.' }
foreach ($file in @('python\python.exe','caddy\caddy.exe','config\directory.json','config\server.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)) { throw "Existing installation not found: $file" }
}
$oldTask = Get-ScheduledTask -TaskName 'BT3-HTTPS' -ErrorAction Stop
if (Get-ScheduledTask -TaskName 'BT3-IP2626' -ErrorAction SilentlyContinue) { throw 'BT3-IP2626 already exists. Keep the existing installation; do not regenerate its certificate.' }
if (Get-NetTCPConnection -LocalPort 2626 -State Listen -ErrorAction SilentlyContinue) { throw 'TCP 2626 is already in use. Existing service was preserved.' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $root ('backups\ip2626-'+$stamp)
New-Item -ItemType Directory -Path $backup | Out-Null
$wasEnabled = [bool]$oldTask.Settings.Enabled
Export-ScheduledTask -TaskName 'BT3-HTTPS' | Set-Content -LiteralPath (Join-Path $backup 'BT3-HTTPS.xml') -Encoding Unicode
Copy-Item -LiteralPath (Join-Path $root 'config\Caddyfile') -Destination (Join-Path $backup 'Caddyfile')
$identityDir = Join-Path $root 'config\tls-ip2626'
if (Test-Path -LiteralPath $identityDir) {
    foreach ($name in @('server.crt','server.key','client-check.json')) {
        if ((Get-SHA256 (Join-Path $identityDir $name)) -ne (Get-SHA256 (Join-Path $packageRoot $name))) { throw 'An existing different private identity was preserved. Do not replace its key.' }
    }
} else {
    New-Item -ItemType Directory -Path $identityDir | Out-Null
    foreach ($name in @('server.crt','server.key','client-check.json')) { Copy-Item -LiteralPath (Join-Path $packageRoot $name) -Destination (Join-Path $identityDir $name) }
}
$identityACL = & icacls.exe $identityDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict server private key permissions.' }
Copy-Item -LiteralPath (Join-Path $packageRoot 'BT3Connect.exe') -Destination (Join-Path $root 'BT3Connect.exe')
Copy-Item -LiteralPath (Join-Path $packageRoot 'Run-IP2626.ps1') -Destination (Join-Path $root 'Run-IP2626.ps1')
Copy-Item -LiteralPath (Join-Path $packageRoot 'migrate_ip2626.py') -Destination (Join-Path $root 'migrate_ip2626.py')
$config = (Get-Content -LiteralPath (Join-Path $packageRoot 'Caddyfile-IP2626.template') -Raw).Replace('@@ROOT@@',$root.Replace('\','/'))
$configPath = Join-Path $root 'config\Caddyfile-IP2626'
[IO.File]::WriteAllText($configPath,$config,(New-Object System.Text.UTF8Encoding($false)))
$validate = Start-Process -FilePath (Join-Path $root 'caddy\caddy.exe') -ArgumentList ('validate --config "'+$configPath+'" --adapter caddyfile') -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $backup 'validate.log') -RedirectStandardError (Join-Path $backup 'validate.stderr.log')
if ($validate.ExitCode -ne 0) { throw "Private TLS configuration failed validation. Existing services remain active. See $backup\validate.stderr.log" }
$migrated = $false
$created = $false
try {
    & (Join-Path $root 'python\python.exe') -X utf8 (Join-Path $root 'migrate_ip2626.py') --root $root --backup $backup
    if ($LASTEXITCODE -ne 0) { throw 'Directory migration failed.' }
    $migrated = $true
    New-NetFirewallRule -DisplayName 'BT3Lobby private TLS TCP 2626' -Group 'BT3Lobby-IP2626' -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort 2626 -Program (Join-Path $root 'caddy\caddy.exe') | Out-Null
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$root+'\Run-IP2626.ps1"') -WorkingDirectory $root
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName 'BT3-IP2626' -Action $action -Settings $settings -Principal $taskPrincipal -Trigger (New-ScheduledTaskTrigger -AtStartup) -Description 'BT3 private IP TLS gateway; no public certificate issuer' | Out-Null
    $created = $true
    Start-ScheduledTask -TaskName 'BT3-IP2626'
    Start-Sleep -Seconds 3
    & (Join-Path $root 'BT3Connect.exe') -config (Join-Path $identityDir 'client-check.json') -check -check-address '127.0.0.1:2626'
    if ($LASTEXITCODE -ne 0) { throw "Local private TLS check failed. See $root\logs\ip2626.stderr.log" }
    # Preserve the old configuration/task for rollback; stop only its exact Caddy process.
    Disable-ScheduledTask -TaskName 'BT3-HTTPS' | Out-Null
    Stop-ScheduledTask -TaskName 'BT3-HTTPS'
    $caddyPath = Join-Path $root 'caddy\caddy.exe'
    $oldConfig = '"'+$root+'\config\Caddyfile"'
    Get-CimInstance Win32_Process -Filter "Name='caddy.exe'" | Where-Object { $_.ExecutablePath -eq $caddyPath -and $_.CommandLine -and $_.CommandLine.Contains($oldConfig) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue }
    @{backup=$backup;previous_https_enabled=$wasEnabled;url='https://114.132.102.42:2626';certificate_sha256=$manifest.certificate_sha256} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'config\ip2626-deployment.json') -Encoding UTF8
} catch {
    if ($created) {
        Disable-ScheduledTask -TaskName 'BT3-IP2626' -ErrorAction SilentlyContinue | Out-Null
        Stop-ScheduledTask -TaskName 'BT3-IP2626' -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName 'BT3-IP2626' -Confirm:$false -ErrorAction SilentlyContinue
    }
    $newConfig = '"'+$configPath+'"'
    Get-CimInstance Win32_Process -Filter "Name='caddy.exe'" | Where-Object { $_.ExecutablePath -eq (Join-Path $root 'caddy\caddy.exe') -and $_.CommandLine -and $_.CommandLine.Contains($newConfig) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue }
    Get-NetFirewallRule -Group 'BT3Lobby-IP2626' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    if ($migrated) { & (Join-Path $root 'python\python.exe') -X utf8 (Join-Path $root 'migrate_ip2626.py') --root $root --backup $backup --restore }
    if ($wasEnabled) { Enable-ScheduledTask -TaskName 'BT3-HTTPS' -ErrorAction SilentlyContinue | Out-Null; Start-ScheduledTask -TaskName 'BT3-HTTPS' -ErrorAction SilentlyContinue }
    throw
}
Write-Host 'Private IP TLS gateway installed. Local TLS identity and API health: OK.' -ForegroundColor Green
Write-Host 'Public entry: TCP 2626. No domain, TCP 80/443 or public CA certificate is required.'
Write-Host 'Keep the existing UDP 3478,8787,49160-49259 rules for TURN and RTT.'
Write-Host 'The directory entry URL was updated. Existing rooms, administrator hashes and TURN keys were preserved.'
Write-Host 'Remote connectivity and actual two-player gameplay still require testing.'
