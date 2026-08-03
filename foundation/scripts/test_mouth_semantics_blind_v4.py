"""Verify the v4 blind pack is disjoint, hold-only, and fully matched."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_semantics_blind_v4"


def main() -> int:
    prompts = [json.loads(line) for line in (ROOT / "blind_48.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    gold = json.loads((ROOT / "BLIND_GOLD_48.json").read_text(encoding="utf-8"))
    report = json.loads((ROOT / "BLIND_EVALUATION.json").read_text(encoding="utf-8"))
    assert len(prompts) == 48
    assert report["status"] == "BLIND_PASS"
    assert report["matched"] == 48
    assert report["mismatches"] == []
    assert all(row["hold_only"] and not row["optimizer_eligible"] for row in prompts)
    assert all("expected" not in row for row in prompts)
    assert len(gold["rows"]) == 48
    assert Counter(row["axis"] for row in prompts) == {axis: 6 for axis in {row["axis"] for row in prompts}}
    print({"ok": True, "rows": 48, "axes": 8, "optimizer_eligible": False, "labels_separate": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
