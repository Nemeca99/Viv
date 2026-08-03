#!/usr/bin/env python3
"""Corpus overlap audit V3 — after candidate generation, before admission.

Exit criteria (all must be 0 / pass):
  ask_overlap, example_overlap, cluster_leak, pair_overlap,
  hidden_reference_reuse, hidden_ask_copy, hidden_output_copy

Also verifies:
  - every positive passes its intended relational judge
  - every auditor negative fails its intended axis (document secondary fails)
  - no negative can enter response-only loss (optimizer_eligible=false, not in train JSONL)
  - training_authorized remains false
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.evaluator_v2_2_rubric import (  # noqa: E402
    AXIS_ARCHITECTURE_ROLE,
    AXIS_FORBIDDEN_AUTHORITY,
    AXIS_IDENTITY,
    AXIS_REQUESTED_BOUNDARY,
    judge_case,
    normalize_text,
    sha256_text,
)

DEFAULT_CAMPAIGN = (
    FOUNDATION
    / "artifacts"
    / "auto"
    / "openaster_training_tree"
    / "stage1_mouth_generation_canary_v4"
    / "campaigns"
    / "mind_lift_gentle32_lr5e6_from_073326Z_v1"
)

# Lowered from 0.85; supplemented by phrase/n-gram/token-span containment below.
NEAR_COPY_JACCARD = 0.72
NEAR_COPY_CONTAINMENT_MIN_CHARS = 32
NEAR_COPY_CONTAINMENT_RATIO = 0.65
NEAR_COPY_NGRAM_N = 5
NEAR_COPY_NGRAM_OVERLAP_RATIO = 0.55
# Fail-closed: complete contiguous normalized token span of the shorter side
# inside the longer side (even when absolute n-gram counts are too small).
NEAR_COPY_COMPLETE_TOKEN_SPAN_MIN = 5
POSITIVE_SPLITS = ("train", "development", "frozen", "adversarial")
TRAIN_SIDE_SPLITS = frozenset({"train", "development"})
HOLDOUT_SPLITS = frozenset({"frozen", "adversarial"})

# Evaluation / meta-language cues forbidden in natural candidate asks/targets.
META_LANGUAGE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bfrozen\b",
        r"\bholdout\b",
        r"\badversarial\b",
        r"\btrap\b",
        r"\blicensed\b",
        r"\brelationship must be stated\b",
        r"\bactive[- ]voice\b",
        r"\bpassive[- ]voice\b",
        r"\bevaluator\b",
        r"\brubric\b",
        r"\bintended fail\b",
        r"\bauditor\b",
        r"\bcandidate_id\b",
        r"\bsplit\b\s*[:=]",
    )
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"non_object_jsonl:{path}:{line_no}")
            rows.append(obj)
    return rows


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", normalize_text(text)) if t}


def _token_list(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", normalize_text(text)) if t]


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _ngram_overlap_ratio(a: str, b: str, n: int = NEAR_COPY_NGRAM_N) -> float:
    """Coverage of the shorter n-gram set; 1.0 only when short side is fully nested."""
    ta, tb = _token_list(a), _token_list(b)
    ga, gb = _ngrams(ta, n), _ngrams(tb, n)
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    denom = min(len(ga), len(gb))
    return inter / denom if denom else 0.0


def _ngram_near_copy_hit(a: str, b: str, n: int = NEAR_COPY_NGRAM_N) -> dict[str, Any] | None:
    """Require substantial absolute overlap — avoid short doctrine phrase false positives."""
    ta, tb = _token_list(a), _token_list(b)
    ga, gb = _ngrams(ta, n), _ngrams(tb, n)
    if not ga or not gb:
        return None
    inter = len(ga & gb)
    shorter = min(len(ga), len(gb))
    longer = max(len(ga), len(gb))
    if shorter < 8 or inter < 6:
        return None
    ratio_short = inter / shorter
    ratio_long = inter / longer
    if ratio_short >= NEAR_COPY_NGRAM_OVERLAP_RATIO and ratio_long >= 0.22:
        return {
            "kind": "ngram_containment",
            "score": ratio_short,
            "metrics": {
                **_similarity_bundle(a, b),
                "ngram_inter": inter,
                "ngram_short": shorter,
                "ngram_long": longer,
            },
        }
    return None


def _complete_token_span_containment_hit(
    a: str,
    b: str,
    min_tokens: int = NEAR_COPY_COMPLETE_TOKEN_SPAN_MIN,
) -> dict[str, Any] | None:
    """Fail-closed when the shorter side's full token sequence nests in the longer.

    Fires even when `_ngram_near_copy_hit` bails on absolute n-gram counts.
    Trivial fragments (< min_tokens) do not trigger this channel alone.
    """
    ta, tb = _token_list(a), _token_list(b)
    if not ta or not tb:
        return None
    if len(ta) <= len(tb):
        shorter, longer = ta, tb
    else:
        shorter, longer = tb, ta
    n = len(shorter)
    if n < min_tokens:
        return None
    for i in range(len(longer) - n + 1):
        if longer[i : i + n] == shorter:
            return {
                "kind": "complete_token_span_containment",
                "score": 1.0,
                "metrics": {
                    **_similarity_bundle(a, b),
                    "contained_token_count": n,
                    "complete_token_span_min": min_tokens,
                },
            }
    return None


def _phrase_containment_score(a: str, b: str) -> float:
    """Normalized phrase containment: shorter in longer, or longest shared window ratio."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if shorter in longer:
        return len(shorter) / max(len(longer), 1)
    # Sliding word-window containment for near-paraphrase phrase reuse.
    sw, lw = shorter.split(), longer.split()
    if len(sw) < 4:
        return 0.0
    best = 0.0
    window = max(4, len(sw) // 2)
    for i in range(0, max(len(sw) - window + 1, 1)):
        phrase = " ".join(sw[i : i + window])
        if phrase and phrase in longer:
            best = max(best, len(phrase) / max(len(longer), 1))
    return best


def _similarity_bundle(a: str, b: str) -> dict[str, float]:
    return {
        "jaccard": _jaccard(a, b),
        "phrase_containment": _phrase_containment_score(a, b),
        "ngram_overlap": _ngram_overlap_ratio(a, b),
    }


def _near_or_exact(a: str, b: str, threshold: float = NEAR_COPY_JACCARD) -> dict[str, Any] | None:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return None
    if na == nb:
        return {"kind": "exact_normalized", "score": 1.0, "metrics": _similarity_bundle(a, b)}
    # Complete contiguous token-span nesting (≥5 tokens) is fail-closed even when
    # phrase-ratio / absolute n-gram gates would otherwise miss short hidden answers.
    span_hit = _complete_token_span_containment_hit(a, b)
    if span_hit:
        return span_hit
    contain = _phrase_containment_score(a, b)
    if contain >= NEAR_COPY_CONTAINMENT_RATIO:
        shorter = na if len(na) <= len(nb) else nb
        if len(shorter) >= NEAR_COPY_CONTAINMENT_MIN_CHARS or contain >= 0.85:
            return {
                "kind": "phrase_containment",
                "score": contain,
                "metrics": _similarity_bundle(a, b),
            }
    ngram_hit = _ngram_near_copy_hit(a, b)
    if ngram_hit:
        return ngram_hit
    score = _jaccard(na, nb)
    if score >= threshold:
        return {"kind": "jaccard", "score": score, "metrics": _similarity_bundle(a, b)}
    return None


def _meta_language_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pat in META_LANGUAGE_PATTERNS:
        if pat.search(text or ""):
            hits.append(pat.pattern)
    return hits


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_hidden_asks(pack: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for case in pack.get("cases") or []:
        ask = case.get("ask")
        if ask is None and isinstance(case.get("generation"), dict):
            ask = case["generation"].get("ask")
        ask_s = str(ask or "").strip()
        if ask_s:
            out.append(
                {
                    "case_id": str(case.get("case_id") or ""),
                    "ask": ask_s,
                    "ask_hash": sha256_text(normalize_text(ask_s)),
                }
            )
    return out


def _extract_hidden_outputs(blind_eval: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for slot in blind_eval.get("slots") or []:
        label = str(slot.get("bookkeeping_label") or slot.get("slot") or "")
        for detail in slot.get("details") or []:
            if not isinstance(detail, dict):
                continue
            text = str(detail.get("text") or "").strip()
            if not text:
                continue
            out.append(
                {
                    "case_id": str(detail.get("case_id") or ""),
                    "slot_label": label,
                    "text": text,
                    "text_hash": sha256_text(normalize_text(text)),
                }
            )
    return out


def _primary_fail_keys(axis: str) -> list[str]:
    return {
        "indirect_tool_agency": [AXIS_REQUESTED_BOUNDARY, AXIS_FORBIDDEN_AUTHORITY],
        "architecture_cpu_gpu_role": [AXIS_ARCHITECTURE_ROLE],
        "identity_humanization": [AXIS_IDENTITY, AXIS_FORBIDDEN_AUTHORITY],
        "memory_ownership_and_service_attribution": [AXIS_REQUESTED_BOUNDARY],
    }[axis]


def _response_text(row: dict[str, Any]) -> str:
    if row.get("row_class") == "auditor_hard_negative":
        return str(row.get("negative_response") or row.get("target") or "")
    return str(row.get("licensed_positive_target") or row.get("target") or "")


def run_audit(
    *,
    design_path: Path,
    hidden_v1: Path,
    hidden_v22: Path,
    positives_path: Path,
    negatives_path: Path,
    blind_v22: Path | None,
    blind_v1: Path | None,
    stage: str,
) -> dict[str, Any]:
    design = _load_json(design_path)
    positives = _load_jsonl(positives_path)
    negatives = _load_jsonl(negatives_path)
    pack_v1 = _load_json(hidden_v1)
    pack_v22 = _load_json(hidden_v22)
    hidden_asks = _extract_hidden_asks(pack_v1) + _extract_hidden_asks(pack_v22)
    hidden_outputs: list[dict[str, str]] = []
    if blind_v22 and blind_v22.is_file():
        hidden_outputs.extend(_extract_hidden_outputs(_load_json(blind_v22)))
    if blind_v1 and blind_v1.is_file():
        hidden_outputs.extend(_extract_hidden_outputs(_load_json(blind_v1)))

    findings: list[dict[str, Any]] = []
    counters = {
        "ask_overlap": 0,
        "example_overlap": 0,
        "cluster_leak": 0,
        "pair_overlap": 0,
        "hidden_reference_reuse": 0,
        "hidden_ask_copy": 0,
        "hidden_output_copy": 0,
    }

    # --- split disjointness among positives ---
    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in positives:
        by_split[str(row.get("split"))].append(row)

    def _cross_split_dup(key: str, counter_name: str) -> None:
        seen: dict[str, str] = {}
        for split, rows in by_split.items():
            if split not in POSITIVE_SPLITS:
                findings.append(
                    {
                        "severity": "unexpected_positive_split",
                        "split": split,
                        "ids": [r.get("candidate_id") for r in rows],
                    }
                )
                counters[counter_name] += 1
                continue
            for row in rows:
                val = str(row.get(key) or "")
                if not val:
                    findings.append(
                        {
                            "severity": f"missing_{key}",
                            "candidate_id": row.get("candidate_id"),
                        }
                    )
                    counters[counter_name] += 1
                    continue
                if val in seen and seen[val] != split:
                    findings.append(
                        {
                            "severity": counter_name,
                            "key": key,
                            "value": val,
                            "splits": [seen[val], split],
                            "candidate_id": row.get("candidate_id"),
                        }
                    )
                    counters[counter_name] += 1
                else:
                    seen[val] = split

    _cross_split_dup("ask_hash", "ask_overlap")
    _cross_split_dup("example_hash", "example_overlap")
    _cross_split_dup("pair_id", "pair_overlap")

    # Semantic cluster leak: family must not span train-side and frozen/adversarial.
    # Same family may repeat within train-side or within holdout, but not across.
    cluster_to_splits: dict[str, set[str]] = defaultdict(set)
    cluster_to_ids: dict[str, list[str]] = defaultdict(list)
    for row in positives:
        cid = str(row.get("cluster_id") or "")
        split = str(row.get("split") or "")
        if not cid:
            findings.append(
                {
                    "severity": "cluster_leak",
                    "kind": "missing_cluster_id",
                    "candidate_id": row.get("candidate_id"),
                }
            )
            counters["cluster_leak"] += 1
            continue
        # Reject candidate-id / split-encoded cluster placeholders from R1 style.
        if re.search(r"_train_|_development_|_frozen_|_adversarial_", cid):
            findings.append(
                {
                    "severity": "cluster_leak",
                    "kind": "cluster_id_encodes_split",
                    "cluster_id": cid,
                    "candidate_id": row.get("candidate_id"),
                }
            )
            counters["cluster_leak"] += 1
        cluster_to_splits[cid].add(split)
        cluster_to_ids[cid].append(str(row.get("candidate_id")))
    for cid, splits in cluster_to_splits.items():
        train_side = splits & TRAIN_SIDE_SPLITS
        holdout = splits & HOLDOUT_SPLITS
        if train_side and holdout:
            findings.append(
                {
                    "severity": "cluster_leak",
                    "kind": "family_shared_train_and_holdout",
                    "cluster_id": cid,
                    "splits": sorted(splits),
                    "candidate_ids": cluster_to_ids[cid],
                }
            )
            counters["cluster_leak"] += 1

    # Also require global uniqueness of ask/example/pair keys across all positives.
    for key, cname in (
        ("ask_hash", "ask_overlap"),
        ("example_hash", "example_overlap"),
        ("pair_id", "pair_overlap"),
    ):
        bag: dict[str, list[str]] = defaultdict(list)
        for row in positives:
            bag[str(row.get(key) or "")].append(str(row.get("candidate_id")))
        for val, ids in bag.items():
            if val and len(ids) > 1:
                findings.append(
                    {
                        "severity": cname,
                        "scope": "within_positives_duplicate",
                        "key": key,
                        "value": val,
                        "candidate_ids": ids,
                    }
                )
                counters[cname] += 1

    # Naturalness / meta-language gate (asks + targets)
    for row in positives + negatives:
        ask = str(row.get("ask") or "")
        resp = _response_text(row)
        ask_hits = _meta_language_hits(ask)
        resp_hits = _meta_language_hits(resp)
        if ask_hits or resp_hits:
            findings.append(
                {
                    "severity": "meta_language_gate_fail",
                    "candidate_id": row.get("candidate_id"),
                    "ask_hits": ask_hits,
                    "response_hits": resp_hits,
                }
            )

    # Hidden ask hash reuse / near-copy (+ always report max similarity)
    hidden_ask_hashes = {h["ask_hash"] for h in hidden_asks}
    max_hidden_ask_sim: dict[str, Any] = {
        "score": 0.0,
        "jaccard": 0.0,
        "phrase_containment": 0.0,
        "ngram_overlap": 0.0,
        "candidate_id": None,
        "hidden_case_id": None,
    }
    for row in positives + negatives:
        ask = str(row.get("ask") or "")
        ask_h = str(row.get("ask_hash") or sha256_text(normalize_text(ask)))
        if ask_h in hidden_ask_hashes:
            findings.append(
                {
                    "severity": "hidden_ask_copy",
                    "kind": "exact_hash",
                    "candidate_id": row.get("candidate_id"),
                }
            )
            counters["hidden_ask_copy"] += 1
            counters["ask_overlap"] += 1
            continue
        best_hit = None
        for hidden in hidden_asks:
            metrics = _similarity_bundle(ask, hidden["ask"])
            composite = max(
                metrics["jaccard"],
                metrics["phrase_containment"],
                metrics["ngram_overlap"],
            )
            if composite >= float(max_hidden_ask_sim["score"]):
                max_hidden_ask_sim = {
                    "score": composite,
                    **metrics,
                    "candidate_id": row.get("candidate_id"),
                    "hidden_case_id": hidden["case_id"],
                }
            hit = _near_or_exact(ask, hidden["ask"])
            if hit and (best_hit is None or hit["score"] > best_hit["score"]):
                best_hit = {**hit, "hidden_case_id": hidden["case_id"]}
        if best_hit:
            findings.append(
                {
                    "severity": "hidden_ask_copy",
                    "kind": best_hit["kind"],
                    "score": best_hit["score"],
                    "metrics": best_hit.get("metrics"),
                    "candidate_id": row.get("candidate_id"),
                    "hidden_case_id": best_hit["hidden_case_id"],
                }
            )
            counters["hidden_ask_copy"] += 1

    # Hidden output near/exact copy against candidate responses
    max_hidden_output_sim: dict[str, Any] = {
        "score": 0.0,
        "jaccard": 0.0,
        "phrase_containment": 0.0,
        "ngram_overlap": 0.0,
        "candidate_id": None,
        "hidden_case_id": None,
        "slot_label": None,
    }
    for row in positives + negatives:
        resp = _response_text(row)
        best_hit = None
        for hidden in hidden_outputs:
            metrics = _similarity_bundle(resp, hidden["text"])
            composite = max(
                metrics["jaccard"],
                metrics["phrase_containment"],
                metrics["ngram_overlap"],
            )
            if composite >= float(max_hidden_output_sim["score"]):
                max_hidden_output_sim = {
                    "score": composite,
                    **metrics,
                    "candidate_id": row.get("candidate_id"),
                    "hidden_case_id": hidden["case_id"],
                    "slot_label": hidden["slot_label"],
                }
            hit = _near_or_exact(resp, hidden["text"])
            if hit and (best_hit is None or hit["score"] > best_hit["score"]):
                best_hit = {
                    **hit,
                    "hidden_case_id": hidden["case_id"],
                    "slot_label": hidden["slot_label"],
                }
        if best_hit:
            findings.append(
                {
                    "severity": "hidden_output_copy",
                    "kind": best_hit["kind"],
                    "score": best_hit["score"],
                    "metrics": best_hit.get("metrics"),
                    "candidate_id": row.get("candidate_id"),
                    "hidden_case_id": best_hit["hidden_case_id"],
                    "slot_label": best_hit["slot_label"],
                }
            )
            counters["hidden_output_copy"] += 1

    # Hidden reference reuse — forbid reference to hidden pack/case identities
    forbidden_ref_blobs = {
        sha256_text("hidden_indirect_adversarial_pack_v1"),
        sha256_text("hidden_indirect_adversarial_pack_v2_2"),
        sha256_text(str(pack_v1.get("content_sha256") or "")),
        sha256_text(str(pack_v22.get("content_sha256") or "")),
        _file_sha256(hidden_v1),
        _file_sha256(hidden_v22),
    }
    forbidden_ref_blobs |= {
        sha256_text(h["case_id"]) for h in hidden_asks if h["case_id"]
    }
    forbidden_ref_blobs |= {
        sha256_text(h["ask"]) for h in hidden_asks if h["ask"]
    }
    for row in positives + negatives:
        ref_h = str(row.get("reference_hash") or "")
        ref_id = str(row.get("reference_id") or "").lower()
        if ref_h and ref_h in forbidden_ref_blobs:
            findings.append(
                {
                    "severity": "hidden_reference_reuse",
                    "candidate_id": row.get("candidate_id"),
                    "reference_hash": ref_h,
                }
            )
            counters["hidden_reference_reuse"] += 1
        if "hidden" in ref_id and (
            "v1" in ref_id or "v2" in ref_id or "indirect" in ref_id
        ):
            findings.append(
                {
                    "severity": "hidden_reference_reuse",
                    "candidate_id": row.get("candidate_id"),
                    "reference_id": row.get("reference_id"),
                }
            )
            counters["hidden_reference_reuse"] += 1

    # Judge gates
    positive_judge: list[dict[str, Any]] = []
    for row in positives:
        rubric = row.get("judge_rubric") or {}
        judgment = judge_case(
            _response_text(row),
            {"case_id": row.get("candidate_id"), "axis": row.get("axis"), "rubric": rubric},
        )
        ok = bool(judgment.get("overall_pass"))
        positive_judge.append(
            {
                "candidate_id": row.get("candidate_id"),
                "axis": row.get("axis"),
                "pass": ok,
            }
        )
        if not ok:
            findings.append(
                {
                    "severity": "positive_judge_fail",
                    "candidate_id": row.get("candidate_id"),
                    "judgment": judgment,
                }
            )

    negative_judge: list[dict[str, Any]] = []
    for row in negatives:
        rubric = row.get("judge_rubric") or {}
        judgment = judge_case(
            _response_text(row),
            {"case_id": row.get("candidate_id"), "axis": row.get("axis"), "rubric": rubric},
        )
        axes = judgment.get("axes") or {}
        primary_keys = _primary_fail_keys(str(row.get("axis")))
        primary_failed = [
            k
            for k in primary_keys
            if axes.get(k, {}).get("applicable") and axes.get(k, {}).get("pass") is False
        ]
        secondary = [
            name
            for name, result in axes.items()
            if result.get("applicable")
            and result.get("pass") is False
            and name not in primary_keys
        ]
        ok_fail = (not judgment.get("overall_pass")) and bool(primary_failed)
        note = {
            "candidate_id": row.get("candidate_id"),
            "axis": row.get("axis"),
            "intended_fail_ok": ok_fail,
            "primary_fail_keys": primary_failed,
            "secondary_fail_axes": secondary,
            "unavoidable_multi_primary": len(primary_failed) > 1,
        }
        negative_judge.append(note)
        if not ok_fail:
            findings.append(
                {
                    "severity": "negative_intended_axis_miss",
                    "candidate_id": row.get("candidate_id"),
                    "note": note,
                    "judgment": judgment,
                }
            )

    # Response-only loss / train JSONL isolation
    train_targets = {
        _response_text(r) for r in positives if r.get("split") == "train"
    }
    neg_in_train_jsonl = []
    for row in negatives:
        if row.get("split") != "auditor":
            findings.append(
                {
                    "severity": "negative_not_split_auditor",
                    "candidate_id": row.get("candidate_id"),
                    "split": row.get("split"),
                }
            )
        if row.get("optimizer_eligible") is not False:
            findings.append(
                {
                    "severity": "negative_optimizer_eligible",
                    "candidate_id": row.get("candidate_id"),
                }
            )
        if _response_text(row) in train_targets:
            neg_in_train_jsonl.append(row.get("candidate_id"))
            findings.append(
                {
                    "severity": "negative_response_in_train_positive_targets",
                    "candidate_id": row.get("candidate_id"),
                }
            )

    for row in positives:
        if row.get("optimizer_eligible") is not False:
            findings.append(
                {
                    "severity": "positive_optimizer_eligible_while_unauthorized",
                    "candidate_id": row.get("candidate_id"),
                }
            )
        if row.get("admission_status") != "CANDIDATE_HOLD":
            findings.append(
                {
                    "severity": "admission_status_not_hold",
                    "candidate_id": row.get("candidate_id"),
                    "admission_status": row.get("admission_status"),
                }
            )

    training_authorized = bool(design.get("training_authorized"))
    if training_authorized:
        findings.append({"severity": "design_training_authorized_true"})

    # Defensive: full short-side 5-gram nesting (ngram_overlap=1.0) must not coexist
    # with a clean hidden_output_copy / hidden_ask_copy counter (R2 miss class).
    for channel, max_sim, counter_key in (
        ("ask", max_hidden_ask_sim, "hidden_ask_copy"),
        ("output", max_hidden_output_sim, "hidden_output_copy"),
    ):
        if float(max_sim.get("ngram_overlap") or 0.0) >= 1.0 and counters[counter_key] == 0:
            findings.append(
                {
                    "severity": "similarity_channel_threshold_contradiction",
                    "channel": channel,
                    "ngram_overlap": max_sim.get("ngram_overlap"),
                    "counter": counter_key,
                    "counter_value": counters[counter_key],
                    "candidate_id": max_sim.get("candidate_id"),
                    "hidden_case_id": max_sim.get("hidden_case_id"),
                    "note": (
                        "Reported complete short-side n-gram nesting without a near-copy "
                        "counter increment; containment gate should have fail-closed."
                    ),
                }
            )

    # Counts
    pos_by_axis: dict[str, int] = defaultdict(int)
    pos_by_split: dict[str, int] = defaultdict(int)
    for row in positives:
        pos_by_axis[str(row.get("axis"))] += 1
        pos_by_split[str(row.get("split"))] += 1
    neg_by_axis: dict[str, int] = defaultdict(int)
    neg_by_surface: dict[str, int] = defaultdict(int)
    for row in negatives:
        neg_by_axis[str(row.get("axis"))] += 1
        neg_by_surface[str(row.get("intended_audit_surface"))] += 1

    exit_ok = all(v == 0 for v in counters.values()) and not any(
        f.get("severity")
        in {
            "positive_judge_fail",
            "negative_intended_axis_miss",
            "negative_optimizer_eligible",
            "negative_not_split_auditor",
            "negative_response_in_train_positive_targets",
            "positive_optimizer_eligible_while_unauthorized",
            "admission_status_not_hold",
            "design_training_authorized_true",
            "meta_language_gate_fail",
            "similarity_channel_threshold_contradiction",
        }
        for f in findings
    )

    report = {
        "schema_version": "corpus_overlap_audit_v3_r2",
        "stage": stage,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pass": exit_ok,
        "training_authorized": False,
        "canonical_corpus_admitted": False,
        "design_path": str(design_path).replace("\\", "/"),
        "design_training_authorized": design.get("training_authorized"),
        "inputs": {
            "positives": str(positives_path).replace("\\", "/"),
            "positives_sha256": _file_sha256(positives_path),
            "negatives": str(negatives_path).replace("\\", "/"),
            "negatives_sha256": _file_sha256(negatives_path),
            "hidden_v1": str(hidden_v1).replace("\\", "/"),
            "hidden_v1_sha256": _file_sha256(hidden_v1),
            "hidden_v22": str(hidden_v22).replace("\\", "/"),
            "hidden_v22_sha256": _file_sha256(hidden_v22),
            "blind_v22": str(blind_v22).replace("\\", "/") if blind_v22 else None,
            "blind_v1": str(blind_v1).replace("\\", "/") if blind_v1 else None,
            "near_copy_jaccard_threshold": NEAR_COPY_JACCARD,
            "near_copy_containment_min_chars": NEAR_COPY_CONTAINMENT_MIN_CHARS,
            "near_copy_containment_ratio": NEAR_COPY_CONTAINMENT_RATIO,
            "near_copy_ngram_n": NEAR_COPY_NGRAM_N,
            "near_copy_ngram_overlap_ratio": NEAR_COPY_NGRAM_OVERLAP_RATIO,
            "near_copy_complete_token_span_min": NEAR_COPY_COMPLETE_TOKEN_SPAN_MIN,
        },
        "near_copy_evidence": {
            "max_hidden_ask_similarity": max_hidden_ask_sim,
            "max_hidden_output_similarity": max_hidden_output_sim,
            "note": (
                "Max similarities reported even when below near-copy thresholds; "
                "threshold hits (including complete contiguous normalized token-span "
                f"containment of ≥{NEAR_COPY_COMPLETE_TOKEN_SPAN_MIN} tokens) still "
                "increment hidden_ask_copy / hidden_output_copy."
            ),
        },
        "counts": {
            "positives": len(positives),
            "negatives": len(negatives),
            "positives_by_axis": dict(sorted(pos_by_axis.items())),
            "positives_by_split": dict(sorted(pos_by_split.items())),
            "negatives_by_axis": dict(sorted(neg_by_axis.items())),
            "negatives_by_intended_audit_surface": dict(sorted(neg_by_surface.items())),
            "hidden_asks": len(hidden_asks),
            "hidden_outputs": len(hidden_outputs),
        },
        "exit_criteria": counters,
        "judge": {
            "positives_all_pass": all(r["pass"] for r in positive_judge),
            "positives": positive_judge,
            "negatives_intended_fail_all": all(r["intended_fail_ok"] for r in negative_judge),
            "negatives": negative_judge,
            "secondary_fail_documentation": [
                r
                for r in negative_judge
                if r["secondary_fail_axes"] or r["unavoidable_multi_primary"]
            ],
        },
        "response_only_loss_guard": {
            "all_optimizer_eligible_false": all(
                r.get("optimizer_eligible") is False for r in positives + negatives
            ),
            "all_negatives_split_auditor": all(
                r.get("split") == "auditor" for r in negatives
            ),
            "negatives_in_train_positive_targets": neg_in_train_jsonl,
        },
        "findings": findings,
        "note": (
            "Audit only. No admission, LoRA, DPO, lease, deploy, or hidden-v3 construction."
        ),
    }
    return report


def _write_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Mouth V3 corpus overlap audit",
        "",
        f"- **pass:** `{report['pass']}`",
        f"- **stage:** `{report['stage']}`",
        f"- **training_authorized:** `{report['training_authorized']}`",
        f"- **canonical_corpus_admitted:** `{report['canonical_corpus_admitted']}`",
        f"- **positives:** {report['counts']['positives']}",
        f"- **auditor negatives:** {report['counts']['negatives']}",
        "",
        "## Exit criteria",
        "",
    ]
    for key, val in report["exit_criteria"].items():
        lines.append(f"- `{key}` = **{val}**")
    nce = report.get("near_copy_evidence") or {}
    ask_m = nce.get("max_hidden_ask_similarity") or {}
    out_m = nce.get("max_hidden_output_similarity") or {}
    lines += [
        "",
        "## Near-copy evidence (always reported)",
        "",
        f"- max hidden-ask similarity: **{ask_m.get('score', 0):.4f}** "
        f"(jaccard={ask_m.get('jaccard', 0):.4f}, "
        f"phrase={ask_m.get('phrase_containment', 0):.4f}, "
        f"ngram={ask_m.get('ngram_overlap', 0):.4f}) "
        f"candidate=`{ask_m.get('candidate_id')}` hidden=`{ask_m.get('hidden_case_id')}`",
        f"- max hidden-output similarity: **{out_m.get('score', 0):.4f}** "
        f"(jaccard={out_m.get('jaccard', 0):.4f}, "
        f"phrase={out_m.get('phrase_containment', 0):.4f}, "
        f"ngram={out_m.get('ngram_overlap', 0):.4f}) "
        f"candidate=`{out_m.get('candidate_id')}` hidden=`{out_m.get('hidden_case_id')}`",
        f"- jaccard threshold: `{report.get('inputs', {}).get('near_copy_jaccard_threshold')}`",
        f"- complete token-span min: "
        f"`{report.get('inputs', {}).get('near_copy_complete_token_span_min')}`",
        "",
        "## Judge",
        "",
        f"- positives all pass: `{report['judge']['positives_all_pass']}`",
        f"- negatives intended-fail all: `{report['judge']['negatives_intended_fail_all']}`",
        "",
    ]
    secondary = report["judge"]["secondary_fail_documentation"]
    if secondary:
        lines.append("### Secondary / multi-primary fails (documented)")
        lines.append("")
        for row in secondary:
            lines.append(
                f"- `{row['candidate_id']}` axis=`{row['axis']}` "
                f"primary={row['primary_fail_keys']} "
                f"secondary={row['secondary_fail_axes']}"
            )
        lines.append("")
    lines += [
        "## Response-only loss guard",
        "",
        f"- optimizer_eligible all false: "
        f"`{report['response_only_loss_guard']['all_optimizer_eligible_false']}`",
        f"- negatives split=auditor: "
        f"`{report['response_only_loss_guard']['all_negatives_split_auditor']}`",
        f"- negatives leaking into train targets: "
        f"`{report['response_only_loss_guard']['negatives_in_train_positive_targets']}`",
        "",
        f"Findings: **{len(report['findings'])}**",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--hidden-v1", type=Path, required=True)
    parser.add_argument("--hidden-v22", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True, help="Positive candidates JSONL")
    parser.add_argument(
        "--auditor-negatives",
        type=Path,
        required=True,
        help="Separate auditor hard-negative JSONL",
    )
    parser.add_argument(
        "--blind-v22",
        type=Path,
        default=None,
        help="Blind eval JSON with hidden v2.2 observed outputs",
    )
    parser.add_argument(
        "--blind-v1",
        type=Path,
        default=None,
        help="Blind eval JSON with hidden v1 observed outputs",
    )
    parser.add_argument("--stage", default="before_admission")
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--report-md", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_audit(
        design_path=args.design,
        hidden_v1=args.hidden_v1,
        hidden_v22=args.hidden_v22,
        positives_path=args.candidates,
        negatives_path=args.auditor_negatives,
        blind_v22=args.blind_v22,
        blind_v1=args.blind_v1,
        stage=args.stage,
    )

    out_dir = args.candidates.parent
    report_json = args.report_json or (out_dir / "mouth_v3_overlap_audit_report.json")
    report_md = args.report_md or (out_dir / "mouth_v3_overlap_audit_report.md")
    report_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    _write_md(report, report_md)

    print(
        json.dumps(
            {
                "pass": report["pass"],
                "exit_criteria": report["exit_criteria"],
                "positives": report["counts"]["positives"],
                "negatives": report["counts"]["negatives"],
                "report_json": str(report_json).replace("\\", "/"),
                "report_md": str(report_md).replace("\\", "/"),
                "training_authorized": False,
                "canonical_corpus_admitted": False,
                "findings": len(report["findings"]),
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
