#!/usr/bin/env python3
"""CPU integrity review CLI — past logs → 'am I still good?' (no GPU)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.integrity_review import INTEGRITY_LATEST, review  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Viv integrity review (CPU-only)")
    p.add_argument("--prt-tail", type=int, default=40)
    p.add_argument("--voice-tail", type=int, default=30)
    args = p.parse_args()
    rep = review(prt_tail=args.prt_tail, voice_tail=args.voice_tail)
    print(json.dumps(rep, indent=2))
    print(f"wrote: {INTEGRITY_LATEST}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
