# COMMIT_READY (overnight pack)

**Do not commit/push from this pack until operator wakes.** Tree is intentionally unstaged.

- Branch: `codex/viv-v60-preflight-backup` @ `def895e`
- Already pushed: `def895e` — *Add AIOS automation preflight, training orchestration, and uml_request canary ingress.* (`origin/codex/viv-v60-preflight-backup`)
- Created UTC: 2026-08-07T09:29:12Z
- COLD_START: not edited (other agents)

## Path verification

All key scripts/libs **exist**.

| path | exists | bytes | git |
|---|---|---|---|
| `foundation/lib/aios_system_smoke_v1.py` | True | 22905 | untracked |
| `foundation/scripts/run_aios_system_smoke_v1.py` | True | 4618 | untracked |
| `foundation/scripts/test_aios_system_smoke_v1.py` | True | 2904 | untracked |
| `foundation/lib/aios_skeleton_bus.py` | True | 10581 | untracked |
| `foundation/lib/aios_skeleton_stub.py` | True | 2675 | untracked |
| `foundation/lib/aios_skeleton_subagent_profiles.py` | True | 2095 | untracked |
| `foundation/lib/aios_subagent_v1.py` | True | 28987 | untracked |
| `foundation/scripts/run_aios_skeleton_v1.py` | True | 2480 | untracked |
| `foundation/scripts/run_aios_subagent_v1.py` | True | 5209 | untracked |
| `foundation/scripts/test_aios_subagent_v1.py` | True | 4260 | untracked |
| `foundation/lib/uml_bridge_security_gate.py` | True | 22942 | untracked |
| `foundation/scripts/test_uml_bridge_security_gate_v1.py` | True | 6407 | untracked |
| `foundation/scripts/run_field_scoped_bridge_canary_v1.py` | True | 37863 | modified |
| `foundation/lib/manual_oracle.py` | True | 4546 | clean_tracked |
| `foundation/scripts/test_manual_oracle_v1.py` | True | 1389 | clean_tracked |

## Excludes (noise)

- COLD_START.md (other agents own; do not include unless operator asks)
- foundation/artifacts/audit/session_journal.md
- foundation/artifacts/auto/agentic/CURRENT_TASK.json
- sandbox/journal/*
- vault/* / gpu packs / *.pt / *.gguf / weight packs
- foundation/models/Training/** (SLM/training lane — separate commit series)
- foundation/lib/node_federation*.py + federation tests (out of tonight theme)
- foundation/docs/VIV_SLM_*.md, drive-download zips, docs/external/
- foundation/artifacts/auto/** receipts (evidence, not source pack)
- models/ top-level untracked

## Suggested commits (1–3)

### 1) Skeleton + smoke + subagent

**Message:** `Add AIOS skeleton bus, system smoke, and subagent runners.`

Wake priority from WAKE_FINISH: land smoke+skeleton+subagent source before broader automation.

Files (11; ~0 KiB):

- `??` `foundation/lib/aios_system_smoke_v1.py` (22905 B)
- `??` `foundation/scripts/run_aios_system_smoke_v1.py` (4618 B)
- `??` `foundation/scripts/test_aios_system_smoke_v1.py` (2904 B)
- `??` `foundation/lib/aios_skeleton_bus.py` (10581 B)
- `??` `foundation/lib/aios_skeleton_stub.py` (2675 B)
- `??` `foundation/lib/aios_skeleton_subagent_profiles.py` (2095 B)
- `??` `foundation/lib/aios_subagent_v1.py` (28987 B)
- `??` `foundation/scripts/run_aios_skeleton_v1.py` (2480 B)
- `??` `foundation/scripts/run_aios_subagent_v1.py` (5209 B)
- `??` `foundation/scripts/test_aios_subagent_v1.py` (4260 B)
- `clean_tracked` `foundation/scripts/test_manual_oracle_v1.py` (1389 B)

- Note: manual_oracle.py is already tracked/clean; include only untracked test_manual_oracle_v1.py
- Note: Do not include COLD_START.md or system_smoke artifact receipts in this commit unless operator asks

### 2) Security gate + canary fix

**Message:** `Add UML bridge security gate and harden field-scoped canary ingress.`

Security gate is new; canary/bridge are post-def895e fixes on already-pushed canary ingress.

Files (4; ~0 KiB):

- `??` `foundation/lib/uml_bridge_security_gate.py` (22942 B)
- `??` `foundation/scripts/test_uml_bridge_security_gate_v1.py` (6407 B)
- `M` `foundation/lib/uml_field_scoped_bridge.py` (17487 B)
- `M` `foundation/scripts/run_field_scoped_bridge_canary_v1.py` (37863 B)

- Note: uml_field_scoped_bridge.py and run_field_scoped_bridge_canary_v1.py were partially in def895e; this commit is the overnight fix delta
- Note: Keep canary default OFF; enable only via --enable-canary

### 3) Core automation expansion

**Message:** `Expand AIOS core automation with service/cognitive/RID runners and core adapters.`

Narrow third commit for automation + cores/adapters/docs that smoke/skeleton depend on for fuller coverage.

Files (93; ~0 KiB):

- `M` `foundation/lib/aios_core_automation.py` (37648 B)
- `M` `foundation/scripts/run_aios_core_automation_v1.py` (8633 B)
- `M` `foundation/scripts/test_aios_core_automation_v1.py` (4533 B)
- `M` `foundation/lib/aios_systems.py` (15706 B)
- `M` `foundation/lib/aios_systems_preflight.py` (29886 B)
- `M` `foundation/lib/core_contracts.py` (11335 B)
- `??` `foundation/lib/cognitive_cores_automation_v1.py` (8974 B)
- `??` `foundation/lib/service_cores_automation.py` (13433 B)
- `??` `foundation/lib/rid_plant_automation_v1.py` (21742 B)
- `??` `foundation/scripts/run_cognitive_cores_automation_v1.py` (5275 B)
- `??` `foundation/scripts/run_service_cores_automation_v1.py` (4747 B)
- `??` `foundation/scripts/run_rid_plant_automation_v1.py` (4931 B)
- `??` `foundation/scripts/test_cognitive_cores_automation_v1.py` (4012 B)
- `??` `foundation/scripts/test_service_cores_automation_v1.py` (3191 B)
- `??` `foundation/scripts/test_rid_plant_automation_v1.py` (5751 B)
- `??` `foundation/scripts/run_carma_automation_v1.py` (885 B)
- `??` `foundation/scripts/run_consciousness_automation_v1.py` (909 B)
- `??` `foundation/scripts/run_voice_contract_automation_v1.py` (15278 B)
- `??` `foundation/lib/data_core.py` (16513 B)
- `??` `foundation/lib/dream_core.py` (13020 B)
- `??` `foundation/lib/enterprise_core.py` (14910 B)
- `??` `foundation/lib/fractal_core.py` (7878 B)
- `??` `foundation/lib/game_core.py` (10616 B)
- `??` `foundation/lib/infra_core.py` (4524 B)
- `??` `foundation/lib/main_core.py` (10683 B)
- `??` `foundation/lib/marketplace_core.py` (7343 B)
- `??` `foundation/lib/music_core.py` (6769 B)
- `??` `foundation/lib/privacy_core.py` (7796 B)
- `??` `foundation/lib/rag_core.py` (11436 B)
- `??` `foundation/lib/support_core.py` (9736 B)
- `??` `foundation/lib/utils_core.py` (15279 B)
- `M` `foundation/lib/carma_core.py` (10196 B)
- `M` `foundation/lib/consciousness_core.py` (15880 B)
- `??` `foundation/lib/aios_adapter_data.py` (4684 B)
- `??` `foundation/lib/aios_adapter_fractal.py` (2385 B)
- `??` `foundation/lib/aios_adapter_game.py` (2557 B)
- `??` `foundation/lib/aios_adapter_infra.py` (2310 B)
- `??` `foundation/lib/aios_adapter_marketplace.py` (2065 B)
- `??` `foundation/lib/aios_adapter_music.py` (1656 B)
- `M` `foundation/lib/aios_adapter_audit.py` (13816 B)
- `M` `foundation/lib/aios_adapter_carma.py` (5423 B)
- `M` `foundation/lib/aios_adapter_consciousness.py` (13485 B)
- `M` `foundation/lib/aios_adapter_dream.py` (12741 B)
- `M` `foundation/lib/aios_adapter_luna.py` (10705 B)
- `M` `foundation/lib/aios_adapter_privacy.py` (2194 B)
- `M` `foundation/lib/aios_adapter_support.py` (9030 B)
- `M` `foundation/lib/aios_adapter_utils.py` (13689 B)
- `M` `foundation/scripts/test_carma_core_v1.py` (2208 B)
- `??` `foundation/scripts/test_data_core_v1.py` (3479 B)
- `??` `foundation/scripts/test_dream_core_v1.py` (2878 B)
- `??` `foundation/scripts/test_enterprise_core_v1.py` (4387 B)
- `??` `foundation/scripts/test_fractal_core_v1.py` (2246 B)
- `??` `foundation/scripts/test_game_core_v1.py` (2940 B)
- `??` `foundation/scripts/test_infra_core_v1.py` (2855 B)
- `??` `foundation/scripts/test_main_core_v1.py` (3794 B)
- `??` `foundation/scripts/test_marketplace_core_v1.py` (2711 B)
- `??` `foundation/scripts/test_music_core_v1.py` (2480 B)
- `??` `foundation/scripts/test_privacy_core_v1.py` (3058 B)
- `??` `foundation/scripts/test_rag_core_v1.py` (3378 B)
- `??` `foundation/scripts/test_support_core_v1.py` (2714 B)
- `??` `foundation/scripts/test_utils_core_v1.py` (4222 B)
- `??` `foundation/scripts/test_carma_adapter_cpu_plan_v1.py` (1604 B)
- `??` `foundation/scripts/test_consciousness_adapter_cpu_plan_v1.py` (2092 B)
- `??` `foundation/scripts/test_data_adapter_cpu_plan_v1.py` (1565 B)
- `??` `foundation/scripts/test_enterprise_adapter_cpu_plan_v1.py` (1844 B)
- `??` `foundation/scripts/test_fractal_adapter_cpu_plan_v1.py` (1087 B)
- `??` `foundation/scripts/test_game_adapter_cpu_plan_v1.py` (933 B)
- `??` `foundation/scripts/test_infra_adapter_cpu_plan_v1.py` (868 B)
- `??` `foundation/scripts/test_marketplace_adapter_cpu_plan_v1.py` (914 B)
- `??` `foundation/scripts/test_music_adapter_cpu_plan_v1.py` (918 B)
- `??` `foundation/scripts/test_privacy_adapter_cpu_plan_v1.py` (926 B)
- `??` `foundation/scripts/test_support_adapter_cpu_plan_v1.py` (1385 B)
- `??` `foundation/scripts/test_utils_adapter_cpu_plan_v1.py` (2020 B)
- `??` `foundation/docs/CARMA_CORE_V1.md` (2854 B)
- `??` `foundation/docs/CONSCIOUSNESS_CORE_V1.md` (3830 B)
- `??` `foundation/docs/DATA_CORE_V1.md` (1885 B)
- `??` `foundation/docs/DREAM_CORE_V1.md` (2480 B)
- `??` `foundation/docs/ENTERPRISE_CORE_V1.md` (2211 B)
- `??` `foundation/docs/FRACTAL_CORE_V1.md` (832 B)
- `??` `foundation/docs/GAME_CORE_V1.md` (1168 B)
- `??` `foundation/docs/INFRA_CORE_V1.md` (633 B)
- `??` `foundation/docs/LUNA_CORE_V1.md` (2692 B)
- `??` `foundation/docs/MAIN_CORE_V1.md` (2158 B)
- `??` `foundation/docs/MARKETPLACE_CORE_V1.md` (885 B)
- `??` `foundation/docs/MUSIC_CORE_V1.md` (797 B)
- `??` `foundation/docs/PRIVACY_CORE_V1.md` (789 B)
- `??` `foundation/docs/RAG_CORE_V1.md` (3348 B)
- `??` `foundation/docs/SUPPORT_CORE_V1.md` (1692 B)
- `??` `foundation/docs/UTILS_CORE_V1.md` (2109 B)
- `??` `foundation/docs/TEMPLATE_CORE_DISPOSITION.md` (592 B)
- `M` `foundation/BACKUP_CORE.md` (5285 B)
- `M` `foundation/VIV_BUILD_STATUS.md` (24264 B)
- `M` `foundation/triad_boundary_registry.json` (97984 B)

- Note: Larger than 1–2 but still source-sized (no weights/pt/vault)
- Note: Optional split later: (3a) automation runners only, (3b) cores+adapters+docs
- Note: luna_core.py has trivial 1-line delta — omit unless needed for consistency

## On wake

1. Review COMMIT_READY.md groups; stage group 1 first
1. git add listed paths only; do not add journals/CURRENT_TASK/vault/pt
1. Commit when ready (operator decision); push after local verify
1. Re-run skeleton system smoke after group 1 lands
1. Re-check canary CANARY_PASS with --enable-canary only

## Deferred (not in these three)

- foundation/lib/cpu_*.py / viv_ide.py / mouth contract tests (adjacent, not tonight theme)
- foundation/lib/node_federation*.py + tests
- foundation/models/Training/** and Viv-SLM probe/docs
- foundation/metacognition/**
- foundation/lib/qwen25_token_policy.py + tokenizer tests
- foundation/lib/viv_identity_personality.py / viv_slm_foundation.py
- foundation/lib/data/** package if present beyond data_core.py

