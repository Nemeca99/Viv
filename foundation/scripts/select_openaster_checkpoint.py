#!/usr/bin/env python3
"""Select one full-v3 checkpoint using only the frozen development pack."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
OUT = FOUNDATION / "artifacts" / "auto" / "openaster_stabilization" / "checkpoint_selection_v3.json"


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, action="append", required=True)
    args = parser.parse_args()
    candidates: list[dict[str, Any]] = []
    for path in args.report:
        report = json.loads(path.read_text(encoding="utf-8"))
        summary = (report.get("dev") or {}).get("summary") or {}
        adapter = str(report.get("adapter") or "")
        eligible = (
            int(summary.get("n") or 0) == 36
            and float(summary.get("valid_speech_rate") or 0) >= 0.90
            and int(summary.get("collapse_cases") or 0) == 0
            and int(summary.get("numeric_prefix_cases") or 0) == 0
            and int(summary.get("errors") or 0) == 0
        )
        candidates.append({
            "adapter": adapter, "report": str(path).replace("\\", "/"),
            "eligible": eligible, "summary": summary,
        })
    ranked = sorted(
        candidates,
        key=lambda row: (
            int(row["eligible"]),
            float(row["summary"].get("mind_pass_rate") or 0),
            float(row["summary"].get("valid_speech_rate") or 0),
            -float(row["summary"].get("median_model_tokens") or 10**9),
            -float(row["summary"].get("median_latency_ms") or 10**9),
        ),
        reverse=True,
    )
    winner = ranked[0] if ranked and ranked[0]["eligible"] else None
    result = {
        "version": 1, "at": utc(), "selection_pack": "development_pack_v1",
        "candidates": ranked, "selected": winner,
        "decision": "evaluate_selected_on_deciding_packs" if winner else "stop_no_eligible_checkpoint",
        "deployment_changed": False,
    }
    if OUT.exists():
        raise FileExistsError(f"frozen selection already exists: {OUT}")
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if winner else 2


if __name__ == "__main__":
    raise SystemExit(main())
