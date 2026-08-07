#!/usr/bin/env python3
"""H_speak_parallel_v2: two differently trained identity specialists, one prompt."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from plant_runtime import configure_plant_runtime, detect_hardware  # noqa: E402
from speak_lanes import speak_viv_parallel  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

OUT = HERE / "artifacts_local" / "experiments" / "H_speak_parallel_identity_pair.json"
BACKUP = "L:/Continue/Viv/foundation/models/Training/backups/cursor_speak_lanes_20260806T013200Z"


def _tiny_train(model: torch.nn.Module, batch: torch.Tensor, steps: int, lr: float) -> None:
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    for _ in range(steps):
        opt.zero_grad(set_to_none=True)
        logits = model(batch[:, :-1])
        loss, _ = model.loss_and_accuracy(logits, batch[:, 1:])
        loss.backward()
        opt.step()
    model.eval()


def main() -> int:
    hypothesis = (
        "Two differently trained specialists sharing Viv identity (same vocab) "
        "run concurrently: CPU-efficient + GPU-deep on one prompt."
    )
    configure_plant_runtime(device="cpu")
    tokenizer = CharacterTokenizer.from_texts(
        ["the dog bites man and the cat sits on the mat\n"]
    )
    cfg = dict(
        vocab_size=tokenizer.vocab_size,
        context_length=32,
        embedding_width=64,
        num_heads=4,
        head_size=16,
        num_layers=2,
        dropout=0.0,
    )
    torch.manual_seed(1)
    efficient = TransformerLanguageModel(**cfg)
    torch.manual_seed(2)
    deep = TransformerLanguageModel(**cfg)

    # Different training pressure → distinct weights, shared identity/vocab.
    text = tokenizer.encode("the dog bites man and the cat sits\n")
    while len(text) < 33:
        text = text + text
    batch = torch.tensor([text[:33]], dtype=torch.long)
    _tiny_train(efficient, batch, steps=8, lr=0.05)
    _tiny_train(deep, batch, steps=40, lr=0.01)

    prompt = torch.tensor([tokenizer.encode("the dog ")], dtype=torch.long)

    # Clone-smoke must be rejected without allow_clone_smoke.
    rejected = False
    try:
        speak_viv_parallel(efficient, efficient, prompt, allow_clone_smoke=False)
    except ValueError as exc:
        rejected = "distinct_identity_specialists" in str(exc)

    result = speak_viv_parallel(
        efficient,
        deep,
        prompt,
        efficient_max_new=24,
        deep_max_new=48,
        decode_fn=tokenizer.decode,
        stamp_master_rid=True,
        allow_clone_smoke=False,
    )
    receipt = dict(result["receipt"])
    receipt["experiment_id"] = "H_speak_parallel_identity_pair"
    receipt["hypothesis"] = hypothesis
    receipt["backup_path"] = BACKUP
    receipt["hardware"] = detect_hardware()
    receipt["clone_same_module_rejected"] = rejected
    receipt["gates"] = dict(receipt.get("gates") or {})
    receipt["gates"]["clone_same_module_rejected"] = rejected
    receipt["decision"] = (
        "keep"
        if receipt.get("status") == "PASS" and rejected
        else "investigate"
    )
    if not rejected:
        receipt["status"] = "FAIL"
        receipt["decision"] = "investigate"
    receipt["efficient_text_preview"] = (
        result["parallel"]["efficient"].get("text") or ""
    )[:120]
    receipt["deep_text_preview"] = (result["parallel"]["deep"].get("text") or "")[:120]
    receipt["commands"] = [
        "L:/Continue/.venv/Scripts/python.exe -B model/run_h_speak_parallel_experiment.py"
    ]
    blob = json.dumps(
        {k: v for k, v in receipt.items() if k != "receipt_sha256"},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    receipt["receipt_sha256"] = sha256(blob.encode("utf-8")).hexdigest().upper()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    print(json.dumps(receipt, indent=2, sort_keys=True, default=str))
    print(f"H_SPEAK_IDENTITY_PAIR_STATUS={receipt['status']}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
