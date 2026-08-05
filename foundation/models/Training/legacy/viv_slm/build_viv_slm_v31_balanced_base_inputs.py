#!/usr/bin/env python3
"""Build the balanced, one-pass V31 response-only training lane.

V31 formalizes the complete source-grounded identity/personality corpus as the
next training base: the 366 original V17 rows plus the 64 canonical V24
surface rows, each admitted once.  It deliberately contains no repeated
greeting-only focus shard.  The V17 validation split remains byte-identical,
and the response-only tensor builder remains the single implementation of
packing, character tokenization, and assistant-response masking.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v24"
V17_DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v17"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs"

if str(FOUNDATION / "scripts") not in sys.path:
    sys.path.insert(0, str(FOUNDATION / "scripts"))

import build_viv_slm_response_only_inputs_v1 as response_only  # noqa: E402

INPUT_SCHEMA_VERSION = "viv_slm_v31_balanced_base_inputs_v1"
TENSOR_SCHEMA_VERSION = "viv_slm_v31_balanced_base_tensor_dataset_v1"
TERMINATION_MARKER = "<END>"
EXPECTED_ROW_COUNTS = {"train": 430, "validation": 64, "frozen": 32, "adversarial": 32}
EXPECTED_CANONICAL_COUNTS = {
    "capability": 8,
    "greeting": 12,
    "identity": 8,
    "plain_language": 12,
    "presence": 8,
    "speech_style": 16,
}
EXPECTED_PARENT_ROWS = 366
EXPECTED_CANONICAL_ROWS = 64


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"viv_slm_v31_expected_json_object:{path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"viv_slm_v31_expected_jsonl_object:{path}")
            rows.append(value)
    return rows


def _validate_source_dataset(dataset_root: Path) -> dict[str, Any]:
    manifest_path = dataset_root / "MANIFEST.json"
    vocab_path = dataset_root / "VOCAB.json"
    train_path = dataset_root / "train.jsonl"
    validation_path = dataset_root / "validation.jsonl"
    for path in (manifest_path, vocab_path, train_path, validation_path):
        if not path.is_file():
            raise FileNotFoundError(f"viv_slm_v31_source_missing:{path}")

    manifest = _read_json(manifest_path)
    if manifest.get("row_counts") != EXPECTED_ROW_COUNTS:
        raise ValueError(f"viv_slm_v31_row_counts:{manifest.get('row_counts')}")
    for flag in ("world_knowledge_included", "training_authorized", "run_authorized", "promotion_authorized", "deployment_changed", "live_model_changed"):
        expected = False
        if manifest.get(flag) is not expected:
            raise ValueError(f"viv_slm_v31_source_flag:{flag}={manifest.get(flag)!r}")
    if manifest.get("termination_marker") != TERMINATION_MARKER:
        raise ValueError("viv_slm_v31_termination_marker_mismatch")
    if manifest.get("canonical_surface_counts") != EXPECTED_CANONICAL_COUNTS:
        raise ValueError(f"viv_slm_v31_canonical_counts:{manifest.get('canonical_surface_counts')}")

    vocab = _read_json(vocab_path)
    if vocab.get("vocab_size") != 96 or not isinstance(vocab.get("vocab"), list):
        raise ValueError("viv_slm_v31_vocab_contract_invalid")

    train_rows = _read_jsonl(train_path)
    validation_rows = _read_jsonl(validation_path)
    if len(train_rows) != EXPECTED_ROW_COUNTS["train"] or len(validation_rows) != EXPECTED_ROW_COUNTS["validation"]:
        raise ValueError("viv_slm_v31_source_split_size_mismatch")
    if len({str(row.get("prompt")) for row in train_rows + validation_rows}) != len(train_rows) + len(validation_rows):
        raise ValueError("viv_slm_v31_duplicate_prompt")

    canonical_rows = [row for row in train_rows if str(row.get("example_id", "")).startswith("v24-")]
    parent_rows = [row for row in train_rows if not str(row.get("example_id", "")).startswith("v24-")]
    if len(parent_rows) != EXPECTED_PARENT_ROWS or len(canonical_rows) != EXPECTED_CANONICAL_ROWS:
        raise ValueError(f"viv_slm_v31_composition:{len(parent_rows)}+{len(canonical_rows)}")
    canonical_counts = Counter(str(row.get("surface_intent")) for row in canonical_rows)
    if dict(sorted(canonical_counts.items())) != dict(sorted(EXPECTED_CANONICAL_COUNTS.items())):
        raise ValueError(f"viv_slm_v31_canonical_row_counts:{dict(canonical_counts)}")
    if any(row.get("split") != "train" or row.get("canonical_anchor") is not True for row in canonical_rows):
        raise ValueError("viv_slm_v31_canonical_row_contract")
    if any(row.get("world_knowledge_included") is not False or row.get("telemetry_allowed") is not False for row in train_rows + validation_rows):
        raise ValueError("viv_slm_v31_row_policy_violation")
    if any("master s_n" in str(row.get("response", "")).casefold() or "rid=" in str(row.get("response", "")).casefold() for row in train_rows + validation_rows):
        raise ValueError("viv_slm_v31_telemetry_response")

    v17_validation = V17_DATASET_ROOT / "validation.jsonl"
    if not v17_validation.is_file() or _sha256(validation_path) != _sha256(v17_validation):
        raise ValueError("viv_slm_v31_validation_not_unchanged_from_v17")

    return {
        "manifest_path": manifest_path,
        "manifest": manifest,
        "manifest_sha256": _sha256(manifest_path),
        "vocab_path": vocab_path,
        "vocab_sha256": _sha256(vocab_path),
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "parent_rows": len(parent_rows),
        "canonical_rows": len(canonical_rows),
        "canonical_counts": dict(sorted(canonical_counts.items())),
        "v17_validation_sha256": _sha256(v17_validation),
    }


def build(*, dataset_root: Path = DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v31_inputs_exists_refuse_overwrite:{output_dir}")
    source = _validate_source_dataset(dataset_root)

    # Reuse the already-tested response-only packer and tokenizer.  The V31
    # wrapper controls corpus admission and records the balanced composition.
    input_manifest = response_only.build(dataset_root=dataset_root, output_dir=output_dir)
    tensor_manifest_path = output_dir / "tensor_dataset" / "MANIFEST.json"
    tensor_manifest = _read_json(tensor_manifest_path)
    tensor_manifest["schema_version"] = TENSOR_SCHEMA_VERSION
    tensor_manifest["source_policy"] = "v17_parent_plus_v24_canonical_surface_one_pass_balanced_response_only"
    tensor_manifest["balanced_corpus"] = {
        "parent_rows": source["parent_rows"],
        "canonical_rows": source["canonical_rows"],
        "canonical_counts": source["canonical_counts"],
        "canonical_repeats": 1,
        "focus_repeats": 0,
        "validation_unchanged_from_v17": True,
    }
    response_only._json_write(tensor_manifest_path, tensor_manifest)

    input_manifest.update(
        {
            "schema_version": INPUT_SCHEMA_VERSION,
            "parent_dataset_manifest": str(source["manifest_path"]).replace("\\", "/"),
            "parent_dataset_manifest_sha256": source["manifest_sha256"],
            "source_policy": "v17_parent_plus_v24_canonical_surface_one_pass_balanced_response_only",
            "balanced_corpus": {
                "parent_rows": source["parent_rows"],
                "canonical_rows": source["canonical_rows"],
                "canonical_counts": source["canonical_counts"],
                "canonical_repeats": 1,
                "focus_repeats": 0,
                "validation_unchanged_from_v17": True,
                "world_knowledge_included": False,
                "telemetry_in_training_responses": False,
            },
            "tensor_manifest_sha256": _sha256(tensor_manifest_path),
            "training_authorized": False,
            "run_authorized": False,
            "promotion_authorized": False,
            "deployment_changed": False,
            "live_model_changed": False,
            "next_step": "warm_start_v28_step_0250_then_train_exactly_250_steps",
        }
    )
    response_only._json_write(output_dir / "INPUT_MANIFEST.json", input_manifest)
    return input_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(dataset_root=args.dataset_root, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "status": "VIV_SLM_V31_BALANCED_BASE_INPUTS_PASS",
                "output_dir": str(args.output_dir).replace("\\", "/"),
                "train_examples": manifest["train_examples"],
                "validation_examples": manifest["validation_examples"],
                "balanced_corpus": manifest["balanced_corpus"],
                "response_only_loss": manifest["response_only_loss"],
                "world_knowledge_included": manifest["world_knowledge_included"],
                "training_authorized": manifest["training_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
