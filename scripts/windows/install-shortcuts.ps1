# One-time setup: build the web UI and put "Surf Clipper" and "Stop Surf Clipper" on the Desktop.
#   powershell -ExecutionPolicy Bypass -File scripts\windows\install-shortcuts.ps1
# Needs the WSL setup from the README (Ubuntu, uv, node). No admin rights.
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$repo = Split-Path -Parent (Split-Path -Parent $here)
$wslRepo = '/mnt/' + $repo.Substring(0, 1).ToLower() + ($repo.Substring(2) -replace '\\', '/')

Write-Host 'Building the web UI...'
& wsl.exe -d Ubuntu --cd $wslRepo -- bash scripts/wsl-run.sh bash -c 'cd web && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build'
if ($LASTEXITCODE -ne 0) { throw 'web UI build failed' }

$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$icon = Join-Path $here 'surfclip.ico'
foreach ($s in @(
        @{ Name = 'Surf Clipper'; Script = 'start.ps1'; Tip = 'Start Surf Session Clipper and open it in the browser' },
        @{ Name = 'Stop Surf Clipper'; Script = 'stop.ps1'; Tip = 'Stop Surf Session Clipper' })) {
    $lnk = $shell.CreateShortcut((Join-Path $desktop "$($s.Name).lnk"))
    $lnk.TargetPath = $ps
    $lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $here $s.Script)`""
    $lnk.WorkingDirectory = $repo
    $lnk.WindowStyle = 7  # minimised: no console flash
    $lnk.Description = $s.Tip
    if (Test-Path $icon) { $lnk.IconLocation = "$icon,0" }
    $lnk.Save()
    Write-Host "Created $($s.Name) on the Desktop"
}
