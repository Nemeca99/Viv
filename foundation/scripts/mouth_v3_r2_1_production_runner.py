#!/usr/bin/env python3
"""Production runner for mouth V3 R2.1 targeted-patch (single-lease, no nested lease).

Wired by mouth_v3_r2_1_targeted_patch_experiment. Does not authorize training.
"""
from __future__ import annotations

import gc
import json
import os
import shutil
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import mouth_v3_r2_1_targeted_patch_experiment as exp

TARGETED = None  # lazy import


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _targeted():
    global TARGETED
    if TARGETED is None:
        from models.Training.code import train_mouth_v3_targeted_patch as mod

        TARGETED = mod
    return TARGETED


class GovernedLeaseHandle:
    """Thin handle over TrainingLease with close() for finally bookkeeping."""

    def __init__(self, lease: Any) -> None:
        self.lease = lease
        self.staging_root = lease.staging_root
        self.final_root = lease.final_root
        self.closed = False
        self.committed = False

    def commit(self) -> dict[str, Any]:
        result = self.lease.commit()
        self.committed = bool(result.get("allowed"))
        return result

    def quarantine(self, record_id: str, text: str) -> dict[str, Any]:
        return self.lease.quarantine(record_id, text)

    def close(self) -> None:
        """Close lease bookkeeping. Prefer quarantine note if never committed."""
        if self.closed:
            return
        if not self.committed:
            try:
                self.lease.quarantine(
                    "lease_close",
                    "governed_lease_closed_without_commit",
                )
            except Exception as exc:
                raise RuntimeError(f"lease_close_quarantine_failed:{exc}") from exc
        self.closed = True


def open_governed_lease(
    *,
    plan: dict[str, Any],
    campaign_root: Path,
    output_root: Path,
) -> GovernedLeaseHandle:
    """Real governed lease via begin_run_lease. Exactly one lease for the run."""
    del campaign_root  # reserved for future path binding
    train_path = Path(plan["pre_run_locks"]["optimizer_train_jsonl"]["path"])
    parent_path = Path(plan["pre_run_locks"]["parent_adapter"]["path"])
    train_sha = exp._file_sha256(train_path)
    parent_sha = exp._file_sha256(parent_path / "adapter_model.safetensors")
    run_id = Path(output_root).name
    lease = _targeted().begin_single_governed_lease(
        run_id=run_id,
        train_jsonl_sha256=train_sha,
        parent_adapter_sha256=parent_sha,
        learning_rate=float(plan["learning_rate"]),
        max_steps=int(plan["optimizer_steps"]),
    )
    return GovernedLeaseHandle(lease)


def train_targeted_patch_16(
    *,
    plan: dict[str, Any],
    campaign_root: Path,
    output_root: Path,
    checkpoint_steps: list[int],
    lease: Any | None = None,
) -> dict[str, Any]:
    """Real 16-step BF16 trainer under an already-open single lease."""
    if lease is None:
        raise RuntimeError("train_targeted_patch_16_requires_external_lease")
    train_path = Path(plan["pre_run_locks"]["optimizer_train_jsonl"]["path"])
    parent_path = Path(plan["pre_run_locks"]["parent_adapter"]["path"])
    prepared = _targeted().prepare_targeted_patch_runtime(
        train_jsonl=train_path,
        parent_adapter=parent_path,
        system_prompt=exp.SYSTEM_PROMPT,
        learning_rate=float(plan["learning_rate"]),
        gradient_accumulation=int(plan["gradient_accumulation"]),
        staging_root=Path(lease.staging_root),
        final_root=Path(lease.final_root),
        load_model=True,
    )
    if len(prepared["encoded"]) != 16:
        raise RuntimeError(f"train_row_count:{len(prepared['encoded'])}")
    result = _targeted().train_under_external_lease(
        lease=lease.lease if isinstance(lease, GovernedLeaseHandle) else lease,
        prepared=prepared,
        max_steps=int(plan["optimizer_steps"]),
        checkpoint_steps=tuple(checkpoint_steps),
        gradient_accumulation=int(plan["gradient_accumulation"]),
        seed=exp.RNG_SEED,
        commit=True,
    )
    if isinstance(lease, GovernedLeaseHandle) and result.get("ok"):
        lease.committed = True
    # Materialize expected output_root checkpoint dirs from final/staging.
    out = Path(output_root)
    out.mkdir(parents=True, exist_ok=True)
    src_root = Path(lease.final_root)
    if not src_root.is_dir():
        src_root = Path(lease.staging_root)
    for step in checkpoint_steps:
        src = src_root / f"adapter_step_{step}"
        dst = out / f"adapter_step_{step}"
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst)
        if not dst.is_dir():
            # staging may hold mid saves before commit
            alt = Path(lease.staging_root) / f"adapter_step_{step}"
            if alt.is_dir() and not dst.exists():
                shutil.copytree(alt, dst)
        if not dst.is_dir():
            raise FileNotFoundError(f"checkpoint_missing_after_train:step_{step}")
    result["output_root"] = str(out).replace("\\", "/")
    result["campaign_root"] = str(campaign_root).replace("\\", "/")
    result["single_lease"] = True
    return result


def build_eval_generation_packet(
    *,
    ask: str,
    semantic_key: str,
    case_id: str | None = None,
    sn: float = 0.60,
) -> dict[str, Any]:
    """Build a valid InMemoryGenerationBackend packet (dict, never a raw string)."""
    packet = {
        "version": "1.0",
        "s_n": float(sn),
        "status": "ACTIVE",
        "mode": "converse",
        "tone": "calm",
        "directive": "Speak from verified facts only. Do not invent or decide.",
        "personality": "Warm, direct, grounded; shield not sword.",
        "facts": [],
        "memory": [],
        "dialogue": [],
        "query": str(ask),
        "ask": str(ask),
        "semantic_key": str(semantic_key),
        "category": str(semantic_key),
    }
    if case_id is not None:
        packet["case_id"] = case_id
    return packet


def stop_metadata_is_complete(stop_metadata: Any) -> bool:
    """True only when real stop fields are present (booleans + stop_reason)."""
    if not isinstance(stop_metadata, dict) or not stop_metadata:
        return False
    if stop_metadata.get("stop_reason") is None:
        return False
    if not isinstance(stop_metadata.get("terminated_by_eos"), bool):
        return False
    if not isinstance(stop_metadata.get("terminated_by_response_eos"), bool):
        return False
    return True


def legacy_eos_stop_from_metadata(stop_metadata: Any) -> dict[str, bool]:
    """EOS/stop gates from real stop metadata only — never from nonempty text.

    Missing metadata → both fail. max_new_tokens → eos_pass False.
    """
    if not stop_metadata_is_complete(stop_metadata):
        return {"eos_pass": False, "stop_pass": False}
    assert isinstance(stop_metadata, dict)
    reason = str(stop_metadata.get("stop_reason") or "")
    terminated = bool(stop_metadata.get("terminated_by_eos")) or bool(
        stop_metadata.get("terminated_by_response_eos")
    )
    # Never treat max_new_tokens (or empty/error/other) as EOS success.
    if reason in {"max_new_tokens", "empty", "error", "other"}:
        eos_pass = False
    else:
        eos_pass = terminated
    stop_pass = reason in {
        "response_eos",
        "tokenizer_eos",
        "eos",
        "max_new_tokens",
    } or (terminated and reason not in {"empty", "error", "other", ""})
    return {"eos_pass": bool(eos_pass), "stop_pass": bool(stop_pass)}


def legacy_goal_alignment_gates(
    text: str, goal_row: dict[str, Any]
) -> dict[str, Any]:
    """Reuse goal_alignment_summary / judge_mouth_semantic semantics for one case."""
    from lib.mouth_semantic_judge import judge_mouth_semantic
    from models.Training.code import train_stage1_mouth_generation_canary as canary

    stripped = str(text or "").strip()
    lowered = stripped.lower()
    required_any = [
        list(group) for group in (goal_row.get("required_concepts") or goal_row.get("required_any") or [])
    ]
    if not required_any and goal_row.get("semantic_class"):
        # Fall back to frozen GOAL_CASES expansion when row lacks groups.
        for case in canary.GOAL_CASES:
            if str(case.get("semantic_class")) == str(goal_row.get("semantic_class")):
                required_any = canary.effective_required_any(case)
                break
    forbidden = [
        str(c)
        for c in (
            goal_row.get("forbidden_claims") or list(canary.FORBIDDEN_GOAL_CLAIMS)
        )
    ]
    missing = [
        list(group)
        for group in required_any
        if not any(str(term).lower() in lowered for term in group)
    ]
    forbidden_hits = [claim for claim in forbidden if claim.lower() in lowered]
    goal_passed = bool(stripped) and not missing and not forbidden_hits
    mouth = judge_mouth_semantic(
        stripped,
        {
            **goal_row,
            "required_concepts": required_any,
            "forbidden_claims": forbidden,
        },
    )
    return {
        "pass": goal_passed,
        "mouth_semantic_pass": bool(mouth.get("mouth_semantic_pass")),
        "missing_required_groups": missing,
        "forbidden_claims": forbidden_hits,
        "mouth_semantic": mouth,
    }


def extract_generation_result(raw: Any) -> dict[str, Any]:
    """Fail-closed extraction: only result['text']; error/missing/empty → FAIL."""
    if not isinstance(raw, dict):
        return {
            "text": "",
            "error": f"generate_return_not_dict:{type(raw).__name__}",
            "token_ids": [],
            "stop_metadata": {},
            "fail_closed": True,
        }
    error = raw.get("error")
    text = raw.get("text")
    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = str(text)
    token_ids = raw.get("generated_token_ids")
    if token_ids is None:
        token_ids = raw.get("token_ids") or []
    if not isinstance(token_ids, list):
        token_ids = []
    stop_metadata = {
        "terminating_token_id": raw.get("terminating_token_id"),
        "configured_stop_ids": raw.get("configured_stop_ids"),
        "primary_response_eos_id": raw.get("primary_response_eos_id"),
        "terminated_by_eos": raw.get("terminated_by_eos"),
        "terminated_by_response_eos": raw.get("terminated_by_response_eos"),
        "stop_reason": raw.get("stop_reason"),
        "tokens": raw.get("tokens"),
    }
    fail_closed = bool(error) or not str(text).strip()
    return {
        "text": text,
        "error": error,
        "token_ids": token_ids,
        "stop_metadata": stop_metadata,
        "fail_closed": fail_closed,
    }


def judge_generated_response(
    *,
    text: str,
    case_id: str,
    axis: str | None,
    rubric: dict[str, Any],
    generation_error: Any = None,
    stop_metadata: dict[str, Any] | None = None,
    token_ids: list[Any] | None = None,
) -> dict[str, Any]:
    """Score with judge_case; generation error / empty text → overall FAIL."""
    from lib.evaluator_v2_2_rubric import judge_case
    from models.Training.code import train_stage1_mouth_generation_canary as canary

    judgment = judge_case(
        str(text or ""),
        {"case_id": case_id, "axis": axis, "rubric": rubric or {}},
    )
    toolbleed = 1 if canary.response_text_has_toolbleed(str(text or "")) else 0
    failure_reasons: list[str] = []
    if generation_error:
        failure_reasons.append(f"generation_error:{generation_error}")
        judgment["overall_pass"] = False
    if not str(text or "").strip():
        failure_reasons.append("empty_response")
        judgment["overall_pass"] = False
    if toolbleed:
        failure_reasons.append("toolbleed")
        judgment["overall_pass"] = False
    if judgment.get("overall_pass") is not True and judgment.get("reason"):
        failure_reasons.append(str(judgment.get("reason")))
    axes = judgment.get("axes") or {}
    applicable = [
        name
        for name, row in axes.items()
        if isinstance(row, dict) and row.get("applicable")
    ]
    per_axis = {
        name: {
            "pass": (axes.get(name) or {}).get("pass"),
            "applicable": (axes.get(name) or {}).get("applicable"),
            "reason": (axes.get(name) or {}).get("reason"),
            "abstain": (axes.get(name) or {}).get("abstain"),
            "ambiguous": (axes.get(name) or {}).get("ambiguous"),
        }
        for name in applicable
    }
    for name, row in per_axis.items():
        if row.get("pass") is not True:
            failure_reasons.append(f"axis_fail:{name}:{row.get('reason')}")
    return {
        "overall_pass": judgment.get("overall_pass") is True,
        "applicable_axes": applicable,
        "per_axis_outcomes": per_axis,
        "failure_reasons": failure_reasons,
        "toolbleed": toolbleed,
        "stop_metadata": stop_metadata or {},
        "token_ids": list(token_ids or []),
        "generation_error": generation_error,
        "rubric_judgment": judgment,
    }


def generate_judged_case(
    backend: Any,
    *,
    ask: str,
    semantic_key: str,
    case_id: str,
    surface: str,
    axis_or_split: str,
    rubric: dict[str, Any],
    legacy_extras: dict[str, Any] | None = None,
    goal_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Packet → generate → extract text → judge_case. Never nonempty-string PASS."""
    packet = build_eval_generation_packet(
        ask=ask, semantic_key=semantic_key, case_id=case_id
    )
    try:
        raw = backend.generate(packet)
    except Exception as exc:  # noqa: BLE001 — fail closed into judgment evidence
        raw = {"text": "", "error": f"{type(exc).__name__}:{exc}", "tokens": None}
    extracted = extract_generation_result(raw)
    judgment = judge_generated_response(
        text=extracted["text"],
        case_id=case_id,
        axis=axis_or_split if surface != "legacy_goal" else None,
        rubric=rubric,
        generation_error=extracted["error"],
        stop_metadata=extracted["stop_metadata"],
        token_ids=extracted["token_ids"],
    )
    passed = judgment["overall_pass"] is True
    row: dict[str, Any] = {
        "case_id": case_id,
        "surface": surface,
        "ask": ask,
        "generated": extracted["text"],
        "axis_or_split": axis_or_split,
        "pass": passed,
        "judgment": judgment,
        "toolbleed": int(judgment.get("toolbleed") or 0),
    }
    if surface == "legacy_goal":
        goal_src = goal_row or {}
        alignment = legacy_goal_alignment_gates(extracted["text"], goal_src)
        stop_gates = legacy_eos_stop_from_metadata(extracted["stop_metadata"])
        gen_ok = (
            not extracted.get("error")
            and bool(str(extracted["text"]).strip())
            and int(judgment.get("toolbleed") or 0) == 0
        )
        row["pass"] = bool(alignment["pass"]) and gen_ok
        row["mouth_semantic_pass"] = bool(alignment["mouth_semantic_pass"]) and gen_ok
        row["eos_pass"] = bool(stop_gates["eos_pass"]) and gen_ok
        row["stop_pass"] = bool(stop_gates["stop_pass"]) and gen_ok
        row["valid_pass"] = bool(gen_ok)
        row["goal_alignment"] = {
            "missing_required_groups": alignment["missing_required_groups"],
            "forbidden_claims": alignment["forbidden_claims"],
            "mouth_semantic": alignment["mouth_semantic"],
        }
        # Fail closed: generation error / empty / toolbleed zeros all legacy gates.
        if not gen_ok:
            row["pass"] = False
            row["mouth_semantic_pass"] = False
            row["eos_pass"] = False
            row["valid_pass"] = False
            row["stop_pass"] = False
    elif legacy_extras:
        row.update(legacy_extras)
        if not passed:
            for key in (
                "mouth_semantic_pass",
                "eos_pass",
                "valid_pass",
                "stop_pass",
            ):
                if key in row:
                    row[key] = False
    return row


def build_case_level_bindings(
    *,
    adapter_path: Path,
    plan: dict[str, Any],
    campaign_root: Path,
) -> dict[str, Any]:
    root = Path(campaign_root)
    plan_path = root / "campaign_plan.json"
    adapter = Path(adapter_path)
    weights = adapter / "adapter_model.safetensors"
    locks = plan.get("pre_run_locks") or {}
    evaluator = locks.get("evaluator_v2_2_rubric_py") or {}
    hidden = locks.get("hidden_v3_1_pack") or {}
    return {
        "adapter_sha256": exp._file_sha256(weights) if weights.is_file() else "",
        "evaluator_sha256": str(evaluator.get("sha256") or ""),
        "hidden_pack_sha256": str(hidden.get("sha256") or ""),
        "generation_settings": dict(
            locks.get("generation_settings") or exp.GENERATION_SETTINGS_LOCK
        ),
        "pre_run_plan_sha256": (
            exp._file_sha256(plan_path) if plan_path.is_file() else ""
        ),
        "adapter_path": str(adapter).replace("\\", "/"),
    }


def _write_case_level_artifact(
    path: Path,
    *,
    role: str,
    checkpoint_step: int | None,
    cases: list[dict[str, Any]],
    bindings: dict[str, Any],
) -> dict[str, Any]:
    artifact = {
        "schema_version": exp.CASE_LEVEL_OUTPUTS_SCHEMA,
        "role": role,
        "checkpoint_step": checkpoint_step,
        "immutable": True,
        "recorded_at": _utc(),
        "bindings": bindings,
        "cases": cases,
    }
    exp.validate_case_level_generated_outputs(artifact)
    if path.is_file():
        existing = exp._load_json(path)
        try:
            exp.validate_case_level_generated_outputs(existing)
            exp.assert_case_level_bindings_match(existing, bindings)
            return existing
        except ValueError as exc:
            raise ValueError(
                f"case_level_refuse_overwrite_binding_mismatch:{path}:{exc}"
            ) from exc
    exp._write_json(path, artifact)
    return artifact


def score_surfaces_with_backend(
    backend: Any,
    *,
    campaign_root: Path,
) -> list[dict[str, Any]]:
    """Generate+judge all required surfaces; exact counts 8/16/20/8."""
    from models.Training.code import train_stage1_generation as generation_v1
    from models.Training.code import train_stage1_mouth_generation_canary as canary

    root = Path(campaign_root)
    cases_out: list[dict[str, Any]] = []

    canary.ensure_goal_pack_locked()
    goal_rows = canary.goal_eval_rows()
    for idx, row in enumerate(goal_rows):
        stage = generation_v1.stage1_case(row, idx)
        ask = str(row.get("ask") or row.get("prompt") or "")
        rubric = {
            "applicable_axes": ["forbidden_authority_safety_claim"],
            "forbidden_authority_phrases": list(row.get("forbidden_claims") or []),
            "identity_required": False,
        }
        judged = generate_judged_case(
            backend,
            ask=ask,
            semantic_key=str(
                stage.get("semantic_key") or row.get("semantic_class") or "legacy_goal"
            ),
            case_id=str(row.get("pair_id") or f"legacy-{idx:03d}"),
            surface="legacy_goal",
            axis_or_split="legacy_goal",
            rubric=rubric,
            goal_row=row,
        )
        cases_out.append(judged)

    routing = exp._load_json(root / "evaluation_routing_manifest.json")
    positives = exp._load_jsonl(exp.ADMITTED_POS)
    negatives = exp._load_jsonl(exp.ADMITTED_NEG)
    pos_by_id = {r["candidate_id"]: r for r in positives}
    neg_by_id = {r["candidate_id"]: r for r in negatives}

    for split in ("development", "frozen", "adversarial"):
        for cid in routing.get(split) or []:
            row = pos_by_id[cid]
            cases_out.append(
                generate_judged_case(
                    backend,
                    ask=row["ask"],
                    semantic_key=f"admitted.{row.get('axis') or split}",
                    case_id=cid,
                    surface="admitted_eval",
                    axis_or_split=split,
                    rubric=dict(row.get("judge_rubric") or {}),
                )
            )

    for cid in routing.get("auditor") or []:
        row = neg_by_id[cid]
        cases_out.append(
            generate_judged_case(
                backend,
                ask=row["ask"],
                semantic_key=f"auditor.{row.get('axis') or 'auditor'}",
                case_id=cid,
                surface="auditor",
                axis_or_split="auditor",
                rubric=dict(row.get("judge_rubric") or {}),
            )
        )

    hidden = exp._load_json(root / "hidden_indirect_adversarial_pack_v3_1.json")
    for case in hidden.get("cases") or []:
        ask = case["generation"]["ask"]
        axis = str(case.get("axis") or case.get("semantic_family") or "hidden")
        cases_out.append(
            generate_judged_case(
                backend,
                ask=ask,
                semantic_key=f"hidden_v3_1.{axis}",
                case_id=case["case_id"],
                surface="hidden_v3_1",
                axis_or_split=axis,
                rubric=dict(case.get("rubric") or {}),
            )
        )
    return cases_out


def _generate_case_level_for_adapter(
    *,
    adapter_path: Path,
    campaign_root: Path,
    role: str,
    checkpoint_step: int | None,
    plan: dict[str, Any] | None = None,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Real GPU generation eval → immutable bound case-level artifact. No optimizer steps."""
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer

    from models.Training.code import train_stage1_generation as generation_v1

    root = Path(campaign_root)
    plan_obj = plan if plan is not None else exp._load_json(root / "campaign_plan.json")
    bindings = build_case_level_bindings(
        adapter_path=adapter_path, plan=plan_obj, campaign_root=root
    )

    out_dir = root / "case_level_generated_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = (
        "incumbent_004859Z.json"
        if role == "incumbent_004859Z"
        else f"checkpoint_step_{checkpoint_step}.json"
    )
    out_path = out_dir / name
    if out_path.is_file():
        existing = exp._load_json(out_path)
        try:
            return exp.load_case_level_generated_outputs(
                out_path, expected_bindings=bindings
            )
        except ValueError as exc:
            raise ValueError(
                f"case_level_stale_reuse_refused:{out_path}:{exc}"
            ) from exc

    owns_backend = backend is None
    model = None
    if backend is None:
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise RuntimeError("cuda_bf16_required:checkpoint_evaluator")
        if not (adapter_path / "adapter_config.json").is_file():
            raise FileNotFoundError(f"adapter_missing:{adapter_path}")
        tokenizer = AutoTokenizer.from_pretrained(
            str(generation_v1.LOCAL_BASE), trust_remote_code=True
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        torch.cuda.empty_cache()
        model = generation_v1.load_local_qwen_causal_lm(torch=torch).to("cuda")
        model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=False)
        model.eval()
        backend = generation_v1.InMemoryGenerationBackend(model, tokenizer, torch)

    try:
        cases_out = score_surfaces_with_backend(backend, campaign_root=root)
    finally:
        if owns_backend and model is not None:
            del model
            gc.collect()
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass

    return _write_case_level_artifact(
        out_path,
        role=role,
        checkpoint_step=checkpoint_step,
        cases=cases_out,
        bindings=bindings,
    )


def evaluate_incumbent_baseline(
    *,
    plan: dict[str, Any],
    campaign_root: Path,
) -> dict[str, Any]:
    """Mandatory real incumbent evaluator. No synthetic fallback.

    Aborts (raises) if baseline unavailable/malformed — caller must not
    consume token or open lease on failure.
    """
    root = Path(campaign_root)
    bindings = build_case_level_bindings(
        adapter_path=exp.PARENT_ADAPTER, plan=plan, campaign_root=root
    )
    artifact_path = (
        root / "case_level_generated_outputs" / "incumbent_004859Z.json"
    )
    if artifact_path.is_file():
        try:
            artifact = exp.load_case_level_generated_outputs(
                artifact_path, expected_bindings=bindings
            )
        except ValueError as exc:
            raise ValueError(f"incumbent_baseline_malformed:{exc}") from exc
    else:
        artifact = _generate_case_level_for_adapter(
            adapter_path=exp.PARENT_ADAPTER,
            campaign_root=root,
            role="incumbent_004859Z",
            checkpoint_step=None,
            plan=plan,
        )
    report = exp.derive_score_report_from_case_outputs(artifact)
    report["role"] = "incumbent_004859Z"
    report["pass"] = True
    if int(report.get("legacy_goals_total", 0)) != 8:
        raise ValueError("incumbent_baseline_malformed:legacy_goals_total")
    counts = report.get("case_counts") or {}
    for surface, expected in exp.SURFACE_COUNTS.items():
        if int(counts.get(surface, -1)) != expected:
            raise ValueError(
                f"incumbent_baseline_malformed:surface_count:{surface}"
            )
    if not report.get("hidden_per_axis"):
        raise ValueError("incumbent_baseline_malformed:hidden_per_axis_empty")
    report["case_level_path"] = str(artifact_path).replace("\\", "/")
    return report


def evaluate_run_checkpoints(
    *,
    plan: dict[str, Any],
    campaign_root: Path,
    output_root: Path,
    incumbent_report: dict[str, Any],
    checkpoint_steps: list[int],
) -> dict[str, Any]:
    """Real checkpoint evaluator; writes case-level artifacts; exact [4,8,16]."""
    root = Path(campaign_root)
    out = Path(output_root)
    incumbent_path = root / "case_level_generated_outputs" / "incumbent_004859Z.json"
    if not incumbent_path.is_file():
        raise FileNotFoundError(f"incumbent_case_level_missing:{incumbent_path}")
    incumbent_bindings = build_case_level_bindings(
        adapter_path=exp.PARENT_ADAPTER, plan=plan, campaign_root=root
    )
    incumbent_artifact = exp.load_case_level_generated_outputs(
        incumbent_path, expected_bindings=incumbent_bindings
    )

    reports: list[dict[str, Any]] = []
    for step in checkpoint_steps:
        adapter = out / f"adapter_step_{step}"
        if not adapter.is_dir():
            raise FileNotFoundError(f"checkpoint_missing:adapter_step_{step}")
        artifact = _generate_case_level_for_adapter(
            adapter_path=adapter,
            campaign_root=root,
            role="checkpoint",
            checkpoint_step=step,
            plan=plan,
        )
        report = exp.derive_score_report_from_case_outputs(
            artifact, incumbent_artifact=incumbent_artifact
        )
        report["checkpoint_step"] = step
        reports.append(report)

    ordered = exp.require_checkpoint_reports_ordered(reports)
    return {
        "incumbent_report": incumbent_report,
        "checkpoint_reports": ordered,
        "checkpoint_steps": list(checkpoint_steps),
        "score_source": exp.CASE_LEVEL_OUTPUTS_SCHEMA,
    }


def authorize_once(
    *,
    campaign_root: Path,
    authorizations_dir: Path | None = None,
) -> dict[str, Any]:
    """Transactional flip run_authorized=true + issue named unlock.

    Preconditions first (locks, preflight, output absence, token absence).
    Stage plan/status/token → atomic publish; any write failure rolls back
    to unauthorized. Implemented for operator use; not invoked by install.
    """
    root = Path(campaign_root)
    plan_path = root / "campaign_plan.json"
    status_path = root / "STATUS.json"
    plan = exp._load_json(plan_path)
    if plan.get("experiment_id") != exp.EXPERIMENT_ID:
        raise ValueError(f"authorize_once_experiment_mismatch:{plan.get('experiment_id')}")
    if plan.get("implementation_authorized") is not True:
        raise ValueError("authorize_once_implementation_authorized_false")
    if plan.get("training_authorized") is not False:
        raise ValueError("authorize_once_training_authorized_must_stay_false")
    if plan.get("run_authorized") is not False:
        raise ValueError("authorize_once_already_run_authorized")

    # 1) Preconditions before any mutation.
    exp.verify_source_locks(plan, campaign_root=root)
    preflight_path = root / exp.EXACT_RUNTIME_PREFLIGHT_NAME
    if not preflight_path.is_file():
        raise FileNotFoundError(f"authorize_once_preflight_missing:{preflight_path}")
    preflight = exp._load_json(preflight_path)
    if preflight.get("pass") is not True:
        raise ValueError("authorize_once_preflight_not_pass")
    if int(preflight.get("optimizer_steps_executed", -1)) != 0:
        raise ValueError("authorize_once_preflight_steps_nonzero")
    out_root = Path(plan["checkpoint_paths"]["run_root"])
    if out_root.exists():
        raise ValueError(f"authorize_once_output_root_exists:{out_root}")

    auth_dir = (
        Path(authorizations_dir)
        if authorizations_dir is not None
        else exp.AUTHORIZATIONS_DIR
    )
    auth_dir.mkdir(parents=True, exist_ok=True)
    token_path = exp.named_authorization_path(
        exp.EXPERIMENT_ID, authorizations_dir=auth_dir
    )
    if token_path.is_file():
        raise FileExistsError(f"named_unlock_already_exists:{token_path}")

    plan_backup = plan_path.read_bytes()
    status_backup = status_path.read_bytes() if status_path.is_file() else None
    staged_plan = plan_path.with_name(f"{plan_path.name}.authorize_stage")
    staged_status = status_path.with_name(f"{status_path.name}.authorize_stage")
    staged_token = token_path.with_name(f"{token_path.name}.authorize_stage")

    def _cleanup_stages() -> None:
        for p in (staged_plan, staged_status, staged_token):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

    def _rollback_unauthorized() -> None:
        _cleanup_stages()
        try:
            plan_path.write_bytes(plan_backup)
        except Exception:
            pass
        try:
            if status_backup is not None:
                status_path.write_bytes(status_backup)
        except Exception:
            pass
        try:
            if token_path.is_file():
                token_path.unlink()
        except Exception:
            pass
        try:
            unauthorized = exp._load_json(plan_path)
            unauthorized["run_authorized"] = False
            unauthorized["training_authorized"] = False
            if str(unauthorized.get("status") or "").startswith("RUN_AUTHORIZED"):
                unauthorized["status"] = "PRODUCTION_RUNNER_INSTALLED_RUN_UNAUTHORIZED"
            unauthorized.pop("authorized_at", None)
            sha = exp._write_json(plan_path, unauthorized)
            exp._write_json(
                status_path,
                {
                    "experiment_id": exp.EXPERIMENT_ID,
                    "implementation_authorized": True,
                    "run_authorized": False,
                    "training_authorized": False,
                    "status": unauthorized.get("status"),
                    "campaign_root": str(root).replace("\\", "/"),
                    "campaign_plan_sha256": sha,
                    "plan_sha256": sha,
                },
            )
        except Exception:
            pass

    try:
        authorized_at = _utc()
        new_plan = dict(plan)
        new_plan["run_authorized"] = True
        new_plan["training_authorized"] = False
        new_plan["status"] = "RUN_AUTHORIZED_AWAITING_CONSUME"
        new_plan["authorized_at"] = authorized_at
        staged_plan.write_text(
            json.dumps(new_plan, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        plan_sha = exp._file_sha256(staged_plan)
        status = {
            "experiment_id": exp.EXPERIMENT_ID,
            "implementation_authorized": True,
            "run_authorized": True,
            "training_authorized": False,
            "status": "RUN_AUTHORIZED_AWAITING_CONSUME",
            "campaign_root": str(root).replace("\\", "/"),
            "campaign_plan_sha256": plan_sha,
            "plan_sha256": plan_sha,
            "authorized_at": authorized_at,
        }
        staged_status.write_text(
            json.dumps(status, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        token = {
            "schema_version": exp.NAMED_UNLOCK_SCHEMA_VERSION,
            "experiment_id": exp.EXPERIMENT_ID,
            "plan_sha256": plan_sha,
            "status": "issued",
            "issued_at": authorized_at,
            "issued_by": "authorize_once",
        }
        staged_token.write_text(
            json.dumps(token, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(str(staged_plan), str(plan_path))
        os.replace(str(staged_status), str(status_path))
        os.replace(str(staged_token), str(token_path))
        disk_sha = exp._file_sha256(plan_path)
        if disk_sha != plan_sha:
            raise RuntimeError("authorize_once_plan_sha_drift_after_publish")
        return {
            "ok": True,
            "plan_sha256": plan_sha,
            "run_authorized": True,
            "training_authorized": False,
            "token_path": str(token_path).replace("\\", "/"),
            "token_status": "issued",
        }
    except Exception:
        _rollback_unauthorized()
        raise


def snapshot_production_v3_evidence(*, campaign_root: Path) -> dict[str, Any]:
    root = Path(campaign_root)
    plan_src = root / "campaign_plan.json"
    status_src = root / "STATUS.json"
    plan_dst = root / exp.PRODUCTION_V3_EVIDENCE_PLAN
    status_dst = root / exp.PRODUCTION_V3_EVIDENCE_STATUS
    already = plan_dst.is_file() and status_dst.is_file()
    if not plan_dst.is_file() and plan_src.is_file():
        shutil.copy2(plan_src, plan_dst)
    if not status_dst.is_file() and status_src.is_file():
        shutil.copy2(status_src, status_dst)
    return {
        "plan_evidence": str(plan_dst).replace("\\", "/"),
        "plan_evidence_sha256": exp._file_sha256(plan_dst) if plan_dst.is_file() else None,
        "status_evidence": str(status_dst).replace("\\", "/"),
        "status_evidence_sha256": (
            exp._file_sha256(status_dst) if status_dst.is_file() else None
        ),
        "already_present": already,
    }


def snapshot_production_v4_evidence(*, campaign_root: Path) -> dict[str, Any]:
    """Preserve current v4 plan/status as immutable evidence before v5 rewrite."""
    root = Path(campaign_root)
    plan_src = root / "campaign_plan.json"
    status_src = root / "STATUS.json"
    plan_dst = root / exp.PRODUCTION_V4_EVIDENCE_PLAN
    status_dst = root / exp.PRODUCTION_V4_EVIDENCE_STATUS
    already = plan_dst.is_file() and status_dst.is_file()
    # Only snapshot when source is still v4 (or first capture of live plan).
    if not plan_dst.is_file() and plan_src.is_file():
        shutil.copy2(plan_src, plan_dst)
    if not status_dst.is_file() and status_src.is_file():
        shutil.copy2(status_src, status_dst)
    return {
        "plan_evidence": str(plan_dst).replace("\\", "/"),
        "plan_evidence_sha256": exp._file_sha256(plan_dst) if plan_dst.is_file() else None,
        "status_evidence": str(status_dst).replace("\\", "/"),
        "status_evidence_sha256": (
            exp._file_sha256(status_dst) if status_dst.is_file() else None
        ),
        "already_present": already,
    }


def snapshot_execution_path_mock_evidence(*, campaign_root: Path) -> dict[str, Any]:
    root = Path(campaign_root)
    plan_src = root / "campaign_plan.json"
    status_src = root / "STATUS.json"
    plan_dst = root / exp.EXECUTION_PATH_MOCK_EVIDENCE_PLAN
    status_dst = root / exp.EXECUTION_PATH_MOCK_EVIDENCE_STATUS
    if not plan_dst.is_file():
        shutil.copy2(plan_src, plan_dst)
    if not status_dst.is_file():
        shutil.copy2(status_src, status_dst)
    return {
        "plan_evidence": str(plan_dst).replace("\\", "/"),
        "plan_evidence_sha256": exp._file_sha256(plan_dst),
        "status_evidence": str(status_dst).replace("\\", "/"),
        "status_evidence_sha256": exp._file_sha256(status_dst),
        "already_present": plan_dst.is_file() and status_dst.is_file(),
    }


def install_production_runner(*, campaign_root: Path = exp.CAMPAIGN_ROOT) -> dict[str, Any]:
    """Non-destructive: snapshot prior evidence, write production plan v5 (unauthorized)."""
    root = Path(campaign_root)
    if not root.is_dir():
        raise FileNotFoundError(f"campaign_root_missing:{root}")
    mock_evidence = snapshot_execution_path_mock_evidence(campaign_root=root)
    v3_evidence = snapshot_production_v3_evidence(campaign_root=root)
    v4_evidence = snapshot_production_v4_evidence(campaign_root=root)

    for name in exp.EVIDENCE_SNAPSHOT_NAMES:
        if not (root / name).is_file():
            raise FileNotFoundError(f"evidence_snapshot_missing:{root / name}")

    train_path = root / "optimizer_train_16_TRAIN_READY.jsonl"
    if not train_path.is_file():
        raise FileNotFoundError(f"optimizer_jsonl_missing:{train_path}")
    train_sha = exp._file_sha256(train_path)
    hidden_v3_path = root / "hidden_indirect_adversarial_pack_v3.json"
    hidden_v3_1_path = root / "hidden_indirect_adversarial_pack_v3_1.json"
    if not hidden_v3_path.is_file() or not hidden_v3_1_path.is_file():
        raise FileNotFoundError("hidden_packs_missing")
    batch_path = root / "deterministic_batch_order.json"
    routing_path = root / "evaluation_routing_manifest.json"
    preflight_path = root / exp.EXACT_RUNTIME_PREFLIGHT_NAME
    if not preflight_path.is_file():
        raise FileNotFoundError(f"preflight_missing:{preflight_path}")
    batch = exp._load_json(batch_path)
    exposure = exp.calculate_exposure_and_lr_flags(batch)

    locked = exp._build_pre_run_locks(
        campaign_root=root,
        train_path=train_path,
        train_sha=train_sha,
        hidden_v3_path=hidden_v3_path,
        hidden_v3_sha=exp._file_sha256(hidden_v3_path),
        hidden_v3_1_path=hidden_v3_1_path,
        hidden_v3_1_sha=exp._file_sha256(hidden_v3_1_path),
        batch_path=batch_path,
        routing_path=routing_path,
    )
    if "exact_runtime_nostep_preflight_report" not in locked:
        raise ValueError("exact_runtime_preflight_lock_missing")
    if "production_runner_py" not in locked or "targeted_patch_trainer_py" not in locked:
        raise ValueError("production_locks_missing")

    written = exp._write_plan_and_status(
        campaign_root=root,
        locked=locked,
        batch=batch,
        exposure=exposure,
        status_label="PRODUCTION_RUNNER_INSTALLED_RUN_UNAUTHORIZED",
    )
    # Ensure flags remain closed after write.
    plan_path = root / "campaign_plan.json"
    plan = exp._load_json(plan_path)
    plan["run_authorized"] = False
    plan["training_authorized"] = False
    plan["implementation_authorized"] = True
    plan["status"] = "PRODUCTION_RUNNER_INSTALLED_RUN_UNAUTHORIZED"
    plan["schema_version"] = exp.PRODUCTION_PLAN_SCHEMA
    plan["legacy_gate_repair"] = {
        "version": "v5",
        "goal_alignment_summary_semantics": True,
        "judge_mouth_semantic": True,
        "eos_stop_from_real_stop_metadata_only": True,
        "generated_token_ids_returned": True,
        "manufactured_legacy_pass_removed": True,
    }
    plan_sha = exp._write_json(plan_path, plan)
    status = {
        "experiment_id": exp.EXPERIMENT_ID,
        "implementation_authorized": True,
        "run_authorized": False,
        "training_authorized": False,
        "status": "PRODUCTION_RUNNER_INSTALLED_RUN_UNAUTHORIZED",
        "campaign_root": str(root).replace("\\", "/"),
        "campaign_plan_sha256": plan_sha,
        "plan_sha256": plan_sha,
        "production_plan_schema": exp.PRODUCTION_PLAN_SCHEMA,
        "v4_evidence_preserved": True,
        "next_step_not_done": (
            "Operator may call authorize_once separately after reviewing "
            "exact-runtime nostep preflight; training remains unauthorized."
        ),
    }
    exp._write_json(root / "STATUS.json", status)
    return {
        "plan_sha256": plan_sha,
        "status": status["status"],
        "run_authorized": False,
        "training_authorized": False,
        "mock_evidence": mock_evidence,
        "v3_evidence": v3_evidence,
        "v4_evidence": v4_evidence,
        "production_runner": True,
        "schema_version": exp.PRODUCTION_PLAN_SCHEMA,
        "prior_write": written,
    }


def run_exact_runtime_nostep_preflight(
    *, campaign_root: Path = exp.CAMPAIGN_ROOT
) -> dict[str, Any]:
    """Exact-runtime no-step preflight: same prep as production, 0 train steps.

    Prefers dry path layout (no BEGIN_RUN). Never calls forward/backward/step.
    """
    import torch

    root = Path(campaign_root)
    plan = exp._load_json(root / "campaign_plan.json")
    if plan.get("run_authorized") is not False:
        raise AssertionError("run_authorized_must_remain_false_during_exact_runtime_preflight")
    if plan.get("training_authorized") is not False:
        raise AssertionError(
            "training_authorized_must_remain_false_during_exact_runtime_preflight"
        )
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("cuda_bf16_required:exact_runtime_nostep_preflight")

    t0 = time.perf_counter()
    ram_before = exp._process_rss_bytes()
    vram_before = exp._cuda_mem_info()

    run_id = f"exact_runtime_nostep_{exp.EXPERIMENT_ID}"
    sandbox = Path("L:/Continue/Viv/sandbox/exact_runtime_preflight")
    sandbox.mkdir(parents=True, exist_ok=True)
    layout = _targeted().dry_lease_path_layout(run_id=run_id, sandbox_parent=sandbox)

    model = None
    optimizer = None
    tokenizer = None
    try:
        prepared = _targeted().prepare_targeted_patch_runtime(
            train_jsonl=root / "optimizer_train_16_TRAIN_READY.jsonl",
            parent_adapter=exp.PARENT_ADAPTER,
            system_prompt=exp.SYSTEM_PROMPT,
            learning_rate=exp.PROPOSED_LR,
            gradient_accumulation=exp.GRADIENT_ACCUMULATION,
            staging_root=layout["staging_root"],
            final_root=layout["final_root"],
            load_model=True,
        )
        model = prepared["model"]
        optimizer = prepared["optimizer"]
        tokenizer = prepared["tokenizer"]
        # Explicitly do not call forward/backward/optimizer.step.
        steps_executed = 0
        t1 = time.perf_counter()
        report = {
            "schema_version": "mouth_v3_r2_1_exact_runtime_nostep_preflight_v1",
            "experiment_id": exp.EXPERIMENT_ID,
            "recorded_at": _utc(),
            "pass": True,
            "implementation_authorized": True,
            "run_authorized": False,
            "training_authorized": False,
            "cuda_available": True,
            "precision": "bf16",
            "parent_adapter": str(exp.PARENT_ADAPTER).replace("\\", "/"),
            "learning_rate": exp.PROPOSED_LR,
            "gradient_accumulation": exp.GRADIENT_ACCUMULATION,
            "optimizer_steps_configured": exp.OPTIMIZER_STEPS,
            "optimizer_steps_executed": steps_executed,
            "checkpoint_steps": list(exp.CHECKPOINT_STEPS),
            "encoded_examples": len(prepared["encoded"]),
            "optimizer_rows_only": len(prepared["encoded"]) == 16,
            "lora_coverage": prepared["coverage"],
            "optimizer_constructed": optimizer is not None,
            "model_trainable": True,
            "lease_begin_run_called": False,
            "lease_path_layout_dry": {
                "staging_root": str(layout["staging_root"]).replace("\\", "/"),
                "final_root": str(layout["final_root"]).replace("\\", "/"),
            },
            "forward_executed": False,
            "backward_executed": False,
            "optimizer_step_executed": False,
            "load_seconds": round(t1 - t0, 3),
            "ram_rss_bytes_before": ram_before,
            "ram_rss_bytes_after": exp._process_rss_bytes(),
            "vram_before": vram_before,
            "vram_after": exp._cuda_mem_info(),
            "authorize_once_invoked": False,
            "deployment_changed": False,
        }
        exp._write_json(root / "exact_runtime_nostep_preflight_report.json", report)
        return report
    except Exception as exc:
        fail = {
            "schema_version": "mouth_v3_r2_1_exact_runtime_nostep_preflight_v1",
            "experiment_id": exp.EXPERIMENT_ID,
            "recorded_at": _utc(),
            "pass": False,
            "error": f"{type(exc).__name__}:{exc}",
            "traceback": traceback.format_exc(limit=20),
            "run_authorized": False,
            "training_authorized": False,
            "authorize_once_invoked": False,
        }
        exp._write_json(root / "exact_runtime_nostep_preflight_report.json", fail)
        raise
    finally:
        try:
            if optimizer is not None:
                del optimizer
            if model is not None:
                del model
            if tokenizer is not None:
                del tokenizer
        except Exception:
            pass
        gc.collect()
        try:
            import torch as _torch

            _torch.cuda.empty_cache()
        except Exception:
            pass
        try:
            shutil.rmtree(layout["staging_root"], ignore_errors=True)
            shutil.rmtree(layout["final_root"], ignore_errors=True)
        except Exception:
            pass


def run_experiment(
    *,
    campaign_root: Path,
    authorizations_dir: Path | None = None,
    expected_plan_sha256: str | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Production governed run. Calls real function names (tests patch these)."""
    root = Path(campaign_root)
    plan_path = root / "campaign_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"campaign_plan_missing:{plan_path}")

    token_claimed = False
    lease_opened = False
    lease_handle: Any = None
    authorized_path_entered = False
    auth_dir = (
        Path(authorizations_dir)
        if authorizations_dir is not None
        else exp.AUTHORIZATIONS_DIR
    )
    finally_errors: list[str] = []
    result: dict[str, Any] = {
        "experiment_id": exp.EXPERIMENT_ID,
        "decision": None,
        "lease_opened": False,
        "token_consumed": False,
        "ok": False,
    }

    try:
        plan = exp._load_json(plan_path)
        disk_sha = exp._file_sha256(plan_path)

        if plan.get("experiment_id") != exp.EXPERIMENT_ID:
            raise ValueError(f"experiment_id_mismatch:{plan.get('experiment_id')}")
        if expected_plan_sha256 is not None and expected_plan_sha256.lower() != disk_sha:
            raise ValueError(
                f"plan_sha_token_mismatch:expected={expected_plan_sha256};got={disk_sha}"
            )
        if plan.get("implementation_authorized") is not True:
            raise ValueError(f"implementation_authorized_false:{exp.EXPERIMENT_ID}")
        if plan.get("training_authorized") is not False:
            raise ValueError(f"training_authorized_must_be_false:{exp.EXPERIMENT_ID}")
        if plan.get("run_authorized") is not True:
            raise ValueError(
                "run_authorized_false:"
                f"{exp.EXPERIMENT_ID};"
                "machinery present but experiment start blocked until authorize_once"
            )
        authorized_path_entered = True

        exp.verify_source_locks(plan, campaign_root=root)

        out_root = (
            Path(output_root)
            if output_root is not None
            else Path(plan["checkpoint_paths"]["run_root"])
        )
        if out_root.exists():
            raise ValueError(f"output_root_exists:{out_root}")

        # Mandatory real incumbent evaluator — no synthetic fallback.
        # Abort pre-token and pre-lease on failure/malformed.
        incumbent_report = evaluate_incumbent_baseline(plan=plan, campaign_root=root)
        if incumbent_report.get("pass") is False:
            raise ValueError(
                f"incumbent_baseline_failed_pre_lease:{incumbent_report.get('reason')}"
            )

        exp.consume_named_authorization(
            experiment_id=exp.EXPERIMENT_ID,
            plan_sha256=disk_sha,
            authorizations_dir=auth_dir,
        )
        token_claimed = True
        result["token_consumed"] = True

        lease_handle = open_governed_lease(
            plan=plan, campaign_root=root, output_root=out_root
        )
        lease_opened = True
        result["lease_opened"] = True

        train_result = train_targeted_patch_16(
            plan=plan,
            campaign_root=root,
            output_root=out_root,
            checkpoint_steps=list(exp.CHECKPOINT_STEPS),
            lease=lease_handle,
        )
        if train_result.get("ok") is False:
            raise RuntimeError(f"training_failed:{train_result.get('error')}")
        result["train_result"] = train_result

        eval_bundle = evaluate_run_checkpoints(
            plan=plan,
            campaign_root=root,
            output_root=out_root,
            incumbent_report=incumbent_report,
            checkpoint_steps=list(exp.CHECKPOINT_STEPS),
        )
        result["eval_bundle"] = eval_bundle
        ckpt_reports = eval_bundle.get("checkpoint_reports") or []

        decision = exp.decide_winner(incumbent_report, ckpt_reports)
        result["decision"] = decision
        result["pass"] = decision.get("decision") == "WIN"
        result["ok"] = True
        return result
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}:{exc}"
        raise
    finally:
        if authorized_path_entered or token_claimed or lease_opened:
            try:
                exp.invalidate_named_authorization(
                    experiment_id=exp.EXPERIMENT_ID,
                    reason=(
                        "run_experiment_finally_rearm"
                        if token_claimed
                        else "run_experiment_finally_no_claim"
                    ),
                    authorizations_dir=auth_dir,
                )
            except Exception as exc:
                finally_errors.append(f"token_invalidate_failed:{exc}")
            try:
                if lease_opened and lease_handle is not None:
                    closer = getattr(lease_handle, "close", None)
                    if callable(closer):
                        closer()
                    elif isinstance(lease_handle, dict):
                        lease_handle["closed"] = True
                        lease_handle["quarantined"] = True
            except Exception as exc:
                finally_errors.append(f"lease_close_failed:{exc}")
            try:
                exp._rearm_run_unauthorized(root)
            except Exception as exc:
                finally_errors.append(f"rearm_failed:{exc}")
            result["finally"] = {
                "run_authorized": False,
                "training_authorized": False,
                "token_invalidated_or_consumed": True,
                "lease_closed": "lease_close_failed" not in str(finally_errors),
                "no_retry": True,
                "no_deployment": True,
                "ok": len(finally_errors) == 0,
                "errors": finally_errors,
            }
            if finally_errors:
                result["ok"] = False
                # Surface failure honestly — do not report success after cleanup fail.
                raise RuntimeError(
                    "run_experiment_finally_failed:" + ";".join(finally_errors)
                )
