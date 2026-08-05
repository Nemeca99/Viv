# Viv-SLM V34 AIFL preflight handoff

Created: 2026-08-04 UTC
Workspace: L:\Continue\Viv
Canonical Python: L:\Continue\.venv\Scripts\python.exe

## Start here

Read these files in order:

1. foundation/artifacts/auto/agentic/CURRENT_TASK.json
2. foundation/artifacts/audit/session_journal.md
3. foundation/artifacts/audit/VIV_SLM_VERSION_HISTORY.md
4. this handoff

This handoff is a checkpoint, not a claim that V34 training completed.

## Current disposition

V34, conflict-aware identity refinement with local AIFL feedback, is implemented and preflighted.

The following are verified:

- V34 source and focused tests pass.
- Source-derived AIFL feedback cases are locked to the existing V33 pair rows.
- The AIFL sensor is read-only during V34 evaluation.
- No global preference buffer is written.
- No global train gate is written.
- No Master S_n, live runtime, promotion, or deployment state is changed.
- Full foundation preflight is green.
- No V34 checkpoint or V34 training result exists yet.

Current task state:

PREFLIGHT_COMPLETE_AIFL_SENSOR_INTEGRATED_CANARY_PENDING

Current authority flags:

- training_authorized: false
- run_authorized: false
- promotion_authorized: false
- deployment_authorized: false
- live_runtime_mutation: false
- knowledge admission: closed

A future run requires the exact V34 task to be authorized and the trainer's explicit --authorize flag. Do not infer authorization from the user's historical general authorization.

## Why AIFL is being used

The local AIFL layer is a sensor and feedback mechanism for the custom Viv-SLM identity lane. It is not a replacement for the CPU boundary and it is not an automatic deployment system.

The established AIFL contract is:

self-ask -> draft responses -> shadow judge -> preference or hard-negative signal -> governed training gate

For this V34 lane:

- The existing read-only score_draft sensor is used.
- judge_and_select is not called.
- The global preference buffer is not touched.
- The global train gate is not touched.
- A synthetic S_n value of 0.5 is used only as a sensor input.
- The synthetic value does not mutate Master S_n.
- AIFL feedback is retained in the run-local evidence pack and checkpoint metadata.
- The CPU mouth boundary remains the final authority for claims, telemetry containment, and fallback.

The older AIFL documentation and implementation were built around the older Qwen/OpenAster lane. They must not be described as already training or controlling the custom Viv-SLM.

## V28 through V34 lineage

| Version | Role | Validation evidence | Disposition |
| --- | --- | --- | --- |
| V28 | Behavioral reference | Primary 9/10, legacy 6/6, telemetry 0; validation NLL 0.14141843159924042; token accuracy 0.9578652247922299 | Frozen behavior reference |
| V31 | Broad balanced diagnostic | Primary 8/10, legacy 6/6, telemetry 0; validation NLL 0.1424706606753508; token accuracy 0.9578288138216045 | Negative behavioral challenger |
| V32 | Full-model lower-LR metric challenger | Primary 8/10, legacy 6/6, telemetry 0; validation NLL 0.13565050303587134; PPL 1.1452815512144916; token accuracy 0.9591669169920897 | Retained metric-progress parent; behavior refinement still required |
| V33 | Pairwise identity refinement | Targeted greeting/current-state behavior passed, but primary 5/10 and legacy 4/6; validation NLL 0.14904492264504401; PPL 1.160725130880954; token accuracy 0.9557115158797346 | Rejected as a Pareto candidate; retained as diagnostic evidence |
| V34 | Conflict-aware identity refinement with local AIFL | Preflight only; no training result yet | Canary pending |

The governing interpretation is cumulative: measurable metric progress is retained as an experimental layer, while behavioral and CPU-boundary regressions are recorded and must be addressed before promotion. Do not erase V32's metric progress merely because its surface behavior is incomplete.

## V34 implementation

Source:

foundation/scripts/train_viv_slm_v34_conflict_aware_identity.py

Source SHA-256:

45F4CB1BEB628B5EFD830CCFE68BD3C3DAB0E418A672EF63A2A721D65C8D494F

Focused test:

foundation/scripts/test_viv_slm_v34_conflict_aware_identity.py

Focused test SHA-256:

AF8848CE77E1F5F6506DDB7A501B45E21ABC797CF5876D7A3851B5A23FFCC967

V34 is derived from the existing V33 pair rows and V32/V28 checkpoints. The feedback cases are not duplicated by hand:

- The trainer verifies the pair-rows hash.
- Prompts and authorized text are derived from PAIRWISE_ROWS.jsonl.
- The source route is checked against the CPU route source.
- The model is restored to its prior train/eval mode after sensor evaluation.
- Parent AIFL feedback is recorded read-only before training.
- Every 50 steps, local AIFL feedback can adjust the focus/replay controller.
- A candidate must meet the AIFL feedback guard and show an allowed metric or guarded-margin improvement before the run-local best checkpoint can advance.
- Checkpoint metadata records parent_aifl_feedback and aifl_feedback_history.
- The run writes aifl_feedback.json and includes its hash in RUN_MANIFEST.json.

The controller is bounded:

- Focus weight: 0.01 to 0.12, starting at 0.10.
- Feedback-derived learning-rate multiplier: 0.10 to 1.05.
- Replay multiplier: 1.0 to 4.0.
- Gradient projection is explicit and tested.
- Recursive feedback nudging is bounded and tested.
- No automatic promotion or deployment exists in this lane.

## Parent AIFL sensor result

This was a read-only sensor run against V32. It is informative, not a training result.

- Criteria version: 3
- Overall status: HOLD
- Mind-pass rate: 0.5
- Unanimous rate: 0.5
- Feedback error: 0.5
- Global preference buffer written: false
- Global train gate written: false
- Live runtime mutation: false
- Deployment changed: false

Greeting case:

- All three drafts were accepted by the sensor.
- Telemetry was clean.
- Admission was REWARD.

Current-state case:

- The drafts were labeled PUNISH by the sensor.
- Telemetry was clean.
- Admission was HOLD.

This confirms that the unresolved current-state distinction is a useful feedback signal, but it does not prove that V34 will improve it.

## Verification already completed

Focused V34 preflight:

VIV_SLM_V34_CONFLICT_AWARE_IDENTITY_PREFLIGHT_PASS
source_derived_aifl=true
pairwise_rows_hash_locked=true
global_preference_write=false
global_train_gate_write=false
gradient_projection=true
recursive_feedback_nudge=true
explicit_authorize_required=true
promotion_closed=true
deployment_closed=true

V33 regression passed.

Architecture scan:

- Python files: 1114
- Boundary modules: 572
- Architecture coverage: 100 percent
- Direct bridge violations: 0
- Registry error: none

Full foundation preflight:

- Parsed Python files: 2097
- Architecture files: 1114
- Architecture coverage: 100 percent
- Boundary modules: 572
- Direct bridge violations: 0
- Registry drift: false
- Configured suites: pass
- Rust: pass

Boundary registry:

- Current registry SHA-256: 2F4A0F4D6DF2652A19A1CB9397B5F4A8622BDE66A2F8EA16E42A57CF03E5DA81
- Review artifact SHA-256: DA16DC84D6EF06E13B243A6D15DEC5603F63D8B3E8619850C00E16E790239B94
- Review result: one intentional addition, V34 trainer; zero removed or changed entries
- Registry backup: foundation/triad_boundary_registry.bak_20260804T195815Z.json

## Backups

Backups are under:

foundation/artifacts/auto/agentic/backups/

Relevant V34 backups include:

- pre_v34_aifl_source_20260804T195305Z
- pre_v34_aifl_registry_20260804T195740Z
- pre_v34_aifl_records_20260804T200121Z
- pre_v34_aifl_sensor_record_20260804T200518Z
- pre_v34_aifl_metadata_20260804T200628Z
- pre_v34_metadata_records_20260804T200826Z

The original V34 source snapshot with its pre-edit CLI syntax is preserved as a .py.txt backup so the full Python preflight does not parse the historical invalid copy.

Relevant V32 final backup:

foundation/artifacts/auto/agentic/backups/final_v32_metric_progress_state_20260804T191600Z

Relevant V33 final backup:

foundation/artifacts/auto/agentic/backups/final_v33_pairwise_identity_state_20260804T194400Z

No historical run directory was deleted.

## Next bounded action: one V34 canary

Before running:

1. Read CURRENT_TASK.json, session_journal.md, VIV_SLM_VERSION_HISTORY.md, and this handoff.
2. Confirm that the V34 output directory does not already exist.
3. Create a fresh pre-authorized backup of the current task, journal, version history, V34 source/test, boundary registry/review, V28/V32 checkpoints, and V33 inputs. Record hashes before and after backup.
4. Authorize only the named V34 task and exact 250-step run. Keep promotion, deployment, live mutation, and knowledge admission closed.
5. Use the exact command below.

PowerShell existence check:

~~~powershell
Test-Path 'L:\Continue\Viv\models\viv_slm_identity_personality_v34_conflict_aware_identity\runs\conflict_aware_identity_steps_0250'
~~~

Expected result before the first run: False.

Exact bounded command:

~~~powershell
& 'L:\Continue\.venv\Scripts\python.exe' 'L:\Continue\Viv\foundation\scripts\train_viv_slm_v34_conflict_aware_identity.py' --authorize --steps 250 --batch-size 64 --eval-batch-size 64 --learning-rate 0.00002 --max-grad-norm 1.0 --seed 42 --device cuda --sample-tokens 160 --top-k 40
~~~

After the run, verify:

- checkpoint.pt exists and has a SHA-256 record;
- RUN_MANIFEST.json and RUN_REPORT.json exist;
- training_history.json exists;
- aifl_feedback.json exists and is hashed in the manifest;
- checkpoint metadata contains parent_aifl_feedback and aifl_feedback_history;
- no global preference buffer or global train gate changed;
- live state, Master S_n, promotion, deployment, and knowledge authority remain unchanged;
- validation NLL, perplexity, token accuracy, AIFL mind-pass rate, telemetry, and behavior probes are compared against V28, V32, and V33;
- CPU mouth containment and malicious-renderer rejection still pass.

Matched probe commands after a successful checkpoint:

~~~powershell
$ckpt = 'L:\Continue\Viv\models\viv_slm_identity_personality_v34_conflict_aware_identity\runs\conflict_aware_identity_steps_0250\checkpoint.pt'
$vocab = 'L:\Continue\Viv\models\viv_slm_identity_personality_v31_balanced_base\inputs\VOCAB.json'
$probe = 'L:\Continue\Viv\foundation\artifacts\auto\uml\viv_slm_identity_personality_v34_conflict_aware_identity\probes'
New-Item -ItemType Directory -Force $probe | Out-Null
& 'L:\Continue\.venv\Scripts\python.exe' 'L:\Continue\Viv\foundation\scripts\run_viv_slm_identity_personality_v15_probe_v1.py' --checkpoint $ckpt --vocab $vocab --output (Join-Path $probe 'v15_probe_steps_0250.json')
& 'L:\Continue\.venv\Scripts\python.exe' 'L:\Continue\Viv\foundation\scripts\run_viv_slm_identity_personality_semantic_probe_v1.py' --checkpoint $ckpt --vocab $vocab --output (Join-Path $probe 'semantic_probe_steps_0250.json')
& 'L:\Continue\Viv\foundation\scripts\test_cpu_mouth_render_contract_v1.py'
~~~

Classify the run as ACCEPTED_PARETO_PROGRESS, INCONCLUSIVE, or REJECTED only after the complete comparison. A lower loss alone does not justify promotion, but it must remain recorded as measurable progress.

## Do not do next

- Do not call foundation/scripts/viv_shell.py aifl for this custom V34 run.
- Do not call judge_and_select.
- Do not write the global preference buffer or global train gate.
- Do not change the tokenizer, architecture, optimizer, AIFL criteria, or training scope during the canary.
- Do not add Wikipedia or general knowledge yet.
- Do not reset or overwrite V28 or V32.
- Do not promote or deploy.
- Do not mutate Master S_n or live runtime state.
- Do not treat an AIFL HOLD as proof of model failure; it is a feedback signal.
- Do not report V34 as trained until the checkpoint and run evidence exist.

## Handoff boundary

This step is complete for AIFL investigation, bounded integration, focused testing, full preflight, and documentation.

The new chat should begin at:

V34 canary preparation and exact authorization, not AIFL discovery.

The identity foundation remains the only active training lane. Knowledge admission remains closed until the identity/mouth contract is stable and the architect explicitly opens the next layer.

