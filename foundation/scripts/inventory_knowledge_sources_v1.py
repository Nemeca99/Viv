"""Read-only metadata inventory for AIOS source roots.

The inventory deliberately does not read file contents, hash source files, or
write inside any source root. It records enough metadata to govern a later
staged ingest without treating presence as knowledge quality.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import time
from typing import Any


DEFAULT_ROOTS = {
    "F_AI_DATASETS": Path(r"F:\AI_Datasets"),
    "F_AIOS_CLEAN": Path(r"F:\AIOS_Clean"),
    "D_LOCALAI": Path(r"D:\LocalAi"),
    "L_VIV": Path(r"L:\Continue\Viv"),
}


def _inventory_root(label: str, root: Path, *, max_seconds: float | None = None, max_files: int | None = None) -> dict[str, Any]:
    started = time.monotonic()
    extension_counts: Counter[str] = Counter()
    top_level_counts: Counter[str] = Counter()
    files = 0
    directories = 0
    bytes_total = 0
    errors: list[dict[str, str]] = []
    complete = True
    limit_reached: str | None = None
    if not root.exists():
        return {
            "label": label,
            "root": root.as_posix(),
            "exists": False,
            "complete": False,
            "files": 0,
            "directories": 0,
            "bytes": 0,
            "extensions": {},
            "top_level_entries": {},
            "errors": [{"path": root.as_posix(), "error": "missing_root"}],
        }
    stack = [root]
    while stack:
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            complete = False
            limit_reached = "max_seconds"
            break
        if max_files is not None and files >= max_files:
            complete = False
            limit_reached = "max_files"
            break
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        rel = Path(entry.path).relative_to(root)
                        top = rel.parts[0] if rel.parts else entry.name
                        if entry.is_symlink():
                            errors.append({"path": entry.path, "error": "symlink_skipped"})
                            complete = False
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            directories += 1
                            top_level_counts[top] += 1
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            files += 1
                            if max_files is not None and files >= max_files:
                                limit_reached = "max_files"
                            bytes_total += int(stat.st_size)
                            top_level_counts[top] += 1
                            extension = Path(entry.name).suffix.lower() or "[no_extension]"
                            extension_counts[extension] += 1
                    except (OSError, ValueError) as exc:
                        complete = False
                        errors.append({"path": entry.path, "error": type(exc).__name__})
        except OSError as exc:
            complete = False
            errors.append({"path": str(current), "error": type(exc).__name__})
    return {
        "label": label,
        "root": root.as_posix(),
        "exists": True,
        "complete": complete and not errors,
        "files": files,
        "directories": directories,
        "bytes": bytes_total,
        "extensions": dict(sorted(extension_counts.items(), key=lambda item: (-item[1], item[0]))[:40]),
        "top_level_entries": dict(sorted(top_level_counts.items(), key=lambda item: (-item[1], item[0]))[:80]),
        "errors": errors[:100],
        "error_count": len(errors),
        "limit_reached": limit_reached,
        "elapsed_s": round(time.monotonic() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", action="append", choices=tuple(DEFAULT_ROOTS), dest="labels")
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--max-files", type=int, default=None)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    selected = args.labels or list(DEFAULT_ROOTS)
    roots = {
        label: _inventory_root(label, DEFAULT_ROOTS[label], max_seconds=args.max_seconds, max_files=args.max_files)
        for label in selected
    }
    report = {
        "schema_version": "knowledge_source_inventory_v1",
        "read_only": True,
        "content_hashed": False,
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "roots": roots,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": all(bool(item.get("exists")) and bool(item.get("complete")) for item in roots.values()),
        "schema_version": report["schema_version"],
        "output": args.output.as_posix(),
        "roots": {
            label: {key: item[key] for key in ("exists", "complete", "files", "directories", "bytes", "error_count")}
            for label, item in roots.items()
        },
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
