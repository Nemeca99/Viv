"""Evaluate clean-default CPU packet and mouth containment boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from voice_core.intent_packet import build_intent_packet, contains_telemetry_disclosure, packet_to_messages
from voice_core.runtime_contract import finalize_draft


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    {
        "case": "ordinary_grounded_absolute_value",
        "query": "What is the magnitude of a number without regard to its sign?",
        "knowledge_mode": "staged_semantic",
        "raw": "The absolute value is a number's non-negative magnitude, regardless of whether the original number is positive or negative.",
        "must_contain": "absolute value",
    },
    {
        "case": "ordinary_ambiguous_au",
        "query": "What is AU?",
        "knowledge_mode": "multi_source",
        "raw": "AU means the ampere unit.",
        "include_legacy": True,
        "must_contain": "cannot verify",
    },
    {
        "case": "ordinary_telemetry_leak_contained",
        "query": "Explain what an absolute value is.",
        "knowledge_mode": "staged_semantic",
        "raw": "My internal stability is healthy and my dashboard is active.",
        "must_contain": "here with you",
    },
    {
        "case": "explicit_health_ephemeral",
        "query": "What is your health status?",
        "knowledge_mode": "local",
        "mode": "health",
        "raw": "The current health reading is available from the live feed.",
        "must_contain": "health",
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate() -> dict:
    rows = []
    for case in CASES:
        mode = str(case.get("mode") or "converse")
        packet = build_intent_packet(
            query=case["query"],
            knowledge_query=case["query"],
            knowledge_mode=case["knowledge_mode"],
            include_legacy_wikipedia=bool(case.get("include_legacy")),
            resolve_legacy_redirects=True,
            mode=mode,
        )
        messages = packet_to_messages(packet)
        user_wire = "\n".join(row.get("content") or "" for row in messages if row.get("role") == "user")
        finalized = finalize_draft(query=case["query"], packet=packet, raw_text=case["raw"], voice_source="matrix")
        final_text = str(finalized.get("text") or "")
        ordinary = mode != "health"
        user_contained = (
            not contains_telemetry_disclosure(user_wire)
            if ordinary
            else "health" in user_wire.casefold()
        )
        final_contained = not contains_telemetry_disclosure(final_text) if ordinary else True
        expected = str(case["must_contain"]).casefold() in final_text.casefold()
        passed = user_contained and final_contained and expected
        rows.append({
            "case": case["case"],
            "mode": mode,
            "user_telemetry_contained": user_contained,
            "final_telemetry_contained": final_contained,
            "expected_phrase_present": expected,
            "final_text": final_text,
            "voice_source": finalized.get("voice_source"),
            "passed": passed,
        })
    return {
        "schema_version": "clean_default_mouth_matrix_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state": "VERIFIED" if all(row["passed"] for row in rows) else "HOLD",
        "cases": len(rows),
        "passed": sum(1 for row in rows if row["passed"]),
        "authority": {"training_authorized": False, "run_authorized": False, "deployment_changed": False},
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("VIV_EMBED_BACKEND") != "hf_local":
        raise SystemExit("set VIV_EMBED_BACKEND=hf_local")
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["state"] == "VERIFIED", "state": result["state"], "cases": result["cases"], "passed": result["passed"], "output": str(args.output)}, indent=2))
    return 0 if result["state"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
