# Three-Mains Audit — Phase 0

Timestamp: `2026-07-04 03:25:00`

Scope: **Canonical Alpha lives in `L:\Continue\Viv\`**. The scan considered broader `L:\Continue` so we know what to absorb, but this phase only writes inside `L:\Continue\Viv`.

Registry: `L:\Continue\Viv\foundation\artifacts\audit\three_mains_registry.json`

---

## Doctrine

The three mains are the only Alpha operator CLI surface:

Alpha is Viv-first because **the CPU is Viv** — the deterministic neuro-symbolic automaton. **The GPU is the persona and human interface** — a later transformer lane, optional/plugin, based on a non-RLHF base model trained directly by Travis so humans can digest Viv's work.

| Main | Owns |
| ------ | ------ |
| `rid_main.py` | CPU-first RID: telemetry, captures, Master S_n, piston/coolant ops, plots, CPU black-hole plant science |
| `auto_main.py` | Agentic/autonomous: loop, gates, journal, runtime, worker queue, supervisor |
| `uml_main.py` | Calculator/language: eval, verify, trace, corpus, written/spoken prep |

Implementation belongs in `foundation/lib/`. The mains import libraries. They do **not** call each other as CLIs.

Housekeeping outside `Viv` is deferred until Alpha is rebuilt.

---

## Phase 0 Results

| Classification | Count | Meaning |
| ---------------- | ------- | --------- |
| `absorb_into_rid` | 9 | RID surfaces to pull into `rid_main.py` |
| `absorb_into_auto` | 1 | Viv-local auto surface to fold into `auto_main.py` |
| `absorb_into_uml` | 1 | Language/corpus surface to expose in `uml_main.py` |
| `bridge_temp` | 5 | External runtime pieces currently bridged; target vendor/rebuild into Viv |
| `keep_in_lib` | 8 | Shared implementation, not CLI |
| `housekeeping_later` | 4 | External duplicate/lane; do not mutate during Alpha |
| `edge_only` | 1 | Deferred demo/model lane |
| `deprecate` | 1 | Duplicate CLI after absorption |

---

## RID Absorption Targets

Immediate Phase 1 work:

| Source | Target |
| -------- | -------- |
| `rid_stability_main.py` | `rid_main.py stability` and `capture --kind coolant` |
| `scripts/foundation_health.py` / `plant_capture_status.py` | `rid_main.py status` |
| `piston_core.py` | `rid_main.py piston halt\|resume\|govern\|status` |
| `black_hole_main.py` | CPU black-hole commands in `rid_main.py`; GPU/coupled/visual paths remain optional plugin evidence |
| `rid_plot_main.py` | `rid_main.py plot --master` |
| `rid_cube_main.py` | `rid_main.py cube` |

Keep as implementation:

- `lib/rid_feed.py`
- `lib/master_rid.py`
- `lib/plant_master_capture.py`
- `lib/plant_piston_bridge.py`
- `lib/stability_capture.py`

---

## Auto Absorption Targets

Alpha target is still `auto_main.py autonomous --interval 1`.

Next auto work after RID:

| Source | Target |
| -------- | -------- |
| `lib/auto_run.py` | remove/deprecate `run`/`loop`; use `autonomous` only |
| `FSAA/scripts/agentic_runtime.py` | `auto_main.py runtime tick\|status`; target vendor into Viv lib |
| `FSAA/scripts/agentic_worker_cli.py` | `auto_main.py worker resume\|pause\|status\|enqueue`; target vendor into Viv lib |
| `FSAA/scripts/agentic_supervisor.py` | `auto_main.py supervisor watch` or autonomous stall-watch option |
| `automation/master_ai_heartbeat_service.py` | `auto_main.py heartbeat`; target Viv-local implementation |

External queue and launcher cleanup is marked `housekeeping_later`.

---

## UML Absorption Targets

After RID and auto:

| Source | Target |
| -------- | -------- |
| `lib/uml_engine.py` REPL-only features | `uml_main.py verify`, `dual-eval`, `trace`, `convert`, `b52`, `vars` |
| `lib/train_corpus.py` | `uml_main.py corpus build` |
| `lib/uml_engine.py` direct `__main__` | deprecate; `uml_main.py` only |

Luna/AIOS_V2 external UML import cleanup is `housekeeping_later`.

---

## Deferred Housekeeping

Do not edit these until the operator explicitly starts housekeeping:

- `L:\Continue\FSAA` duplicate launchers and runtime roots
- `L:\Continue\automation` PS1/BAT launchers, headless runner, 3_body lane
- Luna / AIOS_V2 imports and handoff readers
- Steel_Brain legacy UML copies

They are inventoried only so Alpha can absorb needed behavior into `Viv`.

---

## Next Step

Start Phase 1: rebuild the RID pillar surface in `rid_main.py`, beginning with:

1. `rid_main.py status`
2. unified `rid_main.py capture --kind coolant|coupled|core_spread`
3. Master S_n in coolant/stability capture
4. `plot --master`
