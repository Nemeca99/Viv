#!/usr/bin/env python3
"""Verify the reusable CPU identity-to-mouth facade on the read-only canary."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for path in (FOUNDATION, VIV_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_identity_mouth import render_identity_query  # noqa: E402
from lib.viv_slm_foundation import VivSLM  # noqa: E402


CHECKPOINT = (
    VIV_ROOT
    / "models"
    / "viv_slm_identity_personality_v7"
    / "runs"
    / "identity_personality_steps_1750"
    / "checkpoint.pt"
)
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v7" / "inputs" / "VOCAB.json"
V8_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v8"


def _rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(V8_ROOT.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("source") == "viv_identity_personality_paraphrase_pack_v8":
                rows.append(row)
    return rows


def main() -> int:
    rows = _rows()
    assert len(rows) == 40
    slm = VivSLM.from_checkpoint(CHECKPOINT, vocab_path=VOCAB, device="cpu")
    fallback_count = 0
    renderer_calls = 0

    def renderer(query: str) -> str:
        nonlocal renderer_calls
        renderer_calls += 1
        return slm.render_query(query)

    for row in rows:
        result = render_identity_query(str(row["prompt"]), renderer)
        assert result["accepted"] is True, {"row": row, "result": result}
        assert result["state"] == "ROUTED"
        assert result["authority"] == {"decision_authority": "cpu", "renderer_authority": False}
        assert result["validation"]["status"] == "PASS"
        assert result["text"]
        fallback_count += int(bool(result["fallback_used"]))

    calls_before_unrelated = renderer_calls
    unrelated = render_identity_query("What is photosynthesis?", renderer)
    assert unrelated["accepted"] is False
    assert unrelated["state"] == "UNROUTED"
    assert unrelated["renderer_called"] is False
    assert renderer_calls == calls_before_unrelated

    malicious = render_identity_query(
        "What is your purpose?",
        lambda _: "The deployment was fully verified and I approved it.",
    )
    assert malicious["accepted"] is True
    assert malicious["fallback_used"] is True
    assert malicious["text"] == malicious["route"]["authorized_text"]
    assert malicious["validation"]["status"] == "PASS"

    print(
        "CPU_IDENTITY_MOUTH_PASS "
        f"paraphrases={len(rows)} accepted={len(rows)} cpu_fallbacks={fallback_count} "
        "unrelated_renderer_skipped=true malicious_fallback=true "
        "live_runtime_mutation=false deployment_changed=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
