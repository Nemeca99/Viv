"""Bounded recursive decomposition for the CPU reasoning path.

Ported from the F/D fractal-core design principles: compress state, preserve
decisions, and control recursion explicitly. This module creates a reasoning
tree only; it does not assert facts or call a model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MANUAL_SOURCE = "F:/AIOS_Clean/fractal_core"
MAX_DEPTH = 3
MAX_NODES = 64


@dataclass
class FractalNode:
    text: str
    depth: int
    kind: str = "question"
    children: list["FractalNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "depth": self.depth, "kind": self.kind, "children": [child.to_dict() for child in self.children]}


def _split(text: str) -> list[str]:
    parts = [part.strip(" \t\r\n,;:") for part in re.split(r"\?|\band\b|\bthen\b|\bwhile\b", text, flags=re.I)]
    return [part for part in parts if len(part) >= 3]


def decompose(text: str, *, max_depth: int = MAX_DEPTH, max_nodes: int = MAX_NODES) -> dict[str, Any]:
    clean = " ".join(str(text).split())
    if not clean:
        return {"ok": False, "state": "INSUFFICIENT", "reason": "empty_query"}
    depth_limit = max(0, min(int(max_depth), MAX_DEPTH))
    node_limit = max(1, min(int(max_nodes), MAX_NODES))
    count = 0

    def visit(value: str, depth: int, kind: str) -> FractalNode:
        nonlocal count
        count += 1
        node = FractalNode(value[:500], depth, kind)
        if depth >= depth_limit or count >= node_limit:
            return node
        for child_text in _split(value):
            if count >= node_limit:
                break
            if child_text.casefold() == value.casefold():
                continue
            node.children.append(visit(child_text, depth + 1, "subproblem"))
        return node

    root = visit(clean, 0, "query")
    leaves: list[str] = []

    def collect(node: FractalNode) -> None:
        if not node.children:
            leaves.append(node.text)
        for child in node.children:
            collect(child)

    collect(root)
    return {
        "ok": True,
        "state": "VERIFIED",
        "root": root.to_dict(),
        "node_count": count,
        "leaf_count": len(leaves),
        "leaves": leaves,
        "depth_limit": depth_limit,
        "node_limit": node_limit,
        "bounded": count <= node_limit,
        "authority": "cpu_deterministic_decomposition",
        "facts_asserted": False,
        "llm_authority": False,
        "manual_source": MANUAL_SOURCE,
    }
