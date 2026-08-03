#!/usr/bin/env python3
"""Create a reproducible failure taxonomy from an adapter validation report.

This is a diagnostic report only: it never changes scores, criteria, training
data, or deployment state. The output is written to the audit artifacts and
the operator journal so failure analysis remains visible and rerunnable.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def classify(row: dict) -> str:
    label = str(row.get("label") or "OTHER").upper()
    vidi = int(row.get("vidi") or 0)
    intellexi = int(row.get("intellexi") or 0)
    ask = str(row.get("ask") or "").lower()
    draft = str(row.get("draft") or "").lower()
    if label == "HANG":
        return "generation_hang"
    if vidi == 0 and intellexi == 0:
        return "both_axes_failed"
    if vidi == 0:
        return "verification_or_theater"
    if intellexi == 0:
        if "self-ingest" in ask or "verified facts" in ask:
            return "ingest_understanding"
        if any(token in draft for token in ("careful", "quiet", "being honest")):
            return "repetition_or_theater"
        return "understanding_or_overlap"
    return "other_non_admit"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = args.input.resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    deploy = data.get("deploy_test") or {}
    rows = list(deploy.get("failures") or [])
    if not rows:
        rows = [row for row in (deploy.get("samples") or []) if not bool(row.get("mind_pass"))]
    failures = [row for row in rows if not bool(row.get("mind_pass"))]
    categories = Counter(classify(row) for row in failures)
    report = {
        "ok": True,
        "at": utc(),
        "source": str(source).replace("\\", "/"),
        "pack_id": deploy.get("pack_id"),
        "n_reported_samples": len(rows),
        "n_failures_reported": len(failures),
        "complete_failure_list": bool(deploy.get("failures") is not None),
        "n_total_cases": deploy.get("n"),
        "categories": dict(sorted(categories.items())),
        "failures": [
            {
                "index": row.get("case_index"),
                "ask": str(row.get("ask") or "")[:240],
                "draft": str(row.get("draft") or "")[:500],
                "label": row.get("label"),
                "vidi": row.get("vidi"),
                "intellexi": row.get("intellexi"),
                "overlap": row.get("overlap"),
                "category": classify(row),
            }
            for row in failures
        ],
        "note": "Heuristic taxonomy for engineering triage; does not alter judge scores or deployment.",
    }
    output = args.output or source.with_name("failure_taxonomy.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # validation artifact lives under foundation/artifacts/auto/...;
    # parents[4] is the foundation root.
    journal = source.parents[4] / "artifacts" / "audit" / "session_journal.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n- [{report['at']}] Validation failure taxonomy: pack={report.get('pack_id')} "
            f"failures={len(failures)} categories={dict(categories)} report={output.as_posix()}\n"
        )
    print(json.dumps({"ok": True, "report": str(output), "categories": dict(categories)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
