#!/usr/bin/env python3
"""P2 audit: does the layer survivor prefer cheap UML *without* post-snap?

Measures pre-snap equation text under Prefer-efficient prompts on the current
layer survivor (and optional native speak path). Snap may still run for the
final answer; cheap_raw_rate is what closes P2.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import decide_route, route_efficiency_error  # noqa: E402
from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset  # noqa: E402
from sandbox_paths import EFFICIENT_CKPT  # noqa: E402
from speak_lanes import speak_viv_sandwich  # noqa: E402
from speak_uml_native import speak_uml_native  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402
from uml_speak_pressure import clip_uml_equation_text  # noqa: E402

RECEIPT_JSON = SANDBOX / "runs" / "uml_snap_free_audit_latest.json"
RECEIPT_MD = SANDBOX / "runs" / "uml_snap_free_audit_latest.md"
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
CHARS = list("HAVEiv123+")


def _load(path: Path, tok: CharacterTokenizer, device: torch.device):
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(tok.vocab_size, **IDENTITY_MODEL_CFG).to(device)
    load_plant_state_dict(
        model,
        payload["model_state_dict"],
        strict=False,
        config=dict(payload.get("config") or IDENTITY_MODEL_CFG),
    )
    model.eval()
    return model, payload


def _probe_english_prefer(model_e, model_d, tok, reg, device) -> dict[str, Any]:
    cheap = 0
    match = 0
    snapped_n = 0
    rows = []
    for ch in CHARS:
        if ch not in reg.entries:
            continue
        prompt = f"User: Prefer efficient UML for {ch}\nViv: "
        ids = torch.tensor([tok.encode(prompt)], dtype=torch.long, device=device)
        # deep on CUDA model; efficient verify on CPU copy path via sandwich
        sandwich = speak_viv_sandwich(
            model_e,
            model_d,
            ids.cpu(),
            deep_max=24,
            verify_max=16,
            decode_fn=tok.decode,
            uml_pressure={
                "stoi": tok.stoi,
                "itos": tok.itos,
                "prompt_len": int(ids.shape[1]),
                "hard_mask": False,
                "scale": 0.0,
            },
            uml_pressure_on="deep",
            stamp_master_rid=False,
        )
        snap = sandwich["receipt"].get("prefer_efficient_snap") or {}
        proposed = str(snap.get("proposed") or "")
        deep_text = (sandwich.get("deep") or {}).get("text") or ""
        raw = proposed or clip_uml_equation_text(str(deep_text), prompt)
        final = str(sandwich.get("equation_text") or "")
        try:
            ok = reg.decode_eq(raw) == ch
        except Exception:
            ok = False
        info = route_efficiency_error(reg, proposed=raw if raw else "???", target_char=ch)
        cheap_ok = info.get("kind") == "valid_efficient"
        if ok:
            match += 1
        if cheap_ok:
            cheap += 1
        if snap.get("snapped"):
            snapped_n += 1
        rows.append(
            {
                "char": ch,
                "raw": raw,
                "final": final,
                "raw_kind": info.get("kind"),
                "match_raw": ok,
                "cheap_raw": cheap_ok,
                "snapped": bool(snap.get("snapped")),
                "cheapest": decide_route(reg, target_char=ch).selected,
            }
        )
    n = max(1, len(rows))
    cheap_rate = cheap / n
    return {
        "status": "PASS" if cheap_rate >= 0.5 else "GAP",
        "n": n,
        "match_raw_rate": match / n,
        "cheap_raw_rate": cheap_rate,
        "snap_rate": snapped_n / n,
        "rows": rows,
    }


def _probe_native_no_snap(model, tok, reg, device) -> dict[str, Any]:
    """Native UML speak with prefer_efficient=False so continue does not snap."""
    cheap = 0
    seal = 0
    rows = []
    for surface in ("H", "A", "V", "Hi"):
        if any(c not in reg.entries for c in surface):
            continue
        out = speak_uml_native(
            model,
            surface,
            encode_fn=tok.encode,
            decode_fn=tok.decode,
            max_new_tokens=24,
            prefer_efficient=False,
            temperature=0.0,
            uml_pressure={
                "stoi": tok.stoi,
                "itos": tok.itos,
                "hard_mask": False,
                "scale": 0.0,
            },
        )
        eqs = list(out.get("equations") or [])
        proposed = list(
            ((out.get("receipt") or {}).get("continue") or {}).get("equations_proposed")
            or eqs
        )
        if not proposed and eqs:
            proposed = eqs
        # Score first equation / first char
        ch = surface[0]
        raw = str(proposed[0]) if proposed else ""
        try:
            ok = out.get("surface") == surface or (
                raw and reg.decode_eq(raw) == ch
            )
        except Exception:
            ok = False
        info = (
            route_efficiency_error(reg, proposed=raw, target_char=ch)
            if raw
            else {"kind": "missing"}
        )
        cheap_ok = info.get("kind") == "valid_efficient"
        if ok:
            seal += 1
        if cheap_ok:
            cheap += 1
        rows.append(
            {
                "surface": surface,
                "proposed": proposed,
                "final_eqs": eqs,
                "raw_kind": info.get("kind"),
                "cheap_raw": cheap_ok,
                "roundtrip_or_first_seal": ok,
                "continue_status": ((out.get("receipt") or {}).get("continue") or {}).get(
                    "status"
                ),
            }
        )
    n = max(1, len(rows))
    cheap_rate = cheap / n
    return {
        "status": "PASS" if cheap_rate >= 0.5 else "GAP",
        "n": n,
        "cheap_raw_rate": cheap_rate,
        "seal_rate": seal / n,
        "rows": rows,
    }


def main() -> int:
    if not SURVIVOR.is_file():
        raise FileNotFoundError(SURVIVOR)
    if not EFFICIENT_CKPT.is_file():
        raise FileNotFoundError(EFFICIENT_CKPT)

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    configure_plant_runtime(device=str(device))

    model_e, _ = _load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    model_d, payload = _load(SURVIVOR, tok, device)

    english = _probe_english_prefer(model_e, model_d, tok, reg, device)
    native = _probe_native_no_snap(model_d, tok, reg, device)

    # P2 closes only if raw (pre-snap / no-snap) cheap rate clears bar.
    p2_pass = english["status"] == "PASS" or native["status"] == "PASS"
    objective = "PASS" if p2_pass else "GAP"
    receipt = {
        "schema_version": "uml_snap_free_audit_v1",
        "status": "PASS",
        "objective": objective,
        "hypothesis": (
            "After native math-token layer + stack, LM emits cheapest sealed route "
            "without relying on prefer_efficient_snap."
        ),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ckpt": str(SURVIVOR).replace("\\", "/"),
        "ckpt_leg": (payload.get("leg") if isinstance(payload, dict) else None),
        "english_prefer_efficient_pre_snap": english,
        "native_prefer_efficient_false": native,
        "p2_closed": p2_pass,
        "need": None
        if p2_pass
        else (
            "LM still does not internally prefer cheapest; snap compensates. "
            "Next: stronger native bank / route pressure before or with P3 experts."
        ),
        "device": str(device),
    }
    RECEIPT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    md = "\n".join(
        [
            "# UML Snap-Free Audit (P2)",
            "",
            f"- Objective: **{objective}**",
            f"- Ckpt: `{SURVIVOR.as_posix()}`",
            f"- English pre-snap cheap_rate: **{english['cheap_raw_rate']:.3f}** "
            f"(match={english['match_raw_rate']:.3f}, snap_rate={english['snap_rate']:.3f})",
            f"- Native no-snap cheap_rate: **{native['cheap_raw_rate']:.3f}** "
            f"(seal={native['seal_rate']:.3f})",
            "",
            f"Receipt: `{RECEIPT_JSON.as_posix()}`",
            "",
        ]
    )
    RECEIPT_MD.write_text(md, encoding="utf-8", newline="\n")
    print(
        f"SNAP_FREE_AUDIT_{objective} english_cheap={english['cheap_raw_rate']:.3f} "
        f"native_cheap={native['cheap_raw_rate']:.3f} p2_closed={p2_pass}",
        flush=True,
    )
    return 0 if objective == "PASS" else 0  # audit always returns 0; GAP is informational


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())
