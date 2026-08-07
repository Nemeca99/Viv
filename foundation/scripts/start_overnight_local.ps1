# Start overnight local AIOS runner detached (survives agent/session exit).
# Usage: powershell -File foundation/scripts/start_overnight_local.ps1 [-Hours 10] [-CycleMin 25]

param(
    [double]$Hours = 10,
    [double]$CycleMin = 25
)

$ErrorActionPreference = "Stop"

$Python = "L:\Continue\.venv\Scripts\python.exe"
$Script = "L:\Continue\Viv\foundation\scripts\run_aios_overnight_local_v1.py"
$WorkDir = "L:\Continue\Viv"
$ArtifactRoot = "L:\Continue\Viv\foundation\artifacts\auto\overnight_local"
$ConsoleLog = Join-Path $ArtifactRoot "overnight_console.log"
$ConsoleErr = Join-Path $ArtifactRoot "overnight_console.err.log"

New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null

if (-not (Test-Path $Python)) {
    Write-Error "Python not found: $Python"
}
if (-not (Test-Path $Script)) {
    Write-Error "Overnight script not found: $Script"
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$argList = @(
    "-B",
    "`"$Script`"",
    "--hours", "$Hours",
    "--cycle-min", "$CycleMin",
    "--run-stamp", $stamp
) -join " "

# Detached via cmd so stdout+stderr can share one console log (Start-Process cannot).
$cmd = " `"$Python`" $argList >> `"$ConsoleLog`" 2>&1 "
$proc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", $cmd `
    -WorkingDirectory $WorkDir `
    -WindowStyle Hidden `
    -PassThru

Start-Sleep -Seconds 2

# Resolve python child PID (cmd may exit after spawn depending on /c; prefer python).
$py = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*run_aios_overnight_local_v1.py*" -and $_.CommandLine -like "*$stamp*" } |
    Select-Object -First 1

$pidOut = if ($py) { $py.ProcessId } else { $proc.Id }

# Write a small pointer next to console log
@(
    "started_utc=$stamp"
    "launcher_pid=$($proc.Id)"
    "python_pid=$pidOut"
    "console_log=$ConsoleLog"
    "run_dir=$ArtifactRoot\$stamp"
) | Set-Content -Path (Join-Path $ArtifactRoot "OVERNIGHT_START.txt") -Encoding UTF8

Write-Host "STARTED pid=$pidOut"
Write-Host "launcher_pid=$($proc.Id)"
Write-Host "console_log=$ConsoleLog"
Write-Host "run_stamp=$stamp"
Write-Host "run_dir=$ArtifactRoot\$stamp"
Write-Output $pidOut
