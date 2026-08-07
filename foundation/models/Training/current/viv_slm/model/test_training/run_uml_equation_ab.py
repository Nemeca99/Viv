#!/usr/bin/env python3
"""A/B: Codex-only vs response-masked UML equation mix (sandbox).

Hypothesis (v2)
---------------
H1: From the same specialist warm-start, matched +N steps with a lower-ratio
response-masked UML mix holds Codex val (~96%) while improving UML response NLL.

Policy
------
- Never mutates Codex trees or live efficient/deep specialist files.
- Writes under test_training/runs/uml_equation_ab_v2/ only.
- Primary metric: Codex v61 validation (response-only).
- Secondary: UML mix validation (response-only after ``Viv:``).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
EFF = SANDBOX / "checkpoints" / "efficient" / "specialist.pt"
OUT_DIR = SANDBOX / "runs" / "uml_equation_ab_v2"
RECEIPT_JSON = SANDBOX / "runs" / "uml_equation_ab_v2_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_equation_ab_v2_latest.md"
# Keep pointer for operators looking at the prior path.
RECEIPT_JSON_ALIAS = SANDBOX / "runs" / "uml_equation_ab_latest.json"
RECEIPT_MD_ALIAS = SANDBOX / "runs" / "uml_equation_ab_latest.md"
RECIPE_PATH = SANDBOX / "uml_mix_recipe.json"


def load_mix_recipe(path: Path = RECIPE_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {
            "mix_ratio": 0.15,
            "prefer_cheap_boost": 2.0,
            "rid_residual_weight": 0.0,
            "steps_default": 750,
            "batch_size": 64,
            "lr": 7e-6,
            "seed": 42,
            "log_every": 100,
        }
    return json.loads(path.read_text(encoding="utf-8"))

if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import (  # noqa: E402
    CODEX_MAX_GRAD_NORM,
    CODEX_WEIGHT_DECAY,
    IDENTITY_MODEL_CFG,
    evaluate_split,
    load_split,
    masked_batch_loss,
    resolve_codex_dataset,
    weighted_masked_batch_loss,
)
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

Split = tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]

_ROUTE_TARGET_RE = re.compile(
    r"(?:Prefer efficient UML for|Rank UML routes for|UML equivalent for|"
    r"Is this UML valid for)\s*(.)\??",
    re.IGNORECASE,
)
_VIV_RESP_RE = re.compile(r"Viv:\s*([^\n<]+)")


def _ensure_mix_dataset(*, min_surfaces: int = 5000, require_bank: str = "v6_federation") -> Path:
    build = SANDBOX / "build_uml_equation_mix_dataset.py"
    build_json = SANDBOX / "data" / "uml_equation_mix_v1" / "BUILD.json"
    tensor_dir = SANDBOX / "data" / "uml_equation_mix_v1" / "tensor_dataset"
    need_rebuild = True
    if build_json.is_file() and tensor_dir.is_dir():
        try:
            meta = json.loads(build_json.read_text(encoding="utf-8"))
            if (
                int(meta.get("surface_count") or 0) >= min_surfaces
                and bool(meta.get("response_only_loss"))
                and str(meta.get("bank_version") or "") == require_bank
                and bool(meta.get("quality_drills", False))
            ):
                need_rebuild = False
        except Exception:
            need_rebuild = True
    if need_rebuild:
        subprocess.run([str(PY), "-B", str(build)], check=True, cwd=str(SANDBOX))
    if not tensor_dir.is_dir():
        raise FileNotFoundError(f"uml_mix_tensor_missing:{tensor_dir}")
    manifest = json.loads((tensor_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    if not bool(manifest.get("response_only_loss")):
        raise RuntimeError("uml_mix_expected_response_only_masks")
    return tensor_dir


def _load_model(ckpt: Path, tok: CharacterTokenizer, device: torch.device) -> tuple[Any, int]:
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    if str(payload.get("vocab_sha256", "")) != tok.vocab_sha256:
        raise ValueError("uml_ab_vocab_mismatch")
    model = TransformerLanguageModel(tok.vocab_size, **IDENTITY_MODEL_CFG).to(device)
    load_plant_state_dict(
        model,
        payload["model_state_dict"],
        strict=False,
        config=dict(payload.get("config") or IDENTITY_MODEL_CFG),
    )
    start = int((payload.get("train") or {}).get("steps_completed") or 0)
    return model, start


def _sample_batch(
    inputs: torch.Tensor,
    targets: torch.Tensor,
    masks: torch.Tensor | None,
    *,
    batch_size: int,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]:
    n = int(inputs.shape[0])
    idx = torch.randint(0, n, (batch_size,))
    bi = inputs[idx].to(device)
    bt = targets[idx].to(device)
    bm = None if masks is None else masks[idx].to(device)
    return bi, bt, bm


def _batch_prefer_cheap_scale(
    inputs: torch.Tensor,
    tok: CharacterTokenizer,
    *,
    boost: float,
) -> float:
    """If any row looks like a prefer-cheap / Best: drill, return boost else 1.0."""
    if boost <= 1.0:
        return 1.0
    # Inspect a few rows only (cheap heuristic).
    n = min(8, int(inputs.shape[0]))
    markers = ("Prefer efficient UML", "Best:", "Rank UML routes")
    for i in range(n):
        text = tok.decode(inputs[i].detach().cpu().tolist())
        if any(m in text for m in markers):
            return float(boost)
    return 1.0


def _extract_route_pair(text: str) -> tuple[str | None, str | None]:
    """Pull (target_char, proposed_expr) from a UML drill window, else (None, None)."""
    tm = _ROUTE_TARGET_RE.search(text)
    if tm is None:
        return None, None
    ch = tm.group(1)
    vm = _VIV_RESP_RE.search(text)
    if vm is None:
        return ch, None
    prop = vm.group(1).strip()
    if prop.lower().startswith("no "):
        prop = prop[3:].strip()
    # Skip plain-text decode responses and multi-equation dumps.
    if "," in prop:
        return ch, None
    if any(c.isalpha() for c in prop) and not re.search(r"[\d+\-*/()]", prop):
        return ch, None
    if not prop:
        return ch, None
    return ch, prop


def _rid_token_weights(
    inputs: torch.Tensor,
    masks: torch.Tensor | None,
    tok: CharacterTokenizer,
    *,
    rid_weight: float,
    registry: Any,
    route_efficiency_error: Any,
) -> tuple[torch.Tensor | None, float, int]:
    """J: weight response tokens by (1 + w*(1-route_error)) — cheap targets upweighted."""
    if rid_weight <= 0.0 or masks is None:
        return None, 0.0, 0
    bsz = int(inputs.shape[0])
    weights = torch.ones_like(masks, dtype=torch.float32)
    errors: list[float] = []
    scored = 0
    inspect_n = min(bsz, 16)
    for i in range(inspect_n):
        text = tok.decode(inputs[i].detach().cpu().tolist())
        ch, prop = _extract_route_pair(text)
        if not ch or not prop:
            continue
        try:
            info = route_efficiency_error(registry, proposed=prop, target_char=ch)
            err = float(info["error"])
        except Exception:
            continue
        scale = 1.0 + float(rid_weight) * (1.0 - err)
        weights[i] = float(scale)
        errors.append(err)
        scored += 1
    mean_err = float(sum(errors) / len(errors)) if errors else 0.0
    return weights.to(inputs.device), mean_err, scored


def _thermal_token_weights(
    inputs: torch.Tensor,
    masks: torch.Tensor | None,
    tok: CharacterTokenizer,
    *,
    thermal_weight: float,
    registry: Any,
    decide_route_thermal: Any,
) -> tuple[torch.Tensor | None, float, int]:
    """Upweight teacher rows whose Viv equation is the best thermal route for the seal."""
    if thermal_weight <= 0.0 or masks is None:
        return None, 0.0, 0
    bsz = int(inputs.shape[0])
    weights = torch.ones_like(masks, dtype=torch.float32)
    scores: list[float] = []
    scored = 0
    inspect_n = min(bsz, 16)
    for i in range(inspect_n):
        text = tok.decode(inputs[i].detach().cpu().tolist())
        ch, prop = _extract_route_pair(text)
        if not ch or not prop:
            continue
        try:
            thermal = decide_route_thermal(
                registry, target_char=ch, proposals=[prop], include_registry_pool=True
            )
            if thermal.get("status") != "PASS":
                continue
            best = str(thermal["selected"])
            ts = float(thermal["selected_thermal_score"])
            is_best = best == prop
            if is_best:
                scale = 1.0 + float(thermal_weight)
            else:
                # Find proposed row heat among ranked valids.
                own = next(
                    (r for r in thermal.get("ranked") or [] if r.get("expr") == prop),
                    None,
                )
                if own is None:
                    # Proposed invalid for seal — heavy downweight.
                    scale = max(0.25, 1.0 - float(thermal_weight))
                else:
                    gap = float(own["thermal_score"]) - ts
                    scale = max(0.25, 1.0 - float(thermal_weight) * gap)
            weights[i] = float(scale)
            scores.append(ts)
            scored += 1
        except Exception:
            continue
    mean_ts = float(sum(scores) / len(scores)) if scores else 0.0
    return weights.to(inputs.device), mean_ts, scored


def _train_leg(
    *,
    name: str,
    warm_ckpt: Path,
    steps: int,
    batch_size: int,
    lr: float,
    mix_ratio: float,
    device: torch.device,
    tok: CharacterTokenizer,
    codex_train: Split,
    uml_train: Split,
    seed: int,
    log_every: int,
    prefer_cheap_boost: float = 1.0,
    rid_residual_weight: float = 0.0,
    thermal_route_weight: float = 0.0,
    plant_sn_gate: bool = False,
    plant_sn_refresh_every: int = 50,
    out_dir: Path | None = None,
) -> Path:
    torch.manual_seed(seed)
    model, start_step = _load_model(warm_ckpt, tok, device)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=CODEX_WEIGHT_DECAY)
    c_in, c_tg, c_mask = codex_train
    u_in, u_tg, u_mask = uml_train
    history: list[dict[str, Any]] = []
    target_step = start_step + steps
    step = start_step
    uml_steps = 0
    prefer_hits = 0
    rid_scored_batches = 0
    thermal_scored_batches = 0
    plant_shed_hits = 0
    plant_last: dict[str, Any] | None = None
    registry = None
    route_efficiency_error = None
    compare_equations_thermal = None
    decide_route_thermal = None
    dose_decision = None
    if rid_residual_weight > 0.0 or thermal_route_weight > 0.0:
        from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry
        from lib.uml_route_governor import route_efficiency_error as _ree
        from lib.uml_thermal_route import decide_route_thermal as _drt

        registry = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
        route_efficiency_error = _ree
        decide_route_thermal = _drt
    if plant_sn_gate:
        from lib.uml_plant_sn_gate import dose_decision as _dose

        dose_decision = _dose

    while step < target_step:
        effective_mix = float(mix_ratio)
        if plant_sn_gate and dose_decision is not None:
            if plant_last is None or (step - start_step) % max(1, int(plant_sn_refresh_every)) == 0:
                plant_last = dose_decision(base_mix=float(mix_ratio))
            effective_mix = float(plant_last["effective_mix"])
            if plant_last.get("action") != "ADD_FUEL":
                plant_shed_hits += 1
        use_uml = effective_mix > 0.0 and float(torch.rand(()).item()) < effective_mix
        if use_uml:
            bi, bt, bm = _sample_batch(u_in, u_tg, u_mask, batch_size=batch_size, device=device)
            uml_steps += 1
        else:
            bi, bt, bm = _sample_batch(c_in, c_tg, c_mask, batch_size=batch_size, device=device)
        opt.zero_grad(set_to_none=True)
        logits = model(bi)
        rid_mean = 0.0
        rid_n = 0
        thermal_mean = 0.0
        thermal_n = 0
        tw = None
        if use_uml and bm is not None and registry is not None:
            if rid_residual_weight > 0.0:
                tw, rid_mean, rid_n = _rid_token_weights(
                    bi,
                    bm,
                    tok,
                    rid_weight=rid_residual_weight,
                    registry=registry,
                    route_efficiency_error=route_efficiency_error,
                )
                if tw is not None and rid_n > 0:
                    rid_scored_batches += 1
            if thermal_route_weight > 0.0 and decide_route_thermal is not None:
                tw2, thermal_mean, thermal_n = _thermal_token_weights(
                    bi,
                    bm,
                    tok,
                    thermal_weight=thermal_route_weight,
                    registry=registry,
                    decide_route_thermal=decide_route_thermal,
                )
                if tw2 is not None and thermal_n > 0:
                    thermal_scored_batches += 1
                    tw = tw2 if tw is None else tw * tw2
        if tw is not None and (rid_n > 0 or thermal_n > 0):
            loss, acc = weighted_masked_batch_loss(model, logits, bt, bm, token_weights=tw)
        else:
            loss, acc = masked_batch_loss(model, logits, bt, bm)
        scale = 1.0
        if use_uml and prefer_cheap_boost > 1.0:
            scale = _batch_prefer_cheap_scale(bi, tok, boost=prefer_cheap_boost)
            if scale > 1.0:
                prefer_hits += 1
                loss = loss * scale
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), CODEX_MAX_GRAD_NORM)
        opt.step()
        step += 1
        if step == start_step + 1 or step == target_step or step % log_every == 0:
            history.append(
                {
                    "step": step,
                    "loss": float(loss.detach().cpu()),
                    "acc": float(acc),
                    "source": "uml" if use_uml else "codex",
                    "prefer_scale": scale,
                    "rid_mean_error": rid_mean,
                    "rid_scored_rows": rid_n,
                    "thermal_mean_score": thermal_mean,
                    "thermal_scored_rows": thermal_n,
                    "effective_mix": effective_mix,
                    "plant_action": None if plant_last is None else plant_last.get("action"),
                    "plant_s_n": None if plant_last is None else plant_last.get("plant_s_n"),
                }
            )
            print(
                f"UML_AB_{name} step={step}/{target_step} "
                f"loss={float(loss):.4f} acc={float(acc):.4f} src={'uml' if use_uml else 'codex'}"
                + (
                    f" mix={effective_mix:.3f}/{mix_ratio:.3f} plant={plant_last.get('action')}"
                    if plant_sn_gate and plant_last
                    else ""
                ),
                flush=True,
            )

    dest = out_dir or OUT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{name}.pt"
    payload = {
        "schema_version": "uml_equation_ab_ckpt_v2",
        "sandbox_only": True,
        "originals_untouched": True,
        "leg": name,
        "mix_ratio": mix_ratio,
        "uml_steps": uml_steps,
        "prefer_cheap_boost": float(prefer_cheap_boost),
        "prefer_hits": int(prefer_hits),
        "rid_residual_weight": float(rid_residual_weight),
        "rid_scored_batches": int(rid_scored_batches),
        "thermal_route_weight": float(thermal_route_weight),
        "thermal_scored_batches": int(thermal_scored_batches),
        "plant_sn_gate": bool(plant_sn_gate),
        "plant_shed_hits": int(plant_shed_hits),
        "plant_last": plant_last,
        "response_masked_uml": True,
        "vocab_size": tok.vocab_size,
        "vocab_sha256": tok.vocab_sha256,
        "config": {"vocab_size": tok.vocab_size, **IDENTITY_MODEL_CFG},
        "model_state_dict": model.state_dict(),
        "train": {"steps_completed": step, "from_steps": start_step, "added_steps": steps},
        "training_history": history,
    }
    torch.save(payload, out)
    return out


def _metrics(
    ckpt: Path,
    *,
    tok: CharacterTokenizer,
    device: torch.device,
    codex_val: Split,
    uml_val: Split,
    batch_size: int,
) -> dict[str, float]:
    model, _ = _load_model(ckpt, tok, device)
    model.eval()
    c_in, c_tg, c_mask = codex_val
    u_in, u_tg, u_mask = uml_val
    c = evaluate_split(model, c_in, c_tg, device=device, batch_size=batch_size, loss_masks=c_mask)
    u = evaluate_split(model, u_in, u_tg, device=device, batch_size=batch_size, loss_masks=u_mask)
    return {
        "codex_nll": float(c["nll"]),
        "codex_acc": float(c["token_accuracy"]),
        "codex_ppl": float(c["perplexity"]),
        "codex_tokens": float(c["tokens"]),
        "uml_nll": float(u["nll"]),
        "uml_acc": float(u["token_accuracy"]),
        "uml_ppl": float(u["perplexity"]),
        "uml_tokens": float(u["tokens"]),
    }


def _verdict(delta_acc: float, delta_nll: float, *, min_acc: float = 0.0005) -> str:
    if abs(delta_acc) < min_acc and abs(delta_nll) < 0.001:
        return "INCONCLUSIVE"
    if delta_acc >= min_acc and delta_nll <= 0.0:
        return "PILOT_BETTER"
    if delta_acc <= -min_acc and delta_nll >= 0.0:
        return "BASELINE_BETTER"
    if delta_acc >= min_acc:
        return "PILOT_ACC_UP_MIXED_NLL"
    if delta_acc <= -min_acc:
        return "PILOT_ACC_DOWN_MIXED_NLL"
    return "INCONCLUSIVE"


def _codex_hold(delta_acc: float, *, tol: float = 0.001) -> bool:
    return delta_acc >= -tol


def main() -> int:
    recipe = load_mix_recipe()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=int(recipe.get("steps_default", 750)))
    parser.add_argument("--batch-size", type=int, default=int(recipe.get("batch_size", 64)))
    parser.add_argument("--lr", type=float, default=float(recipe.get("lr", 7e-6)))
    parser.add_argument("--mix-ratio", type=float, default=float(recipe.get("mix_ratio", 0.15)))
    parser.add_argument("--seed", type=int, default=int(recipe.get("seed", 42)))
    parser.add_argument("--log-every", type=int, default=int(recipe.get("log_every", 100)))
    parser.add_argument(
        "--prefer-cheap-boost",
        type=float,
        default=float(recipe.get("prefer_cheap_boost", 2.0)),
        help="Multiply UML loss when batch looks like prefer-cheap/Best drills (G/H).",
    )
    parser.add_argument(
        "--rid-residual-weight",
        type=float,
        default=float(recipe.get("rid_residual_weight", 0.0)),
        help="J: upweight cheap-route teacher rows by 1+w*(1-route_error).",
    )
    parser.add_argument(
        "--thermal-route-weight",
        type=float,
        default=float(recipe.get("thermal_route_weight", 0.0)),
        help="Upweight teacher rows matching best thermal-efficient sealed route.",
    )
    parser.add_argument("--recipe", type=Path, default=RECIPE_PATH)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.recipe.is_file() and args.recipe.resolve() != RECIPE_PATH.resolve():
        recipe = load_mix_recipe(args.recipe)

    if not EFF.is_file():
        raise FileNotFoundError(f"uml_ab_missing_warm_start:{EFF}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    uml_tensor = _ensure_mix_dataset()
    mix_build = json.loads(
        (SANDBOX / "data" / "uml_equation_mix_v1" / "BUILD.json").read_text(encoding="utf-8")
    )
    _, vocab_path, codex_tensor = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)

    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    codex_train = load_split(codex_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_train = load_split(uml_tensor, "train", vocab_size=tok.vocab_size, response_only_loss=True)
    uml_val = load_split(uml_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

    warm = OUT_DIR / "warm_start.pt"
    shutil.copy2(EFF, warm)
    start_metrics = _metrics(
        warm, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )

    baseline_ckpt = _train_leg(
        name="baseline_codex_only",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=0.0,
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed),
        log_every=int(args.log_every),
        prefer_cheap_boost=1.0,
        rid_residual_weight=0.0,
        thermal_route_weight=0.0,
    )
    pilot_ckpt = _train_leg(
        name="pilot_uml_mix_masked",
        warm_ckpt=warm,
        steps=int(args.steps),
        batch_size=int(args.batch_size),
        lr=float(args.lr),
        mix_ratio=float(args.mix_ratio),
        device=device,
        tok=tok,
        codex_train=codex_train,
        uml_train=uml_train,
        seed=int(args.seed) + 1,
        log_every=int(args.log_every),
        prefer_cheap_boost=float(args.prefer_cheap_boost),
        rid_residual_weight=float(args.rid_residual_weight),
        thermal_route_weight=float(args.thermal_route_weight),
    )

    baseline = _metrics(
        baseline_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    pilot = _metrics(
        pilot_ckpt, tok=tok, device=device, codex_val=codex_val, uml_val=uml_val, batch_size=args.batch_size
    )
    delta = {
        "codex_acc": pilot["codex_acc"] - baseline["codex_acc"],
        "codex_nll": pilot["codex_nll"] - baseline["codex_nll"],
        "uml_acc": pilot["uml_acc"] - baseline["uml_acc"],
        "uml_nll": pilot["uml_nll"] - baseline["uml_nll"],
    }
    verdict = _verdict(delta["codex_acc"], delta["codex_nll"])
    hold = _codex_hold(delta["codex_acc"])
    uml_improved = delta["uml_nll"] < -0.05 or delta["uml_acc"] > 0.02
    objective = "PASS" if hold and uml_improved else ("HOLD_ONLY" if hold else "FAIL_HOLD")
    start_step = int(torch.load(warm, map_location="cpu", weights_only=False)["train"]["steps_completed"])

    receipt: dict[str, Any] = {
        "schema_version": "uml_equation_ab_v2",
        "status": "PASS",
        "verdict_primary_codex": verdict,
        "objective_hold_plus_uml": objective,
        "codex_hold": hold,
        "uml_improved": uml_improved,
        "hypothesis": (
            "Matched +N steps with lower-ratio response-masked UML mix "
            "(v5 quality/prefer-cheap drills) holds Codex ~96% and improves UML "
            "response NLL/acc vs Codex-only."
        ),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_only": True,
        "replaces_codex": False,
        "specialists_untouched": True,
        "response_masked_uml": True,
        "bank_version": mix_build.get("bank_version"),
        "bank_surfaces": mix_build.get("surface_count"),
        "bank_dialogues": mix_build.get("dialogue_rows"),
        "warm_start": str(EFF).replace("\\", "/"),
        "start_steps": start_step,
        "added_steps": int(args.steps),
        "batch_size": int(args.batch_size),
        "lr": float(args.lr),
        "mix_ratio_pilot": float(args.mix_ratio),
        "prefer_cheap_boost": float(args.prefer_cheap_boost),
        "rid_residual_weight": float(args.rid_residual_weight),
        "thermal_route_weight": float(args.thermal_route_weight),
        "recipe_path": str(Path(args.recipe)).replace("\\", "/"),
        "device": str(device),
        "start": start_metrics,
        "baseline": baseline,
        "pilot": pilot,
        "delta_pilot_minus_baseline": delta,
        "sample_validity": {
            "codex_val_tokens_baseline": baseline["codex_tokens"],
            "codex_val_tokens_pilot": pilot["codex_tokens"],
            "uml_val_tokens_baseline": baseline["uml_tokens"],
            "uml_val_tokens_pilot": pilot["uml_tokens"],
            "note": "Both metrics are response-masked; Codex val is primary hold bar.",
        },
        "artifacts": {
            "warm": str(warm).replace("\\", "/"),
            "baseline": str(baseline_ckpt).replace("\\", "/"),
            "pilot": str(pilot_ckpt).replace("\\", "/"),
            "uml_tensor": str(uml_tensor).replace("\\", "/"),
        },
    }
    for path in (RECEIPT_JSON, RECEIPT_JSON_ALIAS):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")

    md = "\n".join(
        [
            "# UML Equation A/B v2 (masked + longer)",
            "",
            f"- Codex verdict: **{verdict}**",
            f"- Objective (hold Codex + improve UML): **{objective}**",
            f"- Steps: {start_step} + {args.steps} (matched)",
            f"- Pilot mix_ratio: {args.mix_ratio}",
            f"- Prefer-cheap boost: {args.prefer_cheap_boost}",
            f"- RID residual weight: {args.rid_residual_weight}",
            f"- Thermal route weight: {args.thermal_route_weight}",
            "- UML loss: response-only after `Viv:`",
            "",
            "## Codex validation (primary hold)",
            f"- Baseline acc={baseline['codex_acc']:.6f} nll={baseline['codex_nll']:.6f}",
            f"- Pilot    acc={pilot['codex_acc']:.6f} nll={pilot['codex_nll']:.6f}",
            f"- Delta    acc={delta['codex_acc']:+.6f} nll={delta['codex_nll']:+.6f}",
            "",
            "## UML response validation (secondary)",
            f"- Baseline acc={baseline['uml_acc']:.6f} nll={baseline['uml_nll']:.6f}",
            f"- Pilot    acc={pilot['uml_acc']:.6f} nll={pilot['uml_nll']:.6f}",
            f"- Delta    acc={delta['uml_acc']:+.6f} nll={delta['uml_nll']:+.6f}",
            "",
            f"Receipt: `{RECEIPT_JSON.as_posix()}`",
            "",
        ]
    )
    for path in (RECEIPT_MD, RECEIPT_MD_ALIAS):
        path.write_text(md, encoding="utf-8", newline="\n")
    print(
        f"UML_EQUATION_AB_V2_{objective} codex={verdict} "
        f"codex_acc {baseline['codex_acc']:.6f}->{pilot['codex_acc']:.6f} "
        f"d={delta['codex_acc']:+.6f} "
        f"uml_nll {baseline['uml_nll']:.4f}->{pilot['uml_nll']:.4f} "
        f"uml_acc {baseline['uml_acc']:.4f}->{pilot['uml_acc']:.4f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
