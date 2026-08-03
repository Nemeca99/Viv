#!/usr/bin/env python3
"""Freeze the decomposition evidence corpus for V2 fitting (immutable).

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_decomposition_corpus_freeze.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_decomposition_corpus_freeze import write_freeze  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=str, default="")
    args = p.parse_args()
    out = Path(args.out_dir) if args.out_dir else None
    manifest = write_freeze(out_dir=out)
    print(
        json.dumps(
            {
                "ok": manifest.get("ok"),
                "n_actions": manifest.get("n_actions"),
                "immutable": manifest.get("immutable"),
                "artifact_json": manifest.get("artifact_json"),
                "artifact_md": manifest.get("artifact_md"),
                "missing_sources": manifest.get("missing_sources"),
            },
            indent=2,
        )
    )
    return 0 if manifest.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
