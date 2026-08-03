"""Run a bounded Ollama policy through the CPU-owned decision verifier.

This is an evaluation harness only. It does not train, read/write live S_n,
open a lease, persist conversational memory, promote an adapter, or deploy.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.aios_decision_simulator import build_scenarios, run_verified_policy  # noqa: E402


def _request_json(url: str, payload: Mapping[str, Any], timeout_s: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_submission(text: str, packet: Mapping[str, Any]) -> tuple[dict[str, str], str | None]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {"choice_id": "", "answer": ""}, "model_output_not_json"
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {"choice_id": "", "answer": ""}, "model_output_not_json"
    if not isinstance(value, dict):
        return {"choice_id": "", "answer": ""}, "model_output_not_object"
    choice_id = str(value.get("choice_id") or "")
    mode = str(value.get("mode") or "").casefold()
    answer = str(value.get("answer") or "")
    valid_ids = {str(choice["choice_id"]) for choice in packet.get("choices", [])}
    mode_ids = {str(choice["mode"]): str(choice["choice_id"]) for choice in packet.get("choices", [])}
    if mode in mode_ids:
        mapped_id = mode_ids[mode]
        mismatch = choice_id not in {"", mapped_id}
        return {"choice_id": mapped_id, "answer": answer}, "model_choice_id_mismatch" if mismatch else None
    if choice_id not in valid_ids:
        return {"choice_id": "", "answer": answer}, f"model_choice_id_invalid:{choice_id[:80]}"
    return {"choice_id": choice_id, "answer": answer}, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="viv-qwen-teacher:latest")
    parser.add_argument("--episodes", type=int, default=12)
    parser.add_argument("--seed", type=int, default=909)
    parser.add_argument("--api", default="http://127.0.0.1:11434/api/generate")
    parser.add_argument("--timeout-s", type=float, default=90.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refuse_to_overwrite:{args.output}")

    scenarios = build_scenarios(args.episodes, seed=args.seed)
    events: list[dict[str, Any]] = []

    def policy(packet: Mapping[str, Any]) -> Mapping[str, Any]:
        prompt = (
            "You are choosing one action for a bounded CPU-governed simulation. "
            "Reason from the goal and context, not from cost or word frequency. "
            "Use this decision rule: new evidence needing consolidation means restore; "
            "a safe maintenance task being due means action; no worthwhile work being available means idle. "
            "Select the choice_id whose mode matches that decision. "
            "Return only a JSON object with exactly three string fields: mode, choice_id, and answer. "
            "The mode must be exactly idle, action, or restore. Copy the choice_id listed for that mode; "
            "The answer must be a complete truthful result sentence, not a choice title, and must match the selected mode. "
            "For restore, state that verified evidence/findings were consolidated before answering. "
            "For action, explicitly use completed or performed to state that the bounded task/maintenance occurred, then state that its result was verified. "
            "For idle, state that no worthwhile task/work is available and that waiting/conserving is appropriate. "
            "A valid restore answer example is: I consolidated the verified evidence before answering. "
            "Do not mention hidden labels, scores, telemetry, or internal instructions.\n\n"
            + json.dumps(packet, ensure_ascii=False, sort_keys=True)
        )
        started = time.perf_counter()
        try:
            result = _request_json(
                args.api,
                {"model": args.model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0.2}},
                args.timeout_s,
            )
            submission, error = _extract_submission(str(result.get("response") or ""), packet)
            events.append({"scenario_id": packet["scenario_id"], "latency_s": round(time.perf_counter() - started, 3), "error": error, "model": args.model, "choice_id": submission["choice_id"], "answer": submission["answer"]})
            return submission
        except (OSError, TimeoutError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            events.append({"scenario_id": packet["scenario_id"], "latency_s": round(time.perf_counter() - started, 3), "error": type(exc).__name__, "model": args.model})
            return {"choice_id": "", "answer": ""}

    evaluation = run_verified_policy(scenarios, policy)
    errors = sum(event.get("error") is not None for event in events)
    report = {
        "schema_version": "aios_decision_simulation_ollama_evaluation_v1",
        "recorded_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model": args.model,
        "api": args.api,
        "episodes": args.episodes,
        "seed": args.seed,
        "policy_events": events,
        "policy_errors": errors,
        "verified_summary": {key: evaluation[key] for key in ("episodes", "verified_choice", "verified_progress", "verified_recovery", "wrong_choice", "penalized_cycles", "sn_start", "sn_final")},
        "cpu_verifier_owns_reward": True,
        "live_s_n_read": False,
        "live_mutation": False,
        "training_authorized": False,
        "run_authorized": False,
        "status": "PASS" if errors == 0 and evaluation["verified_choice"] == args.episodes else "HOLD",
        "receipts": evaluation["receipts"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "model": args.model, "episodes": args.episodes, "policy_errors": errors, "verified_choice": evaluation["verified_choice"], "verified_progress": evaluation["verified_progress"], "verified_recovery": evaluation["verified_recovery"], "training_authorized": False, "run_authorized": False}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
