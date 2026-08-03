#!/usr/bin/env python3
"""Build registry health evidence + emit production validation report.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_registry_health_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_policy import policy_stamp  # noqa: E402
from lib.rid_electrical_registry_health import (  # noqa: E402
    evaluate_registry_health,
    load_health_rows,
    materialize_health_evidence_from_live_shadow,
    write_health_report,
)


def main() -> int:
    mat = materialize_health_evidence_from_live_shadow()
    if not mat.get("ok"):
        print(json.dumps(mat, indent=2))
        return 1
    rows = load_health_rows()
    result = evaluate_registry_health(rows)
    result["policy"] = policy_stamp()
    result["evidence_materialize"] = mat
    paths = write_health_report(result)
    result["artifacts"] = paths
    print(json.dumps({
        "status": result.get("status"),
        "all_gates_pass": result.get("all_gates_pass"),
        "n_actions": result.get("n_actions"),
        "selection_counts": result.get("selection_counts"),
        "gates": {
            k: {"pass": v.get("pass"), "n": v.get("n"), "median_eps": v.get("median_eps"),
                "rate": v.get("rate"), "n_leaks": v.get("n_leaks")}
            for k, v in (result.get("gates") or {}).items()
        },
        "artifacts": paths,
    }, indent=2))
    return 0 if result.get("all_gates_pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
