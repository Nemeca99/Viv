"""1 MB split — two semantic shards, original removed (+1 file net)."""
from __future__ import annotations

from pathlib import Path

from memory_core.gate import gated_write
from memory_core.paths import SPLIT_BYTES, as_gate_path


def needs_split(path: Path) -> bool:
    return path.is_file() and path.stat().st_size >= SPLIT_BYTES


def split_point(text: str) -> int:
    """Split near midpoint on paragraph or newline boundary."""
    if len(text.encode("utf-8")) < SPLIT_BYTES:
        return len(text)
    target = len(text) // 2
    lo = max(0, target - 4096)
    hi = min(len(text), target + 4096)
    window = text[lo:hi]
    best = -1
    for sep in ("\n\n", "\n", ". "):
        idx = window.rfind(sep, 0, len(window) // 2 + 2048)
        if idx >= 0:
            abs_idx = lo + idx + len(sep)
            if abs_idx > len(text) * 0.25:
                best = abs_idx
                break
    if best < 0:
        best = target
    return min(best, len(text))


def split_file(path: Path, s_n: float) -> dict[str, str] | None:
    if not needs_split(path):
        return None
    text = path.read_text(encoding="utf-8")
    cut = split_point(text)
    left, right = text[:cut], text[cut:]
    if not left.strip() or not right.strip():
        mid = len(text) // 2
        left, right = text[:mid], text[mid:]
    stem = path.stem
    parent = path.parent
    part_a = parent / f"{stem}_a.txt"
    part_b = parent / f"{stem}_b.txt"
    n = 1
    while part_a.exists() or part_b.exists():
        part_a = parent / f"{stem}_split{n}_a.txt"
        part_b = parent / f"{stem}_split{n}_b.txt"
        n += 1
    ok_a, reason_a, _ = gated_write(as_gate_path(part_a), left, s_n)
    if not ok_a:
        return {"error": reason_a}
    ok_b, reason_b, _ = gated_write(as_gate_path(part_b), right, s_n)
    if not ok_b:
        return {"error": reason_b}
    path.unlink(missing_ok=True)
    return {"left": as_gate_path(part_a), "right": as_gate_path(part_b), "removed": as_gate_path(path)}
