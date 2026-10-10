<#
Supervises the Django app (waitress) so it survives crashes, sleep and
reboots without anyone needing to start it by hand.

This script is meant to run forever, launched once at boot by a Windows
Scheduled Task (see README.md's Deployment section for the exact command
that registers it). It is the thing that keeps the site up after a reboot --
Cloudflared already runs as its own Windows service and needs nothing here.

If you need to restart the app by hand during active development, stop this
task first so it doesn't fight over port 8000:
    Stop-ScheduledTask -TaskName "TShirtBrandWebsite"
and start it again when you're done:
    Start-ScheduledTask -TaskName "TShirtBrandWebsite"
#>

$RepoDir = "C:\Users\trick\OneDrive\Desktop\TShirtBrand\TCWeb"
$Python  = "C:\Users\trick\AppData\Local\Programs\Python\Python314\python.exe"
$EnvFile = "D:\TCData\.env"
$LogFile = Join-Path $RepoDir "waitress.supervisor.log"

function Write-Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Add-Content -Path $LogFile
}

# Explicit per-process, never an ambient/persistent env var -- see README.md
# for why TCWEB_ENV_FILE must never be set machine-wide.
$env:TCWEB_ENV_FILE = $EnvFile
Set-Location $RepoDir

if ($Python -match '\s') {
    Write-Log "Python path contains a space; run_server.ps1 needs quoting added before it can start the app."
    exit 1
}

Write-Log "Supervisor started (pid $PID)."

while ($true) {
    $listening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($listening) {
        # Something's already serving on 8000 -- most likely this script
        # itself was started twice, or someone started the app by hand.
        # Never start a second copy fighting over the same port.
        Write-Log "Port 8000 already in use (pid $($listening.OwningProcess)) -- not starting a second copy. Checking again in 30s."
        Start-Sleep -Seconds 30
        continue
    }

    Write-Log "Starting waitress..."
    # --trusted-proxy*: waitress DROPS X-Forwarded-* headers unless told which proxy to trust,
    # so without these flags Django never learns requests arrived over HTTPS (the Cloudflare
    # connector is the only thing that can reach 127.0.0.1:8000). Keep them in step with the
    # README's launch command.
    # cmd.exe does the redirection: it appends the program's raw output. PowerShell 5.1's
    # own 1>>/2>> would re-encode it as UTF-16, leaving the logs unreadable by most tools.
    # (No quoting needed: the Python path has no spaces -- checked once at the top.)
    cmd.exe /c "$Python -m waitress --listen=127.0.0.1:8000 --trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto config.wsgi:application 1>>waitress.log 2>>waitress.err.log"

    Write-Log "waitress exited (exit code $LASTEXITCODE). Restarting in 5 seconds."
    Start-Sleep -Seconds 5
}
