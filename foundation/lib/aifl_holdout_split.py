#!/usr/bin/env python3
"""P0 permanent holdout ↔ train disjoint split for AIFL.

Freeze holdout once with stable hashes. Ban exact (ask,chosen) pairs and
near-duplicate ask clusters from every SFT export / train snapshot.
Preflight fails train or deploy-validate on any overlap.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lib.paths import AUTO_ARTIFACTS

GATE_DIR = AUTO_ARTIFACTS / "shadow_judge"
HOLDOUT_PACK_PATH = GATE_DIR / "holdout_pack.jsonl"
HOLDOUT_REGISTRY_PATH = GATE_DIR / "holdout_registry.json"
HOLDOUT_ARCHIVE_DIR = GATE_DIR / "holdout_archive"
HOLDOUT_BAN_PATH = GATE_DIR / "holdout_ban_set.json"
DEPLOY_TEST_PACK_PATH = GATE_DIR / "deploy_test_pack.jsonl"
DEPLOY_TEST_REGISTRY_PATH = GATE_DIR / "deploy_test_registry.json"
DEPLOY_TEST_BAN_PATH = GATE_DIR / "deploy_test_ban_set.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_text(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def ask_cluster_key(ask: str) -> str:
    """Near-dup cluster key: collapse volatile ingest fields, keep intent spine."""
    s = normalize_text(ask)
    s = re.sub(r"[a-f0-9]{8,}", "<hex>", s)
    s = re.sub(r"\b\d+\b", "<n>", s)
    s = re.sub(r"path=[^\s;]+", "path=<p>", s)
    s = re.sub(r"fingerprint=<hex>", "fingerprint=<hex>", s)
    s = re.sub(r"bytes=<n>", "bytes=<n>", s)
    # identity curriculum asks stay exact after normalize
    return s


def _sha16(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def pair_hash(ask: str, chosen: str) -> str:
    return _sha16(normalize_text(ask) + "\0" + normalize_text(chosen))


def ask_hash(ask: str) -> str:
    return _sha16(normalize_text(ask))


def cluster_hash(ask: str) -> str:
    return _sha16(ask_cluster_key(ask))


def annotate_pair_ids(ask: str, chosen: str) -> dict[str, str]:
    return {
        "pair_hash": pair_hash(ask, chosen),
        "ask_hash": ask_hash(ask),
        "ask_cluster_hash": cluster_hash(ask),
    }


def load_registry() -> dict[str, Any]:
    if not HOLDOUT_REGISTRY_PATH.is_file():
        return {}
    try:
        data = json.loads(HOLDOUT_REGISTRY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_registry(reg: dict[str, Any]) -> None:
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    HOLDOUT_REGISTRY_PATH.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def load_ban_sets() -> dict[str, set[str]]:
    """Union of continuity holdout bans + deploy-test bans (train must avoid both)."""
    out: dict[str, set[str]] = {"pair": set(), "ask": set(), "cluster": set()}

    def _absorb(src: dict[str, set[str]]) -> None:
        for k in ("pair", "ask", "cluster"):
            out[k] |= src.get(k) or set()

    reg = load_registry()
    if reg.get("pair_hashes"):
        _absorb(
            {
                "pair": set(str(x) for x in (reg.get("pair_hashes") or [])),
                "ask": set(str(x) for x in (reg.get("ask_hashes") or [])),
                "cluster": set(str(x) for x in (reg.get("ask_cluster_hashes") or [])),
            }
        )
    elif HOLDOUT_BAN_PATH.is_file():
        try:
            data = json.loads(HOLDOUT_BAN_PATH.read_text(encoding="utf-8"))
            _absorb(
                {
                    "pair": set(str(x) for x in (data.get("pair_hashes") or [])),
                    "ask": set(str(x) for x in (data.get("ask_hashes") or [])),
                    "cluster": set(str(x) for x in (data.get("ask_cluster_hashes") or [])),
                }
            )
        except (OSError, json.JSONDecodeError):
            pass
    else:
        _absorb(ban_sets_from_holdout_pack(HOLDOUT_PACK_PATH))

    # Deploy-test pack (deciding benchmark) — ban from train even though never in prefs
    dt = load_deploy_test_registry()
    if dt.get("ask_hashes") or dt.get("ask_cluster_hashes"):
        _absorb(
            {
                "pair": set(str(x) for x in (dt.get("pair_hashes") or [])),
                "ask": set(str(x) for x in (dt.get("ask_hashes") or [])),
                "cluster": set(str(x) for x in (dt.get("ask_cluster_hashes") or [])),
            }
        )
    elif DEPLOY_TEST_BAN_PATH.is_file():
        try:
            data = json.loads(DEPLOY_TEST_BAN_PATH.read_text(encoding="utf-8"))
            _absorb(
                {
                    "pair": set(str(x) for x in (data.get("pair_hashes") or [])),
                    "ask": set(str(x) for x in (data.get("ask_hashes") or [])),
                    "cluster": set(str(x) for x in (data.get("ask_cluster_hashes") or [])),
                }
            )
        except (OSError, json.JSONDecodeError):
            pass
    elif DEPLOY_TEST_PACK_PATH.is_file():
        _absorb(ban_sets_from_holdout_pack(DEPLOY_TEST_PACK_PATH))

    return out


def load_deploy_test_registry() -> dict[str, Any]:
    if not DEPLOY_TEST_REGISTRY_PATH.is_file():
        return {}
    try:
        data = json.loads(DEPLOY_TEST_REGISTRY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_deploy_test_registry(reg: dict[str, Any]) -> None:
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    DEPLOY_TEST_REGISTRY_PATH.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def collision_check_asks(
    asks: list[str],
    *,
    against_prefs: bool = True,
    against_sft: bool = True,
    against_continuity: bool = True,
) -> dict[str, Any]:
    """Ensure candidate deploy-test asks do not collide with known train/holdout hashes."""
    from lib.paths import ARTIFACTS
    from lib.viv_shadow_judge import PREFERENCE_JSONL

    banned_ask: set[str] = set()
    banned_cluster: set[str] = set()
    if against_continuity:
        bans = load_ban_sets()
        # Only continuity portion for initial authorship — load registry directly
        reg = load_registry()
        banned_ask |= set(str(x) for x in (reg.get("ask_hashes") or []))
        banned_cluster |= set(str(x) for x in (reg.get("ask_cluster_hashes") or []))
        if not banned_ask:
            b = ban_sets_from_holdout_pack(HOLDOUT_PACK_PATH)
            banned_ask |= b["ask"]
            banned_cluster |= b["cluster"]

    if against_prefs and PREFERENCE_JSONL.is_file():
        for ln in PREFERENCE_JSONL.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            a = str(row.get("ask") or "")
            if a:
                banned_ask.add(ask_hash(a))
                banned_cluster.add(cluster_hash(a))

    sft = ARTIFACTS / "models" / "viv_judge_sft_train.jsonl"
    if against_sft and sft.is_file():
        for ln in sft.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            a, _c = parse_sft_text(str(row.get("text") or ""))
            if a:
                banned_ask.add(ask_hash(a))
                banned_cluster.add(cluster_hash(a))

    # curriculum prompts
    try:
        from lib.viv_aifl import _SELF_PROMPTS

        for p in _SELF_PROMPTS:
            banned_ask.add(ask_hash(p))
            banned_cluster.add(cluster_hash(p))
    except Exception:  # noqa: BLE001
        pass

    hits: list[dict[str, Any]] = []
    for ask in asks:
        ah, ch = ask_hash(ask), cluster_hash(ask)
        reasons = []
        if ah in banned_ask:
            reasons.append("ask_hash")
        if ch in banned_cluster:
            reasons.append("ask_cluster_hash")
        if reasons:
            hits.append({"ask": ask[:120], "ask_hash": ah, "ask_cluster_hash": ch, "reasons": reasons})
    return {"ok": len(hits) == 0, "n": len(asks), "collisions": hits}


def freeze_deploy_test_pack(
    *,
    force: bool = False,
    note: str = "fresh_deploy_test_post_quarantine",
) -> dict[str, Any]:
    """Write sealed asks → deploy_test_pack.jsonl and permanent registry. Ban from train."""
    existing = load_deploy_test_registry()
    if existing.get("frozen") and not force:
        return {
            "ok": True,
            "created": False,
            "frozen": True,
            "pack_id": existing.get("pack_id"),
            "path": str(DEPLOY_TEST_REGISTRY_PATH).replace("\\", "/"),
            "note": "already_frozen",
        }

    from lib.aifl_deploy_test_asks import DEPLOY_TEST_ASKS

    asks = [str(x["ask"]) for x in DEPLOY_TEST_ASKS]
    coll = collision_check_asks(asks)
    if not coll.get("ok"):
        return {"ok": False, "error": "deploy_test_ask_collision", "collisions": coll.get("collisions")}

    GATE_DIR.mkdir(parents=True, exist_ok=True)
    if DEPLOY_TEST_PACK_PATH.is_file():
        HOLDOUT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(
            DEPLOY_TEST_PACK_PATH,
            HOLDOUT_ARCHIVE_DIR / f"deploy_test_pack_{stamp}.jsonl",
        )

    rows_out: list[dict[str, Any]] = []
    ask_hashes: list[str] = []
    cluster_hashes: list[str] = []
    pair_hashes: list[str] = []
    for item in DEPLOY_TEST_ASKS:
        ask = str(item["ask"])
        # ask-only pack for generate→judge validate; chosen empty until scored
        ids = annotate_pair_ids(ask, "")
        row = {
            "ask": ask,
            "draft": "",
            "facts": list(item["facts"]) if isinstance(item.get("facts"), list) else [],
            "sn": float(item.get("sn") or 0.45),
            "tag": str(item.get("tag") or ""),
            "source": "deploy_test_sealed",
            "authored_at": _utc(),
            **ids,
        }
        rows_out.append(row)
        ask_hashes.append(ids["ask_hash"])
        cluster_hashes.append(ids["ask_cluster_hash"])
        pair_hashes.append(ids["pair_hash"])

    def _uniq(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    ask_u, cl_u, pair_u = _uniq(ask_hashes), _uniq(cluster_hashes), _uniq(pair_hashes)
    pack_id = _sha16("|".join(sorted(ask_u)))
    with DEPLOY_TEST_PACK_PATH.open("w", encoding="utf-8") as fh:
        for row in rows_out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    reg = {
        "version": 1,
        "role": "deploy_decision",
        "frozen": True,
        "frozen_at": _utc(),
        "pack_id": pack_id,
        "n": len(rows_out),
        "pair_hashes": pair_u,
        "ask_hashes": ask_u,
        "ask_cluster_hashes": cl_u,
        "pack_path": str(DEPLOY_TEST_PACK_PATH).replace("\\", "/"),
        "continuity_pack_id": load_registry().get("pack_id"),
        "note": note,
        "contract": (
            "Honest deciding deploy benchmark. Authored after quarantine. "
            "Never enter preferences, SFT, or prompt-generation sources. "
            "Continuity pack b7b159… remains regression-only."
        ),
    }
    save_deploy_test_registry(reg)
    DEPLOY_TEST_BAN_PATH.write_text(
        json.dumps(
            {
                "at": _utc(),
                "pack_id": pack_id,
                "pair_hashes": pair_u,
                "ask_hashes": ask_u,
                "ask_cluster_hashes": cl_u,
                "role": "deploy_decision",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Re-scrub SFT in case any accidental overlap
    from lib.paths import ARTIFACTS

    sft = ARTIFACTS / "models" / "viv_judge_sft_train.jsonl"
    scrub = rebuild_sft_excluding_holdout(sft_path=sft, backup=True) if sft.is_file() else None
    return {
        "ok": True,
        "created": True,
        "frozen": True,
        "pack_id": pack_id,
        "n": len(rows_out),
        "n_ask": len(ask_u),
        "n_cluster": len(cl_u),
        "registry": str(DEPLOY_TEST_REGISTRY_PATH).replace("\\", "/"),
        "pack": str(DEPLOY_TEST_PACK_PATH).replace("\\", "/"),
        "collision_check": coll,
        "sft_scrub": scrub,
    }


def ban_sets_from_holdout_pack(path: Path) -> dict[str, set[str]]:
    pairs: set[str] = set()
    asks: set[str] = set()
    clusters: set[str] = set()
    if not path.is_file():
        return {"pair": pairs, "ask": asks, "cluster": clusters}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        ask = str(row.get("ask") or "")
        chosen = str(row.get("draft") or row.get("chosen") or "")
        ids = annotate_pair_ids(ask, chosen)
        # prefer stored hashes if present
        ph = str(row.get("pair_hash") or ids["pair_hash"])
        ah = str(row.get("ask_hash") or ids["ask_hash"])
        ch = str(row.get("ask_cluster_hash") or ids["ask_cluster_hash"])
        pairs.add(ph)
        asks.add(ah)
        clusters.add(ch)
    return {"pair": pairs, "ask": asks, "cluster": clusters}


def is_banned_pair(ask: str, chosen: str, bans: dict[str, set[str]] | None = None) -> dict[str, Any]:
    bans = bans if bans is not None else load_ban_sets()
    ids = annotate_pair_ids(ask, chosen)
    reasons: list[str] = []
    if ids["pair_hash"] in bans["pair"]:
        reasons.append("pair_hash")
    if ids["ask_hash"] in bans["ask"]:
        reasons.append("ask_hash")
    if ids["ask_cluster_hash"] in bans["cluster"]:
        reasons.append("ask_cluster_hash")
    return {"banned": bool(reasons), "reasons": reasons, **ids}


def parse_sft_text(text: str) -> tuple[str, str]:
    """Split 'Architect: …\\nViv: …' SFT row into ask/chosen."""
    raw = str(text or "")
    if "\nViv:" in raw:
        left, right = raw.split("\nViv:", 1)
        ask = left.replace("Architect:", "", 1).strip() if left.startswith("Architect:") else left.strip()
        return ask, right.strip()
    if raw.startswith("Architect:"):
        return raw[len("Architect:") :].strip(), ""
    return raw.strip(), ""


def is_banned_sft_row(row: dict[str, Any], bans: dict[str, set[str]] | None = None) -> dict[str, Any]:
    bans = bans if bans is not None else load_ban_sets()
    ask = str(row.get("ask") or "")
    chosen = str(row.get("chosen") or row.get("draft") or "")
    if not ask and row.get("text"):
        ask, chosen = parse_sft_text(str(row.get("text") or ""))
    return is_banned_pair(ask, chosen, bans)


def filter_sft_rows(
    rows: Iterable[dict[str, Any]],
    *,
    bans: dict[str, set[str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bans = bans if bans is not None else load_ban_sets()
    kept: list[dict[str, Any]] = []
    dropped = 0
    by_reason: dict[str, int] = {}
    for row in rows:
        hit = is_banned_sft_row(row, bans)
        if hit.get("banned"):
            dropped += 1
            for r in hit.get("reasons") or []:
                by_reason[r] = by_reason.get(r, 0) + 1
            continue
        # stamp ids on kept train rows for audit
        ids = annotate_pair_ids(
            str(row.get("ask") or parse_sft_text(str(row.get("text") or ""))[0]),
            str(row.get("chosen") or row.get("draft") or parse_sft_text(str(row.get("text") or ""))[1]),
        )
        out = dict(row)
        out.update(ids)
        kept.append(out)
    return kept, {
        "kept": len(kept),
        "dropped_holdout_overlap": dropped,
        "drop_reasons": by_reason,
        "ban_sizes": {k: len(v) for k, v in bans.items()},
    }


def freeze_holdout_registry_from_pack(
    *,
    pack_path: Path | None = None,
    force: bool = False,
    note: str = "p0_disjoint_freeze",
) -> dict[str, Any]:
    """Attach hashes to holdout pack + write permanent registry. Refuses overwrite unless force."""
    pack_path = Path(pack_path) if pack_path else HOLDOUT_PACK_PATH
    reg = load_registry()
    if reg.get("frozen") and not force:
        return {
            "ok": True,
            "created": False,
            "frozen": True,
            "pack_id": reg.get("pack_id"),
            "path": str(HOLDOUT_REGISTRY_PATH).replace("\\", "/"),
            "note": "already_frozen",
        }
    if not pack_path.is_file():
        return {"ok": False, "error": "holdout_pack_missing", "path": str(pack_path)}

    # Archive prior pack once when (re)freezing
    HOLDOUT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = HOLDOUT_ARCHIVE_DIR / f"holdout_pack_{stamp}.jsonl"
    shutil.copy2(pack_path, archive)

    rows_out: list[dict[str, Any]] = []
    pair_hashes: list[str] = []
    ask_hashes: list[str] = []
    cluster_hashes: list[str] = []
    for ln in pack_path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        row = json.loads(ln)
        ask = str(row.get("ask") or "")
        chosen = str(row.get("draft") or row.get("chosen") or "")
        ids = annotate_pair_ids(ask, chosen)
        row.update(ids)
        rows_out.append(row)
        pair_hashes.append(ids["pair_hash"])
        ask_hashes.append(ids["ask_hash"])
        cluster_hashes.append(ids["ask_cluster_hash"])

    pack_id = _sha16("|".join(sorted(pair_hashes)))
    with pack_path.open("w", encoding="utf-8") as fh:
        for row in rows_out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # unique preserve order
    def _uniq(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    pair_u, ask_u, cl_u = _uniq(pair_hashes), _uniq(ask_hashes), _uniq(cluster_hashes)
    new_reg = {
        "version": 1,
        "frozen": True,
        "frozen_at": _utc(),
        "pack_id": pack_id,
        "n": len(rows_out),
        "pair_hashes": pair_u,
        "ask_hashes": ask_u,
        "ask_cluster_hashes": cl_u,
        "pack_path": str(pack_path).replace("\\", "/"),
        "archive_path": str(archive).replace("\\", "/"),
        "note": note,
        "contract": (
            "Permanent disjoint split. Never train on pair_hash, ask_hash, or "
            "ask_cluster_hash listed here. Regen requires force=True + archive."
        ),
    }
    save_registry(new_reg)
    HOLDOUT_BAN_PATH.write_text(
        json.dumps(
            {
                "at": _utc(),
                "pack_id": pack_id,
                "pair_hashes": pair_u,
                "ask_hashes": ask_u,
                "ask_cluster_hashes": cl_u,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "created": True,
        "frozen": True,
        "pack_id": pack_id,
        "n": len(rows_out),
        "n_pair": len(pair_u),
        "n_ask": len(ask_u),
        "n_cluster": len(cl_u),
        "registry": str(HOLDOUT_REGISTRY_PATH).replace("\\", "/"),
        "archive": str(archive).replace("\\", "/"),
    }


def assert_train_holdout_disjoint(
    train_path: Path | str,
    *,
    max_report: int = 12,
) -> dict[str, Any]:
    """Fail if any training row overlaps holdout pair/ask/cluster hashes."""
    path = Path(train_path)
    bans = load_ban_sets()
    if not bans["pair"] and not bans["ask"] and not bans["cluster"]:
        return {
            "ok": False,
            "error": "holdout_ban_set_empty",
            "pass": False,
            "note": "Freeze holdout registry before train/validate.",
        }
    if not path.is_file():
        return {"ok": False, "error": "train_file_missing", "path": str(path), "pass": False}

    overlaps: list[dict[str, Any]] = []
    n = 0
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        n += 1
        hit = is_banned_sft_row(row, bans)
        if hit.get("banned"):
            ask, chosen = parse_sft_text(str(row.get("text") or ""))
            overlaps.append(
                {
                    "pair_hash": hit.get("pair_hash"),
                    "ask_hash": hit.get("ask_hash"),
                    "ask_cluster_hash": hit.get("ask_cluster_hash"),
                    "reasons": hit.get("reasons"),
                    "ask": (ask or str(row.get("ask") or ""))[:120],
                }
            )

    ok = len(overlaps) == 0
    return {
        "ok": ok,
        "pass": ok,
        "n_train_rows": n,
        "n_overlap": len(overlaps),
        "overlaps": overlaps[:max_report],
        "pack_id": load_registry().get("pack_id"),
        "ban_sizes": {k: len(v) for k, v in bans.items()},
        "train_path": str(path).replace("\\", "/"),
        "error": None if ok else "holdout_train_overlap",
    }


def rebuild_sft_excluding_holdout(
    *,
    sft_path: Path | str,
    backup: bool = True,
) -> dict[str, Any]:
    path = Path(sft_path)
    if not path.is_file():
        return {"ok": False, "error": "sft_missing", "path": str(path)}
    rows: list[dict[str, Any]] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    before = len(rows)
    kept, stats = filter_sft_rows(rows)
    backup_path = None
    if backup:
        backup_path = path.with_suffix(path.suffix + f".pre_disjoint_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak")
        shutil.copy2(path, backup_path)
    with path.open("w", encoding="utf-8") as fh:
        for row in kept:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    # verify
    check = assert_train_holdout_disjoint(path)
    return {
        "ok": bool(check.get("pass")),
        "before": before,
        "after": len(kept),
        "backup": str(backup_path).replace("\\", "/") if backup_path else None,
        "filter": stats,
        "disjoint_check": check,
        "path": str(path).replace("\\", "/"),
    }
