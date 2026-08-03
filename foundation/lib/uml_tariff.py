"""Read-only UML token tariff registry adapter.

The Guardian tariff documents define normalized risk penalties (0..1) and
explicitly reviewed thesaurus aliases. Processing cost is tracked separately.
This module does not mutate the registry or infer aliases.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS

REGISTRY_PATH = AUTO_ARTIFACTS / "uml_tariff_dictionary.json"


def load_registry(path: Path | None = None) -> dict[str, Any]:
    src = path or REGISTRY_PATH
    if not src.is_file():
        return {"ok": False, "tokens": {}, "thesaurus": {"aliases": {}}}
    data = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("UML tariff registry must be an object")
    data.setdefault("tokens", {})
    data.setdefault("thesaurus", {}).setdefault("aliases", {})
    return data


def lookup(token: str, *, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve a canonical token or explicitly registered alias."""
    reg = registry or load_registry()
    key = str(token or "")
    entries = reg.get("tokens") or {}
    if key in entries:
        return {"token": key, "entry": entries[key], "via": "canonical"}
    aliases = (reg.get("thesaurus") or {}).get("aliases") or {}
    canonical = aliases.get(key)
    if canonical in entries:
        return {"token": canonical, "entry": entries[canonical], "via": "approved_alias", "alias": key}
    return None


def cost(token: str, *, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    hit = lookup(token, registry=registry)
    if hit is None:
        return {"ok": False, "token": str(token or ""), "reason": "unregistered"}
    weights = (hit["entry"].get("weights") or {})
    penalty = float(weights.get("penalty_weight") or 0.0)
    if not 0.0 <= penalty <= 1.0:
        raise ValueError(f"penalty_weight out of range for {hit['token']}: {penalty}")
    return {
        "ok": True,
        "token": hit["token"],
        "via": hit["via"],
        "processing_total": int(weights.get("processing_total") or 0),
        "symbolic_processing": int(weights.get("symbolic_processing") or 0),
        "model_tokens": int(weights.get("model_tokens") or 0),
        "penalty_weight": penalty,
    }


def validate_registry(*, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate schema, penalty bounds, and canonical lookup coverage."""
    reg = registry or load_registry()
    tokens = reg.get("tokens") or {}
    aliases = (reg.get("thesaurus") or {}).get("aliases") or {}
    errors: list[str] = []
    checked = 0
    for token, entry in tokens.items():
        checked += 1
        if not isinstance(entry, dict) or entry.get("uml") != token:
            errors.append(f"canonical_mismatch:{token}")
            continue
        weights = entry.get("weights") or {}
        try:
            penalty = float(weights.get("penalty_weight") or 0.0)
            if not 0.0 <= penalty <= 1.0:
                errors.append(f"penalty_out_of_range:{token}")
            if int(weights.get("processing_total") or 0) < 1:
                errors.append(f"missing_processing_cost:{token}")
        except (TypeError, ValueError):
            errors.append(f"invalid_weights:{token}")
    for alias, canonical in aliases.items():
        if canonical not in tokens:
            errors.append(f"alias_target_missing:{alias}->{canonical}")
    return {
        "ok": not errors,
        "checked_tokens": checked,
        "checked_aliases": len(aliases),
        "errors": errors,
        "registry": str(REGISTRY_PATH).replace("\\", "/"),
    }
