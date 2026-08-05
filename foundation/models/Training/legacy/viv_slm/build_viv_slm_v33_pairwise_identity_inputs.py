#!/usr/bin/env python3
"""Build a source-grounded pairwise identity correction view for V33.

The two rejected responses are not invented negatives: they are the actual
V32 outputs for its two failed primary probes.  The chosen responses come from
the deterministic CPU identity router.  Rejected text is retained for the
pairwise preference term only and is never admitted as an SFT target.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
V32_PROBE = FOUNDATION / "artifacts" / "auto" / "uml" / "viv_slm_identity_personality_v32_balanced_low_lr" / "probes" / "v15_probe_steps_0250.json"
VOCAB = VIV_ROOT / "models" / "viv_slm_identity_personality_v31_balanced_base" / "inputs" / "VOCAB.json"
DEFAULT_OUTPUT = VIV_ROOT / "models" / "viv_slm_identity_personality_v33_pairwise_identity" / "inputs"
V32_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v32_balanced_low_lr" / "runs" / "balanced_low_lr_steps_0250" / "checkpoint.pt"
V28_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v28_canonical_disambiguation" / "runs" / "canonical_disambiguation_steps_0250" / "checkpoint.pt"
MODEL_ROOT = VIV_ROOT / "models" / "uml_bigram_part3"

INPUT_SCHEMA_VERSION = "viv_slm_v33_pairwise_identity_inputs_v1"
V32_PROBE_SHA256 = "80AF475E99F6C80294377516F505742CDC2FD281D52140760605687CCA17372B"
V32_CHECKPOINT_SHA256 = "EC7065B19C6630B7CF3DD64AE78FD92371A02A4A4E7465EF3206AB6CE30EE2F9"
V28_CHECKPOINT_SHA256 = "99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0"
VOCAB_SHA256 = "00982C5992060D4D55E4843D0726A9823CCB71C46E04FC9E9DFFBCDB1D3F8179"
TARGET_FAILURES = ("greeting", "current_state")
FORBIDDEN = ("master s_n", "master sn", "rid=", "lease", "security state", "internal telemetry")

for path in (FOUNDATION, VIV_ROOT, MODEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.cpu_identity_router import route_identity_query  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"viv_v33_expected_json_object:{path}")
    return value


def _user_query(prompt: str) -> str:
    prefix = "User: "
    suffix = "\nViv:"
    if not prompt.startswith(prefix) or not prompt.endswith(suffix):
        raise ValueError(f"viv_v33_probe_prompt_shape:{prompt!r}")
    return prompt[len(prefix) : -len(suffix)]


def _load_pairs(*, probe_path: Path, tokenizer: CharacterTokenizer) -> list[dict[str, Any]]:
    probe = _read_json(probe_path)
    if _sha256(probe_path) != V32_PROBE_SHA256:
        raise ValueError("viv_v33_v32_probe_hash_mismatch")
    rows = list(probe.get("core_holdout_probes") or []) + list(probe.get("conversation_holdout_probes") or [])
    failures = [row for row in rows if row.get("semantic_pass") is False]
    if tuple(row.get("id") for row in failures) != TARGET_FAILURES:
        raise ValueError(f"viv_v33_expected_failure_order:{[row.get('id') for row in failures]}")
    pairs: list[dict[str, Any]] = []
    for index, row in enumerate(failures):
        query = _user_query(str(row.get("prompt") or ""))
        route = route_identity_query(query)
        expected_intent = "greeting" if row["id"] == "greeting" else "presence"
        if route.get("ok") is not True or route.get("intent_id") != expected_intent:
            raise ValueError(f"viv_v33_cpu_route_mismatch:{row['id']}:{route}")
        chosen = str(route["authorized_text"])
        rejected = str(row.get("response") or "").strip()
        if not rejected or rejected == chosen:
            raise ValueError(f"viv_v33_rejected_response_invalid:{row['id']}")
        folded = rejected.casefold()
        if any(term in folded for term in FORBIDDEN):
            raise ValueError(f"viv_v33_rejected_telemetry:{row['id']}")
        for text in (query, chosen, rejected, "<END>"):
            tokenizer.encode(text)
        pairs.append(
            {
                "pair_id": f"v33-{index:02d}-{row['id']}",
                "intent_id": row["id"],
                "prompt": query,
                "chosen": chosen,
                "rejected": rejected,
                "chosen_source": "cpu_identity_router_authorized_text",
                "rejected_source": "v32_failed_primary_probe_output",
                "source_probe_id": row["id"],
                "source_probe_sha256": V32_PROBE_SHA256,
                "rejected_is_sft_target": False,
                "training_authorized": False,
                "run_authorized": False,
            }
        )
    return pairs


def build(*, probe_path: Path = V32_PROBE, vocab_path: Path = VOCAB, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"viv_v33_input_exists_refuse_overwrite:{output_dir}")
    if _sha256(vocab_path) != VOCAB_SHA256:
        raise ValueError("viv_v33_vocab_hash_mismatch")
    if _sha256(V32_CHECKPOINT) != V32_CHECKPOINT_SHA256:
        raise ValueError("viv_v33_v32_checkpoint_hash_mismatch")
    if _sha256(V28_CHECKPOINT) != V28_CHECKPOINT_SHA256:
        raise ValueError("viv_v33_v28_checkpoint_hash_mismatch")
    tokenizer = CharacterTokenizer.from_manifest(vocab_path)
    pairs = _load_pairs(probe_path=probe_path, tokenizer=tokenizer)
    output_dir.mkdir(parents=True, exist_ok=True)
    pairs_path = output_dir / "PAIRWISE_ROWS.jsonl"
    pairs_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in pairs),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "status": "COMPLETE_TRAINING_CLOSED",
        "model": "Viv-SLM",
        "vocab": str(vocab_path).replace("\\", "/"),
        "vocab_sha256": VOCAB_SHA256,
        "v32_parent_checkpoint": str(V32_CHECKPOINT).replace("\\", "/"),
        "v32_parent_checkpoint_sha256": V32_CHECKPOINT_SHA256,
        "v28_behavior_reference_checkpoint": str(V28_CHECKPOINT).replace("\\", "/"),
        "v28_behavior_reference_checkpoint_sha256": V28_CHECKPOINT_SHA256,
        "source_probe": str(probe_path).replace("\\", "/"),
        "source_probe_sha256": V32_PROBE_SHA256,
        "pairwise_rows": str(pairs_path).replace("\\", "/"),
        "pairwise_rows_sha256": _sha256(pairs_path),
        "pair_count": len(pairs),
        "intents": [row["intent_id"] for row in pairs],
        "objective": {
            "chosen_sft_weight": 1.0,
            "pairwise_weight": 0.75,
            "pairwise_beta": 1.0,
            "pairwise_margin": 0.2,
            "replay_sft_weight": 0.25,
            "replay_anchor_weight": 1.0,
            "rejected_is_sft_target": False,
        },
        "source_policy": "cpu_authorized_chosen_vs_observed_v32_failed_output_pairwise_identity_refinement",
        "knowledge_policy": "external_cpu_retrieval_only",
        "world_knowledge_included": False,
        "telemetry_in_training_responses": False,
        "training_authorized": False,
        "run_authorized": False,
        "promotion_authorized": False,
        "deployment_changed": False,
        "live_model_changed": False,
        "next_step": "warm_start_v32_then_run_exactly_250_steps_after_named_authorization",
    }
    (output_dir / "INPUT_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, default=V32_PROBE)
    parser.add_argument("--vocab", type=Path, default=VOCAB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = build(probe_path=args.probe, vocab_path=args.vocab, output_dir=args.output_dir)
    print(json.dumps({"status": "VIV_SLM_V33_PAIRWISE_IDENTITY_INPUTS_PASS", "pair_count": manifest["pair_count"], "intents": manifest["intents"], "rejected_is_sft_target": manifest["objective"]["rejected_is_sft_target"], "training_authorized": manifest["training_authorized"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
