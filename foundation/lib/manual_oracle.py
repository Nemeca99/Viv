"""Read-only, hash-verified section lookup for the active AIOS manual.

This ports the useful V1 ManualOracle boundary without importing its mutable
index or filesystem layout. The CPU builds a bounded section map in memory,
returns source and section hashes with every hit, and abstains if the manual
changes after initialization.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.paths import FOUNDATION_ROOT


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _anchor(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")


@dataclass(frozen=True)
class ManualSection:
    anchor: str
    title: str
    start_line: int
    end_line: int
    text: str
    sha256: str


class ManualOracle:
    """CPU-owned manual lookup that fails closed on source drift."""

    def __init__(self, manual_path: str | Path | None = None) -> None:
        self.manual_path = Path(manual_path or FOUNDATION_ROOT / "AIOS_ALPHA_MANUAL.md").resolve()
        self._bytes = self.manual_path.read_bytes()
        self.source_sha256 = _sha256(self._bytes)
        self._sections = self._parse(self._bytes.decode("utf-8", errors="replace"))

    def _parse(self, text: str) -> tuple[ManualSection, ...]:
        lines = text.splitlines(keepends=True)
        headings: list[tuple[int, str]] = []
        for number, line in enumerate(lines, start=1):
            match = _HEADING.match(line.rstrip("\r\n"))
            if match:
                headings.append((number, match.group(2)))
        sections: list[ManualSection] = []
        for index, (start, title) in enumerate(headings):
            end = (headings[index + 1][0] - 1) if index + 1 < len(headings) else len(lines)
            body = "".join(lines[start - 1 : end]).strip()
            sections.append(
                ManualSection(
                    anchor=_anchor(title),
                    title=title,
                    start_line=start,
                    end_line=end,
                    text=body,
                    sha256=_sha256(body.encode("utf-8")),
                )
            )
        return tuple(sections)

    def _verify_source(self) -> bool:
        try:
            return _sha256(self.manual_path.read_bytes()) == self.source_sha256
        except OSError:
            return False

    def lookup(self, anchor: str) -> dict[str, Any]:
        if not self._verify_source():
            return self._abstain("source_changed")
        wanted = _anchor(anchor)
        for section in self._sections:
            if section.anchor == wanted:
                return self._result("VERIFIED", [section])
        return self._result("INSUFFICIENT", [])

    def search(self, query: str, *, top_k: int = 5) -> dict[str, Any]:
        if not self._verify_source():
            return self._abstain("source_changed")
        terms = [term.casefold() for term in re.findall(r"[a-zA-Z0-9]{3,}", query or "")]
        if not terms:
            return self._result("INSUFFICIENT", [])
        ranked: list[tuple[int, ManualSection]] = []
        for section in self._sections:
            haystack = f"{section.title}\n{section.text}".casefold()
            score = sum(term in haystack for term in terms)
            if score:
                ranked.append((score, section))
        ranked.sort(key=lambda row: (-row[0], row[1].start_line))
        return self._result("VERIFIED" if ranked else "INSUFFICIENT", [row[1] for row in ranked[: max(1, min(top_k, 20))]])

    def _result(self, state: str, sections: list[ManualSection]) -> dict[str, Any]:
        return {
            "state": state,
            "source": {"path": self.manual_path.as_posix(), "sha256": self.source_sha256},
            "sections": [
                {
                    "anchor": section.anchor,
                    "title": section.title,
                    "start_line": section.start_line,
                    "end_line": section.end_line,
                    "sha256": section.sha256,
                    "text": section.text,
                }
                for section in sections
            ],
        }

    def _abstain(self, reason: str) -> dict[str, Any]:
        return {
            "state": "ABSTAIN",
            "reason": reason,
            "source": {"path": self.manual_path.as_posix(), "sha256": self.source_sha256},
            "sections": [],
        }
