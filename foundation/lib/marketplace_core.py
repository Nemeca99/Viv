"""Optional, read-only marketplace manifest and trust planner.

The legacy marketplace can browse remote catalogs, install and update plugins,
publish packages, and execute security checks around those effects.  This
slice handles only supplied metadata and source evidence.  It never performs
network access, installation, dependency mutation, publishing, or activation.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

MODULE_ID = "marketplace_core"
VERSION = "v1"
MANUAL_SECTION = "3.13"
MANUAL_SOURCE = "F:/AIOS_Clean/marketplace_core"
MAX_CATALOG = 256
MAX_DEPENDENCIES = 64
MAX_CAPABILITIES = 64
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _clean(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate plugin metadata without resolving paths or URLs."""
    if not isinstance(manifest, Mapping):
        return {"ok": False, "state": "ABSTAIN", "reason": "manifest_not_mapping"}
    name = _clean(manifest.get("name"), 64).casefold()
    version = _clean(manifest.get("version"), 64)
    license_name = _clean(manifest.get("license"), 100)
    capabilities = [str(item).strip().casefold() for item in list(manifest.get("capabilities") or [])[:MAX_CAPABILITIES] if str(item).strip()]
    dependencies = [str(item).strip().casefold() for item in list(manifest.get("dependencies") or [])[:MAX_DEPENDENCIES] if str(item).strip()]
    issues: list[str] = []
    if not _NAME_RE.fullmatch(name):
        issues.append("invalid_name")
    if not version:
        issues.append("missing_version")
    if not license_name:
        issues.append("missing_license")
    if not _clean(manifest.get("description")):
        issues.append("missing_description")
    return {
        "ok": not issues,
        "state": "VERIFIED" if not issues else "ABSTAIN",
        "name": name,
        "version": version,
        "license": license_name,
        "capabilities": capabilities,
        "dependencies": dependencies,
        "issues": issues,
        "manifest_hash": _hash(dict(manifest)),
        "metadata_only": True,
        "network_accessed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "llm_authority": False,
    }


def search_catalog(catalog: Sequence[Mapping[str, Any]], query: str = "", *, capabilities: Iterable[str] = (), price: str | None = None) -> dict[str, Any]:
    """Search a supplied catalog deterministically."""
    needle = _clean(query).casefold()
    wanted = {str(item).strip().casefold() for item in capabilities if str(item).strip()}
    target_price = _clean(price).casefold() if price is not None else None
    matches: list[dict[str, Any]] = []
    rejected = 0
    for manifest in list(catalog)[:MAX_CATALOG]:
        checked = validate_manifest(manifest)
        if not checked.get("ok"):
            rejected += 1
            continue
        haystack = " ".join((checked["name"], _clean(manifest.get("display_name")), _clean(manifest.get("description")), " ".join(checked["capabilities"]))).casefold()
        if needle and needle not in haystack:
            continue
        if wanted and not wanted.issubset(set(checked["capabilities"])):
            continue
        if target_price is not None and _clean(manifest.get("price")).casefold() != target_price:
            continue
        matches.append({"manifest": checked, "display_name": _clean(manifest.get("display_name")) or checked["name"], "description": _clean(manifest.get("description")), "price": _clean(manifest.get("price")) or "unspecified"})
    return {"ok": True, "state": "VERIFIED", "query": needle, "matches": matches, "rejected_manifests": rejected, "network_accessed": False, "writes_performed": False, "llm_authority": False}


def check_dependencies(manifest: Mapping[str, Any], installed: Iterable[str]) -> dict[str, Any]:
    checked = validate_manifest(manifest)
    installed_set = {str(item).strip().casefold() for item in installed if str(item).strip()}
    missing = [name for name in checked.get("dependencies", []) if name not in installed_set]
    return {"ok": bool(checked.get("ok")), "state": "VERIFIED" if checked.get("ok") else "ABSTAIN", "manifest": checked, "installed_count": len(installed_set), "missing": missing, "dependencies_satisfied": not missing and bool(checked.get("ok")), "installation_performed": False, "writes_performed": False, "llm_authority": False}


def assess_trust(manifest: Mapping[str, Any], *, source_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Assess supplied metadata conservatively; absence of evidence is HOLD."""
    checked = validate_manifest(manifest)
    evidence = dict(source_evidence or {})
    issues = list(checked.get("issues") or [])
    capabilities = set(checked.get("capabilities") or [])
    if not evidence.get("source_hash"):
        issues.append("source_hash_missing")
    if not evidence.get("signature_verified"):
        issues.append("signature_not_verified")
    risky = sorted(capabilities.intersection({"network", "filesystem_write", "execute", "install", "external_effect"}))
    if risky:
        issues.append("effectful_capabilities:" + ",".join(risky))
    if not checked.get("ok"):
        state = "ABSTAIN"
    elif risky or not evidence.get("source_hash") or not evidence.get("signature_verified"):
        state = "HOLD"
    else:
        state = "REVIEW_REQUIRED"
    return {"ok": bool(checked.get("ok")), "state": state, "manifest": checked, "issues": sorted(set(issues)), "metadata_only": True, "safe_to_install": False, "security_scan_complete": False, "network_accessed": False, "writes_performed": False, "llm_authority": False}


def plan_install(manifest: Mapping[str, Any], installed: Iterable[str] = (), *, source_evidence: Mapping[str, Any] | None = None, architect_approved: bool = False) -> dict[str, Any]:
    """Return an install handoff; never installs or activates a plugin."""
    checked = validate_manifest(manifest)
    deps = check_dependencies(manifest, installed)
    trust = assess_trust(manifest, source_evidence=source_evidence)
    blocked = not checked.get("ok") or not deps.get("dependencies_satisfied") or trust.get("state") != "REVIEW_REQUIRED" or not architect_approved
    return {"ok": not blocked, "state": "DENIED" if blocked else "PROPOSED", "manifest": checked, "dependencies": deps, "trust": trust, "steps": ["validate_manifest", "check_dependencies", "verify_source_and_signature", "architect_review", "install_and_activate"], "install_authorized": False, "architect_approved": bool(architect_approved), "applied": False, "network_accessed": False, "writes_performed": False, "llm_authority": False}


def module_status() -> dict[str, Any]:
    return {"ok": True, "state": "READY_OPTIONAL", "module": MODULE_ID, "version": VERSION, "manual_section": MANUAL_SECTION, "optional": True, "read_only": True, "network_accessed": False, "installation_authorized": False, "llm_authority": False}
