"""Build fluency corpus for the optional GPU voice (translation, not reasoning)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.train_corpus import _from_theory_files, _msg


def build_voice_corpus(out_path: Path) -> dict[str, int]:
    """
    Voice training = how to speak AIOS/Viv, not how to decide.
    Pairs: structured/neutral CPU-style output → natural language phrasing.
    """
    system = (
        "You are the stateless voice of Viv. You have no memory, no persona RLHF, and no authority. "
        "Translate the given structured system state into clear, honest natural language. "
        "Do not invent facts, permissions, or actions."
    )
    rows: list[dict[str, Any]] = []

    # Theory → speak the spec (fluency on domain vocabulary)
    for row in _from_theory_files():
        msgs = row["messages"]
        rows.append(
            _msg(
                system,
                f"Speak this to the architect in plain language:\n{msgs[2]['content'][:2000]}",
                msgs[2]["content"][:1500],
            )
        )

    # Template pairs: deterministic state → voice
    templates = [
        (
            '{"S_n":0.72,"status":"ACTIVE","RSR":0.91,"LTP":0.68,"RLE":0.55}',
            "Stability is good at Sₙ 0.72. All channels are above dormancy. I am active and within safe limits.",
        ),
        (
            '{"S_n":0.38,"status":"DORMANT","guardian":"BLOCKED","reason":"triadic_incomplete"}',
            "Sₙ is 0.38, below the 0.45 dormancy line. I am in a forced safe state and will not act until stability returns.",
        ),
        (
            '{"uml":"[3,4]","result":7,"verified":true}',
            "The UML expression [3,4] evaluates to 7. Dual-engine verification passed.",
        ),
        (
            "Facts:\n- master_s_n=0.56\n- status=ACTIVE\n- plant=PASS\nSpoken report:",
            "Architect: Master S_n is 0.56. I am active. Plant authority is pass. Speaking from facts only.",
        ),
        (
            "Facts:\n- master_s_n=0.44\n- status=DORMANT\nSpoken report:",
            "Architect: S_n is 0.44 under the dormancy line. I am dormant and silent on actions until stability returns.",
        ),
        (
            "Query: hello\nStatus: ACTIVE S_n=0.60\nFacts:\n- status=ACTIVE\nSpoken report:",
            "Architect: Hello. I am Viv's voice. Stability is 0.60 and active. I translate; I do not decide.",
        ),
    ]
    for structured, spoken in templates:
        rows.append(_msg(system, f"Structured state:\n{structured}", spoken))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"voice_fluency": len(rows), "total": len(rows)}
