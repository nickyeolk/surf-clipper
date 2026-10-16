# Stop Surf Session Clipper (the "Stop Surf Clipper" desktop shortcut). Queued work is dropped;
# a running analysis or export stops and resumes from its cache next time.
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$port = 8765
$m = Select-String -Path (Join-Path $repo 'config\default.toml') -Pattern '^port\s*=\s*(\d+)' | Select-Object -First 1
if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }
try {
    # 127.0.0.1: Windows PowerShell tries IPv6 ::1 for localhost first, which WSL does not forward.
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/shutdown" -TimeoutSec 5 | Out-Null
} catch {
    # Not answering: stop the process directly.
    & wsl.exe -d Ubuntu -- pkill -f 'surfclip serve' | Out-Null
}
