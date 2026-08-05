#!/usr/bin/env python3
"""Build V26 inputs with a narrow, source-grounded surface-discrimination view.

V26 reuses the verified V25 dual-view builder but narrows the repeated focus
rows to greeting, presence, plain-language, and GPU-renderer examples.  The
V17 checkpoint remains the behavior-preserving parent for the canary; the
validation split and all source rows remain unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
SCRIPT_ROOT = FOUNDATION / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import build_viv_slm_v25_target_focused_inputs as _v25  # noqa: E402

DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v24"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v26_surface_discrimination" / "inputs"
SCHEMA_VERSION = "viv_slm_v26_surface_discrimination_tensor_dataset_v1"
INPUT_SCHEMA_VERSION = "viv_slm_v26_surface_discrimination_inputs_v1"
FOCUS_REPEATS = 24
FOCUS_INTENTS = frozenset({"greeting", "presence", "plain_language", "speech_style"})
FOCUS_CONCEPTS = frozenset({"gpu_renderer"})


def _is_focus_row(row: dict[str, object]) -> bool:
    surface_intent = str(row.get("surface_intent") or "")
    concept_id = str(row.get("concept_id") or "")
    return surface_intent in FOCUS_INTENTS or concept_id in FOCUS_CONCEPTS


def _rewrite_manifest(output_dir: Path) -> dict[str, object]:
    tensor_path = output_dir / "tensor_dataset" / "MANIFEST.json"
    input_path = output_dir / "INPUT_MANIFEST.json"
    tensor_manifest = json.loads(tensor_path.read_text(encoding="utf-8"))
    train_manifest = tensor_manifest["splits"]["train"]
    train_manifest["focused_intents"] = sorted(FOCUS_INTENTS)
    train_manifest["focused_concepts"] = sorted(FOCUS_CONCEPTS)
    tensor_manifest["objective"]["focus_intents"] = sorted(FOCUS_INTENTS)
    tensor_manifest["objective"]["focus_concepts"] = sorted(FOCUS_CONCEPTS)
    tensor_manifest["source_policy"] = "v24_source_rows_read_only_plus_v26_narrow_surface_discrimination_focus_view"
    tensor_path.write_text(json.dumps(tensor_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    input_manifest = json.loads(input_path.read_text(encoding="utf-8"))
    input_manifest["schema_version"] = INPUT_SCHEMA_VERSION
    input_manifest["focus_repeats"] = FOCUS_REPEATS
    input_manifest["focus_intents"] = sorted(FOCUS_INTENTS)
    input_manifest["focus_concepts"] = sorted(FOCUS_CONCEPTS)
    input_manifest["focus_view"] = "v26_narrow_surface_discrimination_train_only"
    input_manifest["tensor_manifest_sha256"] = _v25._sha256(tensor_path)
    input_manifest["next_step"] = "train_exactly_250_steps_from_v17_step_250_after_named_authorization"
    input_path.write_text(json.dumps(input_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return input_manifest


def build(*, dataset_root: Path = DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v26_inputs_exists_refuse_overwrite:{output_dir}")
    _v25.SCHEMA_VERSION = SCHEMA_VERSION
    _v25.INPUT_SCHEMA_VERSION = INPUT_SCHEMA_VERSION
    _v25.FOCUS_REPEATS = FOCUS_REPEATS
    _v25.FOCUS_INTENTS = FOCUS_INTENTS
    _v25._is_focus_row = _is_focus_row
    _v25.build(dataset_root=dataset_root, output_dir=output_dir)
    return _rewrite_manifest(output_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(dataset_root=args.dataset_root, output_dir=args.output_dir)
    print(json.dumps({
        "status": "VIV_SLM_V26_SURFACE_DISCRIMINATION_INPUTS_PASS",
        "output_dir": str(args.output_dir).replace("\\", "/"),
        "train_examples": manifest["train_examples"],
        "base_train_examples": manifest["base_train_examples"],
        "focused_train_examples": manifest["focused_train_examples"],
        "focused_train_rows": manifest["focused_train_rows"],
        "validation_examples": manifest["validation_examples"],
        "focus_repeats": manifest["focus_repeats"],
        "training_authorized": manifest["training_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
