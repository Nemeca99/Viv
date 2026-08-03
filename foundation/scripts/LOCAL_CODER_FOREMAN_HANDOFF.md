# Local Coder Foreman Handoff

Status: `OPERATIONAL_BOUNDED_DRAFT_WORKER`

This workflow uses the local Ollama model as an untrusted bulk drafting worker. The foreman reviews every result. Generated code is never executed or integrated automatically.

## Roles

- Architect: defines the requested outcome and authorizes material actions.
- Foreman: Codex; defines bounded tasks, reviews output, checks semantics, and decides whether anything may be staged.
- Draft worker: `nerdsking-python-coder-3b-i:latest`; produces untrusted drafts only.
- Security authority: Rust `security_membrane.tool_gate`; its denials are final.

## Normal workflow

1. Create a JSON task list containing only `draft_code`, `read_only_check`, or `prebuilt_tool` tasks.
2. Run `local_coder_task_queue_v1.py` into a new artifact directory.
3. Inspect `queue_summary.json` and `queue_log.jsonl`.
4. Run `review_local_coder_drafts_v1.py` against the draft artifact directory.
5. Inspect syntax, risk findings, and semantic correctness manually. Every report includes `semantic_review_required=true`; static review is not proof of correctness.
6. After semantic review and explicit foreman approval, stage the draft as sandbox text with `stage_local_coder_draft_v1.py --foreman-approved --semantic-reviewed`.
7. Inventory staged text with `sandbox_state`, then verify the exact staged file with `sandbox_verify_stage`.
8. Keep execution separate and explicit. The staging command never executes code.

## Hard boundaries

- No shell, training, leases, authorization, deployment, promotion, retries, or automatic repository writes.
- Foundation Python source is runtime-immutable; Law 4 denies `.py` writes.
- Policy-approved staging is `.txt` under `L:/Continue/Viv/sandbox/code`.
- Staged drafts remain untrusted and must not be treated as validated merely because static review passes.
- Existing queue logs, summaries, reports, and staged files are never overwritten.
- Every task records task ID, prompt hashes, response hash when available, status, and authority state.
- Queue `QUEUE_PASS` means task execution completed; every queue summary also carries `integration_allowed=false`.

## Semantic review checklist

Static review only checks syntax and broad risk patterns. Before staging, the foreman must also verify:

- required field names were preserved exactly; do not accept singular/plural or renamed fields;
- every safety flag is evaluated with the correct polarity, including safe-looking statuses;
- identifiers used in failure reports exist in the actual task schema (`task_id`, not an assumed `id`);
- return type and required keys match the task contract;
- invalid types and missing fields are guarded before indexing or iteration;
- the implementation does not merely contain required words while omitting their behavior.

Observed examples are preserved in `local_coder_foreman_handoff_v2` and `local_coder_foreman_handoff_v3`; both were syntax-safe but correctly held by the foreman.

## Key components

- `local_coder_task_queue_v1.py` — bounded, logged Ollama queue.
- `local_coder_tool_registry_v1.py` — explicit read-only/artifact-only tool allowlist.
- `sandbox_state` / `sandbox_verify_stage` — read-only staged-file inventory and hash/provenance verification.
- `review_local_coder_drafts_v1.py` — AST and risk review; never integration approval.
- `stage_local_coder_draft_v1.py` — foreman-approved sandbox-text staging.
- `admit_local_coder_draft_v1.py` — source-admission experiment; expected to be denied by Law 4 and retained as evidence.

## Evidence examples

- Successful draft and review: `foundation/artifacts/auto/agentic/local_coder_draft_review_queue_v1/`
- Successful sandbox stage: `foundation/artifacts/auto/agentic/local_coder_marker_smoke_v2/`
- Successful staged verification: `foundation/artifacts/auto/agentic/local_coder_sandbox_verify_v2/`
- Deliberate wrong-hash refusal: `foundation/artifacts/auto/agentic/local_coder_sandbox_verify_failure_v1/`
- Law-4 source-write refusal: `foundation/artifacts/auto/agentic/local_coder_marker_smoke_v1/ADMISSION_FAILURE.json`

## Verification commands

```powershell
L:\Continue\.venv\Scripts\python.exe foundation/scripts/test_local_coder_task_queue_v1.py
L:\Continue\.venv\Scripts\python.exe foundation/scripts/test_review_local_coder_drafts_v1.py
L:\Continue\.venv\Scripts\python.exe foundation/scripts/test_stage_local_coder_draft_v1.py
L:\Continue\.venv\Scripts\python.exe foundation/scripts/test_admit_local_coder_draft_v1.py
```

The workflow is ready for bounded architecture and refactoring drafts. Semantic review and any execution remain foreman-controlled.
