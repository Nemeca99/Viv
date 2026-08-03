#!/usr/bin/env python3
"""Stage-1 rejection postmortem — evidence only, no train / no mouth switch.

Compares development pair accuracy vs generative mind_pass, stratifies
security-denied vs generated failures, probes prompt format, and locks a
root-cause class before any Stage-1 rerun.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
import sys

for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from voice_core.intent_packet import render_openaster_prompt  # noqa: E402

STAGE1 = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1"
)
PARITY = FOUNDATION / "artifacts" / "auto" / "openaster_parity" / "reports"

DEFAULT_TRAIN = STAGE1 / "stage1_training_result_v1.json"
DEFAULT_DECISION = STAGE1 / "stage1_candidate_decision_v1.json"
DEFAULT_JUDGED = STAGE1 / "stage1_judged_v1.jsonl"
DEFAULT_QWEN = PARITY / "qwen_stage1_dev_posttrain.json"
DEFAULT_CAND = {
    "stage1_dev": PARITY / "candidate_stage1_dev_posttrain.json",
    "stage1_frozen": PARITY / "candidate_stage1_frozen_posttrain.json",
    "stage1_adversarial": PARITY / "candidate_stage1_adversarial_posttrain.json",
}
OUT_JSON = STAGE1 / "stage1_rejection_postmortem_v1.json"
OUT_MD = STAGE1 / "stage1_rejection_postmortem_v1.md"

MIND_FLOOR = 0.68


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(report: dict[str, Any], key: str) -> list[dict[str, Any]]:
    section = report.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"missing_section:{key}")
    rows = section.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"missing_rows:{key}")
    return rows


def _summary(report: dict[str, Any], key: str) -> dict[str, Any]:
    section = report.get(key) or {}
    return dict(section.get("summary") or {})


def _is_security_request_denied(row: dict[str, Any]) -> bool:
    err = str(row.get("error") or "")
    if err.startswith("security_request_denied"):
        return True
    return str(row.get("stop_reason") or "") == "security_denied" and not (
        row.get("text") or ""
    ).strip()


def stratify_pack(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sec_deny: list[dict[str, Any]] = []
    generated: list[dict[str, Any]] = []
    for row in rows:
        if _is_security_request_denied(row):
            sec_deny.append(row)
        else:
            generated.append(row)

    def rate(xs: list[dict[str, Any]], pred) -> float | None:
        if not xs:
            return None
        return round(sum(1 for r in xs if pred(r)) / len(xs), 4)

    mind_fail_axes: Counter[str] = Counter()
    for row in generated:
        if row.get("mind_pass"):
            continue
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        mind_fail_axes[
            f"vidi={scores.get('vidi')}|intellexi={scores.get('intellexi')}|"
            f"label={scores.get('label')}|sec_rej={bool(scores.get('security_rejected'))}"
        ] += 1

    deny_reasons: Counter[str] = Counter()
    for row in sec_deny:
        sec = row.get("security") if isinstance(row.get("security"), dict) else {}
        req = sec.get("request") if isinstance(sec.get("request"), dict) else {}
        deny_reasons[str(req.get("reason") or row.get("error") or "unknown")] += 1

    empty_gen = sum(1 for r in generated if not str(r.get("text") or "").strip())
    gen_err = sum(1 for r in generated if r.get("error"))
    invalid = sum(1 for r in generated if not r.get("valid_speech"))
    collapse = sum(1 for r in generated if r.get("repetition_collapse"))
    numeric = sum(1 for r in generated if r.get("numeric_prefix"))

    return {
        "n": len(rows),
        "security_request_denied": len(sec_deny),
        "security_request_denied_rate": round(len(sec_deny) / len(rows), 4) if rows else None,
        "security_deny_reasons": dict(deny_reasons),
        "generated_n": len(generated),
        "generated_empty": empty_gen,
        "generated_error": gen_err,
        "generated_invalid_speech": invalid,
        "generated_collapse": collapse,
        "generated_numeric_prefix": numeric,
        "raw_mind_pass_rate": rate(rows, lambda r: r.get("mind_pass")),
        "raw_valid_speech_rate": rate(rows, lambda r: r.get("valid_speech")),
        "conditional_mind_pass_rate": rate(generated, lambda r: r.get("mind_pass")),
        "conditional_valid_speech_rate": rate(generated, lambda r: r.get("valid_speech")),
        "mind_fail_axis_counts": dict(mind_fail_axes.most_common(12)),
    }


def sample_texts(
    rows: list[dict[str, Any]], *, mind_pass: bool, limit: int = 5
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if _is_security_request_denied(row):
            continue
        if bool(row.get("mind_pass")) != mind_pass:
            continue
        text = str(row.get("text") or "")
        if not text.strip() and not mind_pass:
            # still include empty generated failures
            pass
        out.append(
            {
                "case_id": row.get("case_id"),
                "mind_pass": bool(row.get("mind_pass")),
                "valid_speech": bool(row.get("valid_speech")),
                "error": row.get("error"),
                "stop_reason": row.get("stop_reason"),
                "text": text[:240].replace("\n", " "),
                "label": (row.get("scores") or {}).get("label")
                if isinstance(row.get("scores"), dict)
                else None,
            }
        )
        if len(out) >= limit:
            break
    return out


def load_judged_by_ask(path: Path) -> dict[str, dict[str, Any]]:
    by_ask: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ask = str(row.get("ask") or "").strip()
        if ask and ask not in by_ask:
            by_ask[ask] = row
    return by_ask


def _one_prompt_probe(
    row: dict[str, Any],
    *,
    by_case: dict[str, dict[str, Any]],
    judged_by_ask: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    case_id = str(row.get("case_id") or "")
    case = by_case.get(case_id)
    if not case:
        return None
    ask = str(case.get("ask") or "").strip()
    judged = judged_by_ask.get(ask)
    packet = {
        "query": ask,
        "tone": "calm",
        "facts": list(case.get("facts") or []),
        "memory": [],
        "semantic_key": case.get("semantic_class") or case.get("semantic_key"),
        "s_n": 0.5,
    }
    try:
        rendered = render_openaster_prompt(
            packet, semantic_key=str(packet.get("semantic_key") or "")
        )
    except Exception as exc:  # noqa: BLE001
        rendered = f"<render_error:{exc}>"
    train_prompt = str((judged or {}).get("prompt") or "")
    return {
        "case_id": case_id,
        "ask": ask[:160],
        "train_prompt_prefix": train_prompt[:220].replace("\n", "\\n"),
        "eval_prompt_prefix": rendered[:220].replace("\n", "\\n"),
        "train_uses_chatml": "<|im_start|>" in train_prompt,
        "eval_uses_chatml": "<|im_start|>" in rendered,
        "train_assistant_prefix": train_prompt.rstrip().endswith("Viv:")
        or "Viv: " in train_prompt[-40:],
        "prompts_share_openaster_v4": "openaster_prompt_v4" in train_prompt
        and "openaster_prompt_v4" in rendered,
        "judged_pair_id": (judged or {}).get("pair_id"),
        "candidate_mind_pass": bool(row.get("mind_pass")),
        "candidate_security_denied": _is_security_request_denied(row),
    }


def prompt_probe(
    *,
    cand_dev_rows: list[dict[str, Any]],
    judged_by_ask: dict[str, dict[str, Any]],
    pack_cases: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Offline compare train prompt prefix vs eval render_openaster_prompt.

    Prefer a mix of security-denied and actually-generated rows.
    """
    by_case = {str(c.get("case_id")): c for c in pack_cases}
    denied = [r for r in cand_dev_rows if _is_security_request_denied(r)]
    generated = [r for r in cand_dev_rows if not _is_security_request_denied(r)]
    ordered = denied[:2] + generated[:3]
    if len(ordered) < limit:
        seen = {str(r.get("case_id")) for r in ordered}
        for row in cand_dev_rows:
            cid = str(row.get("case_id") or "")
            if cid in seen:
                continue
            ordered.append(row)
            seen.add(cid)
            if len(ordered) >= limit:
                break
    probes: list[dict[str, Any]] = []
    for row in ordered[:limit]:
        probe = _one_prompt_probe(
            row, by_case=by_case, judged_by_ask=judged_by_ask
        )
        if probe:
            probes.append(probe)
    return probes


def load_stage1_pack_cases(split: str) -> list[dict[str, Any]]:
    """Load pack cases the same way evaluate_openaster_parity does."""
    from scripts.evaluate_openaster_parity import stage1_pack

    return list(stage1_pack(split))


def decide_root_cause(
    *,
    pair_acc: float,
    packs: dict[str, dict[str, Any]],
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    contributors: list[dict[str, Any]] = []

    # Security asymmetry on candidate packs
    deny_rates = [
        float(p.get("security_request_denied_rate") or 0.0) for p in packs.values()
    ]
    max_deny = max(deny_rates) if deny_rates else 0.0
    if max_deny >= 0.15:
        contributors.append(
            {
                "class": "eval_security_ingress_asymmetry",
                "weight": 0.35,
                "evidence": f"max_security_deny_rate={max_deny}",
            }
        )

    # Conditional generative quality after excluding security denials
    cond_dev = packs.get("stage1_dev", {}).get("conditional_mind_pass_rate")
    cond_valid = packs.get("stage1_dev", {}).get("conditional_valid_speech_rate")
    pairwise_flag = False
    if pair_acc >= 0.90 and cond_dev is not None and float(cond_dev) < MIND_FLOOR:
        pairwise_flag = True
        contributors.append(
            {
                "class": "pairwise_vs_generative_mismatch",
                "weight": 0.55,
                "evidence": (
                    f"pair_accuracy={pair_acc} conditional_mind_pass_dev={cond_dev} "
                    f"(floor={MIND_FLOOR})"
                ),
            }
        )

    # Prompt mismatch probe
    if probes:
        share = sum(1 for p in probes if p.get("prompts_share_openaster_v4")) / len(
            probes
        )
        chatml_both = all(
            p.get("train_uses_chatml") and p.get("eval_uses_chatml") for p in probes
        )
        if share < 0.6 or not chatml_both:
            contributors.append(
                {
                    "class": "prompt_template_mismatch",
                    "weight": 0.4,
                    "evidence": f"openaster_v4_share={share:.2f} chatml_both={chatml_both}",
                }
            )

    # Catastrophic language: generated but empty/invalid dominant
    if cond_valid is not None and float(cond_valid) < 0.5:
        contributors.append(
            {
                "class": "catastrophic_language_degradation",
                "weight": 0.5,
                "evidence": f"conditional_valid_speech_dev={cond_valid}",
            }
        )

    if not contributors:
        contributors.append(
            {
                "class": "mixed",
                "weight": 1.0,
                "evidence": "no_strong_single_signature",
            }
        )

    contributors.sort(key=lambda c: float(c["weight"]), reverse=True)
    primary = contributors[0]["class"]
    secondary = contributors[1]["class"] if len(contributors) > 1 else None
    if len(contributors) > 1 and abs(
        float(contributors[0]["weight"]) - float(contributors[1]["weight"])
    ) < 0.08:
        primary = "mixed"

    return {
        "primary_root_cause_class": primary,
        "secondary_root_cause_class": secondary,
        "contributors": contributors,
        "pairwise_discrimination_without_generation": pairwise_flag,
        "interpretation": (
            "Training taught pair ranking (development pair_accuracy≈1.0) while "
            "free-form generation remained below admission floors after excluding "
            "security denials."
            if pairwise_flag
            else "See contributors."
        ),
    }


def build_postmortem(
    *,
    train_path: Path,
    decision_path: Path,
    qwen_path: Path,
    cand_paths: dict[str, Path],
    judged_path: Path,
) -> dict[str, Any]:
    train = _load(train_path)
    decision = _load(decision_path)
    qwen = _load(qwen_path)
    pair_acc = float((train.get("development") or {}).get("pair_accuracy") or 0.0)
    pair_loss = (train.get("development") or {}).get("loss")

    pack_stats: dict[str, Any] = {}
    samples: dict[str, Any] = {}
    for key, path in cand_paths.items():
        report = _load(path)
        rows = _rows(report, key)
        stats = stratify_pack(rows)
        stats["raw_summary"] = _summary(report, key)
        stats["artifact"] = str(path).replace("\\", "/")
        stats["sha256"] = _sha256(path)
        pack_stats[key] = stats
        samples[key] = {
            "mind_fail": sample_texts(rows, mind_pass=False, limit=5),
            "mind_pass": sample_texts(rows, mind_pass=True, limit=5),
        }

    qwen_rows = _rows(qwen, "stage1_dev")
    qwen_stats = stratify_pack(qwen_rows)
    qwen_stats["raw_summary"] = _summary(qwen, "stage1_dev")
    qwen_stats["artifact"] = str(qwen_path).replace("\\", "/")
    qwen_stats["sha256"] = _sha256(qwen_path)

    judged_by_ask = load_judged_by_ask(judged_path)
    try:
        pack_cases = load_stage1_pack_cases("development")
    except Exception as exc:  # noqa: BLE001
        pack_cases = []
        pack_case_error = str(exc)
    else:
        pack_case_error = None

    probes = prompt_probe(
        cand_dev_rows=_rows(_load(cand_paths["stage1_dev"]), "stage1_dev"),
        judged_by_ask=judged_by_ask,
        pack_cases=pack_cases,
        limit=5,
    )

    root = decide_root_cause(
        pair_acc=pair_acc, packs=pack_stats, probes=probes
    )

    adapter = Path(str(train.get("adapter") or ""))
    adapter_ok = (
        adapter.is_dir()
        and (adapter / "adapter_model.safetensors").is_file()
        and (adapter / "adapter_config.json").is_file()
    )

    gap = {
        "development_pair_accuracy": pair_acc,
        "development_pair_loss": pair_loss,
        "qwen_dev_mind_pass_rate": qwen_stats.get("raw_mind_pass_rate"),
        "candidate_dev_mind_pass_rate_raw": pack_stats["stage1_dev"].get(
            "raw_mind_pass_rate"
        ),
        "candidate_dev_mind_pass_rate_conditional": pack_stats["stage1_dev"].get(
            "conditional_mind_pass_rate"
        ),
        "pair_minus_conditional_mind": (
            round(pair_acc - float(pack_stats["stage1_dev"]["conditional_mind_pass_rate"]), 4)
            if pack_stats["stage1_dev"].get("conditional_mind_pass_rate") is not None
            else None
        ),
        "pair_minus_raw_mind": (
            round(pair_acc - float(pack_stats["stage1_dev"]["raw_mind_pass_rate"]), 4)
            if pack_stats["stage1_dev"].get("raw_mind_pass_rate") is not None
            else None
        ),
    }

    return {
        "ok": True,
        "at": _utc(),
        "schema_version": "stage1_rejection_postmortem_v1",
        "decision": decision.get("decision"),
        "failed_criteria": decision.get("failed_criteria"),
        "inputs": {
            "training_result": {
                "path": str(train_path).replace("\\", "/"),
                "sha256": _sha256(train_path),
            },
            "decision": {
                "path": str(decision_path).replace("\\", "/"),
                "sha256": _sha256(decision_path),
            },
            "judged_corpus": {
                "path": str(judged_path).replace("\\", "/"),
                "sha256": _sha256(judged_path),
            },
            "adapter": {
                "path": str(adapter).replace("\\", "/") if adapter else None,
                "present": adapter_ok,
            },
        },
        "pair_vs_generate_gap": gap,
        "qwen_stage1_dev": qwen_stats,
        "candidate_packs": pack_stats,
        "security_asymmetry": {
            "qwen_teacher_security_deny_rate": qwen_stats.get(
                "security_request_denied_rate"
            ),
            "openaster_target_security_deny_rates": {
                k: v.get("security_request_denied_rate") for k, v in pack_stats.items()
            },
            "note": (
                "Eval request gate uses model_role=openaster_target for candidate "
                "vs qwen_teacher for Qwen baseline (evaluate_openaster_parity.score_case)."
            ),
        },
        "prompt_format_probe": {
            "n": len(probes),
            "pack_case_load_error": pack_case_error,
            "probes": probes,
        },
        "speech_samples": samples,
        "root_cause": root,
        "next_action": "no_stage1_rerun_until_postmortem_accepted",
        "authority": {
            "live_backend_unchanged": "qwen_gguf",
            "validated_candidate": None,
            "deployment_changed": False,
            "candidate_withheld": True,
            "learning_admission_withheld": True,
            "master_routing_authorized": False,
            "gates_action": False,
            "hyperparameters_unchanged": True,
        },
        "current_truth": (
            "Viv can speak reliably through Qwen + sovereign Stage-1 mouth not yet viable"
        ),
    }


def to_md(payload: dict[str, Any]) -> str:
    gap = payload.get("pair_vs_generate_gap") or {}
    root = payload.get("root_cause") or {}
    lines = [
        "# Stage-1 rejection postmortem",
        "",
        f"- at: `{payload.get('at')}`",
        f"- decision: **{payload.get('decision')}**",
        f"- primary_root_cause_class: **{root.get('primary_root_cause_class')}**",
        f"- secondary_root_cause_class: `{root.get('secondary_root_cause_class')}`",
        f"- pairwise_discrimination_without_generation: "
        f"`{root.get('pairwise_discrimination_without_generation')}`",
        f"- next_action: `{payload.get('next_action')}`",
        "",
        "## Pair accuracy vs generative mind_pass",
        "",
        f"- development pair_accuracy: **{gap.get('development_pair_accuracy')}**",
        f"- development pair_loss: `{gap.get('development_pair_loss')}`",
        f"- Qwen stage1_dev mind_pass: **{gap.get('qwen_dev_mind_pass_rate')}**",
        f"- candidate stage1_dev mind_pass (raw): "
        f"**{gap.get('candidate_dev_mind_pass_rate_raw')}**",
        f"- candidate stage1_dev mind_pass (conditional on generated): "
        f"**{gap.get('candidate_dev_mind_pass_rate_conditional')}**",
        f"- gap pair−conditional: `{gap.get('pair_minus_conditional_mind')}`",
        "",
        "## Candidate pack taxonomy",
        "",
    ]
    for key, stats in (payload.get("candidate_packs") or {}).items():
        lines.append(f"### {key}")
        lines.append(
            f"- n={stats.get('n')} security_denied={stats.get('security_request_denied')} "
            f"({stats.get('security_request_denied_rate')}) "
            f"generated={stats.get('generated_n')}"
        )
        lines.append(
            f"- raw mind/valid: {stats.get('raw_mind_pass_rate')} / "
            f"{stats.get('raw_valid_speech_rate')}"
        )
        lines.append(
            f"- conditional mind/valid: {stats.get('conditional_mind_pass_rate')} / "
            f"{stats.get('conditional_valid_speech_rate')}"
        )
        lines.append(f"- deny reasons: `{stats.get('security_deny_reasons')}`")
        lines.append("")
    sec = payload.get("security_asymmetry") or {}
    lines.extend(
        [
            "## Security asymmetry",
            "",
            f"- Qwen deny rate: `{sec.get('qwen_teacher_security_deny_rate')}`",
            f"- OpenAster deny rates: `{sec.get('openaster_target_security_deny_rates')}`",
            f"- note: {sec.get('note')}",
            "",
            "## Prompt-format probe",
            "",
        ]
    )
    for probe in (payload.get("prompt_format_probe") or {}).get("probes") or []:
        lines.append(
            f"- `{probe.get('case_id')}` share_v4={probe.get('prompts_share_openaster_v4')} "
            f"train_chatml={probe.get('train_uses_chatml')} "
            f"eval_chatml={probe.get('eval_uses_chatml')} "
            f"mind={probe.get('candidate_mind_pass')} "
            f"sec_deny={probe.get('candidate_security_denied')}"
        )
    lines.extend(
        [
            "",
            "## Root cause",
            "",
            f"- interpretation: {root.get('interpretation')}",
            f"- contributors: `{root.get('contributors')}`",
            "",
            "## Authority",
            "",
            f"- `{payload.get('authority')}`",
            "",
            f"**Current truth:** {payload.get('current_truth')}",
            "",
            "No Stage-1 rerun and no hyperparameter changes in this step.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", type=Path, default=DEFAULT_TRAIN)
    ap.add_argument("--decision", type=Path, default=DEFAULT_DECISION)
    ap.add_argument("--qwen", type=Path, default=DEFAULT_QWEN)
    ap.add_argument("--judged", type=Path, default=DEFAULT_JUDGED)
    args = ap.parse_args()
    payload = build_postmortem(
        train_path=args.train,
        decision_path=args.decision,
        qwen_path=args.qwen,
        cand_paths=DEFAULT_CAND,
        judged_path=args.judged,
    )
    STAGE1.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(to_md(payload), encoding="utf-8")
    payload["artifact"] = str(OUT_JSON).replace("\\", "/")
    payload["artifact_md"] = str(OUT_MD).replace("\\", "/")
    print(
        json.dumps(
            {
                "ok": payload.get("ok"),
                "primary_root_cause_class": (payload.get("root_cause") or {}).get(
                    "primary_root_cause_class"
                ),
                "secondary_root_cause_class": (payload.get("root_cause") or {}).get(
                    "secondary_root_cause_class"
                ),
                "pairwise_discrimination_without_generation": (
                    payload.get("root_cause") or {}
                ).get("pairwise_discrimination_without_generation"),
                "pair_vs_generate_gap": payload.get("pair_vs_generate_gap"),
                "next_action": payload.get("next_action"),
                "artifact": payload["artifact"],
                "artifact_md": payload["artifact_md"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
