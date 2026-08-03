# A/B: RID-on-PID Heater (`ab_rid_pid_heater_v1`)

**Verdict:** INCONCLUSIVE (no_clear_safety_delta)  
**Generated:** 2026-07-16T17:37:27.222146+00:00  
**Contract:** RID layers on PID — never replaces PID.

## Baseline (PID alone)

| Metric | Value |
|--------|-------|
| IAE | 6134.4223 |
| Overshoot °C | 0.0 |
| Mean abs error | 51.1202 |
| Min RLE | 0.361942 |
| Min S_n | 0.701407 |

## Pilot (RID on PID)

| Metric | Value |
|--------|-------|
| IAE | 6134.4223 |
| Overshoot °C | 0.0 |
| Mean abs error | 51.1202 |
| Min RLE | 0.361942 |
| Min S_n | 0.701407 |
| Duty clamps | 0 |
| Interlock trips | 0 |

## Deltas (pilot − baseline)

- IAE: 0.0
- overshoot_c: 0.0
- min_rle: 0.0
- min_sn: 0.0

Lower IAE / overshoot and higher min RLE support **PROVED**. Clear tracking regression without safety gain → **DISPROVED**.
