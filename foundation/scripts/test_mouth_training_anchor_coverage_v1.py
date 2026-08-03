from __future__ import annotations

import json
import tempfile
from pathlib import Path

import mouth_training_anchor_coverage_v1 as builder


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "campaign"
        result = builder.build(root)
        assert result["coverage"]["train"]["pass"]
        assert result["coverage"]["development"]["pass"]
        assert result["coverage"]["blind"]["pass"]
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "ANCHOR_COVERAGE_READY_TRAINING_CLOSED"
        assert manifest["training_authorized"] is False
        assert manifest["run_authorized"] is False
        assert manifest["gpu_steps"] == 0
        assert len((root / "train_32.jsonl").read_text(encoding="utf-8").splitlines()) == 32
        assert len((root / "development_16.jsonl").read_text(encoding="utf-8").splitlines()) == 16
        assert len((root / "blind_16.jsonl").read_text(encoding="utf-8").splitlines()) == 16
        try:
            builder.build(root)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing output must refuse overwrite")
    print("ok: anchor coverage builder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
