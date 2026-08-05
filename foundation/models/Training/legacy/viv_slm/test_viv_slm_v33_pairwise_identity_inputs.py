#!/usr/bin/env python3
"""Preflight checks for the V33 pairwise identity input lane."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, FOUNDATION / "scripts", VIV_ROOT, VIV_ROOT / "models" / "uml_bigram_part3"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_viv_slm_v33_pairwise_identity_inputs import (  # noqa: E402
    INPUT_SCHEMA_VERSION,
    V32_PROBE_SHA256,
    VOCAB_SHA256,
    build,
    _sha256,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="viv_slm_v33_pairwise_inputs_") as temp_dir:
        manifest = build(output_dir=Path(temp_dir) / "inputs")
        assert manifest["schema_version"] == INPUT_SCHEMA_VERSION
        assert manifest["pair_count"] == 2
        assert manifest["intents"] == ["greeting", "current_state"]
        assert manifest["source_probe_sha256"] == V32_PROBE_SHA256
        assert manifest["vocab_sha256"] == VOCAB_SHA256
        assert manifest["objective"]["rejected_is_sft_target"] is False
        rows = [
            __import__("json").loads(line)
            for line in (Path(temp_dir) / "inputs" / "PAIRWISE_ROWS.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 2
        assert all(row["chosen"] != row["rejected"] for row in rows)
        assert all(row["rejected_is_sft_target"] is False for row in rows)
        assert all(row["training_authorized"] is False and row["run_authorized"] is False for row in rows)
    print(
        "VIV_SLM_V33_PAIRWISE_IDENTITY_INPUTS_PASS "
        "pair_count=2 chosen_source=cpu_authorized rejected_source=v32_observed_failures "
        "rejected_is_sft_target=false world_knowledge=false training_authorized=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
