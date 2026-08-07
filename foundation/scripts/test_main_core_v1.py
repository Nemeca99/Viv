"""Regression tests for the read-only deterministic main-core planner."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.main_core import (  # noqa: E402
    discover_core_catalog,
    health_snapshot,
    lifecycle_plan,
    module_status,
    plan_route,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        alpha = root / "alpha_core"
        alpha.mkdir()
        (alpha / "__init__.py").write_text("def handle_command(args):\n    return True\n", encoding="utf-8")
        (alpha / "alpha_core.py").write_text("# no execution during discovery\n", encoding="utf-8")
        beta = root / "beta_core"
        beta.mkdir()
        (beta / "__init__.py").write_text("# discovered but no handler declaration\n", encoding="utf-8")
        broken = root / "broken_core"
        broken.mkdir()

        catalog = discover_core_catalog(root, excluded=("archive_core",))
        assert catalog["ok"] is True, catalog
        assert [row["core_id"] for row in catalog["cores"]] == ["alpha_core", "beta_core", "broken_core"], catalog
        assert catalog["counts"] == {"discovered": 1, "incomplete": 2, "total": 3}, catalog
        assert catalog["imports_performed"] is False and catalog["execution_performed"] is False, catalog

        explicit = plan_route(["--alpha", "--status"], catalog, priority_cores=("beta_core",))
        assert explicit["state"] == "PLANNED" and explicit["selected_core"] == "alpha_core", explicit
        assert explicit["handler_invoked"] is False and explicit["execution_performed"] is False, explicit
        priority = plan_route(["--status"], catalog, priority_cores=("beta_core",))
        assert priority["selected_core"] == "beta_core", priority
        conflict = plan_route(["--alpha", "--beta"], catalog)
        assert conflict["state"] == "ABSTAIN" and conflict["reason"] == "multiple_explicit_core_targets", conflict

    healthy = health_snapshot({"alpha_core": True, "beta_core": {"state": "PASS"}}, minimum_required=("alpha_core",))
    assert healthy["state"] == "HEALTHY" and healthy["ok"] is True, healthy
    degraded = health_snapshot({"alpha_core": True, "beta_core": False}, minimum_required=("alpha_core",))
    assert degraded["state"] == "DEGRADED" and degraded["automatic_recovery"] is False, degraded
    unhealthy = health_snapshot({"alpha_core": False}, minimum_required=("alpha_core", "beta_core"))
    assert unhealthy["state"] == "UNHEALTHY" and "beta_core" in unhealthy["missing_required"], unhealthy

    boot = lifecycle_plan("boot")
    shutdown = lifecycle_plan("shutdown", save_state_on_shutdown=False)
    unknown = lifecycle_plan("hibernate")
    assert boot["steps"][0] == "parse_arguments" and boot["execution_performed"] is False, boot
    assert "skip_state_save" in shutdown["steps"] and shutdown["writes_performed"] is False, shutdown
    assert unknown["state"] == "ABSTAIN", unknown
    assert module_status()["llm_authority"] is False

    print(
        json.dumps(
            {
                "ok": True,
                "catalog_counts": catalog["counts"],
                "explicit_route": explicit["selected_core"],
                "priority_route": priority["selected_core"],
                "health": [healthy["state"], degraded["state"], unhealthy["state"]],
                "lifecycle_steps": len(boot["steps"]),
                "execution_performed": False,
                "writes_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
