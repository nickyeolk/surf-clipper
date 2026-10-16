# Start Surf Session Clipper without a console (003 research R5) and open it in the browser.
# Run by the "Surf Clipper" desktop shortcut (scripts\windows\install-shortcuts.ps1).
# If the server is already running, this only opens the browser.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$port = 8765
$m = Select-String -Path (Join-Path $repo 'config\default.toml') -Pattern '^port\s*=\s*(\d+)' | Select-Object -First 1
if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }
$url = "http://localhost:$port"
$log = Join-Path $repo 'artifacts\logs\server.log'

function Test-Up {
    try { return [bool](Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 2).ok } catch { return $false }
}

if (-not (Test-Up)) {
    # C:\Users\... -> /mnt/c/Users/...
    $wslRepo = '/mnt/' + $repo.Substring(0, 1).ToLower() + ($repo.Substring(2) -replace '\\', '/')
    Start-Process -FilePath 'wsl.exe' -WindowStyle Hidden -ArgumentList @(
        '-d', 'Ubuntu', '--cd', $wslRepo, '--',
        'bash', 'scripts/wsl-run.sh', 'uv', 'run', 'surfclip', 'serve', '--log', 'artifacts/logs/server.log'
    )
    $deadline = (Get-Date).AddSeconds(90)
    while (-not (Test-Up)) {
        if ((Get-Date) -gt $deadline) {
            Add-Type -AssemblyName PresentationFramework
            [void][System.Windows.MessageBox]::Show(
                "Surf Clipper did not start within 90 seconds.`n`nDetails are in:`n$log",
                'Surf Clipper', 'OK', 'Error')
            exit 1
        }
        Start-Sleep -Milliseconds 500
    }
}
Start-Process $url
