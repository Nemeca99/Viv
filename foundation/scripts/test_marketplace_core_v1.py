"""Focused tests for the optional effect-closed marketplace boundary."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.marketplace_core import assess_trust, check_dependencies, module_status, plan_install, search_catalog, validate_manifest


def _manifest() -> dict[str, object]:
    return {"name": "music_core", "display_name": "Music Core", "description": "Local playback", "version": "1.0.0", "license": "MIT", "capabilities": ["playback"], "dependencies": ["data_core"]}


def test_manifest_and_catalog_search() -> None:
    manifest = _manifest()
    assert validate_manifest(manifest)["ok"] is True
    result = search_catalog([manifest], "music", capabilities=["playback"], price=None)
    assert result["ok"] is True
    assert len(result["matches"]) == 1
    assert result["network_accessed"] is False


def test_dependencies_and_trust_hold_without_evidence() -> None:
    manifest = _manifest()
    deps = check_dependencies(manifest, ["data_core"])
    trust = assess_trust(manifest)
    assert deps["dependencies_satisfied"] is True
    assert trust["state"] == "HOLD"
    assert trust["safe_to_install"] is False


def test_install_is_denied_until_separate_authority_and_evidence() -> None:
    result = plan_install(_manifest(), installed=["data_core"], source_evidence={"source_hash": "abc", "signature_verified": True}, architect_approved=False)
    assert result["state"] == "DENIED"
    assert result["install_authorized"] is False
    assert result["applied"] is False
    assert result["writes_performed"] is False


def test_invalid_manifest_abstains_and_effectful_metadata_holds() -> None:
    assert validate_manifest({"name": "bad name"})["ok"] is False
    risky = {**_manifest(), "name": "network_core", "capabilities": ["network"]}
    assert assess_trust(risky, source_evidence={"source_hash": "abc", "signature_verified": True})["state"] == "HOLD"


def test_no_forbidden_effects_or_model_imports() -> None:
    tree = ast.parse((ROOT / "lib" / "marketplace_core.py").read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "torch", "numpy", "pathlib", "urllib"}
    assert all(not isinstance(node, ast.ImportFrom) or node.module not in forbidden for node in ast.walk(tree))
    assert all(not isinstance(node, ast.Import) or all(alias.name not in forbidden for alias in node.names) for node in ast.walk(tree))


def test_module_status() -> None:
    result = module_status()
    assert result["ok"] is True
    assert result["optional"] is True
    assert result["installation_authorized"] is False
