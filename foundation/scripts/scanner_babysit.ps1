param(
    [string]$VenvPython = "L:\Continue\.venv\Scripts\python.exe",
    [string]$ScriptPath = "L:\Continue\Viv\foundation\scripts\file_index_system.py",
    [string]$DbPath = "L:\Continue\Viv\artifacts\file_index\full_machine_baseline_v2.db",
    [string]$HashLogPath = "L:\Continue\Viv\artifacts\file_index\logs\full_machine_baseline_v2_hash_continue.log",
    [string]$BabysitLogPath = "L:\Continue\Viv\artifacts\file_index\logs\scanner_babysit_hash_continue.log",
    [string]$ResumeScanId = "20260728T090105Z",
    [int]$DurationMinutes = 480,
    [int]$IntervalSeconds = 300,
    [int]$HashWorkers = 4,
    [int]$CheckpointEvery = 5000,
    [int]$BatchCommitEvery = 2000
)

$ErrorActionPreference = "Stop"

function Write-BabysitLog {
    param([string]$Message)
    $utc = (Get-Date).ToUniversalTime().ToString("s") + "Z"
    $line = "utc=$utc $Message"
    Add-Content -Path $BabysitLogPath -Value $line -Encoding utf8
    Write-Output $line
}

function Get-ScannerProcs {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "python" -and
        $_.CommandLine -like "*file_index_system.py*" -and
        $_.CommandLine -like "*full_machine_baseline_v2.db*" -and
        $_.CommandLine -like "*scan-update*"
    }
}

function Start-ScannerDetached {
    $argList = @(
        "`"$ScriptPath`"",
        "--db", "`"$DbPath`"",
        "--log-file", "`"$HashLogPath`"",
        "--verbose", "scan-update",
        "--resume-scan-id", $ResumeScanId,
        "--hash-workers", "$HashWorkers",
        "--checkpoint-every", "$CheckpointEvery",
        "--batch-commit-every", "$BatchCommitEvery"
    ) -join " "

    $proc = Start-Process -FilePath $VenvPython -ArgumentList $argList `
        -WorkingDirectory "L:\Continue\Viv" `
        -WindowStyle Hidden `
        -PassThru
    return $proc
}

# Ensure log dir exists
$logDir = Split-Path -Parent $BabysitLogPath
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$start = Get-Date
$deadline = $start.AddMinutes($DurationMinutes)
Write-BabysitLog ("BABYSIT_START deadline_utc={0} interval_s={1} duration_min={2} hash_log={3}" -f `
    (($deadline.ToUniversalTime().ToString("s") + "Z"), $IntervalSeconds, $DurationMinutes, $HashLogPath))

while ((Get-Date) -lt $deadline) {
    $procs = @(Get-ScannerProcs)
    $running = $procs.Count -gt 0
    $pids = @($procs | ForEach-Object { $_.ProcessId }) -join ","
    if (-not $pids) { $pids = "none" }

    $aliveDetail = "process_exists=false"
    if ($running) {
        $cpuBits = @()
        foreach ($p in $procs) {
            try {
                $gp = Get-Process -Id $p.ProcessId -ErrorAction Stop
                $cpuBits += ("pid={0} cpu_s={1:N1} ws_mb={2:N0}" -f $p.ProcessId, $gp.CPU, ($gp.WorkingSet64 / 1MB))
            } catch {
                $cpuBits += ("pid={0} vanished" -f $p.ProcessId)
            }
        }
        $aliveDetail = "process_exists=true " + ($cpuBits -join "; ")
    }

    $tail = @()
    if (Test-Path $HashLogPath) {
        $tail = @(Get-Content -Path $HashLogPath -Tail 80 -ErrorAction SilentlyContinue)
    }

    $completed = $false
    foreach ($line in $tail) {
        if ($line -match '"ok"\s*:\s*true' -and $line -match 'scan_update') {
            $completed = $true
        }
        if ($line -match '"mode"\s*:\s*"scan_update"' -and ($tail -join "`n") -match '"ok"\s*:\s*true') {
            $completed = $true
        }
        if ($line -match "HASH_COMPLETE|hash_phase complete|scan_update complete") {
            $completed = $true
        }
    }
    # Also detect JSON result block written at end of successful run
    $tailText = $tail -join "`n"
    if ($tailText -match '"ok"\s*:\s*true' -and $tailText -match '"mode"\s*:\s*"scan_update"' -and -not $running) {
        $completed = $true
    }

    if ($completed -and -not $running) {
        Write-BabysitLog "SCAN_COMPLETED hash_phase_finished=true"
        break
    }

    $lastProgress = ($tail | Where-Object { $_ -match "progress seen=|hash_progress|hash_phase" } | Select-Object -Last 1)
    if (-not $lastProgress) { $lastProgress = "none_or_quiet_load_expected" }

    $logAgeMin = -1
    if (Test-Path $HashLogPath) {
        $logAgeMin = [int]((Get-Date) - (Get-Item $HashLogPath).LastWriteTime).TotalMinutes
    }

    # Long silence during duplicate-size / candidate load is expected; still require live process.
    if ($running) {
        Write-BabysitLog ("CHECKPOINT running=true pids={0} log_age_min={1} {2} progress={3}" -f `
            $pids, $logAgeMin, $aliveDetail, $lastProgress)
        if ($logAgeMin -ge 30) {
            Write-BabysitLog ("NOTE long_log_silence_min={0} treated_as_expected_if_alive=true {1}" -f $logAgeMin, $aliveDetail)
        }
    } else {
        Write-BabysitLog "INCIDENT type=process_not_running action=detached_resume"
        try {
            $launched = Start-ScannerDetached
            Start-Sleep -Seconds 15
            $recheck = @(Get-ScannerProcs)
            $ok = $recheck.Count -gt 0
            $newPids = @($recheck | ForEach-Object { $_.ProcessId }) -join ","
            if (-not $newPids) { $newPids = "none" }
            Write-BabysitLog ("RESUME_RESULT launched_pid={0} running={1} pids={2}" -f $launched.Id, $ok, $newPids)
            if (-not $ok) {
                Write-BabysitLog "FATAL resume_failed breaking"
                break
            }
        } catch {
            Write-BabysitLog ("FATAL resume_exception={0}" -f $_.Exception.Message)
            break
        }
    }

    Start-Sleep -Seconds $IntervalSeconds
}

Write-BabysitLog "BABYSIT_END"
