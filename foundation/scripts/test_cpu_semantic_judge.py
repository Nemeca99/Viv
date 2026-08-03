"""Offline tests for deterministic double observation and fail-closed HOLD."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
from lib import cpu_semantic_judge as sensor_module
from lib.cpu_semantic_judge import (
    SENSOR_VERSION,
    SensorConfig,
    deterministic_admission,
    observe_twice,
)

SEEDS = FOUNDATION / "artifacts" / "auto" / "openaster_training_tree" / "seed_nodes_v2.jsonl"
TEST_CACHE_ROOT = FOUNDATION / "artifacts" / "auto" / "openaster_training_tree" / "contract_tmp"


def main() -> int:
    TEST_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    row = json.loads(next(line for line in SEEDS.read_text(encoding="utf-8").splitlines() if line.strip()))
    good = json.dumps({
        "candidate_a": "PASS", "candidate_b": "FAIL",
    })
    original_gate = sensor_module.gate_record

    def allow_gate(**kwargs):
        return {"allowed": True, "reason": "OK"}

    sensor_module.gate_record = allow_gate
    observe_twice.__globals__["gate_record"] = allow_gate
    try:
        with tempfile.TemporaryDirectory(dir=TEST_CACHE_ROOT) as directory:
            calls = 0

            def matching(payload, timeout):
                nonlocal calls
                calls += 1
                assert payload["options"]["num_gpu"] == 0
                assert payload["options"]["num_thread"] == 4
                assert payload["options"]["temperature"] == 0
                assert payload["options"]["seed"] == 42
                return {"response": good}

            observation = observe_twice(
                row, cache_dir=Path(directory), transport=matching,
                require_runtime_cpu_proof=False,
                cache_context={"contract_id": "contract-a"},
            )
            assert calls >= 2
            assert observation["categorical_agreement"]
            assert deterministic_admission(row, observation)["admitted"]
            cached = observe_twice(
                row, cache_dir=Path(directory), transport=matching,
                require_runtime_cpu_proof=False,
                cache_context={"contract_id": "contract-a"},
            )
            assert cached["cache_hit"] and calls >= 2
            isolated = observe_twice(
                row,
                cache_dir=Path(directory),
                transport=matching,
                require_runtime_cpu_proof=False,
                cache_context={"contract_id": "contract-b"},
            )
            assert not isolated["cache_hit"] and calls >= 4

        with tempfile.TemporaryDirectory(dir=TEST_CACHE_ROOT) as directory:
            reply_calls = 0

        def transient_gate(**kwargs):
            nonlocal reply_calls
            if kwargs["direction"] == "OUT":
                return {"allowed": True, "reason": "OK"}
            reply_calls += 1
            if reply_calls == 1:
                return {
                    "allowed": False,
                    "reason": "security_ingress_denied",
                    "membrane": {"reason": "[LAW 5] Forced dormancy."},
                }
            return {"allowed": True, "reason": "OK"}

            sensor_module.gate_record = transient_gate
            observe_twice.__globals__["gate_record"] = transient_gate
            transient_calls = 0
            try:
                def stable_after_retry(payload, timeout):
                    nonlocal transient_calls
                    transient_calls += 1
                    return {"response": good}

                recovered = observe_twice(
                    row,
                    cache_dir=Path(directory),
                    config=SensorConfig(stability_retry_delay_s=0),
                    transport=stable_after_retry,
                    require_runtime_cpu_proof=False,
                )
            finally:
                sensor_module.gate_record = allow_gate
                observe_twice.__globals__["gate_record"] = allow_gate
            assert recovered["status"] == "OBSERVED"
            assert recovered["attempts"] == 3 and transient_calls == 3
            assert len(recovered["warnings"]) == 1 and not recovered["errors"]

        with tempfile.TemporaryDirectory(dir=TEST_CACHE_ROOT) as directory:
            answers = iter([
            {"response": good},
            {"response": json.dumps({
                "candidate_a": "FAIL", "candidate_b": "FAIL",
            })},
        ])
            mismatched = observe_twice(
                row, cache_dir=Path(directory),
                transport=lambda payload, timeout: next(answers),
                require_runtime_cpu_proof=False,
            )
            assert not mismatched["categorical_agreement"]
            assert deterministic_admission(row, mismatched)["status"] == "HOLD"

        with tempfile.TemporaryDirectory(dir=TEST_CACHE_ROOT) as directory:
            malformed = observe_twice(
                row, cache_dir=Path(directory),
                transport=lambda payload, timeout: {"response": "not json"},
                require_runtime_cpu_proof=False,
                cache_context={"contract_id": "failure-not-reusable"},
            )
            assert malformed["status"] == "HOLD"
            assert malformed["cache_persisted"] is False
            assert not list(Path(directory).glob("*.json"))
            assert deterministic_admission(row, malformed)["status"] == "HOLD"

            recovery_calls = 0

            def recovered_after_malformed(payload, timeout):
                nonlocal recovery_calls
                recovery_calls += 1
                return {"response": good}

            recovered = observe_twice(
                row,
                cache_dir=Path(directory),
                transport=recovered_after_malformed,
                require_runtime_cpu_proof=False,
                cache_context={"contract_id": "failure-not-reusable"},
            )
            assert recovery_calls == 2
            assert recovered["status"] == "OBSERVED"
            assert recovered["cache_persisted"] is True
    finally:
        sensor_module.gate_record = original_gate
        observe_twice.__globals__["gate_record"] = original_gate
    print(json.dumps({
        "ok": True, "double_observation": True, "cache": True,
        "mismatch_holds": True, "malformed_holds": True,
        "cpu_pin_config": SensorConfig().num_gpu,
        "cpu_thread_limit": SensorConfig().num_thread,
        "sensor_version": SENSOR_VERSION,
        "deterministic_axis_authority": True,
        "cache_context_isolation": True,
        "failed_result_cache_exclusion": True,
        "bounded_stability_retries": SensorConfig().stability_retry_attempts,
        "transient_law5_recovered": True,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
