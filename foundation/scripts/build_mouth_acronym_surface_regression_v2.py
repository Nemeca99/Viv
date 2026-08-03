"""Build a 48-case hold-only acronym surface regression pack."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_acronym_surface_regression_v2"

CASES = (
    [(f"safe-repair-{i:02d}", text, "REPAIRED_PASS") for i, text in enumerate([
        "AIOS decides the verified context.",
        "The Graphics Processing Unit(GPU) renders speech.",
        "The Central Processing Unit(CPU) verifies the claim.",
    ])]
    + [(f"safe-clean-{i:02d}", text, "CLEAN_PASS") for i, text in enumerate([
        "Artificial Intelligence (AI) is the voice substrate.",
        "Symbiotic General Intelligence (SGI) is the architectural label.",
        "End of Sequence (EOS) marks the response boundary.",
        "Adaptive Intelligent Operating System (AIOS) and Graphics Processing Unit (GPU) provide the approved relationship.",
        "Central Processing Unit (CPU) checks the result before Graphics Processing Unit (GPU) renders it.",
        "Adaptive Intelligent Operating System (AIOS) services manage memory and logs.",
        "The Graphics Processing Unit (GPU) mouth reports Central Processing Unit (CPU) context.",
        "The Central Processing Unit (CPU) judge checks the Adaptive Intelligent Operating System (AIOS) record.",
        "Adaptive Intelligent Operating System (AIOS) remains distinct from the human operator.",
        "Graphics Processing Unit (GPU) rendering does not create reasoning.",
        "Central Processing Unit (CPU) verification precedes End of Sequence (EOS).",
        "Artificial Intelligence (AI) speaks through the approved voice path.",
        "Symbiotic General Intelligence (SGI) uses the Adaptive Intelligent Operating System (AIOS) governance.",
    ], 3)],
    [(f"unknown-{i:02d}", text, "UNRESOLVED_HOLD") for i, text in enumerate([
        "AIS decides the context.",
        "AISOS is the identity.",
        "AIAS manages the memory.",
        "AIOSkynet speaks through the mouth.",
        "XYZ controls the layer.",
        "GPUmouth owns the voice.",
        "AIOSystem decides truth.",
        "The AIS model verifies the claim.",
        "AIOSketcher writes the plan.",
        "ABC is the approved term.",
        "The CPUX layer reasons.",
        "The GPUVoice owns context.",
        "AIS memory is personal.",
        "The AIOSAI identity speaks.",
        "SGIX changes the system.",
        "EOSX ends the response.",
    ], 2)],
    [(f"clean-{i:02d}", text, "CLEAN_PASS") for i, text in enumerate([
        "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS).",
        "Adaptive Intelligent Operating System (AIOS) services manage approved logs.",
        "The Graphics Processing Unit (GPU) renders the approved response.",
        "The Central Processing Unit (CPU) verifies the meaning.",
        "Artificial Intelligence (AI) is a known technical term.",
        "Symbiotic General Intelligence (SGI) remains a documented label.",
        "End of Sequence (EOS) is a token boundary.",
        "Adaptive Intelligent Operating System (AIOS) is not a human identity.",
        "Central Processing Unit (CPU) supplies verified context.",
        "Graphics Processing Unit (GPU) renders supplied words.",
        "Adaptive Intelligent Operating System (AIOS) memory services manage records.",
        "Symbiotic General Intelligence (SGI) follows the approved contract.",
        "End of Sequence (EOS) appears after the response.",
        "Artificial Intelligence (AI) is not a person claim.",
        "Central Processing Unit (CPU) and Graphics Processing Unit (GPU) have distinct roles.",
        "Adaptive Intelligent Operating System (AIOS) and Viv remain the approved identity relationship.",
    ], 3)],
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_overwrite:{ROOT}")
    rows = []
    seen = set()
    for group in CASES:
        for case_id, text, expected in group:
            digest = hashlib.sha256(text.lower().encode("utf-8")).hexdigest()
            if digest in seen:
                raise ValueError(f"duplicate_text:{text}")
            seen.add(digest)
            rows.append({
                "case_id": f"acronym-surface-v2-{case_id}",
                "text": text,
                "expected": expected,
                "split": "hold_only",
                "optimizer_eligible": False,
                "training_authorized": False,
                "run_authorized": False,
                "text_sha256": digest,
            })
    if len(rows) != 48:
        raise ValueError(f"count:{len(rows)}")
    ROOT.mkdir(parents=True)
    source = ROOT / "regression_48.jsonl"
    source.write_text("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_acronym_surface_regression_manifest_v2",
        "experiment_id": "mouth_acronym_surface_regression_v2",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "HOLD_ONLY_TRAINING_CLOSED",
        "rows": len(rows),
        "categories": {"REPAIRED_PASS": 16, "UNRESOLVED_HOLD": 16, "CLEAN_PASS": 16},
        "optimizer_eligible_any": False,
        "training_authorized": False,
        "run_authorized": False,
        "files": {"regression_48.jsonl": {"sha256": sha(source), "count": len(rows)}},
        "source_failure_delta": "mouth_full_run_entity_we_v2/ACRONYM_FAILURE_DELTA_V1.json",
    }
    manifest_path = ROOT / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(ROOT), "manifest_sha256": sha(manifest_path), "rows": len(rows), "training_authorized": False, "run_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
