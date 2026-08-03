#!/usr/bin/env python3
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

root = Path(r"L:/Continue/Viv")
impl = {".py", ".rs", ".ps1"}
skip = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "vendor",
    "third_party",
    "site-packages",
    "target",
    "dist",
    "build",
}
buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})


def blocked(p: Path) -> bool:
    s = str(p).replace("\\", "/").lower()
    return any(
        x in s
        for x in ("/.venv/", "/site-packages/", "/node_modules/", "/models/gpu/")
    )


def bucket_for(p: Path) -> str:
    s = str(p).replace("\\", "/").lower()
    name = p.name.lower()
    if "/models/training/" in s:
        return "training_tree"
    if "/foundation/scripts/" in s and any(
        k in name
        for k in (
            "train",
            "mouth",
            "lora",
            "canary",
            "adapter",
            "sft",
            "eval",
            "corpus",
            "admit",
            "openaster",
            "generation",
        )
    ):
        return "training_adjacent_scripts"
    if "/foundation/lib/" in s and any(
        k in name for k in ("eval", "mouth", "rubric", "judge", "train", "parity")
    ):
        return "training_adjacent_lib"
    return "non_training_runtime"


for dirpath, dirnames, filenames in os.walk(root):
    p = Path(dirpath)
    dirnames[:] = [
        d
        for d in dirnames
        if d.lower() not in skip and not d.lower().endswith("-hf")
    ]
    for fn in filenames:
        fp = p / fn
        if fp.suffix.lower() not in impl or blocked(fp):
            continue
        try:
            n = len(fp.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
        b = bucket_for(fp)
        buckets[b]["files"] += 1
        buckets[b]["lines"] += n

total = sum(v["lines"] for v in buckets.values())
print("Viv impl lines by rough bucket")
for k in sorted(buckets, key=lambda x: -buckets[x]["lines"]):
    v = buckets[k]
    pct = 100.0 * v["lines"] / total if total else 0.0
    print(f"{k}: {v['files']} files, {v['lines']} lines ({pct:.1f}%)")
trainish = (
    buckets["training_tree"]["lines"]
    + buckets["training_adjacent_scripts"]["lines"]
    + buckets["training_adjacent_lib"]["lines"]
)
print(f"total {total}")
print(f"training_ish {trainish} ({100*trainish/total:.1f}%)")
print(
    f"non_training_runtime {buckets['non_training_runtime']['lines']} "
    f"({100*buckets['non_training_runtime']['lines']/total:.1f}%)"
)
