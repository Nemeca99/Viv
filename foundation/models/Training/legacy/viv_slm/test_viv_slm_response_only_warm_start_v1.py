"""Verify the V16 response-only input and warm-start contract."""
from __future__ import annotations

import json
import inspect
from pathlib import Path
import sys

FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.triad_kernel import TRIAD_CONTRACT_VERSION  # noqa: E402
from train_viv_slm_identity_v1 import _load_resume, _load_warm_start, _make_model, train  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
import torch  # noqa: E402

INPUTS = VIV_ROOT / "models" / "viv_slm_identity_personality_v16_response_only" / "inputs"
PARENT_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v15" / "runs" / "identity_personality_steps_2750" / "checkpoint.pt"
RESUME_CHECKPOINT = VIV_ROOT / "models" / "viv_slm_identity_personality_v16_response_only" / "runs" / "response_only_steps_0250" / "checkpoint.pt"


def test_response_only_inputs() -> None:
    manifest = json.loads((INPUTS / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "viv_slm_training_inputs_response_only_v1"
    assert manifest["response_only_loss"] is True
    assert manifest["train_examples"] == 44899
    assert manifest["validation_examples"] == 8672
    assert manifest["training_authorized"] is False
    assert manifest["run_authorized"] is False
    shard = torch.load(INPUTS / "tensor_dataset" / "train" / "shard_00000.pt", map_location="cpu", weights_only=True)
    assert shard["schema_version"] == "viv_slm_response_only_tensor_dataset_v1"
    assert shard["loss_mask"].dtype is torch.bool
    assert bool(shard["loss_mask"].any())


def test_warm_start_loads_weights_without_resume_state() -> None:
    tokenizer = CharacterTokenizer.from_manifest(INPUTS / "VOCAB.json")
    model = _make_model(tokenizer.vocab_size, device=torch.device("cpu"))
    sample = _load_warm_start(PARENT_CHECKPOINT, tokenizer=tokenizer, model=model)
    assert isinstance(sample, str)
    assert model.training is True


def test_resume_contract_preserves_step_and_labels_metadata() -> None:
    tokenizer = CharacterTokenizer.from_manifest(INPUTS / "VOCAB.json")
    model = _make_model(tokenizer.vocab_size, device=torch.device("cpu"))
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.0003)
    start_step, history, _sample, _best_state = _load_resume(
        RESUME_CHECKPOINT,
        tokenizer=tokenizer,
        model=model,
        optimizer=optimizer,
        response_only_loss=True,
    )
    assert start_step == 250
    assert history[-1]["step"] == 250
    source = inspect.getsource(train)
    assert 'initialization = "resume_optimizer_state"' in source
    assert '"resume_checkpoint": str(resume)' in source


def main() -> int:
    assert TRIAD_CONTRACT_VERSION
    test_response_only_inputs()
    test_warm_start_loads_weights_without_resume_state()
    test_resume_contract_preserves_step_and_labels_metadata()
    print({"ok": True, "objective": "response_only_warm_start", "training_authorized": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
