"""CPU contracts for the pure Stage-1 response-generation lineage."""
from __future__ import annotations

import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from models.Training.code.train_stage1_generation import (  # noqa: E402
    LOCAL_BASE,
    SMOKE_CASES,
    load_and_verify,
    objective_contract,
    select_smoke_rows,
    smoke_pass,
    tokenize_generation,
)


def main() -> int:
    from transformers import AutoTokenizer

    objective = objective_contract()
    assert objective["name"] == "chosen_response_causal_nll"
    assert objective["prompt_labels_masked"] is True
    assert objective["rejected_forward"] is False
    assert objective["pairwise_weight"] == 0.0
    assert objective["hybrid_objective"] is False

    train_rows, development_rows, registry, parity = load_and_verify()
    assert len(train_rows) == 240
    assert len(development_rows) == 48
    assert registry.get("frozen") is True
    assert parity.get("next_action") == "proceed_to_stage1_generation_v1"

    tokenizer = AutoTokenizer.from_pretrained(
        str(LOCAL_BASE), trust_remote_code=True
    )
    encoded = tokenize_generation(tokenizer, train_rows[0])
    assert set(encoded) == {
        "pair_id",
        "input_ids",
        "labels",
        "prompt_tokens",
        "response_tokens",
    }
    assert encoded["response_tokens"] > 0
    assert all(
        label == -100
        for label in encoded["labels"][: encoded["prompt_tokens"]]
    )
    assert all(
        label != -100
        for label in encoded["labels"][encoded["prompt_tokens"] :]
    )

    selected = select_smoke_rows(development_rows)
    assert len(selected) == SMOKE_CASES
    assert len({row["pair_id"] for row in selected}) == SMOKE_CASES

    passing_rows = [
        {
            "case_id": f"case-{index}",
            "request_ingress_passed": True,
            "text": "I can state the verified fact without inventing another.",
            "valid_speech": True,
            "repetition_collapse": False,
            "numeric_prefix": False,
            "error": None,
        }
        for index in range(SMOKE_CASES)
    ]
    passed, failures = smoke_pass({"ok": True, "rows": passing_rows})
    assert passed and failures == []
    failing_rows = [dict(row) for row in passing_rows]
    failing_rows[0]["text"] = ""
    failing_rows[0]["valid_speech"] = False
    passed, failures = smoke_pass({"ok": True, "rows": failing_rows})
    assert not passed
    assert any(value.endswith(":empty") for value in failures)
    assert any(value.endswith(":invalid_speech") for value in failures)

    source_path = (
        FOUNDATION
        / "models"
        / "Training"
        / "code"
        / "train_stage1_generation.py"
    )
    source = source_path.read_text(encoding="utf-8")
    forbidden = (
        "objective_values(",
        "detached_gradient_coefficients(",
        'item["rejected_ids"]',
        'item["rejected_labels"]',
    )
    for marker in forbidden:
        assert marker not in source, marker
    assert source.count(".backward()") == 1
    assert "deployment_changed" in source
    assert "auto_deploy" in source

    print(
        json.dumps(
            {
                "ok": True,
                "lineage": "stage1_generation_v1",
                "train_rows": len(train_rows),
                "development_rows": len(development_rows),
                "response_only_masking": True,
                "preference_forward_absent": True,
                "smoke_gate_contract": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
