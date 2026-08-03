"""Function-preserving LoRA rank widen (Net2Wider spirit for PEFT adapters)."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.growth_gate import check_growth
from lib.growth_strain import (
    load_growth_config,
    load_state,
    save_growth_config,
    write_state,
    _emit,
)
from lib.paths import FOUNDATION_ROOT

ADAPTER_DIR = FOUNDATION_ROOT / "models" / "gpu" / "viv_voice_lora"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _backup_adapter() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = FOUNDATION_ROOT / "models" / "gpu" / f"viv_voice_lora_pre_grow_{ts}"
    dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "adapter_config.json",
        "adapter_model.safetensors",
        "adapter_model.bin",
        "tokenizer.json",
        "tokenizer_config.json",
        "README.md",
    ):
        src = ADAPTER_DIR / name
        if src.is_file():
            shutil.copy2(src, dst / name)
    meta = {"copied_at": _utc(), "from": str(ADAPTER_DIR).replace("\\", "/")}
    (dst / "backup_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return dst


def widen_lora(*, delta_r: int, force: bool = False) -> dict[str, Any]:
    """Increase LoRA rank by delta_r with zero-pad (identity-preserving at init)."""
    import torch
    from safetensors.torch import load_file, save_file

    delta_r = int(delta_r)
    if delta_r <= 0:
        return {"ok": False, "reason": "delta_r_must_be_positive"}

    # --force skips cooldown only; ceilings + near_dead still bind
    gate = check_growth("lora_widen", delta_r=delta_r, skip_cooldown=bool(force))
    if not gate.get("allowed"):
        return {"ok": False, "reason": "growth_gate_denied", "gate": gate}

    cfg_path = ADAPTER_DIR / "adapter_config.json"
    weight_path = ADAPTER_DIR / "adapter_model.safetensors"
    if not cfg_path.is_file() or not weight_path.is_file():
        return {"ok": False, "reason": "adapter_missing", "path": str(ADAPTER_DIR)}

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    old_r = int(cfg.get("r") or 16)
    new_r = old_r + delta_r
    old_alpha = int(cfg.get("lora_alpha") or 32)
    # Keep alpha/r ratio roughly stable
    new_alpha = max(old_alpha, int(round(old_alpha * (new_r / max(1, old_r)))))

    backup = _backup_adapter()
    tensors = load_file(str(weight_path))
    new_tensors: dict[str, torch.Tensor] = {}
    widened = 0
    for key, tensor in tensors.items():
        t = tensor.detach().cpu().clone()
        if "lora_A" in key:
            # lora_A: (r, in) → (new_r, in); pad rows with zeros
            if t.ndim == 2 and t.shape[0] == old_r:
                pad = torch.zeros((delta_r, t.shape[1]), dtype=t.dtype)
                t = torch.cat([t, pad], dim=0)
                widened += 1
        elif "lora_B" in key:
            # lora_B: (out, r) → (out, new_r); pad cols with zeros
            if t.ndim == 2 and t.shape[1] == old_r:
                pad = torch.zeros((t.shape[0], delta_r), dtype=t.dtype)
                t = torch.cat([t, pad], dim=1)
                widened += 1
        new_tensors[key] = t

    if widened == 0:
        return {"ok": False, "reason": "no_lora_matrices_matched", "old_r": old_r}

    # Unload live voice adapter so files are not locked
    try:
        import sys
        from pathlib import Path as P

        viv = P(__file__).resolve().parents[2]
        if str(viv) not in sys.path:
            sys.path.insert(0, str(viv))
        from voice_core.hf_lora import unload

        unload()
    except Exception:  # noqa: BLE001
        pass

    save_file(new_tensors, str(weight_path))
    cfg["r"] = new_r
    cfg["lora_alpha"] = new_alpha
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    gcfg = load_growth_config()
    gcfg["lora_r"] = new_r
    gcfg["lora_alpha"] = new_alpha
    if new_r >= 32 and gcfg.get("stage") == "hatchling":
        gcfg["stage"] = "drake"
    save_growth_config(gcfg)

    from lib.growth_chamber_ledger import bump_chambers

    chambers = bump_chambers(
        delta=max(1, delta_r),
        reason="lora_widen",
        linked_actuator="lora_widen",
    )

    state = load_state()
    state["pending_growth"] = False
    state["pending_delta_r"] = 0
    state["strain"] = 0.0
    state["last_grow_at"] = _utc()
    state["last_grow"] = {
        "old_r": old_r,
        "new_r": new_r,
        "delta_r": delta_r,
        "widened_tensors": widened,
        "chambers": chambers,
    }
    write_state(state)
    _emit("lora_widen", old_r=old_r, new_r=new_r, delta_r=delta_r, backup=str(backup).replace("\\", "/"))

    return {
        "ok": True,
        "actuator": "lora_widen",
        "old_r": old_r,
        "new_r": new_r,
        "delta_r": delta_r,
        "lora_alpha": new_alpha,
        "widened_tensors": widened,
        "backup": str(backup).replace("\\", "/"),
        "stage": gcfg.get("stage"),
        "chambers": chambers,
        "gate": gate,
    }


def apply_pending_widen() -> dict[str, Any]:
    state = load_state()
    if not state.get("pending_growth"):
        return {"ok": False, "reason": "no_pending_growth"}
    delta = int(state.get("pending_delta_r") or 1)
    return widen_lora(delta_r=delta)
