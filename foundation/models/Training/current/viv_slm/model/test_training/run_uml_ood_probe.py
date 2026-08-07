#!/usr/bin/env python3
"""OOD / never-seen probe against the mix survivor.

Builds surfaces and speak prompts that do **not** appear in the v6 mix bank
surface list, packs a small response-masked OOD tensor, then measures:
  - UML val acc/nll on OOD dialogues
  - speak match / cheap / route error on novel prompt templates
  - encode/decode seal on OOD surfaces

Does not train. Warm ckpt default: layer_survivor.pt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
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
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from sandbox_paths import EFFICIENT_CKPT  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
import run_uml_equation_ab as ab  # noqa: E402
import run_uml_speak_ab_f as speak  # noqa: E402
import build_uml_equation_mix_dataset as mix_build  # noqa: E402

SURFACES_PATH = SANDBOX / "data" / "uml_equation_mix_v1" / "surfaces.json"
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"
OOD_DIR = SANDBOX / "data" / "uml_ood_probe_v1"
RUNS = SANDBOX / "runs"

# Novel speak wrappers — keep inferable target patterns, but wording absent
# from speak_ab_f PROMPTS and mix bank surfaces.
OOD_SPEAK_TEMPLATES = [
    ("H", "OOD never-seen probe. Prefer efficient UML for H\nViv: "),
    ("Z", "OOD never-seen probe. Rank UML routes for Z\nBest: none\nViv: "),
    ("A", "OOD never-seen probe. Is this UML valid for A?\nCandidate: none\nViv: "),
    ("V", "OOD never-seen probe. What is the UML for 'V'?\nViv: "),
    ("Q", "OOD never-seen probe. UML for Q\nViv: "),
    ("B", "OOD never-seen probe. char='B'\nViv: "),
    ("X", "OOD never-seen probe. character X please\nViv: "),
    ("M", "OOD never-seen probe. Prefer efficient UML for M\nViv: "),
    ("K", "OOD never-seen probe. UML encode\nSurface: K\nViv: "),
    ("W", "OOD never-seen probe. equivalent for W\nViv: "),
]


def _load_seen_surfaces() -> set[str]:
    seen: set[str] = set()
    if SURFACES_PATH.is_file():
        data = json.loads(SURFACES_PATH.read_text(encoding="utf-8"))
        for s in data.get("surfaces") or []:
            seen.add(str(s))
    # Also mark the fixed speak_ab_f prompts as seen so OOD templates stay distinct.
    for _ch, prompt in speak.PROMPTS:
        seen.add(prompt)
    return seen


_HARD_LEXICON = (
    "quartz nexus filament orbit braid cipher lattice ember voltage ripple "
    "anchor vector prism delta sigma omega flux throttle coolant piston "
    "manifold telemetry seal route federation substrate skeleton "
    "unknown stranger alien foreign novel unseen scarce rare odd "
    "compute decode encode clamp residual stability authority budget"
).split()


def _synth_surfaces(
    tok: CharacterTokenizer,
    seen: set[str],
    *,
    n: int,
    seed: int,
    hard: bool = False,
) -> list[str]:
    """Procedural surfaces guaranteed absent from the mix bank."""
    rng = random.Random(seed)
    vocab = [ch for ch in tok.vocab if ch.isprintable() and ch not in "\n\r\t"]
    letters = [ch for ch in vocab if ch.isalpha()]
    digits = [ch for ch in vocab if ch.isdigit()]
    punct = [ch for ch in vocab if ch in " .,;:!?()-"]
    out: list[str] = []
    attempt = 0
    kinds = 8 if hard else 5
    while len(out) < n and attempt < n * 50:
        attempt += 1
        kind = rng.randrange(kinds)
        if kind == 0:
            words = []
            for _ in range(rng.randint(4, 12)):
                w = "".join(rng.choice(letters) for _ in range(rng.randint(3, 8)))
                words.append(w)
            surface = "oodprobe " + " ".join(words)
        elif kind == 1:
            surface = "OOD-" + "".join(rng.choice(digits) for _ in range(12)) + "-END"
        elif kind == 2:
            surface = (
                "never seen mix bank surface "
                + "".join(rng.choice(letters) for _ in range(16))
                + str(rng.randint(10000, 99999))
            )
        elif kind == 3:
            surface = "".join(rng.choice(punct + letters) for _ in range(rng.randint(20, 60)))
        elif kind == 4:
            surface = (
                f"probe#{rng.randint(1, 10**9)}: "
                + "".join(rng.choice(letters) for _ in range(8))
                + " encodes differently"
            )
        elif kind == 5:
            # Hard: lexicon sentences with unique nonce (English-ish, not in bank).
            words = [rng.choice(_HARD_LEXICON) for _ in range(rng.randint(8, 18))]
            surface = (
                f"hardood {rng.randint(10**6, 10**9)}: "
                + " ".join(words)
                + f" epoch {rng.randint(1, 9999)}"
            )
        elif kind == 6:
            # Hard: multi-clause + digits/punctuation density.
            surface = (
                f"HARD-OOD/{rng.randint(1000,9999)} "
                f"route={rng.choice(_HARD_LEXICON)} "
                f"seal={rng.choice(_HARD_LEXICON)}; "
                f"budget={rng.random():.4f} "
                f"residual={rng.random():.4f} "
                f"note={''.join(rng.choice(letters) for _ in range(10))}"
            )
        else:
            # Hard: long paragraph-like.
            clauses = []
            for _ in range(rng.randint(3, 6)):
                clauses.append(
                    " ".join(rng.choice(_HARD_LEXICON) for _ in range(rng.randint(5, 10)))
                )
            surface = f"paraood{rng.randint(1,10**7)}. " + ". ".join(clauses) + "."
        surface = mix_build._clean_surface(surface, set(tok.vocab))
        if len(surface) < 8 or surface in seen or surface in out:
            continue
        out.append(surface)
        seen.add(surface)
    return out


def _ood_dialogues(
    reg: UMLEquationRegistry, surfaces: list[str], *, hard: bool = False
) -> list[str]:
    dialogues: list[str] = []
    for surface in surfaces:
        eqs = reg.encode_text(surface)
        if not eqs:
            continue
        uml_line = " | ".join(eqs)
        dialogues.append(
            f"User: OOD encode this surface\n{surface}\nViv: {uml_line}<END>\n"
        )
        ch0 = surface[0]
        if ch0 in reg.entries:
            canon = str(reg.entries[ch0]["canonical"])
            dialogues.append(
                f"User: Prefer efficient UML for OOD char {ch0!r}\nViv: {canon}<END>\n"
            )
            if hard:
                dialogues.append(
                    f"User: Rank UML routes for {ch0}\nBest: unknown\nViv: {canon}<END>\n"
                )
                dialogues.append(
                    f"User: Is this UML valid for {ch0}?\nCandidate: {canon}\nViv: {canon}<END>\n"
                )
                # Non-canonical equivalent if present — still sealed destination.
                eq_list = list(reg.entries[ch0].get("equivalents") or [])
                alt = next((e for e in eq_list if str(e) != canon), None)
                if alt:
                    dialogues.append(
                        f"User: UML equivalent for {ch0}\nViv: {alt}<END>\n"
                    )
    return dialogues


def _pack_ood_tensor(
    tok: CharacterTokenizer, dialogues: list[str], out_dir: Path
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    shuffled = list(dialogues)
    rng.shuffle(shuffled)
    n_val = max(16, len(shuffled) // 5)
    train_d, val_d = shuffled[:-n_val], shuffled[-n_val:]
    train_text = "".join(train_d)
    val_text = "".join(val_d)
    # Ensure long enough for context windows.
    while len(train_text) < 256:
        train_text += train_text or "Viv: 0<END>\n"
    while len(val_text) < 256:
        val_text += val_text or "Viv: 0<END>\n"

    def encode_split(text: str) -> tuple[list[list[int]], list[list[int]], list[list[bool]]]:
        ids = [int(tok.stoi[ch]) for ch in text]
        rmask = mix_build._response_char_mask(text)
        return mix_build._window_masked(ids, rmask, context_length=128, stride=128)

    tr_in, tr_tg, tr_m = encode_split(train_text)
    va_in, va_tg, va_m = encode_split(val_text)
    if not tr_in or not va_in:
        raise RuntimeError("ood_pack_no_response_windows")
    train_meta = mix_build._write_masked_split(
        out_dir / "train", inputs=tr_in, targets=tr_tg, masks=tr_m, shard_examples=512
    )
    val_meta = mix_build._write_masked_split(
        out_dir / "validation", inputs=va_in, targets=va_tg, masks=va_m, shard_examples=512
    )
    manifest = {
        "schema_version": "uml_ood_probe_tensor_v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "dialogues": len(dialogues),
        "train": train_meta,
        "validation": val_meta,
        "vocab_size": tok.vocab_size,
    }
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "dialogues.txt").write_text("".join(dialogues), encoding="utf-8")
    return out_dir


def _speak_ood(
    ckpt: Path, tok: CharacterTokenizer, reg: UMLEquationRegistry, device: torch.device
) -> dict[str, Any]:
    """Speak eval using OOD templates with explicit target_char pressure."""
    from lib.uml_route_governor import route_efficiency_error
    from speak_lanes import speak_viv_sandwich

    model_e = speak._load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    model_d = speak._load(ckpt, tok, device)
    rows: list[dict[str, Any]] = []
    match_n = cheap_n = valid_n = dirty_n = 0
    err_sum = 0.0
    for ch, prompt in OOD_SPEAK_TEMPLATES:
        ids = torch.tensor([tok.encode(prompt)], dtype=torch.long)
        pressure = {
            "stoi": tok.stoi,
            "itos": tok.itos,
            "prompt_len": int(ids.shape[1]),
            "hard_mask": True,
            "scale": 6.0,
            "target_char": ch,
        }
        sandwich = speak_viv_sandwich(
            model_e,
            model_d,
            ids,
            deep_max=24,
            verify_max=16,
            decode_fn=tok.decode,
            uml_pressure=pressure,
            uml_pressure_on="deep",
            stamp_master_rid=False,
        )
        eq = str(sandwich.get("equation_text") or "").strip()
        dirty = (not eq) or ("\n" in eq) or eq.startswith("Vi")
        if dirty:
            dirty_n += 1
        try:
            back = reg.decode_eq(eq) if eq and not dirty else None
            match = back == ch
        except Exception:
            match = False
        if match:
            match_n += 1
        info = route_efficiency_error(reg, proposed=eq if eq else "???", target_char=ch)
        if info.get("valid"):
            valid_n += 1
        if info.get("kind") == "valid_efficient":
            cheap_n += 1
        err_sum += float(info.get("error") or 1.0)
        rows.append(
            {
                "target": ch,
                "equation": eq,
                "match": match,
                "dirty": dirty,
                "kind": info.get("kind"),
                "error": info.get("error"),
            }
        )
    n = len(OOD_SPEAK_TEMPLATES)
    return {
        "name": "ood_speak",
        "ckpt": str(ckpt).replace("\\", "/"),
        "n": n,
        "match_rate": match_n / n,
        "valid_rate": valid_n / n,
        "cheap_rate": cheap_n / n,
        "dirty_rate": dirty_n / n,
        "mean_route_error": err_sum / n,
        "rows": rows,
    }


def _surface_seal(reg: UMLEquationRegistry, surfaces: list[str]) -> dict[str, Any]:
    ok = 0
    fail = 0
    examples: list[dict[str, Any]] = []
    for s in surfaces:
        try:
            eqs = reg.encode_text(s)
            back = reg.decode_equations(eqs)
            good = back == s
        except Exception as exc:  # noqa: BLE001
            good = False
            eqs = []
            back = f"ERR:{type(exc).__name__}"
        if good:
            ok += 1
        else:
            fail += 1
            if len(examples) < 8:
                examples.append({"surface": s, "back": back, "n_eq": len(eqs)})
    return {
        "n": len(surfaces),
        "roundtrip_ok": ok,
        "roundtrip_fail": fail,
        "rate": ok / len(surfaces) if surfaces else 0.0,
        "fail_examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ckpt", type=Path, default=SURVIVOR)
    parser.add_argument("--n-surfaces", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--hard", action="store_true", help="Harder lexicon/long OOD surfaces")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    if not args.ckpt.is_file():
        raise FileNotFoundError(args.ckpt)

    seen = _load_seen_surfaces()
    seen_n = len(seen)
    tok = CharacterTokenizer.from_manifest(resolve_codex_dataset("v61")[1])
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)

    surfaces = _synth_surfaces(
        tok,
        seen,
        n=int(args.n_surfaces),
        seed=int(args.seed),
        hard=bool(args.hard),
    )
    if len(surfaces) < 32:
        raise RuntimeError(f"ood_too_few_surfaces:{len(surfaces)}")

    # Verify zero overlap with original bank surfaces file.
    bank = set()
    if SURFACES_PATH.is_file():
        bank = set(json.loads(SURFACES_PATH.read_text(encoding="utf-8")).get("surfaces") or [])
    overlap = sorted(set(surfaces) & bank)
    if overlap:
        raise RuntimeError(f"ood_overlap_with_bank:{overlap[:5]}")

    seal = _surface_seal(reg, surfaces)
    dialogues = _ood_dialogues(reg, surfaces, hard=bool(args.hard))
    tensor_dir = _pack_ood_tensor(tok, dialogues, OOD_DIR / "tensor_dataset")

    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    if str(device).startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
    configure_plant_runtime(device=str(device))

    # In-distribution reference: mix val
    mix_tensor = ab._ensure_mix_dataset()
    mix_val = load_split(mix_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    ood_val = load_split(tensor_dir, "validation", vocab_size=tok.vocab_size, response_only_loss=True)
    _, _, codex_tensor = resolve_codex_dataset("v61")
    codex_val = load_split(codex_tensor, "validation", vocab_size=tok.vocab_size, response_only_loss=True)

    id_metrics = ab._metrics(
        args.ckpt,
        tok=tok,
        device=device,
        codex_val=codex_val,
        uml_val=mix_val,
        batch_size=args.batch_size,
    )
    ood_metrics = ab._metrics(
        args.ckpt,
        tok=tok,
        device=device,
        codex_val=codex_val,
        uml_val=ood_val,
        batch_size=args.batch_size,
    )

    # Speak: ID templates vs OOD templates
    model_e = speak._load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    id_speak = speak._eval_ckpt(
        name="id_speak", deep_path=args.ckpt, model_e=model_e, tok=tok, reg=reg, device=device
    )
    ood_speak = _speak_ood(args.ckpt, tok, reg, device)

    # Gate: informative, not a promote gate.
    uml_drop = float(id_metrics["uml_acc"]) - float(ood_metrics["uml_acc"])
    match_drop = float(id_speak["match_rate"]) - float(ood_speak["match_rate"])
    if seal["rate"] < 1.0:
        objective = "FAIL_OOD_SEAL"
    elif ood_speak["match_rate"] < 0.5:
        objective = "FAIL_OOD_SPEAK_MATCH"
    elif uml_drop > 0.25 or match_drop > 0.25:
        objective = "PASS_OOD_STRESS_GAP"
    elif uml_drop > 0.08 or match_drop > 0.08:
        objective = "PASS_OOD_MILD_GAP"
    else:
        objective = "PASS_OOD_HOLDS"

    receipt = {
        "schema_version": "uml_ood_probe_v1",
        "experiment_id": "uml_ood_probe_v1",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "objective": objective,
        "hypothesis": (
            "Never-seen surfaces/prompts reveal whether the survivor sealed "
            "destination + UML route under distribution shift."
        ),
        "ckpt": str(args.ckpt).replace("\\", "/"),
        "seen_bank_surfaces": seen_n,
        "ood_surfaces": len(surfaces),
        "ood_dialogues": len(dialogues),
        "overlap_with_bank": 0,
        "seed": int(args.seed),
        "hard": bool(args.hard),
        "surface_seal": seal,
        "id_metrics": {
            "codex_acc": id_metrics["codex_acc"],
            "uml_acc": id_metrics["uml_acc"],
            "uml_nll": id_metrics["uml_nll"],
        },
        "ood_metrics": {
            "codex_acc": ood_metrics["codex_acc"],
            "uml_acc": ood_metrics["uml_acc"],
            "uml_nll": ood_metrics["uml_nll"],
            "uml_tokens": ood_metrics["uml_tokens"],
        },
        "id_speak": {
            k: id_speak[k]
            for k in ("match_rate", "cheap_rate", "mean_route_error", "valid_rate", "dirty_rate")
        },
        "ood_speak": {
            k: ood_speak[k]
            for k in ("match_rate", "cheap_rate", "mean_route_error", "valid_rate", "dirty_rate")
        },
        "delta": {
            "uml_acc_id_minus_ood": uml_drop,
            "speak_match_id_minus_ood": match_drop,
            "speak_cheap_id_minus_ood": float(id_speak["cheap_rate"])
            - float(ood_speak["cheap_rate"]),
        },
        "artifacts": {
            "ood_dir": str(OOD_DIR).replace("\\", "/"),
            "tensor_dir": str(tensor_dir).replace("\\", "/"),
            "surfaces_sha256": hashlib.sha256("\n".join(surfaces).encode()).hexdigest(),
        },
        "note": "OOD surfaces are procedural and verified absent from uml_equation_mix_v1/surfaces.json.",
    }

    OOD_DIR.mkdir(parents=True, exist_ok=True)
    (OOD_DIR / "surfaces.json").write_text(
        json.dumps({"count": len(surfaces), "surfaces": surfaces}, indent=2) + "\n",
        encoding="utf-8",
    )
    RUNS.mkdir(parents=True, exist_ok=True)
    text = json.dumps(receipt, indent=2, sort_keys=True)
    (RUNS / "uml_ood_probe_latest.json").write_text(text + "\n", encoding="utf-8")
    (OOD_DIR / "PROBE.json").write_text(text + "\n", encoding="utf-8")
    print(
        f"UML_OOD_{objective} surfaces={len(surfaces)} "
        f"uml_id={id_metrics['uml_acc']:.3f} ood={ood_metrics['uml_acc']:.3f} "
        f"speak_match_id={id_speak['match_rate']:.3f} ood={ood_speak['match_rate']:.3f} "
        f"cheap_id={id_speak['cheap_rate']:.3f} ood={ood_speak['cheap_rate']:.3f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
