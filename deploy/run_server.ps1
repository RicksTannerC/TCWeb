<#
Supervises the Django app (waitress) so it survives crashes, sleep and
reboots without anyone needing to start it by hand.

This script is meant to run forever, launched once at boot by a Windows
Scheduled Task (see README.md's Deployment section for the exact command
that registers it). It is the thing that keeps the site up after a reboot --
Cloudflared already runs as its own Windows service and needs nothing here.

RESTARTING THE APP (to pick up new code) needs no administrator rights: create the
file  D:\TCData\restart.flag  (any contents). Within a couple of seconds the
supervisor deletes it, stops waitress and starts a fresh copy. The task runs in
its own sign-in session, so a normal Stop-Process from your own window is refused;
this file is the supported way. Example:
    New-Item D:\TCData\restart.flag -ItemType File -Force

If you need to stop the supervisor itself (rare), do it from an administrator
PowerShell:  Stop-ScheduledTask -TaskName "TShirtBrandWebsite"  (then Start-... again).

The parameters exist so the script can be tested on a spare port without touching the
live site; the scheduled task passes none and gets the defaults.
#>
param(
    [int]$Port = 8000,
    [string]$EnvFile = "D:\TCData\.env",
    [string]$RestartFlag = "D:\TCData\restart.flag",
    [string]$LogDir = ""
)

$RepoDir = "C:\Users\trick\OneDrive\Desktop\TShirtBrand\TCWeb"
$Python  = "C:\Users\trick\AppData\Local\Programs\Python\Python314\python.exe"
if (-not $LogDir) { $LogDir = $RepoDir }
$LogFile = Join-Path $LogDir "waitress.supervisor.log"

function Write-Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Add-Content -Path $LogFile
}

# Explicit per-process, never an ambient/persistent env var -- see README.md
# for why TCWEB_ENV_FILE must never be set machine-wide.
$env:TCWEB_ENV_FILE = $EnvFile
Set-Location $RepoDir

if ($Python -match '\s' -or $LogDir -match '\s') {
    Write-Log "A path contains a space; run_server.ps1 needs quoting added before it can start the app."
    exit 1
}

Write-Log "Supervisor started (pid $PID, port $Port)."

while ($true) {
    $listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listening) {
        # Something's already serving on this port -- most likely this script
        # itself was started twice, or someone started the app by hand.
        # Never start a second copy fighting over the same port.
        Write-Log "Port $Port already in use (pid $($listening.OwningProcess)) -- not starting a second copy. Checking again in 30s."
        Start-Sleep -Seconds 30
        continue
    }

    # A restart request left over from before this start is stale; don't act on it.
    if (Test-Path $RestartFlag) { Remove-Item $RestartFlag -Force -ErrorAction SilentlyContinue }

    Write-Log "Starting waitress..."
    # --trusted-proxy*: waitress DROPS X-Forwarded-* headers unless told which proxy to trust,
    # so without these flags Django never learns requests arrived over HTTPS (the Cloudflare
    # connector is the only thing that can reach 127.0.0.1). Keep them in step with the
    # README's launch command.
    # cmd.exe does the redirection: it appends the program's raw output. PowerShell 5.1's
    # own 1>>/2>> would re-encode it as UTF-16, leaving the logs unreadable by most tools.
    # (No quoting needed: the paths have no spaces -- checked once at the top.)
    $out = Join-Path $LogDir "waitress.log"
    $err = Join-Path $LogDir "waitress.err.log"
    $cmd = "$Python -m waitress --listen=127.0.0.1:$Port --trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto config.wsgi:application 1>>$out 2>>$err"
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c $cmd" -WorkingDirectory $RepoDir -WindowStyle Hidden -PassThru

    while (-not $proc.HasExited) {
        if (Test-Path $RestartFlag) {
            Remove-Item $RestartFlag -Force -ErrorAction SilentlyContinue
            Write-Log "Restart requested (flag file) -- stopping waitress."
            & taskkill.exe /PID $proc.Id /T /F | Out-Null
            break
        }
        Start-Sleep -Seconds 2
    }
    $proc.WaitForExit()

    Write-Log "waitress exited (exit code $($proc.ExitCode)). Restarting in 5 seconds."
    Start-Sleep -Seconds 5
}
