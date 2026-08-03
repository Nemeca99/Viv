"""Small, dependency-free validators for AIFL judge and run records."""
from __future__ import annotations

from typing import Any

REQUIRED_PREFERENCE_KEYS = {
    "at", "ask", "chosen", "chosen_scores", "rejected", "n_drafts",
    "min_drafts", "alignment_required", "unanimous_alignment",
    "draft_mind_passes", "source",
}


def validate_preference_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_PREFERENCE_KEYS.difference(row))
    if missing:
        errors.append("missing:" + ",".join(missing))
    scores = row.get("chosen_scores")
    if not isinstance(scores, dict):
        errors.append("chosen_scores_not_object")
    elif not {"vidi", "intellexi", "vixi"}.issubset(scores):
        errors.append("chosen_scores_missing_triad")
    drafts = row.get("n_drafts")
    minimum = row.get("min_drafts")
    if not isinstance(drafts, int) or drafts < 0:
        errors.append("n_drafts_invalid")
    if not isinstance(minimum, int) or minimum < 3:
        errors.append("min_drafts_invalid")
    if bool(row.get("alignment_required")) and bool(row.get("unanimous_alignment")):
        if not isinstance(drafts, int) or drafts < int(minimum or 3):
            errors.append("unanimous_alignment_below_minimum")
        if row.get("draft_mind_passes") != drafts:
            errors.append("unanimous_alignment_pass_count_mismatch")
    return errors


def validate_semantic_class(semantic_key: str | None) -> str | None:
    key = str(semantic_key or "").strip()
    if not key or key == "judge_set":
        return None
    if len(key) > 96 or any(ord(ch) < 32 for ch in key):
        return None
    return key
