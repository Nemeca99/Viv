"""CPU judge — soft-reject GPU draft before plant measure; one retry with teach packet.

Does not replace plant scoring. Max one redo. Local script judge (not a second LLM).
"""
from __future__ import annotations

import json
import random
from typing import Any

_TRIAD = (
    ("rsr", "predicted_master_rsr", "master_rsr"),
    ("ltp", "predicted_master_ltp", "master_ltp"),
    ("rle", "predicted_master_rle", "master_rle"),
)


def judge_draft(
    prediction: dict[str, Any] | None,
    *,
    before: dict[str, Any],
    prior: dict[str, Any],
    scaffold: dict[str, Any] | None = None,
    cpu_sample: dict[str, Any] | None = None,
    far_tol: float = 0.12,
) -> dict[str, Any]:
    """Return {retry: bool, reasons: [...], hints: {channel: value}}."""
    pred = prediction or {}
    reasons: list[str] = []
    hints: dict[str, float] = {}
    blanked = list((scaffold or {}).get("blanked") or [])

    missing = []
    for short, pk, ak in _TRIAD:
        if pred.get(pk) is None:
            missing.append(short)
            # Prefer prior / live before as teach target
            src = prior.get(pk)
            if src is None:
                src = before.get(ak)
            if src is not None:
                hints[pk] = round(float(src), 4)
    if missing:
        reasons.append("incomplete_triad:" + ",".join(missing))

    for short, pk, ak in _TRIAD:
        pv = pred.get(pk)
        if pv is None:
            continue
        ref = prior.get(pk)
        if ref is None:
            ref = before.get(ak)
        if ref is None:
            continue
        err = abs(float(pv) - float(ref))
        if err > far_tol:
            reasons.append(f"far_from_prior_{short}:{err:.3f}")
            hints[pk] = round(float(ref), 4)

    for b in blanked:
        if pred.get(b) is None:
            reasons.append(f"blank_empty:{b}")
            if b in prior and prior[b] is not None:
                hints[b] = round(float(prior[b]), 4)
            else:
                # map predicted_master_X → master_X
                if b.startswith("predicted_"):
                    ak = b.replace("predicted_", "", 1)
                    if before.get(ak) is not None:
                        hints[b] = round(float(before[ak]), 4)

    # Optional: if cpu_sample triad present and draft contradicts it wildly
    sample_triad = (cpu_sample or {}).get("triad") or (cpu_sample or {}).get("guide") or {}
    for short, pk, _ak in _TRIAD:
        if pred.get(pk) is None:
            continue
        sv = sample_triad.get(short) or sample_triad.get(pk)
        if sv is None:
            continue
        if abs(float(pred[pk]) - float(sv)) > max(far_tol, 0.15):
            reasons.append(f"far_from_cpu_sample_{short}")
            hints.setdefault(pk, round(float(sv), 4))

    retry = bool(reasons)
    return {
        "retry": retry,
        "reasons": reasons,
        "hints": hints,
        "far_tol": far_tol,
    }


def madlibs_options(
    correct: float,
    *,
    rng: random.Random | None = None,
) -> list[float]:
    """Four options, one correct — shuffled."""
    r = rng or random.Random()
    distractors = [
        round(max(0.0, min(1.0, correct + 0.15)), 4),
        round(max(0.0, min(1.0, correct - 0.12)), 4),
        round(max(0.0, min(1.0, 1.0 - correct)), 4),
    ]
    # ensure uniqueness
    opts = [round(correct, 4)]
    for d in distractors:
        if d not in opts:
            opts.append(d)
    while len(opts) < 4:
        opts.append(round(r.random(), 4))
    r.shuffle(opts)
    return opts[:4]


def format_retry_block(verdict: dict[str, Any], *, use_madlibs: bool = True) -> str:
    """CPU teach packet appended to predict prompt for one redo."""
    reasons = verdict.get("reasons") or []
    hints = dict(verdict.get("hints") or {})
    lines = [
        "[TAG:retry] CPU judge rejected draft — one redo only.",
        f"Reasons: {', '.join(reasons) if reasons else 'none'}.",
        "Emit complete triad JSON. Prefer host prior / plant norms.",
    ]
    if hints and use_madlibs:
        # Mad Libs on first hinted channel
        pk = next(iter(hints))
        correct = float(hints[pk])
        opts = madlibs_options(correct)
        lines.append(f"Mad Libs for {pk} — pick the best value, emit it in JSON:")
        for i, lab in enumerate("ABCD"):
            lines.append(f"  {lab}) {opts[i]}")
        lines.append(f"Other hinted channels: {json.dumps(hints, separators=(',', ':'))}")
    elif hints:
        lines.append(f"Host teach values: {json.dumps(hints, separators=(',', ':'))}")
    lines.append("JSON redo:")
    return "\n".join(lines) + "\n"
