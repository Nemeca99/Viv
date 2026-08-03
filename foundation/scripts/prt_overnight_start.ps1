# Start PRT overnight loop detached (sleep-safe).
# Usage:
#   .\prt_overnight_start.ps1
#   .\prt_overnight_start.ps1 -MaxRounds 6 -Cooldown 600
#   .\prt_overnight_start.ps1 -DryRun

param(
    [int]$MaxRounds = 0,
    [double]$MaxHours = 0,
    [double]$Cooldown = -1,
    [switch]$DryRun,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
$PY = "L:\Continue\.venv\Scripts\python.exe"
$Main = "L:\Continue\Viv\foundation\prt_main.py"
$Out = "L:\Continue\Viv\foundation\artifacts\audit\prt_overnight_console.log"
$Err = "L:\Continue\Viv\foundation\artifacts\audit\prt_overnight_console.err"

$argsList = @($Main, "night", "start")
if ($MaxRounds -gt 0) { $argsList += @("--max-rounds", "$MaxRounds") }
if ($MaxHours -gt 0) { $argsList += @("--max-hours", "$MaxHours") }
if ($Cooldown -ge 0) { $argsList += @("--cooldown", "$Cooldown") }
if ($DryRun) { $argsList += "--dry-run" }

Write-Host "PRT overnight: $($argsList -join ' ')"
if ($Foreground) {
    & $PY @argsList
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
$p = Start-Process -FilePath $PY -ArgumentList $argsList `
    -RedirectStandardOutput $Out `
    -RedirectStandardError $Err `
    -WindowStyle Hidden `
    -PassThru
Write-Host "Started PID $($p.Id)"
Write-Host "Console: $Out"
Write-Host "Halt:   $PY $Main night halt"
Write-Host "Status: $PY $Main night status"
