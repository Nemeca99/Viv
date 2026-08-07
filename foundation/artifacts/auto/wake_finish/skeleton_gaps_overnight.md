# Skeleton gaps overnight (2026-08-07)

## Landed

- Bus slots (PARTIAL stubs): `perception_plan`, `ethics_plan`, `federation_plan`, `hardware_plan`
- Adapters: `aios_adapter_perception.py`, `aios_adapter_ethics.py`, `aios_adapter_federation.py`
- Catalog cores: `perception_core`, `ethics_core`, `federation_core`
- `subagent_spawn` **BOUND** to `lib.aios_subagent_v1` (plan-only/SKIP worker; not deep cognition)
- Map: `scripts/run_aios_skeleton_v1.py --plan-only` → `LATEST.json` + `skeleton_map_latest.json`

## Still vacant (compute-core wire-in)

| Slot | Fill | Note |
| --- | --- | --- |
| `uml_invoke` | **VACANT** | Nested-PEMDAS / UML invoke — deliberately empty for compute core |

## Coverage (stamp `20260807T093018Z`)

- Systems: **39** · structural **100%** · PARTIAL **23.1%** · SKELETON **76.9%**
- Bus: **13** slots · filled **92.3%** · vacant **7.7%** (`uml_invoke`)
- Gap stubs in map: `perception_core`, `ethics_core`, `federation_core` = SKELETON

## Do not

- AIOS start/stop · GPU_LONG · soft-0.99 · 120s plant · federation activation · fake BUILT

## Re-run

```powershell
cd L:\Continue\Viv
L:\Continue\.venv\Scripts\python.exe foundation\scripts\run_aios_skeleton_v1.py --plan-only
```
