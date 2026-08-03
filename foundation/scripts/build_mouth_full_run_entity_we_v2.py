"""Build a contract-repaired copy of the 256-row mouth corpus; never trains."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
sys.path.insert(0, str(FOUNDATION.parent))
from voice_core.acronym_registry import APPROVED_ACRONYMS  # noqa: E402

TREE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns"
SOURCE_ROOT = TREE / "mouth_full_run_entity_we_v1"
ROOT = TREE / "mouth_full_run_entity_we_v2"
SOURCE = SOURCE_ROOT / "train_256.jsonl"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expand_first_use(text: str) -> str:
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        spec = APPROVED_ACRONYMS.get(token)
        if spec is None or token in seen:
            return token
        seen.add(token)
        return f"{spec.expansion} ({token})"

    return re.sub(r"(?<![A-Za-z])[A-Z][A-Z0-9]{1,}(?![A-Za-z])", replace, text)


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    source_rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(source_rows) != 256:
        raise ValueError(f"source_row_count:{len(source_rows)}")
    rows = []
    changed = 0
    reclassified = 0
    for source in source_rows:
        row = dict(source)
        old_target = str(row.get("target") or row.get("chosen") or "")
        target = expand_first_use(old_target)
        row["target"] = target
        row["chosen"] = target
        row["target_hash"] = hashlib.sha256(target.lower().encode("utf-8")).hexdigest()
        row["approx_token_count"] = len(target.split())
        if target != old_target:
            changed += 1
        if str(row.get("candidate_id", "")).startswith("entity-we-"):
            row["axis"] = "entity_we_boundary"
            reclassified += 1
        row["training_authorized"] = False
        row["run_authorized"] = False
        rows.append(row)
    if changed == 0 or reclassified != 3:
        raise ValueError(f"repair_shape:changed={changed}:reclassified={reclassified}")
    ROOT.mkdir(parents=True)
    train = ROOT / "train_256.jsonl"
    train.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_full_run_entity_we_manifest_v2",
        "experiment_id": "mouth_full_run_entity_we_v2",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "CORPUS_READY_TRAINING_CLOSED",
        "optimizer_rows": len(rows),
        "training_authorized": False,
        "run_authorized": False,
        "automatic_retry": False,
        "source_campaign": str(SOURCE_ROOT).replace("\\", "/"),
        "source_train_sha256": sha(SOURCE),
        "source_manifest_sha256": sha(SOURCE_ROOT / "MANIFEST.json"),
        "train_256_sha256": sha(train),
        "repair": {
            "first_use_acronym_expansion": True,
            "approved_registry": str((FOUNDATION.parent / "voice_core/acronym_registry.py")).replace("\\", "/"),
            "reclassified_entity_we_rows": reclassified,
            "changed_targets": changed,
        },
        "evaluation_contract": {
            "calibration_campaign": str(TREE / "mouth_semantics_calibration_v4").replace("\\", "/"),
            "blind_campaign": str(TREE / "mouth_semantics_blind_v1").replace("\\", "/"),
        },
        "promotion_authorized": False,
        "deployment_authorized": False,
    }
    manifest_path = ROOT / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(ROOT), "rows": len(rows), "changed_targets": changed, "reclassified_entity_we_rows": reclassified, "train_256_sha256": sha(train), "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
