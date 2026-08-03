#!/usr/bin/env python3
"""Build Ollama Modelfile for viv-voice from AIOS fluency pairs (local, no RLHF).

True LoRA/SFT needs torch — this bakes few-shot MESSAGE examples into the Ollama
model so a BASE generative GGUF learns the *shape* of Viv speech until weights train.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
GGUF = FOUNDATION / "models" / "gpu" / "OpenAster1-128k-base.i1-Q6_K.gguf"
OUT = FOUNDATION / "models" / "gpu" / "Modelfile.viv-voice"
CORPUS = FOUNDATION / "artifacts" / "models" / "voice_fluency.jsonl"

# Dedicated short state→speech pairs (match live intent-packet speak shape)
PAIRS: list[tuple[str, str]] = [
    (
        "Translate facts only. Do not invent. Do not decide.\n"
        "Tone: measured.\nQuery: state summary\nStatus: ACTIVE S_n=0.72\n"
        "Facts:\n- master_s_n=0.7200\n- status=ACTIVE\n- n_subsystems=4\n- plant=PASS\n"
        "Memory:\n- (none)\nSpoken report:\n",
        "Architect: stability is 0.72 and I am active. Four subsystems are reporting. "
        "Plant authority is pass. I am speaking from facts only.",
    ),
    (
        "Translate facts only. Do not invent. Do not decide.\n"
        "Tone: terse.\nQuery: state summary\nStatus: DORMANT S_n=0.38\n"
        "Facts:\n- master_s_n=0.3800\n- status=DORMANT\n- n_subsystems=4\n"
        "Memory:\n- (none)\nSpoken report:\n",
        "S_n is 0.38, under the 0.45 dormancy line. I am dormant and will not act until stability recovers.",
    ),
    (
        "Translate facts only. Do not invent. Do not decide.\n"
        "Tone: calm.\nQuery: state summary\nStatus: ACTIVE S_n=0.56\n"
        "Facts:\n- master_s_n=0.5600\n- status=ACTIVE\n- piston_mode=background\n"
        "Memory:\n- [live] first real memory for CPU AI\nSpoken report:\n",
        "Stability is 0.56. I am active with the piston in background. "
        "Recent memory notes the first CPU AI memory was written. That is all I am authorized to say.",
    ),
    (
        "Translate facts only. Do not invent. Do not decide.\n"
        "Tone: measured.\nQuery: hello\nStatus: ACTIVE S_n=0.61\n"
        "Facts:\n- master_s_n=0.6100\n- status=ACTIVE\n"
        "Memory:\n- (none)\nSpoken report:\n",
        "Hello, Architect. Master stability is 0.61 and I am active. I translate the CPU state; I do not decide.",
    ),
]


def _load_corpus_pairs(limit: int = 6) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not CORPUS.is_file():
        return out
    with CORPUS.open(encoding="utf-8") as fh:
        for line in fh:
            if len(out) >= limit:
                break
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = row.get("messages") or []
            if len(msgs) < 3:
                continue
            user = str(msgs[1].get("content") or "")
            asst = str(msgs[2].get("content") or "")
            # Keep short assistant targets only — long copy jobs train bad habits
            if 40 <= len(asst) <= 420 and "Speak this" in user:
                # Prefer templates that aren't full theory dumps
                if asst.count("\n") > 12:
                    continue
                out.append((user[:800], asst[:420]))
    return out


def write_modelfile(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Viv GPU right-brain — OpenAster1 BASE + AIOS fluency few-shots (local Ollama)",
        f"FROM {GGUF.as_posix()}",
        "",
        "PARAMETER temperature 0.45",
        "PARAMETER num_ctx 2048",
        "PARAMETER num_predict 96",
        "PARAMETER stop Spoken report:",
        "PARAMETER stop Architect:",
        "",
        'SYSTEM """You are Viv\'s stateless voice. Translate structured CPU facts into clear English. '
        "No RLHF persona. No memory. No decisions. Do not invent facts. Prefer one short paragraph.\"\"\"",
        "",
    ]
    pairs = list(PAIRS)
    pairs.extend(_load_corpus_pairs(4))
    for user, asst in pairs:
        # Escape for Modelfile triple-quote blocks
        u = user.replace('"""', "'''")
        a = asst.replace('"""', "'''")
        lines.append(f'MESSAGE user """{u}"""')
        lines.append(f'MESSAGE assistant """{a}"""')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(OUT))
    args = p.parse_args()
    out = write_modelfile(Path(args.out))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
