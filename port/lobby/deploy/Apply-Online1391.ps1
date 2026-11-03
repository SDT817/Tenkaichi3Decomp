[CmdletBinding()]
param([string]$GameDir, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
if (-not $GameDir) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Select the game folder containing Tenkaichi3Decomp.exe'
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return }
    $GameDir = $dialog.SelectedPath
    $dialog.Dispose()
}
$target = [IO.Path]::GetFullPath($GameDir).TrimEnd('\')
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $manifest.package.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw ('Package checksum failed: '+$entry.Name) }
}
$exePath = Join-Path $target 'Tenkaichi3Decomp.exe'
$current = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifest.expected_exe_sha256 -notcontains $current) { throw 'Unknown game build; existing files were preserved. Use the retained CN8 test, r12/r13 private client, or the listed official build.' }
if ($CheckOnly) { Write-Host 'Online1391 client checksums and installed version: OK. No files changed.'; return }
if (Get-Process -Name 'Tenkaichi3Decomp','BT3Connect' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exePath -or $_.Path -eq (Join-Path $target 'BT3Connect.exe') }) { throw 'Close this game and its lobby launcher before updating.' }
$backup = Join-Path $target ('backups\before-online1391-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $backup | Out-Null
$changes = @()
foreach ($entry in $manifest.install.PSObject.Properties) {
    $name = $entry.Name
    $item = $entry.Value
    $destination = Join-Path $target $name
    $existed = Test-Path -LiteralPath $destination -PathType Leaf
    if ($item.only_if_missing -and $existed) { continue }
    $source = Join-Path $PSScriptRoot $item.source
    if ($existed -and (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $manifest.package.($item.source)) { continue }
    if ($existed) {
        $saved = Join-Path $backup $name
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($saved)) -Force | Out-Null
        Copy-Item -LiteralPath $destination -Destination $saved
    }
    $changes += [PSCustomObject]@{name=$name;source=$source;existed=$existed}
}
$changes | Select-Object name,existed | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backup 'changed-files.json') -Encoding UTF8
try {
    foreach ($change in $changes) {
        $destination = Join-Path $target $change.name
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
        Copy-Item -LiteralPath $change.source -Destination $destination
    }
} catch {
    foreach ($change in $changes) {
        $destination = Join-Path $target $change.name
        if ($change.existed) { Copy-Item -LiteralPath (Join-Path $backup $change.name) -Destination $destination }
        elseif (Test-Path -LiteralPath $destination -PathType Leaf) { Remove-Item -LiteralPath $destination -Force }
    }
    throw
}
Write-Host 'Updated: official v0.1.39.1 + CN8 + Wii + private lobby r15 (protocol 6).' -ForegroundColor Green
Write-Host 'Start 01-Play-PrivateLobby.cmd in the game folder. Both players and the server need this update.'
Write-Host 'Settings, Wii bindings/profiles, saves and administrator credentials were preserved.'
Write-Host "Backup of changed files: $backup"
