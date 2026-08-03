"""Build AIOS-domain SFT corpus for GPU + CPU training."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from lib.paths import CONTINUE_ROOT, FOUNDATION_ROOT

THEORY_DIR = CONTINUE_ROOT / "Dev-Tests-External" / "theory"

AIOS_V2 = CONTINUE_ROOT / "FSAA" / "Luna" / "AIOS_V2"
SLM_TRAINING = AIOS_V2 / "slm_core" / "training_data"
DATASET_BUILT = AIOS_V2 / "dataset_core" / "built"
FSAA_REPORTS = CONTINUE_ROOT / "FSAA" / "reports"


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _msg(system: str, user: str, assistant: str) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def _from_theory_files() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    system = (
        "You are the stateless voice of Viv (AIOS). You translate; the deterministic core decides. "
        "Be precise, fail-closed on safety ambiguity, and ground claims in physics (S_n, RID) when relevant."
    )
    for name in ("main.txt", "intent.txt", "theory.txt", "extension.txt"):
        p = THEORY_DIR / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore").strip()
        if len(text) < 200:
            continue
        chunk = text[:12000]
        rows.append(
            _msg(
                system,
                f"Summarize the AIOS/Viv specification section from {name} for an engineer rebuilding the stack.",
                chunk[:4000],
            )
        )
    uml_md = THEORY_DIR / "UML_Introduction.md"
    if uml_md.is_file():
        body = uml_md.read_text(encoding="utf-8", errors="ignore")[:8000]
        rows.append(
            _msg(
                system,
                "Explain UML (Universal Mathematical/Machine Language) for a new AIOS developer.",
                body,
            )
        )
    return rows


def _from_slm_logs(max_rows: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    system = "You are Luna, the stateless voice of AIOS. Respond in clear technical prose."
    path = SLM_TRAINING / "blue.jsonl"
    for row in _iter_jsonl(path):
        if row.get("source") != "logs":
            continue
        text = str(row.get("text") or "").strip()
        if len(text) < 80:
            continue
        prompt = text[:512]
        response = text[512:2500] if len(text) > 512 else text
        rows.append(_msg(system, prompt, response))
        if len(rows) >= max_rows:
            break
    return rows


def _from_dict_training(max_rows: int = 2000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = DATASET_BUILT / "dict_training.jsonl"
    for row in _iter_jsonl(path):
        prompt = str(row.get("prompt", "")).strip()
        response = str(row.get("response", "")).strip()
        if not prompt or not response:
            continue
        rows.append(_msg("You are Luna. Answer dictionary queries accurately.", prompt, response))
        if len(rows) >= max_rows:
            break
    return rows


def _from_train_good(max_rows: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ("train_good_strict.jsonl", "train_good.jsonl"):
        for row in _iter_jsonl(FSAA_REPORTS / name):
            src = str(row.get("source_code") or row.get("rebuilt_code") or "").strip()
            target = str(row.get("target", "")).strip()
            if not src:
                continue
            user = f"Rebuild or explain this AIOS module faithfully: {target}"
            rows.append(_msg("You are an AIOS engineer assistant.", user, src[:6000]))
            if len(rows) >= max_rows:
                return rows
    return rows


def build_corpus(
    out_path: Path,
    *,
    include_wiki: bool = False,
    max_slm_logs: int = 500,
) -> dict[str, int]:
    """Merge AIOS sources into one chat-jsonl for SFT."""
    sections: list[tuple[str, Iterable[dict[str, Any]]]] = [
        ("theory", _from_theory_files()),
        ("slm_logs", _from_slm_logs(max_rows=max_slm_logs)),
        ("dict_training", _from_dict_training()),
        ("train_good", _from_train_good()),
    ]

    counts: dict[str, int] = {}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for name, items in sections:
            n = 0
            for row in items:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
                total += 1
            counts[name] = n
    counts["total"] = total
    return counts
