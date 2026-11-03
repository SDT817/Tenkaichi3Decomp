[CmdletBinding()]
param([string]$InstallDir = 'C:\BT3Lobby')
$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator on the SERVER.' }
$root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$record = Get-Content -LiteralPath (Join-Path $root 'config\ip2626-deployment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$backup = [IO.Path]::GetFullPath($record.backup)
if (-not $backup.StartsWith(($root+'\backups\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected backup path; nothing changed.' }
& (Join-Path $root 'python\python.exe') -X utf8 (Join-Path $root 'migrate_ip2626.py') --root $root --backup $backup --restore
if ($LASTEXITCODE -ne 0) { throw 'Directory restore failed; private TLS task remains active.' }
if (Get-ScheduledTask -TaskName 'BT3-IP2626' -ErrorAction SilentlyContinue) {
    Disable-ScheduledTask -TaskName 'BT3-IP2626' | Out-Null
    Stop-ScheduledTask -TaskName 'BT3-IP2626'
    Unregister-ScheduledTask -TaskName 'BT3-IP2626' -Confirm:$false
}
$caddyPath = Join-Path $root 'caddy\caddy.exe'
$config = '"'+$root+'\config\Caddyfile-IP2626"'
Get-CimInstance Win32_Process -Filter "Name='caddy.exe'" | Where-Object { $_.ExecutablePath -eq $caddyPath -and $_.CommandLine -and $_.CommandLine.Contains($config) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue }
Get-NetFirewallRule -Group 'BT3Lobby-IP2626' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
if ($record.previous_https_enabled) { Enable-ScheduledTask -TaskName 'BT3-HTTPS' | Out-Null; Start-ScheduledTask -TaskName 'BT3-HTTPS' }
Write-Host 'Previous directory URL and HTTPS task restored. Private identity and backups retained; rooms, administrators and TURN keys preserved.'
