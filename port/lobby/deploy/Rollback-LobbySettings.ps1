[CmdletBinding()]
param([string]$InstallDir = 'C:\BT3Lobby')
$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator on the SERVER.' }
$root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$record = Get-Content -LiteralPath (Join-Path $root 'config\lobby-settings-deployment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$backup = (Resolve-Path -LiteralPath $record.backup -ErrorAction Stop).ProviderPath
if (-not $backup.StartsWith($root+'\backups\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected backup path; nothing changed.' }
$names = @('app\server.py','app\directory_server.py','config\server.json','config\directory.json')
foreach ($name in $names) { if (-not (Test-Path -LiteralPath (Join-Path $backup $name) -PathType Leaf)) { throw "Backup file missing: $name" } }
$tasks = @('BT3-Rooms','BT3-Directory')
foreach ($task in $tasks) { Disable-ScheduledTask -TaskName $task | Out-Null; Stop-ScheduledTask -TaskName $task }
$pythonPath = Join-Path $root 'python\python.exe'
$roomScript = '"'+$root+'\app\server.py"'
$directoryScript = '"'+$root+'\app\directory_server.py"'
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.ExecutablePath -eq $pythonPath -and $_.CommandLine -and
    ($_.CommandLine.Contains($roomScript) -or $_.CommandLine.Contains($directoryScript))
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue }
foreach ($name in $names) { Copy-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $root $name) }
foreach ($task in $tasks) { Enable-ScheduledTask -TaskName $task | Out-Null; Start-ScheduledTask -TaskName $task }
Write-Host 'Previous room/directory applications and configurations restored. Current databases, TLS and TURN preserved.'
