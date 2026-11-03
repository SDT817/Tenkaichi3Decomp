[CmdletBinding()]
param([string]$InstallDir = 'C:\BT3Lobby', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $manifest.files.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw "Package checksum failed: $($entry.Name)" }
}
if ($CheckOnly) { Write-Host 'LobbySettings update checksums: OK. No server changes performed.'; return }
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator on the SERVER.' }
$root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
if ($root -eq [IO.Path]::GetPathRoot($root).TrimEnd('\')) { throw 'Expected the existing dedicated BT3Lobby installation.' }
foreach ($name in @('python\python.exe','app\server.py','app\directory_server.py','config\server.json','config\directory.json','config\ip2626-deployment.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $name) -PathType Leaf)) { throw "Installed IP2626 service not found: $name" }
}
foreach ($entry in $manifest.expected_sources.PSObject.Properties) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $root $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($entry.Value -notcontains $actual) { throw "Unexpected installed source; preserved: $($entry.Name)" }
}
& (Join-Path $root 'python\python.exe') -X utf8 (Join-Path $PSScriptRoot 'migrate_lobby_settings.py') --root $root --check
if ($LASTEXITCODE -ne 0) { throw 'Room administration preflight failed. Existing services were not stopped.' }
$tasks = @('BT3-Rooms','BT3-Directory')
foreach ($task in $tasks) {
    if (-not (Get-ScheduledTask -TaskName $task -ErrorAction Stop).Settings.Enabled) { throw "Start the existing $task service before upgrading." }
}
$backup = Join-Path $root ('backups\lobby-settings-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path (Join-Path $backup 'app') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $backup 'config') -Force | Out-Null
foreach ($name in @('app\server.py','app\directory_server.py','config\server.json','config\directory.json')) {
    Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $backup $name)
}
function Stop-RoomServices {
    foreach ($task in $tasks) { Disable-ScheduledTask -TaskName $task | Out-Null; Stop-ScheduledTask -TaskName $task }
    $pythonPath = Join-Path $root 'python\python.exe'
    $roomScript = '"'+$root+'\app\server.py"'
    $directoryScript = '"'+$root+'\app\directory_server.py"'
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.ExecutablePath -eq $pythonPath -and $_.CommandLine -and
        ($_.CommandLine.Contains($roomScript) -or $_.CommandLine.Contains($directoryScript))
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue }
}
function Start-RoomServices {
    foreach ($task in $tasks) { Enable-ScheduledTask -TaskName $task | Out-Null; Start-ScheduledTask -TaskName $task }
}
try {
    Stop-RoomServices
    & (Join-Path $root 'python\python.exe') -X utf8 (Join-Path $PSScriptRoot 'migrate_lobby_settings.py') --root $root --backup $backup
    if ($LASTEXITCODE -ne 0) { throw 'Room administration configuration failed.' }
    foreach ($name in @('server.py','directory_server.py')) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $root ('app\'+$name)) }
    Start-RoomServices
    $healthy = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $headers = @{'X-Real-IP'='127.0.0.1'}
            $rooms = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/healthz' -TimeoutSec 2
            $directory = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/directory/v1/request' -Method Post -ContentType 'application/json' -Body '{"op":"list"}' -Headers $headers -TimeoutSec 2
            if ($rooms.ok -and $rooms.protocol -eq 5 -and $directory.ok -and $directory.api -eq 1) { $healthy = $true; break }
        } catch { }
    }
    if (-not $healthy) { throw "Updated services did not pass health checks. See $root\logs\rooms.stderr.log and directory.stderr.log" }
    @{backup=$backup;revision='r13-LobbySettings'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'config\lobby-settings-deployment.json') -Encoding UTF8
} catch {
    Stop-RoomServices
    foreach ($name in @('app\server.py','app\directory_server.py','config\server.json','config\directory.json')) {
        Copy-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $root $name)
    }
    Start-RoomServices
    Write-Host 'Previous room/directory application files and configuration restored.'
    throw
}
Write-Host 'LobbySettings installed. Existing room and directory services: OK.' -ForegroundColor Green
Write-Host 'Default speed: 100%. Administrators can save room mode, time and speed from the updated client.'
Write-Host 'TCP/TLS, TURN, administrator identities, room definitions and saved player data were preserved.'
Write-Host "Backup: $backup"
