"""Focused tests for privacy consent, retention, transparency, and data plans."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.privacy_core import authorize_learning, module_status, normalize_settings, plan_data_action, plan_mode_change, plan_retention, transparency_report


def test_default_and_consented_modes_fail_closed() -> None:
    default = normalize_settings()
    assert default["mode"] == "semi-auto"
    assert default["consent"]["full_auto_enabled"] is False
    full = normalize_settings({"mode": "full-auto", "learning": {"behavior_tracking": True}, "consent": {"full_auto_enabled": True, "user_acknowledged": True}})
    assert full["mode"] == "full-auto"
    assert authorize_learning("behavior", full)["allowed"] is True
    assert authorize_learning("behavior", default)["allowed"] is False


def test_mode_change_and_retention_are_plans_only() -> None:
    denied = plan_mode_change({}, "full-auto", explicit_consent=False)
    allowed = plan_mode_change({"consent": {"full_auto_enabled": True, "user_acknowledged": True}}, "full-auto", explicit_consent=True)
    retention = plan_retention({}, category="conversations", max_age_days=5000, automatic_cleanup=True)
    assert denied["state"] == "DENIED"
    assert allowed["state"] == "PROPOSED"
    assert allowed["applied"] is False
    assert retention["max_age_days"] == 3650
    assert retention["delete_performed"] is False


def test_transparency_and_data_actions_do_not_return_raw_content_or_execute() -> None:
    report = transparency_report([{"category": "conversation", "source_kind": "explicit_user_input", "content": "secret"}])
    export = plan_data_action("export", "conversation")
    delete = plan_data_action("delete_all", "all", confirmation="DELETE")
    assert report["categories"] == {"conversation": 1}
    assert report["raw_content_returned"] is False
    assert export["executed"] is False
    assert delete["executed"] is False


def test_unknown_actions_and_sources_fail_closed() -> None:
    assert plan_retention({}, category="unknown")["state"] == "DENIED"
    assert plan_data_action("delete_all", "all", confirmation="delete")["state"] == "DENIED"
    assert authorize_learning("unknown")["allowed"] is False


def test_no_forbidden_effects_or_model_imports() -> None:
    tree = ast.parse((ROOT / "lib" / "privacy_core.py").read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "torch", "numpy", "pathlib", "urllib"}
    assert all(not isinstance(node, ast.ImportFrom) or node.module not in forbidden for node in ast.walk(tree))
    assert all(not isinstance(node, ast.Import) or all(alias.name not in forbidden for alias in node.names) for node in ast.walk(tree))


def test_module_status() -> None:
    result = module_status()
    assert result["ok"] is True
    assert result["fail_closed"] is True
    assert result["full_auto_requires_explicit_consent"] is True
