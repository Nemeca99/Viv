# Install Python 3.12 ONLY on L:\Python312, set PATH, create L:\Continue\.venv
# Run AFTER reboot from python_remove_c_drive.ps1
# Usage: powershell -ExecutionPolicy Bypass -File L:\Continue\Viv\foundation\scripts\python_install_l_drive.ps1

$ErrorActionPreference = "Stop"
$PyRoot = "L:\Python312"
$PyExe = Join-Path $PyRoot "python.exe"
$VenvPath = "L:\Continue\.venv"

Write-Host "=== Python L-drive-only install ===" -ForegroundColor Cyan

if (-not (Test-Path "L:\")) {
    throw "L: drive not found."
}

$installer = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
$url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"

if (-not (Test-Path $PyExe)) {
    Write-Host "Downloading Python 3.12.10 ..."
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    Write-Host "Installing to $PyRoot ..."
    New-Item -ItemType Directory -Force -Path $PyRoot | Out-Null
    $installerArgs = @(
        "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_test=0",
        "Include_doc=0", "Include_pip=1", "Include_launcher=0",
        "TargetDir=$PyRoot", "AssociateFiles=0", "Shortcuts=0"
    )
    Start-Process -FilePath $installer -ArgumentList $installerArgs -Wait -NoNewWindow
    if (-not (Test-Path $PyExe)) {
        throw "Install failed - $PyExe missing."
    }
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Already installed: $PyExe"
}

$pyScripts = Join-Path $PyRoot "Scripts"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) {
    $userPath = ""
}
$scrubbed = ($userPath -split ';' | Where-Object {
    $_ -and $_ -notmatch '(?i)\\Python|\\python|Python311|Python312|Python310|Python314'
}) -join ';'
$newPath = "$PyRoot;$pyScripts"
if ($scrubbed) {
    $newPath = "$newPath;$scrubbed"
}
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")
$env:Path = "$PyRoot;$pyScripts;" + $env:Path

& $PyExe --version
& $PyExe -m pip install --upgrade pip

if (Test-Path $VenvPath) {
    Write-Host "Removing broken venv $VenvPath ..."
    Remove-Item -LiteralPath $VenvPath -Recurse -Force
}
Write-Host "Creating venv $VenvPath ..."
& $PyExe -m venv $VenvPath
$venvPy = Join-Path $VenvPath "Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install psutil pyopencl nvidia-ml-py matplotlib numpy pygame-ce

Write-Host ""
Write-Host "DONE." -ForegroundColor Green
Write-Host "  System Python : $PyExe"
Write-Host "  Viv venv      : $venvPy"
Write-Host "  Test          : $venvPy L:\Continue\Viv\foundation\rid_main.py sample"
Write-Host ""
Write-Host "Close and reopen terminals (or reboot) so PATH picks up L:\Python312"
