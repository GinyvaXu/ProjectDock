# ProjectDock local iteration reinstall (uninstall old -> install latest Setup -> health check).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File reinstall_local.ps1 [-Setup <path>] [-NoVerify]
param(
    [string]$Setup = "",
    [switch]$NoVerify
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\ProjectDock"
$HealthUrl = "http://127.0.0.1:8765/api/health"

function Stop-ProjectDock {
    Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "ProjectDock*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
}

function Wait-Health([int]$Seconds) {
    for ($i = 0; $i -lt ($Seconds * 2); $i++) {
        try { return Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2 } catch { Start-Sleep -Milliseconds 500 }
    }
    return $null
}

# 1) locate Setup package (explicit path > newest under versions/*/dist)
if (-not $Setup) {
    $cand = Get-ChildItem (Join-Path $Root "versions") -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ChildItem (Join-Path $_.FullName "dist") -Filter "ProjectDock_Setup_v*.exe" -File -ErrorAction SilentlyContinue
    }
    $latest = $cand | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "No Setup package found. Build it first: .venv\Scripts\python.exe build_setup.py" }
    $Setup = $latest.FullName
}
if (-not (Test-Path $Setup)) { throw "Setup not found: $Setup" }
Write-Host "[reinstall] Setup: $Setup"

# 2) stop running app
Stop-ProjectDock

# 3) uninstall installed version (if any)
$unins = Join-Path $InstallDir "unins000.exe"
if (Test-Path $unins) {
    Write-Host "[reinstall] Uninstalling installed version..."
    $p = Start-Process -FilePath $unins -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
    $null = $p.WaitForExit(300000)
    Start-Sleep -Milliseconds 800
    Write-Host "[reinstall] Uninstall exit: $($p.ExitCode)"
} else {
    Write-Host "[reinstall] No installed version found; skip uninstall."
}

# 4) install new Setup (silent; installer self-cleans old program files)
Write-Host "[reinstall] Installing..."
$p2 = Start-Process -FilePath $Setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
$null = $p2.WaitForExit(600000)
if ($p2.ExitCode -ne 0) { throw "Setup failed with exit code $($p2.ExitCode)" }
Write-Host "[reinstall] Install exit: 0"

# 5) verify: poll health; launch app if not auto-started
if (-not $NoVerify) {
    $h = Wait-Health 30
    if (-not $h) {
        $exe = Get-ChildItem $InstallDir -Filter "ProjectDock_v*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exe) {
            Write-Host "[reinstall] App not running; launching $($exe.Name)"
            Start-Process -FilePath $exe.FullName | Out-Null
            $h = Wait-Health 30
        }
    }
    if ($h) {
        Write-Host "[reinstall] OK: ProjectDock v$($h.version) running, root=$($h.root)"
    } else {
        Write-Host "[reinstall] WARN: health check failed ($HealthUrl)."
        exit 1
    }
}
Write-Host "[reinstall] Done."
