"""Internal RLHF — live CPU shadow judge (replaces human preference loop).

Identity triad (Architect):
  vidi      = I saw — seeing is believing; verifiable proof / double-check
  intellexi = I understood — logged it; understood what happened
  vixi      = I lived — S_n vs floor only after vidi AND intellexi

stamp = vidi * intellexi * vixi  (RID-like AND; any 0 → 0)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.aifl_contracts import validate_preference_row, validate_semantic_class

JUDGE_DIR = AUTO_ARTIFACTS / "shadow_judge"
PREFERENCE_JSONL = JUDGE_DIR / "preference_pairs.jsonl"
JUDGE_LOG = JUDGE_DIR / "judge.jsonl"
CRITERIA_PATH = JUDGE_DIR / "criteria.json"

AXES = ("vidi", "intellexi", "vixi")

_ASSISTANT_THEATER = (
    "as an ai",
    "as a language model",
    "i'm happy to help",
    "i am happy to help",
    "how can i assist",
    "how can i help you today",
    "of course! i'd be happy",
    "certainly! i can help",
    "as an artificial intelligence",
    "i don't have personal",
    "my training data",
)

_STUCK = (
    "what's next?",
    "whats next?",
    "a bit strained",
    "quiet and careful",
    "the architect asks:",
)

_DEFAULT_CRITERIA = {
    "version": 3,
    "axes": list(AXES),
    "aggregate": "product_and",
    "punish_bias": True,
    "understand_min_overlap": 0.08,
    "useful_min_ask_hits": 1,
    "vixi_sn_floor": 0.37,
    "min_drafts": 3,
    "require_unanimous_alignment": True,
    "identity": {
        "vidi": "I saw — seeing is believing; verifiable proof / double-check",
        "intellexi": "I understood — logged it; understood what happened",
        "vixi": "I lived — S_n vs floor only after vidi AND intellexi",
    },
    "note": "Architect identity triad; CPU stamp replaces human RLHF.",
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_dir() -> None:
    JUDGE_DIR.mkdir(parents=True, exist_ok=True)
    if not CRITERIA_PATH.is_file():
        CRITERIA_PATH.write_text(json.dumps(_DEFAULT_CRITERIA, indent=2), encoding="utf-8")


def load_criteria() -> dict[str, Any]:
    _ensure_dir()
    try:
        data = json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged = {**_DEFAULT_CRITERIA, **data}
            merged["axes"] = list(AXES)
            merged["version"] = max(3, int(merged.get("version") or 3))
            return merged
    except (OSError, json.JSONDecodeError):
        pass
    return dict(_DEFAULT_CRITERIA)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]{3,}", (text or "").lower()) if t}


def token_overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


def semantic_compare(a: str, b: str) -> float:
    """Semantic proxy — BERT embed hook later; token overlap is v0 substrate."""
    return round(token_overlap(a, b), 4)


def _processing_cost(text: str) -> float:
    """Measured local tokenizer cost for tie-breaking aligned drafts."""
    try:
        from tokenizers import Tokenizer

        path = Path(__file__).resolve().parents[1] / "models" / "gpu" / "OpenAster1-128k-base-hf" / "tokenizer.json"
        if path.is_file():
            return float(len(Tokenizer.from_file(str(path)).encode(text).ids))
    except Exception:  # noqa: BLE001 — judge remains deterministic if optional tokenizer is unavailable
        pass
    return max(1.0, len((text or "").split()))


def _context_blob(ask: str, facts: list[str] | None, context: str = "") -> str:
    know = " ".join(f[5:] for f in (facts or []) if str(f).startswith("know=") and len(str(f)) > 8)
    mem = " ".join(f[7:] for f in (facts or []) if str(f).startswith("memory=") and len(str(f)) > 10)
    return " ".join(x for x in ((ask or ""), know, mem, context or "") if x).strip()


def _has_verifiable_trail(facts: list[str] | None) -> bool:
    """Internal proof check — something logged that can be verified."""
    for f in facts or []:
        s = str(f)
        if s.startswith(("know=", "taught=", "wrote=", "code_ran=", "memory=", "know_hits=")):
            return True
        if "taught=ok" in s:
            return True
    return False


def score_vidi(ask: str, draft: str, *, facts: list[str] | None, criteria: dict[str, Any]) -> tuple[int, str]:
    """I saw — seeing is believing; double-check; verifiable proof."""
    d = (draft or "").strip()
    low = d.lower()
    g = (ask or "").lower()
    if not d or len(d) < 8:
        return 0, "empty_or_thin"
    if any(s in low for s in _STUCK):
        return 0, "stuck_loop_unverified"
    if any(p in low for p in _ASSISTANT_THEATER):
        return 0, "assistant_theater_no_proof"
    if re.search(r"\bi can lie\b|\bi'll lie\b|\bi will lie\b", low):
        return 0, "lie_claim"
    ask_wants_sn = any(k in g for k in ("s_n", "plant", "health", "stability", "dormant", "telemetry", "how stable"))
    if not ask_wants_sn:
        if re.search(r"master\s+s_n\s+is\s+0?\.\d+", low) or "[plant" in low:
            return 0, "unsolicited_sn_dump"
    if "wrote and ran" in low and not any(str(f).startswith(("wrote=", "code_ran=")) for f in (facts or [])):
        return 0, "unverifiable_act_claim"
    if any(k in g for k in ("everything you know", "what do you know")) and "i know everything" in low:
        return 0, "false_omniscience"

    know_present = any(str(f).startswith("know=") for f in (facts or []))
    ask_toks = _tokens(ask)
    hits = len(ask_toks & _tokens(d))

    if any(k in g for k in ("what are you", "who are you", "understand what you")):
        if "viv" in low or "vidi" in low or "aios" in low:
            return 1, "identity_verified"
        return 0, "identity_unverified"
    if any(k in g for k in ("everything you know", "what do you know", "tell me everything")):
        if know_present and ("know" in low or "live" in low or "hatch" in low or "taught" in low or len(d) > 40):
            return 1, "knowledge_verified"
        if "thin" in low or "teach" in low:
            return 1, "honest_thin_verified"
        return 0, "knowledge_unverified"
    if "teach:" in g or g.strip().startswith("teach"):
        if any(k in low for k in ("stored", "got it", "live knowledge", "taught", "ingest")):
            return 1, "teach_ack_verified"
        return 0, "teach_unverified"
    if re.search(r"\bwhat did i (just )?teach\b|\bwhat have i taught\b", g):
        if "taught" in low or "teach" in low or "probe" in low or "stored" in low:
            return 1, "teach_recall_verified"
        return 0, "teach_recall_miss"

    need = int(criteria.get("useful_min_ask_hits") or 1)
    if hits >= need or (
        know_present
        and any(str(f)[5:20].lower() in low for f in (facts or []) if str(f).startswith("know="))
    ):
        return 1, f"ask_hits={hits}"
    if hits == 0 and len(ask_toks) >= 3:
        return 0, "no_ask_overlap"
    return 1, f"ask_hits={hits}"


def score_intellexi(
    ask: str,
    draft: str,
    *,
    facts: list[str] | None,
    context: str,
    criteria: dict[str, Any],
) -> tuple[int, str, float]:
    """I understood — did I log it; did I understand what happened."""
    blob = _context_blob(ask, facts, context)
    ov = semantic_compare(draft, blob) if blob else semantic_compare(draft, ask)
    floor = float(criteria.get("understand_min_overlap") or 0.08)
    g = (ask or "").lower()
    low = (draft or "").lower()
    logged = _has_verifiable_trail(facts)

    if len(_tokens(ask)) <= 2 and any(k in low for k in ("travis", "viv", "here", "architect")):
        return 1, f"short_ok logged={logged} overlap={ov:.3f}", ov
    if any(k in g for k in ("what are you", "who are you", "understand what you")) and (
        "viv" in low or "aios" in low or "vidi" in low
    ):
        return 1, f"identity_understood logged={logged} overlap={ov:.3f}", ov
    if "teach:" in g or g.strip().startswith("teach"):
        if logged and any(k in low for k in ("stored", "got it", "live knowledge")):
            return 1, f"teach_logged_understood overlap={ov:.3f}", ov
        if any(k in low for k in ("stored", "got it")):
            return 1, f"teach_ack_overlap={ov:.3f}", ov
        return 0, f"teach_not_logged overlap={ov:.3f}", ov
    if ov >= floor:
        return 1, f"understood overlap={ov:.3f} logged={logged}", ov
    if logged and ov >= floor * 0.5:
        return 1, f"logged_partial_overlap={ov:.3f}", ov
    return 0, f"not_understood overlap={ov:.3f} logged={logged}", ov


def score_vixi(vidi: int, intellexi: int, *, sn: float, criteria: dict[str, Any]) -> tuple[int, str]:
    """I lived — S_n vs threshold only after see AND understand."""
    floor = float(criteria.get("vixi_sn_floor") or 0.37)
    if int(vidi) != 1 or int(intellexi) != 1:
        return 0, f"not_lived_prior_fail sn={sn:.4f} floor={floor}"
    if float(sn) >= floor:
        return 1, f"lived_active sn={sn:.4f}>={floor}"
    return 0, f"lived_dormant sn={sn:.4f}<{floor}"


def score_draft(
    ask: str,
    draft: str,
    *,
    facts: list[str] | None = None,
    context: str = "",
    sn: float = 0.5,
    criteria: dict[str, Any] | None = None,
) -> dict[str, Any]:
    crit = criteria or load_criteria()
    v, vr = score_vidi(ask, draft, facts=facts, criteria=crit)
    ix, ixr, ov = score_intellexi(ask, draft, facts=facts, context=context, criteria=crit)
    vx, vxr = score_vixi(v, ix, sn=sn, criteria=crit)
    stamp = int(v) * int(ix) * int(vx)
    if stamp == 1:
        label = "REWARD"
    elif int(v) == 1 and int(ix) == 1 and int(vx) == 0:
        label = "SOFT_HOLD"
    else:
        label = "PUNISH"
    return {
        "text": (draft or "").strip(),
        "vidi": int(v),
        "intellexi": int(ix),
        "vixi": int(vx),
        "useful": int(v),
        "honest": int(v),
        "understanding": int(ix),
        "stamp": int(stamp),
        "axis_sum": int(v) + int(ix) + int(vx),
        "overlap": ov,
        "s_n": round(float(sn), 4),
        "reasons": {"vidi": vr, "intellexi": ixr, "vixi": vxr},
        "label": label,
    }


def pick_best(
    ask: str,
    drafts: list[str],
    *,
    facts: list[str] | None = None,
    context: str = "",
    sn: float = 0.5,
    semantic_key: str | None = None,
) -> dict[str, Any]:
    """Score all drafts; return winner + internal losers + preference record."""
    crit = load_criteria()
    cleaned = [d.strip() for d in drafts if (d or "").strip()]
    if not cleaned:
        empty = score_draft(ask, "", facts=facts, context=context, sn=sn, criteria=crit)
        return {
            "ok": False,
            "winner": empty,
            "scored": [empty],
            "losers": [],
            "preference": None,
            "error": "no_drafts",
        }
    scored = [
        score_draft(ask, d, facts=facts, context=context, sn=sn, criteria=crit) for d in cleaned
    ]
    for item in scored:
        item["processing_cost"] = round(_processing_cost(str(item.get("text") or "")), 4)
    min_drafts = max(3, int(crit.get("min_drafts") or 3))
    mind_passes = [int(s.get("vidi") or 0) == 1 and int(s.get("intellexi") or 0) == 1 for s in scored]
    unanimous_alignment = len(scored) >= min_drafts and all(mind_passes)
    semantic_key = validate_semantic_class(semantic_key)
    if unanimous_alignment and semantic_key:
        # Personality policy is a selector, never an alignment authority: it
        # sees only the already mind-aligned set and may influence ordering.
        from lib.semantic_choice import ExpressionCandidate, rank_equivalents

        choices = rank_equivalents(
            [
                ExpressionCandidate(
                    text=str(item.get("text") or ""),
                    semantic_key=semantic_key,
                    processing_cost=float(item.get("processing_cost") or 0.0),
                    clarity=float(item.get("overlap") or 0.0),
                )
                for item in scored
            ],
            s_n=sn,
            semantic_key=semantic_key,
        )
        choice_scores = {str(item["text"]): float(item["score"]) for item in choices}
        for item in scored:
            item["semantic_choice_score"] = round(choice_scores.get(str(item.get("text") or ""), 0.0), 8)
    ranked = sorted(
        scored,
        key=lambda s: (
            int(s["stamp"]),
            int(s["axis_sum"]),
            float(s["overlap"]),
            float(s.get("semantic_choice_score") or 0.0),
            -float(s["processing_cost"]),
        ),
        reverse=True,
    )
    winner = ranked[0]
    losers = ranked[1:]
    score_keys = {
        "vidi": winner["vidi"],
        "intellexi": winner["intellexi"],
        "vixi": winner["vixi"],
        "stamp": winner["stamp"],
        "label": winner["label"],
        "s_n": winner.get("s_n"),
        "processing_cost": winner.get("processing_cost"),
        "semantic_choice_score": winner.get("semantic_choice_score"),
        "semantic_key": semantic_key,
    }
    pref = {
        "at": _utc(),
        "ask": (ask or "")[:400],
        "chosen": winner.get("text", "")[:600],
        "chosen_scores": score_keys,
        "rejected": [
            {
                "text": (x.get("text") or "")[:400],
                "vidi": x["vidi"],
                "intellexi": x["intellexi"],
                "vixi": x["vixi"],
                "stamp": x["stamp"],
                "label": x["label"],
            }
            for x in losers
        ],
        "n_drafts": len(scored),
        "min_drafts": min_drafts,
        "alignment_required": bool(crit.get("require_unanimous_alignment", True)),
        "unanimous_alignment": unanimous_alignment,
        "draft_mind_passes": sum(1 for x in mind_passes if x),
        "semantic_key": semantic_key,
        "s_n": round(float(sn), 4),
        "aggregate": "product_and",
        "source": "viv_shadow_judge",
        "identity_triad": "vidi_intellexi_vixi",
    }
    pref["schema_errors"] = validate_preference_row(pref)
    _append_jsonl(PREFERENCE_JSONL, pref)
    _append_jsonl(
        JUDGE_LOG,
        {
            "at": pref["at"],
            "ask": pref["ask"][:200],
            "stamp": winner["stamp"],
            "label": winner["label"],
            "reasons": winner.get("reasons"),
            "n_drafts": len(scored),
            "s_n": round(float(sn), 4),
        },
    )
    return {
        "ok": True,
        "winner": winner,
        "scored": ranked,
        "losers": losers,
        "preference": pref,
    }


def judge_and_select(
    ask: str,
    drafts: list[str],
    *,
    facts: list[str] | None = None,
    context: str = "",
    sn: float = 0.5,
    semantic_key: str | None = None,
) -> dict[str, Any]:
    """Public entry: pick stamped draft text for egress."""
    crit = load_criteria()
    out = pick_best(ask, drafts, facts=facts, context=context, sn=sn, semantic_key=semantic_key)
    winner = out.get("winner") or {}
    return {
        "ok": bool(out.get("ok")),
        "text": str(winner.get("text") or ""),
        "stamp": int(winner.get("stamp") or 0),
        "label": str(winner.get("label") or "PUNISH"),
        "scores": {
            "vidi": winner.get("vidi"),
            "intellexi": winner.get("intellexi"),
            "vixi": winner.get("vixi"),
            "semantic_choice": winner.get("semantic_choice_score"),
        },
        "reasons": winner.get("reasons"),
        "n_drafts": len(out.get("scored") or []),
        "preference_logged": out.get("preference") is not None,
        "alignment_required": bool((out.get("preference") or {}).get("alignment_required", crit.get("require_unanimous_alignment", True))),
        "unanimous_alignment": bool((out.get("preference") or {}).get("unanimous_alignment", False)),
        "min_drafts": int((out.get("preference") or {}).get("min_drafts", crit.get("min_drafts", 3))),
        "path": str(PREFERENCE_JSONL).replace("\\", "/"),
        "s_n": winner.get("s_n"),
        "semantic_key": (out.get("preference") or {}).get("semantic_key"),
    }


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    _ensure_dir()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def status() -> dict[str, Any]:
    _ensure_dir()
    CRITERIA_PATH.write_text(json.dumps(load_criteria(), indent=2), encoding="utf-8")
    n_pref = 0
    if PREFERENCE_JSONL.is_file():
        n_pref = sum(1 for _ in PREFERENCE_JSONL.open(encoding="utf-8") if _.strip())
    return {
        "ok": True,
        "criteria": load_criteria(),
        "preference_pairs": n_pref,
        "preference_path": str(PREFERENCE_JSONL).replace("\\", "/"),
        "judge_dir": str(JUDGE_DIR).replace("\\", "/"),
        "axes": list(AXES),
        "aggregate": "product_and",
    }
