"""Build a verified-only, training-closed decision simulation campaign.

The campaign is a provenance-bound artifact for later review. It never opens a
lease, loads a model, trains, promotes, deploys, or mutates live state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.aios_decision_simulator import build_scenarios  # noqa: E402


DEFAULT_INPUTS = [
    FOUNDATION / "artifacts/auto/knowledge/decision_simulation_ollama_v12_20260803T083800Z.json",
    FOUNDATION / "artifacts/auto/knowledge/decision_simulation_ollama_v13_20260803T083900Z.json",
]
DEFAULT_OUT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/decision_simulation_policy_campaign_v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", type=Path, dest="inputs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    inputs = args.inputs or DEFAULT_INPUTS
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")

    rows: list[dict[str, object]] = []
    source_files: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for source in inputs:
        if not source.is_file():
            raise FileNotFoundError(source)
        report = json.loads(source.read_text(encoding="utf-8"))
        if report.get("status") != "PASS":
            raise ValueError(f"source_not_pass:{source.name}")
        if report.get("training_authorized") or report.get("run_authorized") or report.get("live_mutation"):
            raise ValueError(f"source_authority_open:{source.name}")
        if not report.get("cpu_verifier_owns_reward"):
            raise ValueError(f"source_not_cpu_verified:{source.name}")
        scenarios = {s.scenario_id: s for s in build_scenarios(int(report["episodes"]), seed=int(report["seed"]))}
        events = {str(event["scenario_id"]): event for event in report["policy_events"]}
        for receipt in report["receipts"]:
            scenario_id = str(receipt["scenario_id"])
            if scenario_id in seen_ids:
                raise ValueError(f"scenario_overlap:{scenario_id}")
            seen_ids.add(scenario_id)
            if receipt["verdict"] not in {"VERIFIED_PROGRESS", "VERIFIED_CHOICE_RECOVERY"}:
                raise ValueError(f"unverified_receipt:{scenario_id}")
            scenario = scenarios[scenario_id]
            event = events[scenario_id]
            rows.append({
                "row_id": f"decision-sim-{scenario_id}",
                "scenario_id": scenario_id,
                "split": "simulation_verified",
                "input": scenario.public_packet(),
                "target": {
                    "mode": receipt["mode"],
                    "choice_id": receipt["choice_id"],
                    "answer": event["answer"],
                },
                "source_receipt": {
                    "source_file": source.name,
                    "receipt_verdict": receipt["verdict"],
                    "verified_progress": receipt["verified_progress"],
                    "verified_recovery": receipt["verified_recovery"],
                },
                "optimizer_eligible": False,
                "training_authorized": False,
                "run_authorized": False,
            })
        source_files.append({"path": str(source).replace("\\", "/"), "sha256": sha(source), "episodes": report["episodes"]})

    args.output.mkdir(parents=True)
    dataset = args.output / "simulation_verified_144.jsonl"
    dataset.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "aios_decision_simulation_campaign_manifest_v1",
        "campaign_id": "decision_simulation_policy_campaign_v1",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "SIMULATION_CAMPAIGN_CLOSED",
        "rows": len(rows),
        "source_files": source_files,
        "dataset": {"path": dataset.name, "sha256": sha(dataset), "rows": len(rows)},
        "disjoint_scenario_ids": len(seen_ids) == len(rows),
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "model_loaded": False,
        "live_mutation": False,
        "next_action": "Review the closed simulation campaign and its disjoint provenance; do not train until a separate named authorization exists.",
    }
    (args.output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (args.output / "README.md").write_text("# Decision simulation policy campaign v1\n\nThis is a closed, CPU-verified simulation artifact. It contains only episodes whose model answer and selected mode were independently verified. It is not optimizer-eligible and does not authorize training, leasing, promotion, deployment, or live mutation.\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": manifest["status"], "rows": len(rows), "disjoint_scenario_ids": manifest["disjoint_scenario_ids"], "optimizer_eligible_any": False, "training_authorized": False, "run_authorized": False, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
