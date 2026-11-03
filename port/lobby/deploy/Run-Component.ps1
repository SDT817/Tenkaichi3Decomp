param([Parameter(Mandatory=$true)][ValidateSet('rooms','directory','turn','https')][string]$Component)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$root = $PSScriptRoot
Set-Location -LiteralPath $root
$log = Join-Path $root ('logs\'+$Component+'.log')
$errorLog = Join-Path $root ('logs\'+$Component+'.stderr.log')
$env:PYTHONUTF8 = '1'
$env:XDG_DATA_HOME = Join-Path $root 'data'
$env:XDG_CONFIG_HOME = Join-Path $root 'config'
switch ($Component) {
    'rooms' { $executable = "$root\python\python.exe"; $arguments = '-X utf8 "'+$root+'\app\server.py" --config "'+$root+'\config\server.json"' }
    'directory' { $executable = "$root\python\python.exe"; $arguments = '-X utf8 "'+$root+'\app\directory_server.py" --config "'+$root+'\config\directory.json"' }
    'turn' { $executable = "$root\bt3-turn.exe"; $arguments = '-config "'+$root+'\config\turn.json"' }
    'https' { $executable = "$root\caddy\caddy.exe"; $arguments = 'run --config "'+$root+'\config\Caddyfile" --adapter caddyfile' }
}
# Keep native stderr out of PowerShell 5.1's NativeCommandError handling.
$process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $log -RedirectStandardError $errorLog
exit $process.ExitCode
