# A/B: Piston Ghost vs Live (`ab_piston_ghost_vs_live_v1`)

**Verdict:** COMPARABLE  
**Generated:** 2026-07-18T08:53:05.256082+00:00  
**Telemetry epoch start:** 2026-07-17T05:06:46.840251+00:00

## Baseline (ghost / stale piston)

| Metric | Value |
|--------|-------|
| Cycles | 1800 (valid sample: True) |
| REWARD rate | 0.06 |
| Self-emit rate | 0.1839 (331/1800) |
| PUNISH rate | 0.7683 |
| Window | 2026-07-16T06:10:52.492567+00:00 → 2026-07-17T04:54:50.992284+00:00 |

## Pilot (live piston_background)

| Metric | Value |
|--------|-------|
| Cycles | 1830 (valid sample: True) |
| REWARD rate | 0.006 |
| Self-emit rate | 0.2235 (409/1830) |
| PUNISH rate | 0.9071 |
| Trust modes | {'none': 24, 'incomplete': 1142, 'ADAPT': 210, 'SOLO': 63, 'MIXED': 289, 'COPY_BLIND': 73, 'FOLLOW': 29} |
| Follow rate (FOLLOW/(FOLLOW+ADAPT)) | 0.1213 |

## Deltas (pilot − baseline)

- reward_rate: -0.054
- self_emit_rate: 0.0396
- punish_rate: 0.1388

## Notes

- Promotion metrics use `telemetry_epoch_start` filter in `lib/prt_stage.py`.
- Do not claim improvement until pilot window has ≥ 30 Phase-2 cycles.
