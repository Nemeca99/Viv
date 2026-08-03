# L: Drive Housekeeping — Existing Tools

**Do not invent new cleanup scripts until these are exhausted.**  
Canonical toolchain lives under `L:/Continue/FSAA/scripts/` with PowerShell wrappers.

**Last full L: scan:** 2026-04 (597k files) — artifacts in `reports/structure_inventory/`  
**Policy:** move to `D:/LocalAi` with manifest; do not silent-delete (AIOS doctrine).

---

## Pipeline (in order)

```text
1. structure_inventory.py   → classify every file (read-only)
2. build_promote_map.py     → deterministic promote/archive/quarantine decisions
3. apply_promote_map.py     → copy-verify-move (dry-run / apply / what-if)
```

Supporting: `migration_firewall.py`, `generate_migration_fixture.py`, `audit_removed_inventory.py`

---

## Step 1 — Structure inventory (read-only scan)

| Item | Path |
|------|------|
| Script | `L:/Continue/FSAA/scripts/structure_inventory.py` |
| Wrapper | `L:/Continue/FSAA/run_structure_inventory.ps1` |
| Default scan | `L:/Continue` (README shows prior run used `L:/` whole drive) |
| Output | `L:/Continue/FSAA/reports/structure_inventory/` |

**Categories emitted:**

| Bucket | Meaning |
|--------|---------|
| `canonical_keep` | Belongs in cleaned FSAA/package boundary |
| `runtime_keep` | Active runtime tree still needed |
| `archive_keep` | History/logs — retain, don't promote |
| `candidate_review` | Real content, needs human decision |
| `candidate_remove` | Generated/cache — not architecture |

**Last known counts** (`reports/structure_inventory/README.md`):

| Bucket | Files |
|--------|------:|
| candidate_remove | 326,484 |
| runtime_keep | 155,258 |
| candidate_review | 113,005 |
| archive_keep | 2,473 |
| canonical_keep | 106 |

```powershell
cd L:\Continue\FSAA
.\run_structure_inventory.ps1 -ScanRoot "L:\" -ReportDir "L:\Continue\FSAA\reports\structure_inventory"
```

---

## Step 2 — Build promote map

| Item | Path |
|------|------|
| Script | `L:/Continue/FSAA/scripts/build_promote_map.py` |
| Wrapper | `L:/Continue/FSAA/run_build_promote_map.ps1` |
| Input | `candidate_review.txt` + policy JSON in report dir |
| Output | `promote_map.jsonl`, `promote_map_summary.json`, layout decisions |

Policies/schemas: `reports/structure_inventory/schemas/`, `promote_rules.json`, `layout_strategy.json`, `metadata_policy.json`

**Last promote-map build:** 2026-04-29 — 113,005 rows (mostly `quarantine` decisions)

```powershell
cd L:\Continue\FSAA
.\run_build_promote_map.ps1 -ScanRoot "L:\Continue"
```

---

## Step 3 — Apply promote map (mutating — dry-run first)

| Item | Path |
|------|------|
| Script | `L:/Continue/FSAA/scripts/apply_promote_map.py` |
| Wrapper | `L:/Continue/FSAA/run_apply_promote_map.ps1` |
| Firewall | `L:/Continue/FSAA/scripts/migration_firewall.py` |
| Stop switch | `L:/Continue/FSAA/STOP_RUN` |
| Run lock | `reports/structure_inventory/run.lock` |

**Modes:** `--dry-run`, `--what-if`, `--apply` (mutually exclusive apply vs dry-run)

```powershell
cd L:\Continue\FSAA
.\run_apply_promote_map.ps1 -DryRun
# only after review:
.\run_apply_promote_map.ps1 -Apply
```

Protected paths (firewall): `.git/`, `.cursor/`, recycle bins, anti-patterns.

---

## Other housekeeping / migration tools

| Tool | Path | Purpose |
|------|------|---------|
| **rebuild_runner.py** | `L:/Continue/FSAA/rebuild_runner.py` | Manifest-driven rebuild with `--dry-run` |
| **auto_rebuild_orchestrator.py** | `L:/Continue/FSAA/auto_rebuild_orchestrator.py` | Wraps rebuild_runner |
| **audit_removed_inventory.py** | `L:/Continue/FSAA/scripts/audit_removed_inventory.py` | Compare git-clean log vs current tree |
| **generate_migration_fixture.py** | `L:/Continue/FSAA/scripts/generate_migration_fixture.py` | Synthetic tree for promote-map tests |
| **check_codebase.py** | `L:/Continue/FSAA/scripts/check_codebase.py` | FSAA integrity checks |
| **stage_automation_migration** | via `automation/check_automation.ps1` | Automation folder staging (see roadmap below) |
| **Luna migration** | `FSAA/Luna/AIOS_V2/migration_v1_to_v2.py` | V1→V2 (legacy) |
| **inventory_refactor_staging.md** | `FSAA/docs/inventory_refactor_staging.md` | Staging notes |
| **inventory_py_rs_db_models.json** | `FSAA/docs/` | Py/Rust/DB model inventory |

**Automation-specific:** `L:/Continue/automation/docs/MIGRATION_WRAPPER_ROADMAP.md` — copy-only migration, shim rules, `check_automation.ps1` verification.

**Duplicate tree:** `L:/Continue/AIOS_Standalone/` mirrors many FSAA scripts — prefer **`L:/Continue/FSAA/`** as canonical.

---

## Artifact index (bootstrap state fast)

| Pointer | Path |
|---------|------|
| Run log index | `L:/Continue/FSAA/reports/run_log_index.json` |
| Promote map summary | `L:/Continue/FSAA/reports/structure_inventory/promote_map_summary.json` |
| Session journal | `L:/Continue/FSAA/reports/session_journal.md` |
| Local context index | `L:/Continue/FSAA/reports/local_context/context_index.json` |
| Pipeline docs | `L:/Continue/FSAA/docs/agent_context/PIPELINES.md` |
| Directory map | `L:/Continue/FSAA/docs/agent_context/DIRECTORY_MAP.md` |

---

## Viv-specific (not L:-wide housekeeping)

| Tool | Path |
|------|------|
| Doc index | `Viv/foundation/VIV_INDEX.md` |
| Alpha manual | `Viv/foundation/AIOS_ALPHA_MANUAL.md` |
| V1 read mirrors | `lib/aios_adapter_*.py` → `D:/LocalAi/AIOS_V1/` (Law 4 blocks cross-drive writes) |
| Archive doctrine | move stale assets to `D:/LocalAi`, not delete |

---

## Safe procedure (when you're ready)

1. **Do not run apply during AIFL overnight** (GPU + file moves conflict).
2. Refresh inventory: `run_structure_inventory.ps1` (whole `L:\` or scoped `L:\Continue`).
3. Review manifests: `canonical_keep.txt`, `candidate_review.txt`, `summary.json`.
4. Rebuild promote map if inventory changed.
5. **Always** `apply_promote_map.ps1 -DryRun` first; read action journals.
6. Human review `human_review_queue.jsonl` for edge cases.
7. Apply only with `STOP_RUN` absent and run lock clear.
8. Update `session_journal.md` + `.cursor/CHANGELOG.md` after any apply.

---

## What we should NOT do yet

- Build a new `L:/AIOS_MAP.md` generator from scratch (inventory already exists).
- Run `apply` without fresh dry-run on current tree (last inventory is **April 2026**).
- Delete anything — quarantine/archive to `D:/LocalAi` per policy.

**Next housekeeping session:** re-run Step 1 on `L:\`, diff against April manifests, then promote-map dry-run.
