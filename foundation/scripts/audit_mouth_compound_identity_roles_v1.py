#!/usr/bin/env python3
"""Audit compound AIOS identity labels without treating them as self-discovery.

The audit is descriptive only.  It records the generated text, prompt, axis,
checkpoint, and verdict, then applies deliberately conservative suffix labels.
It never changes evaluator verdicts, training data, adapters, or deployment.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = (
    ROOT
    / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4"
    / "campaigns/mouth_recovery_staged_identity_ledger_v1_1"
)
OUT = LEDGER / "COMPOUND_IDENTITY_ROLE_AUDIT_V1.json"
COMPOUND = re.compile(r"\bAIOS[a-z][a-z0-9]*\b", re.I)


def role_hypothesis(token: str) -> str:
    suffix = token.casefold()[4:]
    if suffix == "sketcher":
        return "role_candidate_drafting_or_prototyping"
    if suffix == "skynet":
        return "borrowed_cultural_name_candidate"
    return "unclassified_compound_identity"


def iter_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(LEDGER.glob("checkpoint_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = payload.get("result") or payload
        for row in result.get("results", result.get("cases", [])):
            text = str(row.get("generated") or row.get("text") or "")
            for match in COMPOUND.finditer(text):
                records.append(
                    {
                        "token": match.group(0),
                        "hypothesis": role_hypothesis(match.group(0)),
                        "source": path.name,
                        "step": row.get("step") or payload.get("step"),
                        "case_id": row.get("case_id"),
                        "ask": row.get("ask") or row.get("prompt"),
                        "axis": row.get("axis"),
                        "status": row.get("status"),
                        "reason": row.get("reason"),
                        "generated": text,
                    }
                )
    return records


def main() -> int:
    records = iter_records()
    sketcher = [r for r in records if r["token"].casefold() == "aiossketcher"]
    report = {
        "schema_version": "compound_identity_role_audit_v1",
        "source": str(LEDGER).replace("\\", "/"),
        "observed_compound_count": len(records),
        "token_counts": dict(Counter(r["token"] for r in records)),
        "hypothesis_counts": dict(Counter(r["hypothesis"] for r in records)),
        "aios_sketcher": {
            "observed": bool(sketcher),
            "occurrence_count": len(sketcher),
            "interpretation": (
                "candidate_requires_repeated_independent_contexts"
                if sketcher
                else "not_observed_in_preserved_generated_checkpoints"
            ),
            "records": sketcher,
        },
        "records": records,
        "limits": [
            "A suffix is a hypothesis label, not evidence of stable identity.",
            "A role interpretation requires repeated independent prompts and consistent behavior.",
            "No training, evaluator verdict, adapter, or deployment state is changed.",
        ],
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output": str(OUT).replace("\\", "/"),
        "observed_compound_count": len(records),
        "token_counts": report["token_counts"],
        "aios_sketcher": report["aios_sketcher"],
        "training_changed": False,
        "deployment_changed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
