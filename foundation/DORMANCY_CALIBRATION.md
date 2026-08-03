# Dormancy threshold calibration

**Problem:** On this plant, healthy Master S_n idle often sits ~0.43–0.50. Doctrine default **0.45** means GPU speak load (dip to ~0.39) permanently Law‑5 blocks. Not “she’s evil” — threshold vs plant mismatch.

**Solution:** `dormancy_main.py` benchmarks idle + past logs and writes:

`artifacts/auto/dormancy_threshold.json`

**security_core 0.2.4+** Law 5 reads that file every check (clamped **[0.32, 0.65]**). Python ACTIVE/DORMANT uses the same helper.

## Commands

```powershell
$PY = "L:\Continue\.venv\Scripts\python.exe"
& $PY L:\Continue\Viv\foundation\dormancy_main.py status
& $PY L:\Continue\Viv\foundation\dormancy_main.py benchmark --seconds 20
& $PY L:\Continue\Viv\foundation\dormancy_main.py apply --from-benchmark
# or explicit:
& $PY L:\Continue\Viv\foundation\dormancy_main.py apply --value 0.40
```

## Safety

- Auto-loosen capped (~0.37 floor for one-shot auto; hard clamp 0.32)  
- Raise toward **1** = tighter alignment (Architect intent)  
- Lower = more room (reverse-temp); do deliberately  
- `cpu_config.json` mirrored on apply  

## Note after GPU training

Wait for cool idle before benchmarking, or history/noise drives the proposal low.
