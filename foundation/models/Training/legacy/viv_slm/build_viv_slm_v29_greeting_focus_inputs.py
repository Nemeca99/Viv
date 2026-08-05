#!/usr/bin/env python3
"""Add a greeting-only canonical focus view to the V28 lane."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
SCRIPT_ROOT = FOUNDATION / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import build_viv_slm_v25_target_focused_inputs as _v25  # noqa: E402

BASE_INPUT_ROOT = VIV_ROOT / "models" / "viv_slm_identity_personality_v28_canonical_disambiguation" / "inputs"
FOCUS_DATASET_ROOT = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v24"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v29_greeting_focus" / "inputs"
SCHEMA_VERSION = "viv_slm_v29_greeting_focus_tensor_dataset_v1"
INPUT_SCHEMA_VERSION = "viv_slm_v29_greeting_focus_inputs_v1"
FOCUS_REPEATS = 32
CANONICAL_GREETING_RESPONSES = frozenset({
    "Hello. I am here and ready to listen.",
    "Yes. I am here and ready to listen.",
})


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def build(*, base_input_root: Path = BASE_INPUT_ROOT, focus_dataset_root: Path = FOCUS_DATASET_ROOT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_slm_v29_inputs_exists_refuse_overwrite:{output_dir}")
    base_manifest_path = base_input_root / "INPUT_MANIFEST.json"
    base_vocab_path = base_input_root / "VOCAB.json"
    base_tensor_path = base_input_root / "tensor_dataset" / "MANIFEST.json"
    focus_manifest_path = focus_dataset_root / "MANIFEST.json"
    for path in (base_manifest_path, base_vocab_path, base_tensor_path, focus_manifest_path):
        if not path.is_file():
            raise FileNotFoundError(f"viv_slm_v29_source_missing:{path}")
    base_input = _read_json(base_manifest_path)
    base_tensor = _read_json(base_tensor_path)
    focus_manifest = _read_json(focus_manifest_path)
    if base_input.get("world_knowledge_included") is not False or focus_manifest.get("world_knowledge_included") is not False:
        raise ValueError("viv_slm_v29_world_knowledge_policy_violation")
    if base_input.get("validation_unchanged_from_v17") is not True:
        raise ValueError("viv_slm_v29_base_validation_contract_missing")
    tokenizer = _v25.CharacterTokenizer(_read_json(base_vocab_path)["vocab"])
    focus_rows = [row for row in _read_jsonl(focus_dataset_root / "train.jsonl") if str(row.get("response") or "") in CANONICAL_GREETING_RESPONSES]
    if len(focus_rows) != 9:
        raise ValueError(f"viv_slm_v29_greeting_row_count:{len(focus_rows)}")
    validation_ids = {str(row["example_id"]) for row in _read_jsonl(focus_dataset_root / "validation.jsonl")}
    if validation_ids.intersection({str(row["example_id"]) for row in focus_rows}):
        raise ValueError("viv_slm_v29_focus_validation_overlap")

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_vocab_path, output_dir / "VOCAB.json")
    tensor_dir = output_dir / "tensor_dataset"
    shutil.copytree(base_input_root / "tensor_dataset", tensor_dir)
    train_manifest = base_tensor["splits"]["train"]
    focus_chunks: list[dict[str, Any]] = []
    for _ in range(FOCUS_REPEATS):
        for row in focus_rows:
            focus_chunks.extend(_v25._focused_chunks(row, tokenizer))
    focus_inputs = [item["inputs"] for item in focus_chunks]
    focus_targets = [item["targets"] for item in focus_chunks]
    focus_masks = [item["loss_mask"] for item in focus_chunks]
    focus_ids = [str(item["source_example_id"]) for item in focus_chunks]
    focus_shards = _v25._write_shards(
        output=tensor_dir / "train",
        inputs=focus_inputs,
        targets=focus_targets,
        masks=focus_masks,
        view="v29_greeting_only_focus",
        source_ids=focus_ids,
        file_index_start=len(train_manifest["shards"]),
    )
    train_manifest["focused_examples"] += len(focus_inputs)
    train_manifest["focused_rows"] += len(focus_rows)
    train_manifest["examples"] += len(focus_inputs)
    train_manifest["masked_target_tokens"] += sum(sum(mask) for mask in focus_masks)
    train_manifest["additional_greeting_examples"] = len(focus_inputs)
    train_manifest["additional_greeting_rows"] = len(focus_rows)
    train_manifest["additional_greeting_repeats"] = FOCUS_REPEATS
    train_manifest["shards"].extend(focus_shards)
    base_tensor["schema_version"] = SCHEMA_VERSION
    base_tensor["objective"]["kind"] = "v28_canonical_disambiguation_plus_v29_greeting_only_focus"
    base_tensor["objective"]["greeting_only_repeats"] = FOCUS_REPEATS
    base_tensor["objective"]["greeting_only_rows"] = len(focus_rows)
    base_tensor["source_policy"] = "v28_inputs_plus_v24_train_only_canonical_greeting_rows"
    _write_json(tensor_dir / "MANIFEST.json", base_tensor)
    input_manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "parent_input_manifest": str(base_manifest_path).replace("\\", "/"),
        "parent_input_manifest_sha256": _sha256(base_manifest_path),
        "focus_dataset_manifest": str(focus_manifest_path).replace("\\", "/"),
        "focus_dataset_manifest_sha256": _sha256(focus_manifest_path),
        "vocab_manifest": str((output_dir / "VOCAB.json")).replace("\\", "/"),
        "vocab_manifest_sha256": _sha256(output_dir / "VOCAB.json"),
        "tensor_manifest": str((tensor_dir / "MANIFEST.json")).replace("\\", "/"),
        "tensor_manifest_sha256": _sha256(tensor_dir / "MANIFEST.json"),
        "payload_schema_version": _v25.PAYLOAD_SCHEMA_VERSION,
        "vocab_size": tokenizer.vocab_size,
        "context_length": _v25.CONTEXT_LENGTH,
        "termination_marker": _v25.TERMINATION_MARKER,
        "response_only_loss": True,
        "base_replay": "v28_canonical_disambiguation_unchanged",
        "focus_view": "v29_greeting_only_train_only",
        "greeting_only_repeats": FOCUS_REPEATS,
        "greeting_only_rows": len(focus_rows),
        "greeting_response_count": len(CANONICAL_GREETING_RESPONSES),
        "base_train_examples": train_manifest["base_examples"],
        "prior_focused_train_examples": base_tensor["splits"]["train"]["focused_examples"] - len(focus_inputs),
        "additional_greeting_examples": len(focus_inputs),
        "focused_train_examples": train_manifest["focused_examples"],
        "focused_train_rows": train_manifest["focused_rows"],
        "train_examples": train_manifest["examples"],
        "validation_examples": base_tensor["splits"]["validation"]["examples"],
        "validation_unchanged_from_v17": True,
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "training_authorized": False,
        "run_authorized": False,
        "lease_opened": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "train_exactly_250_steps_from_v28_step_250_after_named_authorization",
    }
    _write_json(output_dir / "INPUT_MANIFEST.json", input_manifest)
    return input_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-input-root", type=Path, default=BASE_INPUT_ROOT)
    parser.add_argument("--focus-dataset-root", type=Path, default=FOCUS_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(base_input_root=args.base_input_root, focus_dataset_root=args.focus_dataset_root, output_dir=args.output_dir)
    print(json.dumps({
        "status": "VIV_SLM_V29_GREETING_FOCUS_INPUTS_PASS",
        "output_dir": str(args.output_dir).replace("\\", "/"),
        "train_examples": manifest["train_examples"],
        "base_train_examples": manifest["base_train_examples"],
        "prior_focused_train_examples": manifest["prior_focused_train_examples"],
        "additional_greeting_examples": manifest["additional_greeting_examples"],
        "greeting_only_rows": manifest["greeting_only_rows"],
        "validation_examples": manifest["validation_examples"],
        "training_authorized": manifest["training_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
