#!/usr/bin/env python3
"""Show latest AIOS plant stability capture verdict (piston input side)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.plant_piston_bridge import LAST_CAPTURE_PATH, finalize_from_summary_path
from lib.stability_capture import validate_summary_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AIOS plant capture status")
    ap.add_argument("--summary", type=Path, default=None, help="Validate a summary.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.summary:
        verdict = finalize_from_summary_path(args.summary)
        out = verdict.to_dict()
    elif LAST_CAPTURE_PATH.is_file():
        out = json.loads(LAST_CAPTURE_PATH.read_text(encoding="utf-8"))
    else:
        print("No plant capture published yet.")
        return 1

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        v = out.get("verdict", out)
        if isinstance(v, dict):
            print(f"Verdict: {v.get('verdict')}  logged={v.get('n_logged')}  stress={v.get('stress')}")
            print(f"CSV: {v.get('csv_path')}")
            if v.get("cpu_load_max_pct") is not None:
                print(f"CPU load max: {v['cpu_load_max_pct']}%  workers_end: {v.get('stress_workers_alive_end')}")
            for r in v.get("reasons") or []:
                print(f"  - {r}")
        else:
            print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
