# Remove Python from C: (keeps L:\ project files). Run as normal user. Reboot after.
#Usage: powershell -ExecutionPolicy Bypass -File L:\Continue\Viv\foundation\scripts\python_remove_c_drive.ps1

$ErrorActionPreference = "Continue"
Write-Host "=== Python C: removal (L: projects untouched) ===" -ForegroundColor Cyan

$wingetIds = @(
    "Python.Python.3.12",
    "Python.Python.3.11",
    "Python.Python.3.14",
    "Python.Launcher",
    "Python.PythonInstallManager"
)
foreach ($id in $wingetIds) {
    Write-Host "winget uninstall $id ..."
    winget uninstall --id $id -e --silent 2>$null
}

$cPaths = @(
    "$env:LOCALAPPDATA\Programs\Python",
    "$env:LOCALAPPDATA\Python",
    "$env:APPDATA\Python",
    "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe",
    "$env:LOCALAPPDATA\Microsoft\WindowsApps\python3.exe"
)
foreach ($p in $cPaths) {
    if (Test-Path $p) {
        Write-Host "Removing $p"
        Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Strip Python entries from USER Path only (not system, not D: forge unless on C:)
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $keep = $userPath -split ';' | Where-Object {
        $_ -and $_ -notmatch '(?i)\\Python|\\python|Python311|Python312|Python310|Python314|PythonInstallManager|WindowsApps\\python'
    }
    $newPath = ($keep | Where-Object { $_ }) -join ';'
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Cleaned user PATH (Python C: entries removed)."
}

Write-Host ""
Write-Host "DONE. Reboot PC, then run:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File L:\Continue\Viv\foundation\scripts\python_install_l_drive.ps1"
