#!/usr/bin/env python3
"""Sandbox smoke: load specialists, prove distinct fingerprints + shared vocab,
stub CPU→GPU→CPU verify sandwich via speak_lanes (import only; no parent writes).

Writes: sandbox runs/ + sealed receipt under model/artifacts_local/experiments/.
Never mutates Codex/operator campaign trees or checkpoints outside test_training/.
"""
from __future__ import annotations

from hashlib import sha256
import json
import sys
from pathlib import Path
from typing import Any

import torch
from torch import Tensor, nn

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime, detect_hardware  # noqa: E402
from sandbox_paths import (  # noqa: E402
    DEEP_CKPT,
    EFFICIENT_CKPT,
    RECEIPT_PATH,
    RUNS_DIR,
    SCHEMA_RECEIPT,
    VOCAB_MANIFEST,
)
from speak_lanes import speak_viv, speak_viv_parallel  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

# Originals that must remain untouched (mtime/size check).
_PROTECTED = (
    MODEL / "train.py",
    MODEL / "speak_lanes.py",
    MODEL / "transformer.py",
    MODEL / "run_h_speak_parallel_experiment.py",
)


def _fingerprint_module(m: nn.Module) -> str:
    blob: list[str] = []
    for key, tensor in sorted(m.state_dict().items()):
        if torch.is_tensor(tensor):
            blob.append(
                f"{key}:{float(tensor.detach().float().sum())}:{tuple(tensor.shape)}"
            )
    return sha256("|".join(blob).encode("utf-8")).hexdigest().upper()


def _load_specialist(path: Path, tok: CharacterTokenizer) -> tuple[TransformerLanguageModel, dict]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict) or "model_state_dict" not in payload:
        raise ValueError(f"sandbox_ckpt_invalid:{path}")
    if int(payload.get("vocab_size", -1)) != tok.vocab_size:
        raise ValueError("sandbox_ckpt_vocab_size_mismatch")
    if str(payload.get("vocab_sha256", "")) != tok.vocab_sha256:
        raise ValueError("sandbox_ckpt_vocab_sha_mismatch")
    cfg = dict(payload.get("config") or {})
    model = TransformerLanguageModel(
        vocab_size=tok.vocab_size,
        context_length=int(cfg.get("context_length", 32)),
        embedding_width=int(cfg.get("embedding_width", 64)),
        num_heads=int(cfg.get("num_heads", 4)),
        head_size=int(cfg.get("head_size", 16)),
        num_layers=int(cfg.get("num_layers", 2)),
        dropout=float(cfg.get("dropout", 0.0)),
        position_encoding=str(cfg.get("position_encoding", "rope")),
        fused_qkv=bool(cfg.get("fused_qkv", False)),
    )
    load_plant_state_dict(
        model,
        payload["model_state_dict"],
        strict=False,
        config=cfg,
    )
    model.eval()
    return model, payload


def _speak_viv_sandwich_stub(
    model_efficient: nn.Module,
    model_deep: nn.Module,
    context_ids: Tensor,
    *,
    decode_fn,
    front_max: int = 8,
    deep_max: int = 16,
    verify_max: int = 8,
) -> dict[str, Any]:
    """CPU speculate → GPU deep → CPU verify (prefix accept). Sandbox stub only."""

    front = speak_viv(
        model_efficient,
        context_ids,
        lane="efficient",
        max_new_tokens=front_max,
        decode_fn=decode_fn,
        stamp_master_rid=False,
        configure_runtime=True,
    )
    draft_ids = front["ids"]
    deep = speak_viv(
        model_deep,
        draft_ids,
        lane="deep",
        max_new_tokens=deep_max,
        decode_fn=decode_fn,
        stamp_master_rid=False,
        configure_runtime=False,
    )
    # CPU verifier: re-draft from original prompt; accept matching prefix of GPU new tokens.
    verify = speak_viv(
        model_efficient,
        context_ids,
        lane="efficient",
        max_new_tokens=verify_max,
        decode_fn=decode_fn,
        stamp_master_rid=False,
        configure_runtime=False,
    )
    prompt_len = int(context_ids.shape[-1] if context_ids.ndim > 1 else context_ids.numel())
    gpu_full = deep["ids"][0].detach().cpu().tolist()
    cpu_full = verify["ids"][0].detach().cpu().tolist()
    gpu_new = gpu_full[prompt_len:]
    cpu_new = cpu_full[prompt_len:]
    accept = 0
    for a, b in zip(gpu_new, cpu_new):
        if a != b:
            break
        accept += 1
    accepted = gpu_new[:accept]
    rejected = gpu_new[accept:]
    # Merge: prompt + accepted GPU prefix + CPU continuation after mismatch (if any).
    merged = gpu_full[:prompt_len] + accepted + cpu_new[accept:]
    receipt = {
        "schema_version": "viv_slm_sandbox_sandwich_stub_v1",
        "path": "cpu_speculate_gpu_deep_cpu_verify",
        "prompt_tokens": prompt_len,
        "front_new_tokens": int(front["receipt"]["new_tokens"]),
        "deep_new_tokens": int(deep["receipt"]["new_tokens"]),
        "verify_new_tokens": int(verify["receipt"]["new_tokens"]),
        "accepted_prefix_len": accept,
        "rejected_suffix_len": len(rejected),
        "efficient_device": front["receipt"]["device"],
        "deep_device": deep["receipt"]["device"],
        "piston_actuated": False,
        "sandbox_only": True,
    }
    text = decode_fn(merged) if decode_fn is not None else None
    return {
        "ids": torch.tensor([merged], dtype=torch.long),
        "text": text,
        "receipt": receipt,
        "front": front,
        "deep": deep,
        "verify": verify,
    }


def _stat_snapshot(paths: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in paths:
        key = str(path).replace("\\", "/")
        if not path.is_file():
            out[key] = {"exists": False}
            continue
        st = path.stat()
        out[key] = {
            "exists": True,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
        }
    return out


def _peek_checkpoint_meta(path: Path) -> dict:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    return payload if isinstance(payload, dict) else {}


def _load_vocab_for_checkpoints(meta_e: dict, meta_d: dict) -> CharacterTokenizer:
    """Prefer Codex vocab path sealed in checkpoint dataset meta."""

    for meta in (meta_e, meta_d):
        dataset = meta.get("dataset") or {}
        root = str(dataset.get("root") or "")
        if root and "identity" in root.replace("\\", "/"):
            vocab = Path(root) / "VOCAB.json"
            if vocab.is_file():
                return CharacterTokenizer.from_manifest(vocab)
    if VOCAB_MANIFEST.is_file():
        return CharacterTokenizer.from_manifest(VOCAB_MANIFEST)
    raise FileNotFoundError("sandbox_vocab_missing_for_smoke")


def main() -> int:
    before = _stat_snapshot(_PROTECTED)

    if not EFFICIENT_CKPT.is_file() or not DEEP_CKPT.is_file():
        # Auto-mint inside sandbox if missing (still no writes outside sandbox).
        from mint_specialists import main as mint_main

        code = mint_main()
        if code != 0:
            print("VIV_SANDBOX_SMOKE_FAIL mint_failed")
            return code

    peek_e = _peek_checkpoint_meta(EFFICIENT_CKPT)
    peek_d = _peek_checkpoint_meta(DEEP_CKPT)
    tok = _load_vocab_for_checkpoints(peek_e, peek_d)
    efficient, meta_e = _load_specialist(EFFICIENT_CKPT, tok)
    deep, meta_d = _load_specialist(DEEP_CKPT, tok)

    fp_e = _fingerprint_module(efficient)
    fp_d = _fingerprint_module(deep)
    # Prefer sealed fingerprint from checkpoint payload when present.
    sealed_e = str(meta_e.get("weight_fingerprint") or fp_e)
    sealed_d = str(meta_d.get("weight_fingerprint") or fp_d)

    configure_plant_runtime(device="cpu")
    prompt = torch.tensor([tok.encode("User: Hello, Viv.\nViv:")], dtype=torch.long)

    # Clone-of-same must be rejected.
    clone_rejected = False
    try:
        speak_viv_parallel(efficient, efficient, prompt, allow_clone_smoke=False)
    except ValueError as exc:
        clone_rejected = "distinct_identity_specialists" in str(exc)

    parallel = speak_viv_parallel(
        efficient,
        deep,
        prompt,
        efficient_max_new=16,
        deep_max_new=24,
        decode_fn=tok.decode,
        stamp_master_rid=False,
        allow_clone_smoke=False,
    )
    sandwich = _speak_viv_sandwich_stub(
        efficient,
        deep,
        prompt,
        decode_fn=tok.decode,
        front_max=8,
        deep_max=16,
        verify_max=8,
    )

    after = _stat_snapshot(_PROTECTED)
    originals_untouched = before == after

    vocab_match = (
        int(meta_e["vocab_size"]) == int(meta_d["vocab_size"]) == tok.vocab_size
        and str(meta_e["vocab_sha256"]) == str(meta_d["vocab_sha256"]) == tok.vocab_sha256
    )
    distinct = sealed_e != sealed_d and fp_e != fp_d
    ckpt_under_sandbox = (
        "test_training" in str(EFFICIENT_CKPT)
        and "test_training" in str(DEEP_CKPT)
    )
    parallel_pass = str(parallel["receipt"].get("status")) == "PASS"
    sandwich_ok = (
        sandwich["receipt"]["efficient_device"] == "cpu"
        and sandwich["receipt"]["accepted_prefix_len"] >= 0
        and sandwich["ids"].shape[1] >= prompt.shape[1]
    )

    gates = {
        "fingerprints_distinct": distinct,
        "vocab_shared": vocab_match,
        "clone_same_module_rejected": clone_rejected,
        "checkpoints_under_sandbox": ckpt_under_sandbox,
        "originals_untouched": originals_untouched,
        "parallel_speak_pass": parallel_pass,
        "sandwich_stub_ok": sandwich_ok,
        "efficient_on_cpu": parallel["receipt"].get("efficient_device") == "cpu",
    }
    status = "PASS" if all(gates.values()) else "FAIL"

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_RECEIPT,
        "experiment_id": "H_sandbox_test_training",
        "hypothesis": (
            "Sandbox-only efficient+deep specialists (shared vocab, distinct weights) "
            "load and speak without mutating Codex/operator originals."
        ),
        "sandbox_only": True,
        "originals_untouched": originals_untouched,
        "operator_authorized_sandbox_train_test": True,
        "source": "freshly_minted_no_live_checkpoints_found_under_viv_slm",
        "status": status,
        "decision": "keep_sandbox" if status == "PASS" else "investigate",
        "paths": {
            "sandbox": str(SANDBOX).replace("\\", "/"),
            "vocab_manifest": str(VOCAB_MANIFEST).replace("\\", "/"),
            "efficient_checkpoint": str(EFFICIENT_CKPT).replace("\\", "/"),
            "deep_checkpoint": str(DEEP_CKPT).replace("\\", "/"),
            "receipt": str(RECEIPT_PATH).replace("\\", "/"),
        },
        "identity": {
            "vocab_size": tok.vocab_size,
            "vocab_sha256": tok.vocab_sha256,
            "vocab_match": vocab_match,
        },
        "weight_fingerprint_efficient": sealed_e,
        "weight_fingerprint_deep": sealed_d,
        "weights_identical": sealed_e == sealed_d,
        "parallel_receipt": {
            k: parallel["receipt"].get(k)
            for k in (
                "status",
                "efficient_device",
                "deep_device",
                "efficient_new_tokens_parallel",
                "deep_new_tokens_parallel",
                "speedup_vs_sequential",
            )
        },
        "sandwich_stub": sandwich["receipt"],
        "sandwich_text_preview": (sandwich.get("text") or "")[:120],
        "protected_originals_before": before,
        "protected_originals_after": after,
        "gates": gates,
        "hardware": detect_hardware(),
        "commands": [
            r"L:\Continue\.venv\Scripts\python.exe -B test_training\mint_specialists.py",
            r"L:\Continue\.venv\Scripts\python.exe -B test_training\run_sandbox_smoke.py",
        ],
    }
    blob = json.dumps(
        {k: v for k, v in receipt.items() if k != "receipt_sha256"},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    receipt["receipt_sha256"] = sha256(blob.encode("utf-8")).hexdigest().upper()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    local_run = RUNS_DIR / "sandbox_smoke_latest.json"
    with local_run.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        handle.write("\n")

    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        handle.write("\n")

    # Re-check originals after receipt write (receipt is allowed; protected list excludes it).
    final_ok = _stat_snapshot(_PROTECTED) == before
    if not final_ok:
        receipt["status"] = "FAIL"
        receipt["gates"]["originals_untouched"] = False
        status = "FAIL"

    print(
        f"VIV_SANDBOX_SMOKE_{status} "
        f"distinct={distinct} vocab={vocab_match} "
        f"originals_untouched={originals_untouched and final_ok} "
        f"sandwich_accept={sandwich['receipt']['accepted_prefix_len']}"
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
