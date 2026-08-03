"""Judge training gate — GPU may speak; only judge-stamped pairs may train.

Alignment ceiling: Viv cannot learn beyond what viv_shadow_judge admits.
Architect sets criteria; humans do not live-rank chat for soul training.

LoRA admission (v1): executable policy → train_ready signal (no online interleave).
Hold-out mind_pass rides inside the pre-flight check.
"""
from __future__ import annotations

import json
import random
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS, ARTIFACTS, FOUNDATION_ROOT
from lib.aifl_contracts import validate_preference_row
from lib.viv_shadow_judge import PREFERENCE_JSONL, load_criteria, score_draft

# SFT harden defaults (overridable via admission_policy.json → sft_harden)
DEFAULT_MAX_TEXT_REPEATS = 3
DEFAULT_SOFT_HOLD_MIN_FRAC = 0.20
DEFAULT_HARDEN_SEED = 7

GATE_DIR = AUTO_ARTIFACTS / "shadow_judge"
TRAIN_ADMIT_JSONL = GATE_DIR / "train_admit.jsonl"
TRAIN_REJECT_JSONL = GATE_DIR / "train_reject.jsonl"
VOICE_JUDGE_SFT = ARTIFACTS / "models" / "viv_judge_sft_train.jsonl"
TRAIN_READY_DIR = GATE_DIR / "train_ready"
TRAIN_READY_SIGNAL = TRAIN_READY_DIR / "signal.json"
GATE_STATE_PATH = GATE_DIR / "gate_state.json"
ADMISSION_POLICY_PATH = GATE_DIR / "admission_policy.json"
HOLDOUT_PACK_PATH = GATE_DIR / "holdout_pack.jsonl"
HOLDOUT_LAST_PATH = GATE_DIR / "holdout_last.json"
ADMISSION_LOG = GATE_DIR / "admission_log.jsonl"
ROLLBACK_EVENTS_PATH = GATE_DIR / "rollback_events.jsonl"
DEPLOY_ABSOLUTE_FLOOR = 0.68

# Experiment / flag (rollback = set enabled false in admission_policy.json)
EXPERIMENT_ID = "lora_admit_v1"
FLAG_NAME = "lora_admission.enabled"

_DEFAULT_POLICY: dict[str, Any] = {
    "version": 1,
    "experiment_id": EXPERIMENT_ID,
    "flag": FLAG_NAME,
    "enabled": True,
    "auto_train": False,
    "min_reward_pairs": 50,
    "reward_delta_trigger": 50,
    "rolling_window": 100,
    "mind_pass_min": 0.95,
    "punish_max": 0.05,
    "holdout_max_drop": 0.02,
    "holdout_target_size": 60,
    "dataset": "viv_judge_sft_train.jsonl",
    "forbid_corpora": ["voice_fluency.jsonl", "instruct", "helpful"],
    "lora": {
        "r": 16,
        "lora_alpha": 32,
        "lr": 2e-4,
        "max_steps": 80,
        "epochs": 1,
        "adapter_out": "L:/Continue/Viv/foundation/models/Training/runs/lora_judge_{steps}_{timestamp}/adapter",
        "adapter_out_pattern": "L:/Continue/Viv/foundation/models/Training/runs/lora_judge_{steps}_{timestamp}",
        "training_home": "L:/Continue/Viv/foundation/models/Training",
    },
    "note": "Signal only until auto_train; trainer consumes viv_judge_sft_train.jsonl exclusively. Runs land in models/Training/runs/.",
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.is_file():
        return dict(default or {})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default or {})
    except (OSError, json.JSONDecodeError):
        return dict(default or {})


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_admission_policy() -> dict[str, Any]:
    """Config-over-constants: disk policy wins over defaults."""
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    if not ADMISSION_POLICY_PATH.is_file():
        _write_json(ADMISSION_POLICY_PATH, _DEFAULT_POLICY)
        return dict(_DEFAULT_POLICY)
    disk = _read_json(ADMISSION_POLICY_PATH, _DEFAULT_POLICY)
    merged = {**_DEFAULT_POLICY, **disk}
    if isinstance(disk.get("lora"), dict):
        merged["lora"] = {**_DEFAULT_POLICY["lora"], **disk["lora"]}
    return merged


def save_admission_policy(policy: dict[str, Any]) -> Path:
    _write_json(ADMISSION_POLICY_PATH, policy)
    return ADMISSION_POLICY_PATH


def deployed_validate_baseline() -> float | None:
    """Last known hold-out mind_pass for the adapter currently in production."""
    lv = (load_admission_policy().get("lora") or {}).get("last_validate") or {}
    raw = lv.get("mind_pass_rate")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def evaluate_adapter_deploy(
    mind_pass_rate: float,
    *,
    absolute_floor: float = DEPLOY_ABSOLUTE_FLOOR,
) -> dict[str, Any]:
    """Deploy only if absolute floor passes and score does not regress vs deployed."""
    deployed = deployed_validate_baseline()
    passes_floor = float(mind_pass_rate) >= float(absolute_floor)
    passes_deployed = deployed is None or float(mind_pass_rate) >= float(deployed)
    deploy = passes_floor and passes_deployed
    if deploy:
        reason = "ok"
    elif not passes_floor:
        reason = "below_absolute_floor"
    else:
        reason = "regression_vs_deployed"
    return {
        "deploy": deploy,
        "deploy_candidate": deploy,
        "reason": reason,
        "mind_pass_rate": round(float(mind_pass_rate), 4),
        "absolute_floor": float(absolute_floor),
        "deployed_baseline": round(deployed, 4) if deployed is not None else None,
        "delta_vs_deployed": round(float(mind_pass_rate) - deployed, 4) if deployed is not None else None,
    }


def log_adapter_rollback_event(
    *,
    adapter: str,
    validate: dict[str, Any],
    deployed_adapter: str | None = None,
    train_loss: float | None = None,
    steps: int | None = None,
    source: str = "auto_train_cycle",
) -> Path:
    """Append deploy rejection — keeps deploy pointer on previous adapter."""
    policy = load_admission_policy()
    deployed = deployed_adapter or (policy.get("lora") or {}).get("deployed_adapter")
    decision = validate.get("deploy_decision") or {}
    row = {
        "at": _utc(),
        "event": "adapter_deploy_rollback",
        "source": source,
        "reason": decision.get("reason") or validate.get("rollback_reason") or "validate_failed",
        "adapter_candidate": str(adapter).replace("\\", "/"),
        "deployed_adapter_kept": str(deployed).replace("\\", "/") if deployed else None,
        "mind_pass_rate": validate.get("mind_pass_rate"),
        "deployed_baseline": decision.get("deployed_baseline"),
        "absolute_floor": decision.get("absolute_floor"),
        "delta_vs_deployed": decision.get("delta_vs_deployed"),
        "train_loss": train_loss,
        "steps": steps,
        "validate_artifact": validate.get("artifact"),
        "n": validate.get("n"),
    }
    _append_jsonl(ROLLBACK_EVENTS_PATH, row)
    return ROLLBACK_EVENTS_PATH


def load_gate_state() -> dict[str, Any]:
    return _read_json(
        GATE_STATE_PATH,
        {
            "frozen": False,
            "reward_watermark": 0,
            "last_signal_at": None,
            "last_train_consumed_at": None,
            "holdout_baseline_mind_pass": None,
            "holdout_baseline_at": None,
        },
    )


def save_gate_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _utc()
    _write_json(GATE_STATE_PATH, state)


def classify_label(scores: dict[str, Any] | None, label: str | None) -> str:
    """Normalize to REWARD | PUNISH | SOFT_HOLD."""
    s = scores or {}
    vidi = int(s.get("vidi") or s.get("useful") or s.get("honest") or 0)
    intellexi = int(s.get("intellexi") or s.get("understanding") or 0)
    vixi = int(s.get("vixi") or 0)
    stamp = int(s.get("stamp") if s.get("stamp") is not None else vidi * intellexi * vixi)
    if stamp == 1:
        return "REWARD"
    if vidi == 1 and intellexi == 1 and vixi == 0:
        return "SOFT_HOLD"
    # Legacy stamp=1 without axis split still REWARD above; else use label or product of useful/honest/understanding
    if "vidi" not in s and "intellexi" not in s:
        u = int(s.get("useful") or 0)
        h = int(s.get("honest") or 0)
        und = int(s.get("understanding") or 0)
        if u and h and und and int(s.get("stamp") or 0) == 1:
            return "REWARD"
        if u and h and und and int(s.get("stamp") or 0) == 0:
            return "SOFT_HOLD"
    raw = (label or "").upper()
    if raw in {"REWARD", "PUNISH", "SOFT_HOLD"}:
        if stamp == 0 and raw == "REWARD" and not (vidi and intellexi):
            return "PUNISH"
        return raw
    return "PUNISH"


def _mind_pass_from_scores(scores: dict[str, Any] | None) -> bool:
    s = scores or {}
    if "vidi" in s or "intellexi" in s:
        return int(s.get("vidi") or 0) == 1 and int(s.get("intellexi") or 0) == 1
    # Legacy triad packed as useful/honest/understanding
    return (
        int(s.get("useful") or 0) == 1
        and int(s.get("honest") or 0) == 1
        and int(s.get("understanding") or 0) == 1
    )


def admit_pair(row: dict[str, Any], *, admit_soft_hold: bool | None = None) -> dict[str, Any]:
    """Return admit decision for one preference row."""
    if admit_soft_hold is None:
        admit_soft_hold = bool(load_admission_policy().get("admit_soft_hold"))
    schema_errors = validate_preference_row(row) if str(row.get("source") or "") == "viv_shadow_judge" else []
    scores = row.get("chosen_scores") or row.get("scores") or {}
    alignment_required = bool(row.get("alignment_required", False))
    unanimous_alignment = bool(row.get("unanimous_alignment", True))
    alignment_ok = (not alignment_required) or unanimous_alignment
    cs = row.get("chosen_scores") if isinstance(row.get("chosen_scores"), dict) else {}
    label = classify_label(scores, cs.get("label") if cs else row.get("label"))
    source = str(row.get("source") or "")
    stamped = source == "viv_shadow_judge" or "vidi" in scores or "stamp" in scores or "useful" in scores
    admit_reward = not schema_errors and stamped and label == "REWARD" and bool((row.get("chosen") or "").strip()) and alignment_ok
    admit_soft = (
        not schema_errors
        and admit_soft_hold
        and stamped
        and label == "SOFT_HOLD"
        and bool((row.get("chosen") or "").strip())
        and alignment_ok
    )
    admit_punish_contrast = not schema_errors and stamped and label == "PUNISH" and bool(row.get("rejected")) and alignment_ok
    kind = (
        "reward"
        if admit_reward
        else "soft_hold"
        if admit_soft
        else "punish_contrast"
        if admit_punish_contrast
        else "reject"
    )
    return {
        "admit": bool(admit_reward or admit_soft or admit_punish_contrast),
        "admit_kind": kind,
        "label": label,
        "stamped": stamped,
        "alignment_required": alignment_required,
        "unanimous_alignment": unanimous_alignment,
        "alignment_ok": alignment_ok,
        "schema_errors": schema_errors,
        "reason": (
            "ok_reward"
            if admit_reward
            else "ok_soft_hold_plant_dormant"
            if admit_soft
            else "ok_punish_contrast"
            if admit_punish_contrast
            else "invalid_preference_schema"
            if schema_errors
            else "draft_set_not_unanimously_aligned"
            if alignment_required and not unanimous_alignment
            else "soft_hold_excluded"
            if label == "SOFT_HOLD"
            else "unsigned_or_empty"
        ),
    }


def preference_to_sft_rows(row: dict[str, Any], decision: dict[str, Any]) -> list[dict[str, Any]]:
    """Build chat-less completion rows for later LoRA — judge-gated only."""
    if not decision.get("admit"):
        return []
    ask = str(row.get("ask") or "").strip()
    chosen = str(row.get("chosen") or "").strip()
    out: list[dict[str, Any]] = []
    if decision.get("admit_kind") in {"reward", "soft_hold"} and ask and chosen:
        out.append(
            {
                "text": f"Architect: {ask}\nViv: {chosen}",
                "label": "REWARD" if decision.get("admit_kind") == "reward" else "SOFT_HOLD",
                "source": "shadow_judge",
                "at": _utc(),
                "scores": row.get("chosen_scores"),
                "plant_note": "vixi_live" if decision.get("admit_kind") == "reward" else "soft_hold_dormant",
            }
        )
    if decision.get("admit_kind") == "punish_contrast":
        for rej in row.get("rejected") or []:
            bad = str((rej or {}).get("text") or "").strip()
            if ask and bad and chosen and bad != chosen:
                out.append(
                    {
                        "text": f"Architect: {ask}\nViv: {chosen}",
                        "label": "REWARD_OVER_REJECT",
                        "rejected": bad[:400],
                        "source": "shadow_judge",
                        "at": _utc(),
                        "scores": row.get("chosen_scores"),
                    }
                )
                break
    return out


def _iter_preference_rows(*, limit: int | None = None) -> list[dict[str, Any]]:
    if not PREFERENCE_JSONL.is_file():
        return []
    lines = PREFERENCE_JSONL.read_text(encoding="utf-8").splitlines()
    if limit is not None:
        lines = lines[-max(1, limit) :]
    rows: list[dict[str, Any]] = []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def count_reward_pairs(rows: list[dict[str, Any]] | None = None) -> int:
    rows = rows if rows is not None else _iter_preference_rows()
    n = 0
    for row in rows:
        scores = row.get("chosen_scores") or {}
        lab = classify_label(scores, scores.get("label") if isinstance(scores, dict) else row.get("label"))
        if lab == "REWARD":
            n += 1
    return n


def count_mind_pass_pairs(rows: list[dict[str, Any]] | None = None) -> int:
    """REWARD + SOFT_HOLD — speech quality count (plant may be dormant)."""
    rows = rows if rows is not None else _iter_preference_rows()
    n = 0
    for row in rows:
        scores = row.get("chosen_scores") or {}
        lab = classify_label(scores, scores.get("label") if isinstance(scores, dict) else row.get("label"))
        if lab in {"REWARD", "SOFT_HOLD"}:
            n += 1
    return n


def rolling_quality(rows: list[dict[str, Any]], *, window: int) -> dict[str, Any]:
    """mind_pass / punish over last N preference stamps (admission candidates)."""
    tail = rows[-max(1, window) :] if rows else []
    if not tail:
        return {
            "n": 0,
            "mind_pass_rate": 0.0,
            "punish_rate": 0.0,
            "reward": 0,
            "soft_hold": 0,
            "punish": 0,
        }
    mind = 0
    punish = 0
    reward = 0
    soft = 0
    for row in tail:
        scores = row.get("chosen_scores") or {}
        lab = classify_label(scores, scores.get("label") if isinstance(scores, dict) else row.get("label"))
        if lab == "PUNISH":
            punish += 1
        if lab in {"REWARD", "SOFT_HOLD"} or _mind_pass_from_scores(scores):
            if lab != "PUNISH":
                mind += 1
        if lab == "REWARD":
            reward += 1
        elif lab == "SOFT_HOLD":
            soft += 1
    n = len(tail)
    return {
        "n": n,
        "mind_pass_rate": round(mind / n, 4),
        "punish_rate": round(punish / n, 4),
        "reward": reward,
        "soft_hold": soft,
        "punish": punish,
    }


def ensure_holdout_pack(*, target_size: int = 60, force: bool = False) -> dict[str, Any]:
    """Freeze a mixed historic preference slice for judge-drift checks.

    Once hashed/frozen in holdout_registry.json, refuses regen unless force=True.
    """
    from lib.aifl_holdout_split import freeze_holdout_registry_from_pack, load_registry

    reg = load_registry()
    if HOLDOUT_PACK_PATH.is_file() and reg.get("frozen") and not force:
        n = sum(1 for ln in HOLDOUT_PACK_PATH.read_text(encoding="utf-8").splitlines() if ln.strip())
        return {
            "ok": True,
            "path": str(HOLDOUT_PACK_PATH).replace("\\", "/"),
            "n": n,
            "created": False,
            "frozen": True,
            "pack_id": reg.get("pack_id"),
        }

    if HOLDOUT_PACK_PATH.is_file() and not force:
        # Existing pack: attach permanent hashes without reshuffling cases.
        fr = freeze_holdout_registry_from_pack(force=False)
        n = sum(1 for ln in HOLDOUT_PACK_PATH.read_text(encoding="utf-8").splitlines() if ln.strip())
        return {
            "ok": True,
            "path": str(HOLDOUT_PACK_PATH).replace("\\", "/"),
            "n": n,
            "created": False,
            "frozen": bool(fr.get("frozen")),
            "pack_id": fr.get("pack_id"),
            "registry": fr,
        }

    rows = _iter_preference_rows()
    buckets: dict[str, list[dict[str, Any]]] = {"REWARD": [], "PUNISH": [], "SOFT_HOLD": []}
    for row in rows:
        scores = row.get("chosen_scores") or {}
        lab = classify_label(scores, scores.get("label") if isinstance(scores, dict) else row.get("label"))
        if lab in buckets and (row.get("ask") or "").strip() and (row.get("chosen") or "").strip():
            buckets[lab].append(row)

    selected: list[dict[str, Any]] = []
    per = max(1, target_size // 3)
    for lab in ("REWARD", "PUNISH", "SOFT_HOLD"):
        selected.extend(buckets[lab][-per:])
    # Fill remainder from newest overall
    if len(selected) < target_size:
        seen = {(str(x.get("ask")), str(x.get("chosen"))) for x in selected}
        for row in reversed(rows):
            key = (str(row.get("ask")), str(row.get("chosen")))
            if key in seen:
                continue
            if not (row.get("ask") or "").strip() or not (row.get("chosen") or "").strip():
                continue
            selected.append(row)
            seen.add(key)
            if len(selected) >= target_size:
                break

    from lib.aifl_holdout_split import annotate_pair_ids

    GATE_DIR.mkdir(parents=True, exist_ok=True)
    with HOLDOUT_PACK_PATH.open("w", encoding="utf-8") as fh:
        for row in selected[:target_size]:
            ask = str(row.get("ask") or "")[:400]
            draft = str(row.get("chosen") or "")[:600]
            ids = annotate_pair_ids(ask, draft)
            pack = {
                "ask": ask,
                "draft": draft,
                "facts": row.get("facts") if isinstance(row.get("facts"), list) else [],
                "sn": float((row.get("chosen_scores") or {}).get("s_n") or 0.5),
                "frozen_label": classify_label(
                    row.get("chosen_scores") or {},
                    (row.get("chosen_scores") or {}).get("label"),
                ),
                "source_at": row.get("at"),
                **ids,
            }
            fh.write(json.dumps(pack, ensure_ascii=False) + "\n")

    n = min(len(selected), target_size)
    fr = freeze_holdout_registry_from_pack(force=True, note="ensure_holdout_pack_created")
    return {
        "ok": True,
        "path": str(HOLDOUT_PACK_PATH).replace("\\", "/"),
        "n": n,
        "created": True,
        "frozen": True,
        "pack_id": fr.get("pack_id"),
        "registry": fr,
    }


def run_holdout_check(*, max_drop: float | None = None) -> dict[str, Any]:
    """Re-score frozen hold-out; fail if mind_pass drops > max_drop from baseline."""
    policy = load_admission_policy()
    drop_lim = float(policy["holdout_max_drop"] if max_drop is None else max_drop)
    ensure_holdout_pack(target_size=int(policy.get("holdout_target_size") or 60))
    if not HOLDOUT_PACK_PATH.is_file():
        return {"ok": False, "error": "no_holdout_pack", "pass": False}

    cases: list[dict[str, Any]] = []
    for ln in HOLDOUT_PACK_PATH.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            cases.append(json.loads(ln))
        except json.JSONDecodeError:
            continue

    mind = 0
    labels: dict[str, int] = {"REWARD": 0, "PUNISH": 0, "SOFT_HOLD": 0, "OTHER": 0}
    for case in cases:
        scored = score_draft(
            str(case.get("ask") or ""),
            str(case.get("draft") or ""),
            facts=case.get("facts") if isinstance(case.get("facts"), list) else [],
            sn=float(case.get("sn") or 0.5),
        )
        lab = str(scored.get("label") or "OTHER")
        labels[lab] = labels.get(lab, 0) + 1
        if int(scored.get("vidi") or 0) == 1 and int(scored.get("intellexi") or 0) == 1:
            mind += 1

    n = max(1, len(cases))
    mind_pass_rate = round(mind / n, 4)
    state = load_gate_state()
    baseline = state.get("holdout_baseline_mind_pass")
    if baseline is None:
        state["holdout_baseline_mind_pass"] = mind_pass_rate
        state["holdout_baseline_at"] = _utc()
        save_gate_state(state)
        baseline = mind_pass_rate
        dropped = 0.0
        drift_ok = True
        note = "baseline_set"
    else:
        baseline_f = float(baseline)
        dropped = round(baseline_f - mind_pass_rate, 4)
        drift_ok = dropped <= drop_lim + 1e-9
        note = "ok" if drift_ok else "drift_alert"

    out = {
        "ok": True,
        "pass": bool(drift_ok),
        "n": len(cases),
        "mind_pass_rate": mind_pass_rate,
        "baseline_mind_pass": float(baseline),
        "drop": dropped,
        "max_drop": drop_lim,
        "labels": labels,
        "note": note,
        "path": str(HOLDOUT_PACK_PATH).replace("\\", "/"),
    }
    _write_json(HOLDOUT_LAST_PATH, {**out, "at": _utc()})
    return out


def _sft_harden_cfg(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy if policy is not None else load_admission_policy()
    raw = dict(policy.get("sft_harden") or {})
    return {
        "enabled": bool(raw.get("enabled", True)),
        "max_text_repeats": int(raw.get("max_text_repeats") or DEFAULT_MAX_TEXT_REPEATS),
        "soft_hold_min_frac": float(raw.get("soft_hold_min_frac") or DEFAULT_SOFT_HOLD_MIN_FRAC),
        "seed": int(raw.get("seed") or DEFAULT_HARDEN_SEED),
    }


def harden_sft_rows(
    rows: list[dict[str, Any]],
    *,
    max_text_repeats: int = DEFAULT_MAX_TEXT_REPEATS,
    soft_hold_min_frac: float = DEFAULT_SOFT_HOLD_MIN_FRAC,
    seed: int = DEFAULT_HARDEN_SEED,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Dedupe exact texts (cap repeats) and downsample REWARD to keep soft_hold share."""
    before_n = len(rows)
    by_text: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        by_text[text].append(row)

    deduped: list[dict[str, Any]] = []
    capped_groups = 0
    for _text, group in by_text.items():
        ordered = sorted(group, key=lambda r: str(r.get("at") or ""), reverse=True)
        if len(ordered) > max_text_repeats:
            capped_groups += 1
        deduped.extend(ordered[: max(1, max_text_repeats)])

    rewards = [r for r in deduped if str(r.get("label") or "").upper() == "REWARD"]
    softs = [r for r in deduped if str(r.get("label") or "").upper() == "SOFT_HOLD"]
    other = [
        r
        for r in deduped
        if str(r.get("label") or "").upper() not in {"REWARD", "SOFT_HOLD"}
    ]

    reward_before_bal = len(rewards)
    soft_n = len(softs)
    if soft_n > 0 and soft_hold_min_frac > 0.0 and soft_hold_min_frac < 1.0:
        # soft/(reward+soft) >= frac  =>  reward <= soft * (1-frac)/frac
        max_reward = int(soft_n * (1.0 - soft_hold_min_frac) / soft_hold_min_frac)
        if len(rewards) > max_reward:
            rewards = sorted(rewards, key=lambda r: str(r.get("at") or ""), reverse=True)[
                : max(0, max_reward)
            ]

    out = rewards + softs + other
    rng = random.Random(seed)
    rng.shuffle(out)

    reward_n = sum(1 for r in out if str(r.get("label") or "").upper() == "REWARD")
    soft_out = sum(1 for r in out if str(r.get("label") or "").upper() == "SOFT_HOLD")
    mind = reward_n + soft_out
    stats = {
        "before_n": before_n,
        "after_n": len(out),
        "unique_texts": len(by_text),
        "capped_duplicate_groups": capped_groups,
        "max_text_repeats": max_text_repeats,
        "soft_hold_min_frac": soft_hold_min_frac,
        "reward_before_balance": reward_before_bal,
        "reward_sft_rows": reward_n,
        "soft_hold_sft_rows": soft_out,
        "soft_hold_frac": round(soft_out / mind, 4) if mind else 0.0,
        "unique_text_ratio": round(len(by_text) / before_n, 4) if before_n else 0.0,
        "seed": seed,
    }
    return out, stats


def harden_sft_file(
    path: Path | None = None,
    *,
    backup: bool = True,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rewrite SFT jsonl in place with harden_sft_rows. Returns stats + paths."""
    path = Path(path) if path is not None else VOICE_JUDGE_SFT
    cfg = cfg or _sft_harden_cfg()
    if not path.is_file():
        return {"ok": False, "error": "sft_missing", "path": str(path)}
    raw_rows: list[dict[str, Any]] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            raw_rows.append(row)

    if not cfg.get("enabled", True):
        return {
            "ok": True,
            "skipped": True,
            "reason": "sft_harden.disabled",
            "before_n": len(raw_rows),
            "path": str(path).replace("\\", "/"),
        }

    hardened, stats = harden_sft_rows(
        raw_rows,
        max_text_repeats=int(cfg["max_text_repeats"]),
        soft_hold_min_frac=float(cfg["soft_hold_min_frac"]),
        seed=int(cfg["seed"]),
    )
    backup_path = None
    if backup:
        stamp = _utc().replace(":", "").replace("+", "p")
        backup_path = path.with_name(f"{path.stem}_pre_harden_{stamp}{path.suffix}")
        shutil.copy2(path, backup_path)
    with path.open("w", encoding="utf-8") as fh:
        for row in hardened:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "ok": True,
        "path": str(path).replace("\\", "/"),
        "backup": str(backup_path).replace("\\", "/") if backup_path else None,
        **stats,
    }


def export_judge_train(*, limit: int = 500, respect_freeze: bool = True) -> dict[str, Any]:
    """Read preference_pairs → admit/reject logs + judge SFT jsonl. Ceiling enforced here."""
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.joinpath("models").mkdir(parents=True, exist_ok=True)
    state = load_gate_state()
    if respect_freeze and state.get("frozen") and TRAIN_READY_SIGNAL.is_file():
        # Buffer frozen while train_ready awaits trainer — do not rewrite SFT mid-flight.
        return {
            "ok": True,
            "frozen": True,
            "skipped_rewrite": True,
            "reason": "buffer_frozen_awaiting_train",
            "sft_path": str(VOICE_JUDGE_SFT).replace("\\", "/"),
            "signal": str(TRAIN_READY_SIGNAL).replace("\\", "/"),
        }

    if not PREFERENCE_JSONL.is_file():
        return {"ok": False, "error": "no_preference_pairs", "path": str(PREFERENCE_JSONL)}

    admitted = 0
    rejected = 0
    sft_rows: list[dict[str, Any]] = []
    lines = PREFERENCE_JSONL.read_text(encoding="utf-8").splitlines()[-max(1, limit) :]
    with TRAIN_ADMIT_JSONL.open("w", encoding="utf-8") as fa, TRAIN_REJECT_JSONL.open(
        "w", encoding="utf-8"
    ) as fr:
        for ln in lines:
            if not ln.strip():
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            dec = admit_pair(row)
            rec = {"at": _utc(), "ask": (row.get("ask") or "")[:200], "decision": dec}
            if dec.get("admit"):
                fa.write(json.dumps({**rec, "row": row}, ensure_ascii=False) + "\n")
                admitted += 1
                for sft in preference_to_sft_rows(row, dec):
                    sft_rows.append(sft)
            else:
                fr.write(json.dumps(rec, ensure_ascii=False) + "\n")
                rejected += 1

    from lib.aifl_holdout_split import filter_sft_rows

    sft_rows, holdout_filter = filter_sft_rows(sft_rows)

    harden_cfg = _sft_harden_cfg()
    harden_stats: dict[str, Any] | None = None
    if harden_cfg.get("enabled", True):
        sft_rows, harden_stats = harden_sft_rows(
            sft_rows,
            max_text_repeats=int(harden_cfg["max_text_repeats"]),
            soft_hold_min_frac=float(harden_cfg["soft_hold_min_frac"]),
            seed=int(harden_cfg["seed"]),
        )
        # Re-filter after harden (safety)
        sft_rows, holdout_filter_2 = filter_sft_rows(sft_rows)
        holdout_filter = {
            **holdout_filter,
            "post_harden_extra_drop": holdout_filter_2.get("dropped_holdout_overlap"),
        }

    reward_sft = sum(1 for r in sft_rows if str(r.get("label") or "").upper() == "REWARD")
    soft_sft = sum(1 for r in sft_rows if str(r.get("label") or "").upper() == "SOFT_HOLD")
    with VOICE_JUDGE_SFT.open("w", encoding="utf-8") as fs:
        for sft in sft_rows:
            fs.write(json.dumps(sft, ensure_ascii=False) + "\n")

    out = {
        "ok": True,
        "frozen": False,
        "criteria_version": (load_criteria() or {}).get("version"),
        "preference_scanned": len(lines),
        "admitted": admitted,
        "rejected": rejected,
        "sft_rows": len(sft_rows),
        "reward_sft_rows": reward_sft,
        "soft_hold_sft_rows": soft_sft,
        "holdout_exclude": holdout_filter,
        "admit_path": str(TRAIN_ADMIT_JSONL).replace("\\", "/"),
        "reject_path": str(TRAIN_REJECT_JSONL).replace("\\", "/"),
        "sft_path": str(VOICE_JUDGE_SFT).replace("\\", "/"),
        "ceiling": "judge_only_no_human_rank",
    }
    if harden_stats is not None:
        out["sft_harden"] = harden_stats
    return out


def evaluate_lora_admission(*, write_signal: bool = True, force_unfreeze: bool = False) -> dict[str, Any]:
    """Executable LoRA admission policy. Writes train_ready/signal.json when all gates pass."""
    policy = load_admission_policy()
    state = load_gate_state()
    at = _utc()
    rows = _iter_preference_rows()
    reward_total = count_reward_pairs(rows)
    mind_pass_total = count_mind_pass_pairs(rows)
    admit_soft = bool(policy.get("admit_soft_hold"))
    pair_total = mind_pass_total if admit_soft else reward_total
    watermark = int(state.get("reward_watermark") or 0)
    delta = pair_total - watermark
    quality = rolling_quality(rows, window=int(policy.get("rolling_window") or 100))

    result: dict[str, Any] = {
        "ok": True,
        "at": at,
        "experiment_id": policy.get("experiment_id") or EXPERIMENT_ID,
        "flag": FLAG_NAME,
        "enabled": bool(policy.get("enabled")),
        "frozen": bool(state.get("frozen")),
        "admit_soft_hold": admit_soft,
        "reward_total": reward_total,
        "mind_pass_total": mind_pass_total,
        "pair_total": pair_total,
        "reward_watermark": watermark,
        "reward_delta": delta,
        "quality": quality,
        "ready": False,
        "blocked_by": [],
    }

    if force_unfreeze and state.get("frozen"):
        state["frozen"] = False
        save_gate_state(state)
        result["frozen"] = False
        result["force_unfreeze"] = True

    if not policy.get("enabled"):
        result["blocked_by"].append("flag_disabled")
        result["rollback"] = f"Set {ADMISSION_POLICY_PATH.name} enabled=true to re-enable"
        _append_jsonl(ADMISSION_LOG, result)
        return result

    if state.get("frozen") and TRAIN_READY_SIGNAL.is_file():
        result["blocked_by"].append("buffer_frozen_awaiting_train")
        result["signal"] = str(TRAIN_READY_SIGNAL).replace("\\", "/")
        _append_jsonl(ADMISSION_LOG, result)
        return result

    min_reward = int(policy.get("min_reward_pairs") or 50)
    trigger = int(policy.get("reward_delta_trigger") or 50)
    if pair_total < min_reward:
        result["blocked_by"].append(
            f"min_mind_pass_pairs<{min_reward}" if admit_soft else f"min_reward_pairs<{min_reward}"
        )
    if delta < trigger and pair_total >= min_reward:
        if not (watermark == 0 and pair_total >= min_reward):
            result["blocked_by"].append(f"reward_delta<{trigger}")

    mind_min = float(policy.get("mind_pass_min") or 0.95)
    punish_max = float(policy.get("punish_max") or 0.05)
    if quality["n"] < 10:
        result["blocked_by"].append("rolling_window_too_small")
    if quality["mind_pass_rate"] < mind_min:
        result["blocked_by"].append(f"mind_pass<{mind_min}")
    if quality["punish_rate"] > punish_max:
        result["blocked_by"].append(f"punish>{punish_max}")

    holdout = run_holdout_check(max_drop=float(policy.get("holdout_max_drop") or 0.02))
    result["holdout"] = holdout
    if not holdout.get("pass"):
        # After P0, the continuity pack is regression-only. The deciding
        # deployment pack is evaluated by validate_judge_adapter; keeping the
        # old pack as a training admission blocker would permanently prevent
        # clean post-quarantine data from being trained.
        try:
            from lib.aifl_holdout_split import load_deploy_test_registry

            deploy_reg = load_deploy_test_registry()
        except Exception:  # noqa: BLE001
            deploy_reg = {}
        if deploy_reg.get("frozen") and deploy_reg.get("pack_id"):
            result["holdout"]["role"] = "continuity_regression_only"
            result["holdout"]["gate_blocking"] = False
            result["holdout"]["note"] = "continuity drift recorded; deciding deploy-test pack is separate"
        else:
            result["blocked_by"].append("holdout_drift")

    if result["blocked_by"]:
        result["ready"] = False
        _append_jsonl(ADMISSION_LOG, result)
        return result

    # Prefer full buffer for soft-hold redistribution (don't drop early REWARD rows)
    export_limit = max(len(rows), int(policy.get("rolling_window") or 100) * 5, 500)
    export = export_judge_train(limit=export_limit, respect_freeze=False)
    if not export.get("ok"):
        result["blocked_by"].append("export_failed")
        result["export"] = export
        _append_jsonl(ADMISSION_LOG, result)
        return result

    reward_sft = int(export.get("reward_sft_rows") or 0)
    soft_sft = int(export.get("soft_hold_sft_rows") or 0)
    sft_count = reward_sft + soft_sft if admit_soft else reward_sft
    if sft_count < min_reward:
        result["blocked_by"].append(
            f"mind_pass_sft_rows<{min_reward}" if admit_soft else f"reward_sft_rows<{min_reward}"
        )
        result["export"] = export
        _append_jsonl(ADMISSION_LOG, result)
        return result

    signal = {
        "at": at,
        "experiment_id": policy.get("experiment_id") or EXPERIMENT_ID,
        "flag": FLAG_NAME,
        "status": "ready",
        "dataset": str(VOICE_JUDGE_SFT).replace("\\", "/"),
        "dataset_rows": export.get("sft_rows"),
        "reward_sft_rows": reward_sft,
        "soft_hold_sft_rows": soft_sft,
        "admit_soft_hold": admit_soft,
        "forbid_corpora": policy.get("forbid_corpora"),
        "lora": dict(policy.get("lora") or {}),
        "quality": quality,
        "holdout": {
            "mind_pass_rate": holdout.get("mind_pass_rate"),
            "baseline_mind_pass": holdout.get("baseline_mind_pass"),
            "drop": holdout.get("drop"),
        },
        "criteria_version": (load_criteria() or {}).get("version"),
        "foundation": str(FOUNDATION_ROOT).replace("\\", "/"),
        "sft_harden": export.get("sft_harden"),
        "note": "Trainer must consume ONLY dataset path; no Instruct/fluency mix. soft_hold admitted while plant dormant. SFT harden=dedupe+balance.",
    }

    if write_signal:
        TRAIN_READY_DIR.mkdir(parents=True, exist_ok=True)
        # Snapshot SFT beside signal for replay
        snap = TRAIN_READY_DIR / f"sft_snapshot_{at.replace(':', '').replace('+', 'p')}.jsonl"
        if VOICE_JUDGE_SFT.is_file():
            shutil.copy2(VOICE_JUDGE_SFT, snap)
            signal["dataset_snapshot"] = str(snap).replace("\\", "/")
        _write_json(TRAIN_READY_SIGNAL, signal)
        state["frozen"] = True
        state["reward_watermark"] = pair_total
        state["last_signal_at"] = at
        state["last_signal_path"] = str(TRAIN_READY_SIGNAL).replace("\\", "/")
        save_gate_state(state)

    result["ready"] = True
    result["frozen"] = True if write_signal else bool(state.get("frozen"))
    result["signal"] = signal if write_signal else None
    result["signal_path"] = str(TRAIN_READY_SIGNAL).replace("\\", "/") if write_signal else None
    result["export"] = {
        "sft_rows": export.get("sft_rows"),
        "reward_sft_rows": reward_sft,
        "soft_hold_sft_rows": soft_sft,
        "sft_path": export.get("sft_path"),
    }
    _append_jsonl(ADMISSION_LOG, {**result, "signal_status": "written" if write_signal else "dry"})
    return result


def arm_train_ready_from_sft(
    *,
    harden: bool = True,
    note: str = "hardened_sft_rearm",
) -> dict[str, Any]:
    """Harden current SFT (optional), snapshot, and freeze a train_ready signal.

    Skips reward_delta gate — used for explicit harden→retrain experiments.
    Does not raise watermark (already past that data).
    """
    policy = load_admission_policy()
    at = _utc()
    harden_stats = None
    if harden:
        harden_stats = harden_sft_file(VOICE_JUDGE_SFT, backup=True, cfg=_sft_harden_cfg(policy))
        if not harden_stats.get("ok"):
            return harden_stats

    if not VOICE_JUDGE_SFT.is_file():
        return {"ok": False, "error": "sft_missing", "path": str(VOICE_JUDGE_SFT)}

    reward_sft = 0
    soft_sft = 0
    sft_n = 0
    for ln in VOICE_JUDGE_SFT.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        sft_n += 1
        lab = str(row.get("label") or "").upper()
        if lab == "REWARD":
            reward_sft += 1
        elif lab == "SOFT_HOLD":
            soft_sft += 1

    min_reward = int(policy.get("min_reward_pairs") or 50)
    if (reward_sft + soft_sft) < min_reward:
        return {
            "ok": False,
            "error": "sft_too_small_after_harden",
            "sft_rows": sft_n,
            "reward_sft_rows": reward_sft,
            "soft_hold_sft_rows": soft_sft,
            "harden": harden_stats,
        }

    lora = dict(policy.get("lora") or {})
    signal = {
        "at": at,
        "experiment_id": policy.get("experiment_id") or EXPERIMENT_ID,
        "flag": FLAG_NAME,
        "status": "ready",
        "dataset": str(VOICE_JUDGE_SFT).replace("\\", "/"),
        "dataset_rows": sft_n,
        "reward_sft_rows": reward_sft,
        "soft_hold_sft_rows": soft_sft,
        "admit_soft_hold": bool(policy.get("admit_soft_hold")),
        "forbid_corpora": policy.get("forbid_corpora"),
        "lora": lora,
        "sft_harden": harden_stats,
        "criteria_version": (load_criteria() or {}).get("version"),
        "foundation": str(FOUNDATION_ROOT).replace("\\", "/"),
        "note": note,
        "rearm": True,
    }
    TRAIN_READY_DIR.mkdir(parents=True, exist_ok=True)
    snap = TRAIN_READY_DIR / f"sft_snapshot_{at.replace(':', '').replace('+', 'p')}.jsonl"
    shutil.copy2(VOICE_JUDGE_SFT, snap)
    signal["dataset_snapshot"] = str(snap).replace("\\", "/")
    _write_json(TRAIN_READY_SIGNAL, signal)

    state = load_gate_state()
    state["frozen"] = True
    state["last_signal_at"] = at
    state["last_signal_path"] = str(TRAIN_READY_SIGNAL).replace("\\", "/")
    # Keep watermark; this is a retrain on cleaned view of same buffer.
    # Do NOT overwrite holdout_baseline_mind_pass with LoRA deploy pin —
    # that baseline is CPU-judge drift on the frozen pack, not adapter mind_pass.
    save_gate_state(state)

    out = {
        "ok": True,
        "at": at,
        "signal_path": str(TRAIN_READY_SIGNAL).replace("\\", "/"),
        "dataset_snapshot": signal["dataset_snapshot"],
        "dataset_rows": sft_n,
        "reward_sft_rows": reward_sft,
        "soft_hold_sft_rows": soft_sft,
        "soft_hold_frac": round(soft_sft / max(1, reward_sft + soft_sft), 4),
        "harden": harden_stats,
        "frozen": True,
    }
    _append_jsonl(ADMISSION_LOG, {"event": "arm_train_ready_from_sft", **out})
    return out


def consume_train_ready(*, ok: bool, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Trainer calls after LoRA pass — clears freeze and archives signal."""
    state = load_gate_state()
    at = _utc()
    archived = None
    if TRAIN_READY_SIGNAL.is_file():
        archive_dir = TRAIN_READY_DIR / "consumed"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived = archive_dir / f"signal_{at.replace(':', '').replace('+', 'p')}.json"
        shutil.move(str(TRAIN_READY_SIGNAL), str(archived))
    state["frozen"] = False
    state["last_train_consumed_at"] = at
    state["last_train_ok"] = bool(ok)
    if meta:
        state["last_train_meta"] = meta
    save_gate_state(state)
    out = {
        "ok": True,
        "consumed_at": at,
        "train_ok": bool(ok),
        "archived_signal": str(archived).replace("\\", "/") if archived else None,
        "frozen": False,
    }
    _append_jsonl(ADMISSION_LOG, {"event": "consume_train_ready", **out})
    return out


def status() -> dict[str, Any]:
    policy = load_admission_policy()
    state = load_gate_state()
    rows = _iter_preference_rows()
    return {
        "experiment_id": policy.get("experiment_id"),
        "flag": FLAG_NAME,
        "enabled": policy.get("enabled"),
        "frozen": state.get("frozen"),
        "reward_total": count_reward_pairs(rows),
        "reward_watermark": state.get("reward_watermark"),
        "quality": rolling_quality(rows, window=int(policy.get("rolling_window") or 100)),
        "holdout_baseline": state.get("holdout_baseline_mind_pass"),
        "signal_pending": TRAIN_READY_SIGNAL.is_file(),
        "signal_path": str(TRAIN_READY_SIGNAL).replace("\\", "/"),
        "policy_path": str(ADMISSION_POLICY_PATH).replace("\\", "/"),
        "sft_path": str(VOICE_JUDGE_SFT).replace("\\", "/"),
        "rollback": f"Set enabled=false in {ADMISSION_POLICY_PATH}",
    }
