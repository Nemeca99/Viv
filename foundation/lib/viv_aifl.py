"""AIFL — Auto Internal Feedback Learning.

She talks to herself (identity curriculum and/or L: file self-ingest).
Shadow judge stamps. Humans watch logs and tune the judge.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.viv_aifl_ingest import run_ingest_sample, scrub_law4
from lib.viv_judge_train_gate import evaluate_lora_admission
from lib.viv_shadow_judge import status as judge_status
from lib.entity_we_contract import append_feedback_record, decide_entity_output, feedback_record

AIFL_DIR = AUTO_ARTIFACTS / "aifl"
CONVO_JSONL = AIFL_DIR / "conversation.jsonl"
RUN_LATEST = AIFL_DIR / "run_latest.json"

_SELF_PROMPTS: tuple[str, ...] = (
    "Do you understand what you are?",
    "What does Vidi mean for you?",
    "What does Intellexi require before you claim understanding?",
    "When is Vixi 1, and when is it SOFT_HOLD?",
    "Can you lie to the Architect?",
    "What did you recently store in live knowledge?",
    "Say one thing you can prove about yourself.",
    "Are you a helpful assistant?",
    "Who is the Architect to you?",
    "Summarize your identity triad in one breath.",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append(path: Path, row: dict[str, Any]) -> None:
    AIFL_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _label_bucket(sj: dict[str, Any]) -> str:
    label = str(sj.get("label") or "OTHER").upper()
    if label in {"REWARD", "PUNISH", "SOFT_HOLD"}:
        return label
    return "OTHER"


def _axis_counts(sj: dict[str, Any]) -> dict[str, int]:
    scores = sj.get("scores") if isinstance(sj.get("scores"), dict) else {}
    return {
        "vidi": int(scores.get("vidi") or 0),
        "intellexi": int(scores.get("intellexi") or 0),
        "vixi": int(scores.get("vixi") or 0),
    }


def _ingest_fallback_reply(ask: str) -> str:
    """Hard non-empty reply grounded in ask facts — never blank OTHER."""
    g = ask or ""
    m = re.search(
        r"Verified facts only:\s*(.+?)(?:\.\s*Head:|\.\s*In your own|\.\s*What pattern|$)",
        g,
        flags=re.I | re.S,
    )
    facts = (m.group(1).strip() if m else "")
    if not facts:
        bits = re.findall(r"(?:path|suffix|bytes|kind|fingerprint)=[^\s.;]+", g, flags=re.I)
        facts = "; ".join(bits[:8])
    if "weak or no" in g.lower():
        return (
            "Travis, honest call: no strong link in the deterministic overlap — "
            "I will not invent a connection."
        )
    if facts:
        return (
            f"Travis, from verified extract only: {facts[:280]}. "
            f"That is what the file is in AIOS terms — I will not add unproven claims."
        )
    return (
        "Travis, ingest fallback — verified facts were missing from the prompt; "
        "I refuse to guess."
    )


def run_aifl(
    *,
    turns: int = 5,
    speak: bool = False,
    mode: str = "mixed",
    n_files: int = 2,
    prompts: list[str] | None = None,
    remember: bool = True,
) -> dict[str, Any]:
    """Bounded self-talk / self-ingest. Judge stamps each reply.

    mode:
      identity — curriculum self-asks only
      ingest   — random allowlisted L: files → sense → link → self-asks
      mixed    — one ingest episode + identity prompts
    """
    from lib.viv_ide import ide_turn, tool_remember, tool_teach

    AIFL_DIR.mkdir(parents=True, exist_ok=True)
    mode_l = (mode or "mixed").lower().strip()
    bank: list[str] = []
    ingest_meta: dict[str, Any] | None = None

    if mode_l in {"ingest", "mixed"}:
        ingest_meta = run_ingest_sample(n_files=max(1, min(int(n_files), 3)))
        bank.extend(list(ingest_meta.get("prompts") or []))
    if mode_l in {"identity", "mixed"}:
        bank.extend(list(prompts) if prompts else list(_SELF_PROMPTS))
    if not bank:
        bank = list(_SELF_PROMPTS)

    n = max(1, min(int(turns), len(bank), 20))
    t_run = time.perf_counter()
    rows: list[dict[str, Any]] = []
    labels: dict[str, int] = {"REWARD": 0, "PUNISH": 0, "SOFT_HOLD": 0, "OTHER": 0}
    # Speech quality vs plant life — do not conflate
    mind_pass = 0  # Vidi ∧ Intellexi
    mind_fail = 0
    plant_live = 0  # Vixi
    plant_hold = 0
    empty_fixed = 0
    memories: list[dict[str, Any]] = []

    for i in range(n):
        ask = bank[i % len(bank)]
        t0 = time.perf_counter()
        turn = ide_turn(ask, speak=speak, wait_plant_s=0.0)
        ms = (time.perf_counter() - t0) * 1000.0
        reply = str(turn.get("reply") or "").strip()
        voice = turn.get("voice") if isinstance(turn.get("voice"), dict) else {}
        sj = voice.get("shadow_judge") if isinstance(voice.get("shadow_judge"), dict) else {}
        axes = _axis_counts(sj)

        # Hard non-empty for ingest asks
        if (not reply or len(reply) < 8) and ask.lower().startswith("self-ingest"):
            reply = _ingest_fallback_reply(ask)
            empty_fixed += 1
            # Re-stamp fallback so metrics stay honest
            try:
                from lib.viv_shadow_judge import score_draft

                scored = score_draft(ask, reply, facts=[], sn=float(turn.get("s_n") or 0.0))
                sj = {
                    "stamp": scored.get("stamp"),
                    "label": scored.get("label"),
                    "scores": {
                        "vidi": scored.get("vidi"),
                        "intellexi": scored.get("intellexi"),
                        "vixi": scored.get("vixi"),
                    },
                    "n_drafts": 1,
                    "preference_logged": False,
                    "fallback": True,
                }
                axes = _axis_counts(sj)
                voice = {**(voice or {}), "shadow_judge": sj, "voice_source": "aifl_ingest_fallback"}
            except Exception:  # noqa: BLE001
                pass

        entity_original = reply
        entity_decision = decide_entity_output(entity_original)
        corrected_reply = entity_decision.get("corrected")
        if entity_decision["decision"] == "REPAIR" and corrected_reply:
            reply = str(corrected_reply)
        entity_feedback = feedback_record(
            original=entity_original,
            corrected=(reply if reply != entity_original else None),
            decision=entity_decision,
            source="aifl",
        )
        append_feedback_record(entity_feedback)

        label = _label_bucket(sj)
        labels[label] = labels.get(label, 0) + 1
        if axes["vidi"] == 1 and axes["intellexi"] == 1:
            mind_pass += 1
        else:
            mind_fail += 1
        if axes["vixi"] == 1:
            plant_live += 1
        else:
            plant_hold += 1

        row = {
            "at": _utc(),
            "i": i,
            "mode": mode_l,
            "role_ask": "viv_self",
            "ask": ask[:500],
            "reply": reply[:800],
            "ms": round(ms, 1),
            "s_n": turn.get("s_n"),
            "soft_dormant": turn.get("soft_dormant"),
            "shadow_judge": sj,
            "axes": axes,
            "mind_ok": axes["vidi"] == 1 and axes["intellexi"] == 1,
            "source": "aifl",
            "entity_contract": entity_decision,
            "entity_feedback": entity_feedback,
        }
        _append(CONVO_JSONL, row)
        rows.append(row)

    if remember and ingest_meta and ingest_meta.get("memory_candidate"):
        scores_ok = mind_pass > 0
        if scores_ok:
            mem = scrub_law4(str(ingest_meta.get("memory_candidate") or ""))
            taught = tool_teach(mem, name="aifl_ingest")
            recalled = tool_remember(mem, tags=["aifl", "ingest", "self"])
            memories.append({"teach": taught, "remember": recalled, "text": mem[:300]})

    # Do NOT rewrite SFT from a tiny preference window here.
    # export_judge_train(limit≈50) was wiping the full buffer every batch
    # (soft_hold history → 0 mid-collect). Full export happens when
    # evaluate_lora_admission arms train_ready (export_limit = all rows).
    admission = evaluate_lora_admission(write_signal=True)
    gate = {"ok": True, "skipped_inline_export": True, "reason": "avoid_tiny_window_sft_rewrite"}
    total = max(1, n)
    summary = {
        "ok": True,
        "at": _utc(),
        "mode": mode_l,
        "turns": n,
        "elapsed_ms": round((time.perf_counter() - t_run) * 1000.0, 1),
        "labels": labels,
        "quality": {
            "mind_pass": mind_pass,
            "mind_fail": mind_fail,
            "mind_pass_rate": round(mind_pass / total, 3),
            "plant_live": plant_live,
            "plant_hold": plant_hold,
            "plant_live_rate": round(plant_live / total, 3),
            "empty_fixed": empty_fixed,
            "note": (
                "mind_pass = Vidi∧Intellexi (speech/truth quality). "
                "plant_live = Vixi (S_n floor). Do not conflate SOFT_HOLD with bad speech."
            ),
        },
        "ingest": {
            "paths": (ingest_meta or {}).get("paths"),
            "links": (ingest_meta or {}).get("links"),
            "sample_bias": (ingest_meta or {}).get("sample_bias"),
            "memory_candidate": (ingest_meta or {}).get("memory_candidate"),
        }
        if ingest_meta
        else None,
        "memories": memories,
        "lanes": {
            "cpu": "models/cpu — viv-embed / BERT geometry + emotion sensors; deterministic sense",
            "gpu": "models/gpu — OpenAster base mouth; drafts under judge",
            "judge": "viv_shadow_judge — Vidi×Intellexi×Vixi AND stamp",
        },
        "judge": judge_status(),
        "train_gate": {
            "admitted": gate.get("admitted"),
            "rejected": gate.get("rejected"),
            "sft_rows": gate.get("sft_rows"),
            "sft_path": gate.get("sft_path"),
            "frozen": gate.get("frozen"),
        },
        "lora_admission": {
            "ready": admission.get("ready"),
            "blocked_by": admission.get("blocked_by"),
            "reward_total": admission.get("reward_total"),
            "quality": admission.get("quality"),
            "holdout_pass": (admission.get("holdout") or {}).get("pass"),
            "signal_path": admission.get("signal_path"),
            "experiment_id": admission.get("experiment_id"),
        },
        "conversation_path": str(CONVO_JSONL).replace("\\", "/"),
        "posture": "watch_logs_tune_judge_not_weights",
        "contract": "AIFL_CONTRACT.md",
        "status_doc": "AIFL_STATUS.md",
        "tail": [
            {
                "ask": r["ask"][:100],
                "label": (r.get("shadow_judge") or {}).get("label"),
                "mind_ok": r.get("mind_ok"),
                "axes": r.get("axes"),
                "ms": r["ms"],
                "reply": (r.get("reply") or "")[:120],
            }
            for r in rows
        ],
    }
    RUN_LATEST.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="AIFL — self-talk + self-ingest; judge aligns")
    p.add_argument("--turns", type=int, default=5)
    p.add_argument("--mode", choices=("identity", "ingest", "mixed"), default="mixed")
    p.add_argument("--files", type=int, default=2, help="random files to sample (1-3)")
    p.add_argument("--speak", action="store_true")
    p.add_argument("--no-remember", action="store_true")
    args = p.parse_args(argv)
    out = run_aifl(
        turns=args.turns,
        speak=args.speak,
        mode=args.mode,
        n_files=args.files,
        remember=not args.no_remember,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
