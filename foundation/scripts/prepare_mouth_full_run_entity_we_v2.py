"""Install and preflight the contract-repaired 256-row full run.

The implementation reuses the governed v1 execution path with a new campaign
identity and immutable v2 corpus bindings.  It never authorizes or trains by
default.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
for candidate in (FOUNDATION, FOUNDATION.parent, Path(__file__).resolve().parent):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import prepare_mouth_full_run_entity_we_v1 as governed  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
governed.ROOT = TREE / "mouth_full_run_entity_we_v2"
governed.TRAIN = governed.ROOT / "train_256.jsonl"
governed.EXPERIMENT_ID = "mouth_full_run_entity_we_v2"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install-preflight", "authorize", "run"))
    args = parser.parse_args()
    if args.mode == "install-preflight":
        result = governed.install()
        report = governed.exact_nostep_preflight()
        result["preflight"] = report
        governed.write_new(governed.ROOT / "EXACT_RUNTIME_NOSTEP_PREFLIGHT.json", report)
        print(governed.json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.mode == "authorize":
        print(governed.json.dumps(governed.authorize_once(), indent=2, sort_keys=True))
        return 0
    print(governed.json.dumps(governed.execute_once(), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
