$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$arguments = 'run --config "'+$root+'\config\Caddyfile-IP2626" --adapter caddyfile'
$process = Start-Process -FilePath (Join-Path $root 'caddy\caddy.exe') -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $root 'logs\ip2626.log') -RedirectStandardError (Join-Path $root 'logs\ip2626.stderr.log')
exit $process.ExitCode
