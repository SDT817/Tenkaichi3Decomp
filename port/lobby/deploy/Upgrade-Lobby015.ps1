[CmdletBinding()]
param([string]$InstallDir = 'C:\BT3Lobby', [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $manifest.files.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw "Package checksum failed: $($entry.Name)" }
}
if ($CheckOnly) { Write-Host 'Lobby 0.15 package checksums: OK. No server changes performed.'; return }
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator on the SERVER.' }
$root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
if ($root -eq [IO.Path]::GetPathRoot($root).TrimEnd('\')) { throw 'Expected the dedicated existing BT3Lobby installation.' }
foreach ($name in @('python\python.exe','app\server.py','config\server.json','config\tls-ip2626\client-check.json','BT3Connect.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $name) -PathType Leaf)) { throw "Existing private server missing: $name" }
}
$old = (Get-FileHash -LiteralPath (Join-Path $root 'app\server.py') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifest.expected_server_sources -notcontains $old) { throw 'Unknown server source; existing installation preserved.' }
$python = Join-Path $root 'python\python.exe'
& $python -X utf8 (Join-Path $PSScriptRoot 'install_release.py') --check --release (Join-Path $PSScriptRoot 'updates')
if ($LASTEXITCODE -ne 0) { throw 'Private release preflight failed.' }
$backup = Join-Path $root ('backups\lobby015-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'app\server.py') -Destination (Join-Path $backup 'server.py')
function Stop-Rooms {
    Disable-ScheduledTask -TaskName 'BT3-Rooms' | Out-Null
    Stop-ScheduledTask -TaskName 'BT3-Rooms'
    $script = $root+'\app\server.py'
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.ExecutablePath -eq $python -and $_.CommandLine -and $_.CommandLine.Contains($script)
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue }
}
function Start-Rooms {
    Enable-ScheduledTask -TaskName 'BT3-Rooms' | Out-Null
    Start-ScheduledTask -TaskName 'BT3-Rooms'
}
try {
    Stop-Rooms
    & $python -X utf8 (Join-Path $PSScriptRoot 'install_release.py') --backup-config (Join-Path $root 'config\server.json') --backup (Join-Path $backup 'rooms.sqlite3')
    if ($LASTEXITCODE -ne 0) { throw 'Database backup failed; previous application will be restarted.' }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'server.py') -Destination (Join-Path $root 'app\server.py')
    & $python -X utf8 (Join-Path $PSScriptRoot 'install_release.py') --release (Join-Path $PSScriptRoot 'updates') --target (Join-Path $root 'updates')
    if ($LASTEXITCODE -ne 0) { throw 'Release publication failed.' }
    Start-Rooms
    $healthy=$false
    for ($i=0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        try {
            $health=Invoke-RestMethod 'http://127.0.0.1:8787/healthz' -TimeoutSec 2
            $release=Invoke-RestMethod 'http://127.0.0.1:8787/updates/latest.json' -TimeoutSec 2
            if ($health.ok -and $health.protocol -eq 6 -and $health.slots -eq 8 -and $release.tag_name) { $healthy=$true; break }
        } catch { }
    }
    if (-not $healthy) { throw 'Updated service health or release check failed.' }
    & (Join-Path $root 'BT3Connect.exe') -config (Join-Path $root 'config\tls-ip2626\client-check.json') -check -check-address '127.0.0.1:2626'
    if ($LASTEXITCODE -ne 0) { throw 'Existing private TLS health check failed.' }
} catch {
    Stop-Rooms
    Copy-Item -LiteralPath (Join-Path $backup 'server.py') -Destination (Join-Path $root 'app\server.py')
    Start-Rooms
    Write-Host 'Previous room service restored. Permanent room names, rules and administrator identities preserved.'
    throw
}
Write-Host 'Lobby 0.15 installed: client version checks, eight seats, synchronized pause and signed private updates.' -ForegroundColor Green
Write-Host 'Existing TCP 2626 / TURN ports and battle protocol 6 are unchanged. No new firewall rules are needed.'
Write-Host "Backup: $backup"
