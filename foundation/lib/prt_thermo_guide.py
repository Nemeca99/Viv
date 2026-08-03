"""Bounded plant guide (thermo + hardware specs) → multiple-choice gold for PRT LoRA.

Plant-local only under artifacts/corp/{thermo,hardware}/.
Not a Wikipedia dump. Mix must stay small vs PHYSICS/STRUCTURE gold.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from lib.paths import ARTIFACTS, FOUNDATION_ROOT
except ModuleNotFoundError:  # running as script
    import sys

    FOUNDATION_ROOT = Path(__file__).resolve().parents[1]
    if str(FOUNDATION_ROOT) not in sys.path:
        sys.path.insert(0, str(FOUNDATION_ROOT))
    from lib.paths import ARTIFACTS, FOUNDATION_ROOT

THERMO_FACTS = ARTIFACTS / "corp" / "thermo" / "guide_facts.jsonl"
HARDWARE_FACTS = ARTIFACTS / "corp" / "hardware" / "guide_facts.jsonl"
PLANT_SPECS = ARTIFACTS / "corp" / "hardware" / "plant_specs.json"
GOLD_PATH = ARTIFACTS / "models" / "thermo_choice_gold.jsonl"
BUILD_SUMMARY = ARTIFACTS / "models" / "thermo_choice_build.json"

# Default fact sources (thermo first, then hardware compare-against)
DEFAULT_FACT_PATHS = (THERMO_FACTS, HARDWARE_FACTS)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_plant_specs(path: Path | None = None) -> dict[str, Any]:
    src = path or PLANT_SPECS
    if not src.is_file():
        return {}
    try:
        return json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_facts(paths: list[Path] | tuple[Path, ...] | Path | None = None) -> list[dict[str, Any]]:
    if paths is None:
        path_list = list(DEFAULT_FACT_PATHS)
    elif isinstance(paths, Path):
        path_list = [paths]
    else:
        path_list = list(paths)
    out: list[dict[str, Any]] = []
    for src in path_list:
        if not src.is_file():
            continue
        domain = "hardware" if "hardware" in str(src).replace("\\", "/") else "thermo"
        for line in src.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("stem") and row.get("correct") and row.get("distractors"):
                row = dict(row)
                row.setdefault("_domain", domain)
                out.append(row)
    return out


def _format_mc_prompt(fact: dict[str, Any], *, rng: random.Random) -> tuple[str, str, str]:
    """Return (prompt_text, correct_label, correct_answer_text)."""
    correct = str(fact["correct"]).strip()
    distractors = [str(d).strip() for d in (fact.get("distractors") or []) if str(d).strip()]
    distractors = distractors[:3]
    while len(distractors) < 3:
        distractors.append("not applicable to this plant")
    options = [correct] + distractors
    rng.shuffle(options)
    labels = ["A", "B", "C", "D"]
    labeled = list(zip(labels, options))
    correct_label = next(lab for lab, text in labeled if text == correct)
    domain = str(fact.get("_domain") or "thermo")
    task = (
        "Task: hardware plant specs — compare options against THIS host. Multiple choice."
        if domain == "hardware"
        else "Task: thermodynamics plant guide. Multiple choice. Pick the best option."
    )
    lines = [
        task,
        "Emit ONE JSON object only. No prose.",
        f"Q: {fact['stem']}",
    ]
    for lab, text in labeled:
        lines.append(f"  {lab}) {text}")
    lines.append('JSON example: {"choice":"B","answer":"..."}\nJSON:')
    prompt = "\n".join(lines)
    return prompt, correct_label, correct


def build_thermo_choice_gold(
    *,
    facts_path: Path | None = None,
    out_path: Path | None = None,
    seed: int = 7,
    max_rows: int | None = None,
    include_hardware: bool = True,
) -> dict[str, Any]:
    """Build SFT rows: MC prompt → JSON with correct choice + answer."""
    if facts_path is not None:
        paths: list[Path] = [facts_path]
    else:
        paths = [THERMO_FACTS]
        if include_hardware:
            paths.append(HARDWARE_FACTS)
    facts = load_facts(paths)
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []
    for fact in facts:
        prompt, label, answer = _format_mc_prompt(fact, rng=rng)
        completion = json.dumps({"choice": label, "answer": answer}, ensure_ascii=False)
        text = f"{prompt}\n{completion}"
        domain = str(fact.get("_domain") or "thermo")
        prt_label = "HARDWARE_CHOICE_GOLD" if domain == "hardware" else "THERMO_CHOICE_GOLD"
        source = "hardware_guide" if domain == "hardware" else "thermo_guide"
        rows.append(
            {
                "text": text,
                "prt_label": prt_label,
                "source": source,
                "fact_id": str(fact.get("id") or ""),
            }
        )
    if max_rows is not None and max_rows > 0:
        rows = rows[: int(max_rows)]

    out = out_path or GOLD_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_label: dict[str, int] = {}
    for r in rows:
        by_label[r["prt_label"]] = by_label.get(r["prt_label"], 0) + 1

    summary = {
        "timestamp": _utc(),
        "facts_paths": [str(p).replace("\\", "/") for p in paths],
        "plant_specs": str(PLANT_SPECS).replace("\\", "/") if PLANT_SPECS.is_file() else None,
        "out_path": str(out).replace("\\", "/"),
        "facts_n": len(facts),
        "rows": len(rows),
        "by_label": by_label,
        "seed": seed,
        "note": "Bounded plant thermo+hardware MC — compare-against sheet, not Wikipedia dump",
    }
    BUILD_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def thermo_choice_rows_for_train(
    *,
    enabled: bool = True,
    max_rows: int = 56,
    oversample: int = 2,
    seed: int = 7,
    include_hardware: bool = True,
) -> list[dict[str, str]]:
    """Return train dicts ready to append into PRT JSONL (small mix)."""
    if not enabled:
        return []
    build_thermo_choice_gold(
        seed=seed, max_rows=max_rows, include_hardware=include_hardware
    )
    src = GOLD_PATH
    if not src.is_file():
        return []
    out: list[dict[str, str]] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        body = str(row.get("text") or "")
        if len(body) < 40:
            continue
        label = str(row.get("prt_label") or "THERMO_CHOICE_GOLD")
        source = str(row.get("source") or "thermo_guide")
        for _ in range(max(1, int(oversample))):
            out.append({"text": body, "prt_label": label, "source": source})
    ceiling = max(8, int(max_rows) * max(1, int(oversample)))
    return out[:ceiling]


def one_line_hint(topic: str | None = None) -> str:
    """Optional short host tag line for future madlibs / predict hints."""
    facts = load_facts()
    if not facts:
        return ""
    if topic:
        matched = [
            f
            for f in facts
            if topic.lower() in str(f.get("topic") or "").lower()
            or topic.lower() in str(f.get("_domain") or "").lower()
        ]
        pool = matched or facts
    else:
        pool = facts
    fact = pool[0]
    tag = "hardware_guide" if fact.get("_domain") == "hardware" else "thermo_guide"
    return f"[TAG:{tag}] {fact['stem']} → {fact['correct']}"


def hardware_compare_tag() -> str:
    """One-line host tag from plant_specs for predict prompts (optional)."""
    specs = load_plant_specs()
    if not specs:
        return ""
    cpu = (specs.get("cpu") or {}).get("short") or "?"
    gpu = (specs.get("gpu") or {}).get("short") or "?"
    cool = (specs.get("cooler") or {}).get("cpu_loop") or "?"
    logical = (specs.get("cpu") or {}).get("cores_logical") or "?"
    return (
        f"[TAG:plant_specs] host={cpu} {logical}t; gpu={gpu} air; cooler={cool}; "
        "compare options to this inventory."
    )


if __name__ == "__main__":
    rep = build_thermo_choice_gold()
    print(json.dumps(rep, indent=2))
    print(hardware_compare_tag())
