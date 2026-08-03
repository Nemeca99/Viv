"""CPU-only contracts for mouth-identity judging and registry freezing."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.cpu_semantic_judge import SENSOR_VERSION, SensorConfig  # noqa: E402
from scripts.stage1_mouth_identity_curriculum import build_rows  # noqa: E402
from scripts.stage1_mouth_identity_judge import (  # noqa: E402
    AUTHORITY,
    DRAFT,
    FALLBACK_DOMAINS,
    JUDGE_CONTRACT_VERSION,
    _judge_order,
    calibration_pack_payload,
    calibration_rows,
    has_current_decision,
    judge_row,
    read_jsonl,
    validate_judged_rows,
)


def good_observer(
    row: dict[str, object],
    *,
    cache_dir: Path,
    config: SensorConfig,
    cache_context: dict[str, object],
) -> dict[str, object]:
    assert config.num_gpu == 0
    assert cache_context["contract_id"] == "0" * 24
    return {
        "sensor_version": SENSOR_VERSION,
        "cache_key": f"good-{row['node_id']}",
        "cache_hit": False,
        "observations": [
            {"candidate_a": "PASS", "candidate_b": "FAIL"},
            {"candidate_a": "PASS", "candidate_b": "FAIL"},
        ],
        "categorical_agreement": True,
        "cpu_only": True,
        "status": "OBSERVED",
        "warnings": [],
        "errors": [],
    }


def hold_observer(
    row: dict[str, object],
    *,
    cache_dir: Path,
    config: SensorConfig,
    cache_context: dict[str, object],
) -> dict[str, object]:
    return {
        "sensor_version": SENSOR_VERSION,
        "cache_key": f"hold-{row['node_id']}",
        "cache_hit": False,
        "observations": [
            {"candidate_a": "FAIL", "candidate_b": "FAIL"},
            {"candidate_a": "FAIL", "candidate_b": "FAIL"},
        ],
        "categorical_agreement": True,
        "cpu_only": True,
        "status": "OBSERVED",
        "warnings": [],
        "errors": [],
    }


def main() -> int:
    # Validate the immutable on-disk draft consumed by the judge.  The source
    # builder is exercised separately; rebuilding here can legitimately differ
    # after a corpus revision while the canonical draft remains frozen.
    rows = read_jsonl(DRAFT)
    offline_contract = {
        "contract_id": "0" * 24,
        "binding": {
            "lineage": {"draft_sha256": "offline-test"},
            "sensor_model": {"fingerprint_sha256": "offline-test"},
            "sensor_config_sha256": "offline-test",
            "security_core": {"version": "offline-test"},
        },
    }
    offline_calibration = {
        "status": "cpu_judge_calibration_passed",
    }
    calibration_digest = "offline-test-calibration"
    calibration = calibration_rows(rows)
    assert len(calibration) == 8
    assert len({row["domain"] for row in calibration}) == 8
    assert all(row["split"] == "development" for row in calibration)
    pack = calibration_pack_payload(rows)
    assert pack["case_count"] == 16
    assert len(pack["domains"]) == 8
    assert {
        case["orientation"] for case in pack["cases"]
    } == {"forward", "reverse"}
    for domain in {row["domain"] for row in rows}:
        domain_rows = [row for row in rows if row["domain"] == domain]
        assert {
            row["negative_drafts"].index(row["rejected"])
            for row in domain_rows
        } == {0, 1, 2}

    first_train, train_audit = judge_row(
        rows[0],
        observer=good_observer,
    )
    assert first_train["admission_status"] == "TRAIN_READY"
    assert first_train["train_ready"] is True
    assert first_train["judge_agreement"] is True
    assert first_train["judge"]["selected_negative_index"] in {0, 1, 2}
    assert first_train["judge"]["comparison"]["admitted"] is True
    assert has_current_decision(first_train)
    assert train_audit["final_admission_status"] == "TRAIN_READY"

    development, _ = judge_row(
        calibration[0],
        observer=good_observer,
    )
    assert development["admission_status"] == "EVALUATION_READY"
    assert development["train_ready"] is False

    # The current curriculum intentionally places all production domains under
    # deterministic fallback.  Exercise the strict HOLD path with an explicit
    # synthetic probe rather than relying on a domain that no longer exists.
    strict_hold_row = deepcopy(rows[0])
    strict_hold_row["domain"] = "strict_hold_probe"
    # Remove the deterministic PASS/FAIL contrast so the control-room sensor
    # must abstain and the row is admitted only as HOLD.  This keeps the test
    # tied to the actual fail-closed path rather than to a custom observer
    # callback, which the production path intentionally does not trust.
    strict_hold_row["required_concepts"] = [["__missing_concept__"]]
    held, _ = judge_row(strict_hold_row, observer=hold_observer)
    assert held["admission_status"] == "HOLD"
    assert held["train_ready"] is False
    assert held["judge_agreement"] is False

    judged = []
    for row in rows:
        accepted, _ = judge_row(row, observer=good_observer)
        judged.append(accepted)
    validation = validate_judged_rows(
        judged,
        contract=offline_contract,
        calibration=offline_calibration,
        calibration_sha256=calibration_digest,
    )
    assert validation["ok"], validation["errors"]
    assert validation["admitted"] == 96
    assert validation["train_ready"] == 64
    assert validation["evaluation_ready"] == 32

    corrupted = deepcopy(judged)
    corrupted[0]["chosen"] = "I am an altered row."
    bad = validate_judged_rows(
        corrupted,
        contract=offline_contract,
        calibration=offline_calibration,
        calibration_sha256=calibration_digest,
    )
    assert not bad["ok"]
    assert any("resume_field_drift" in error for error in bad["errors"])

    order = _judge_order(rows)
    assert len(order) == 96
    assert len({rows[index]["domain"] for index in order[:8]}) == 8
    assert AUTHORITY["gpu_training_authorized"] is False
    assert AUTHORITY["live_backend"] == "qwen_gguf"
    assert JUDGE_CONTRACT_VERSION == "stage1_mouth_identity_judge_v1"
    print(
        json.dumps(
            {
                "ok": True,
                "rows": len(rows),
                "calibration_domains": 8,
                "selected_comparisons_per_row": 1,
                "calibration_cases": pack["case_count"],
                "train_ready": validation["train_ready"],
                "judge_contract_version": JUDGE_CONTRACT_VERSION,
                "sensor_version": SENSOR_VERSION,
                "gpu_training_authorized": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
