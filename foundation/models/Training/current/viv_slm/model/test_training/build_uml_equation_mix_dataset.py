#!/usr/bin/env python3
"""Expand UML parallel slice + build response-masked equation dialogues.

Bank expansion (v3):
- seed phrases + identity_corpus
- mined Codex v61 response spans (read-only decode)
- full single-char encode/decode coverage
- limited equivalents per surface

Loss only on tokens after each ``Viv:`` marker.
Does NOT replace Codex.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))
if str(SANDBOX) not in sys.path:
    sys.path.insert(0, str(SANDBOX))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from sandbox_codex_identity import load_split, resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

OUT_SLICE = SANDBOX / "data" / "uml_parallel_slice_v1"
OUT_MIX = SANDBOX / "data" / "uml_equation_mix_v1"
CORPUS = SANDBOX / "data" / "identity_corpus.txt"
EXTRA_SURFACES = SANDBOX / "data" / "uml_mix_extra_surfaces" / "surfaces.json"
VOCAB = (
    FOUNDATION
    / "models"
    / "Training"
    / "data"
    / "identity"
    / "v61_stratified_preservation_replay"
    / "VOCAB.json"
)
CONTEXT = 128
STRIDE = 32
SHARD_EXAMPLES = 512
RESPONSE_MARKER = "Viv: "
MASKED_SCHEMA = "viv_slm_response_only_tensor_dataset_v1"

SEED_PHRASES = [
    "Viv",
    "Hello",
    "I am an Adaptive Intelligent Operating System",
    "User: Who are you?\nViv:",
    "identity before knowledge",
    "Nested PEMDAS is the math lane",
    "encode then compute then decode",
    "Universal Machine Language",
    "Universal Mathematical Language",
    "RID is a stability score",
    "PID actuates inside the fold",
    "the dog bites man and the cat sits on the mat",
    "viv speaks with one identity and two specialists",
    "same vocab same identity different weights",
]


def _clean_surface(text: str, vocab: set[str]) -> str:
    text = text.replace("<END>", "").replace("\r", "").strip()
    text = "".join(ch for ch in text if ch in vocab)
    # collapse excessive whitespace but keep single spaces/newlines
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def _mine_codex_phrases(
    tok: CharacterTokenizer,
    *,
    max_examples_per_split: int,
    min_len: int,
    max_len: int,
) -> list[str]:
    _, _, tensor = resolve_codex_dataset("v61")
    vocab = set(tok.vocab)
    phrases: set[str] = set()
    for split in ("validation", "train"):
        _inputs, targets, masks = load_split(
            tensor, split, vocab_size=tok.vocab_size, response_only_loss=True
        )
        n = min(int(max_examples_per_split), int(targets.shape[0]))
        for i in range(n):
            on = masks[i].tolist()
            ids = targets[i].tolist()
            buf: list[str] = []
            for flag, tid in zip(on, ids):
                if flag:
                    buf.append(tok.itos[int(tid)])
                elif buf:
                    surface = _clean_surface("".join(buf), vocab)
                    if min_len <= len(surface) <= max_len:
                        phrases.add(surface)
                    buf = []
            if buf:
                surface = _clean_surface("".join(buf), vocab)
                if min_len <= len(surface) <= max_len:
                    phrases.add(surface)
    return sorted(phrases, key=lambda s: (len(s), s))


def _load_extra_surfaces() -> list[str]:
    """Permanent hard/real-heldout extras (see merge_uml_mix_extra_surfaces.py)."""
    if not EXTRA_SURFACES.is_file():
        return []
    try:
        payload = json.loads(EXTRA_SURFACES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    surfaces = payload.get("surfaces") if isinstance(payload, dict) else None
    if not isinstance(surfaces, list):
        return []
    return [str(s) for s in surfaces if str(s).strip()]


def _phrases(
    tok: CharacterTokenizer,
    *,
    mine_per_split: int,
    max_surfaces: int,
) -> list[str]:
    vocab = set(tok.vocab)
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        surface = _clean_surface(raw, vocab)
        if len(surface) < 1 or surface in seen:
            return
        seen.add(surface)
        out.append(surface)

    for raw in SEED_PHRASES:
        add(raw)
    if CORPUS.is_file():
        for line in CORPUS.read_text(encoding="utf-8").splitlines():
            add(line)

    # Full single-char coverage (machine index completeness).
    for ch in tok.vocab:
        add(ch)

    # Hard-OOD / real-heldout catalog before Codex mining (priority within cap).
    for surface in _load_extra_surfaces():
        add(surface)
        if len(out) >= max_surfaces:
            return out[:max_surfaces]

    mined = _mine_codex_phrases(
        tok,
        max_examples_per_split=mine_per_split,
        min_len=3,
        max_len=96,
    )
    for surface in mined:
        add(surface)
        if len(out) >= max_surfaces:
            break

    return out[:max_surfaces]


def _corrupt_equation(expr: str, target_value: int) -> str | None:
    """Produce a near-miss invalid equation (looks local, wrong value)."""
    text = str(expr)
    if not text:
        return None
    # Digit nudge: change last digit if present.
    for i in range(len(text) - 1, -1, -1):
        if text[i].isdigit():
            d = int(text[i])
            nd = (d + 1) % 10
            if nd == d:
                nd = (d + 2) % 10
            cand = text[:i] + str(nd) + text[i + 1 :]
            if cand != text:
                return cand
    # Operator swap
    for old, new in (("+", "*"), ("*", "+"), ("-", "+")):
        if old in text:
            return text.replace(old, new, 1)
    return f"{int(target_value) + 7}"


def _dialogues(
    reg: UMLEquationRegistry,
    surfaces: list[str],
    *,
    equivalents_per_surface: int,
    quality_drills: bool = True,
) -> list[str]:
    """Build encode/decode/equivalent dialogues plus quality+preference drills."""
    rows: list[str] = []
    for kept in surfaces:
        if not kept:
            continue
        eqs = reg.encode_text(kept)
        joined = ",".join(eqs)
        rows.append(f"User: UML encode\nSurface: {kept}\nViv: {joined}<END>\n")
        rows.append(f"User: UML decode\nUML: {joined}\nViv: {kept}<END>\n")
        # Decode then re-encode drill (fixed destination, route may be canonical).
        rows.append(
            f"User: UML decode then encode\nUML: {joined}\nViv: {joined}<END>\n"
        )
        first = kept[0]
        entry = reg.entries.get(first)
        if entry is None:
            continue
        canon = str(entry["canonical"])
        alts = list(entry.get("equivalents") or [])[:equivalents_per_surface]
        for alt in alts:
            rows.append(f"User: UML equivalent for {first}\nViv: {alt}<END>\n")
        # Prefer cheapest route (train↔generate loop signal).
        rows.append(
            f"User: Prefer efficient UML for {first}\nViv: {canon}<END>\n"
        )
        if alts:
            expensive = alts[-1]
            rows.append(
                f"User: Rank UML routes for {first}\n"
                f"Best: {canon}\nAlso valid: {expensive}\n"
                f"Viv: {canon}<END>\n"
            )

        if quality_drills:
            # Hard negative: reject wrong value / near-miss.
            bad = _corrupt_equation(canon, int(entry["value"]))
            if bad and bad != canon:
                rows.append(
                    f"User: Is this UML valid for {first}?\n"
                    f"Candidate: {bad}\nViv: no {canon}<END>\n"
                )
            # Long-ish surface chunk (up to 48 chars) encode.
            if len(kept) >= 12:
                chunk = kept[:48]
                chunk_eqs = ",".join(reg.encode_text(chunk))
                rows.append(
                    f"User: UML encode long\nSurface: {chunk}\nViv: {chunk_eqs}<END>\n"
                )
                rows.append(
                    f"User: UML decode long\nUML: {chunk_eqs}\nViv: {chunk}<END>\n"
                )
    return rows


def _response_char_mask(text: str) -> list[bool]:
    mask = [False] * len(text)
    start = 0
    while True:
        idx = text.find(RESPONSE_MARKER, start)
        if idx < 0:
            break
        body = idx + len(RESPONSE_MARKER)
        end = text.find("\n", body)
        if end < 0:
            end = len(text)
        for i in range(body, end):
            mask[i] = True
        start = end
    return mask


def _window_masked(
    token_ids: list[int],
    response_mask: list[bool],
    *,
    context_length: int,
    stride: int,
) -> tuple[list[list[int]], list[list[int]], list[list[bool]]]:
    if len(token_ids) != len(response_mask):
        raise ValueError("uml_mix_mask_len_mismatch")
    if len(token_ids) < context_length + 1:
        raise ValueError("uml_mix_text_too_short_for_context")
    inputs: list[list[int]] = []
    targets: list[list[int]] = []
    masks: list[list[bool]] = []
    max_start = len(token_ids) - (context_length + 1)
    for start in range(0, max_start + 1, stride):
        inp = token_ids[start : start + context_length]
        tgt = token_ids[start + 1 : start + context_length + 1]
        m = response_mask[start + 1 : start + context_length + 1]
        if not any(m):
            continue
        inputs.append(inp)
        targets.append(tgt)
        masks.append(m)
    return inputs, targets, masks


def _write_masked_split(
    split_dir: Path,
    *,
    inputs: list[list[int]],
    targets: list[list[int]],
    masks: list[list[bool]],
    shard_examples: int,
) -> dict[str, object]:
    split_dir.mkdir(parents=True, exist_ok=True)
    shards = 0
    for offset in range(0, len(inputs), shard_examples):
        chunk_in = inputs[offset : offset + shard_examples]
        chunk_tg = targets[offset : offset + shard_examples]
        chunk_m = masks[offset : offset + shard_examples]
        payload = {
            "schema_version": MASKED_SCHEMA,
            "storage_dtype": "torch.int16",
            "loss_mask_dtype": "torch.bool",
            "inputs": torch.tensor(chunk_in, dtype=torch.int16),
            "targets": torch.tensor(chunk_tg, dtype=torch.int16),
            "loss_mask": torch.tensor(chunk_m, dtype=torch.bool),
        }
        path = split_dir / f"shard_{shards:05d}.pt"
        torch.save(payload, path)
        shards += 1
    return {
        "examples": len(inputs),
        "shards": shards,
        "schema_version": MASKED_SCHEMA,
        "response_only_loss": True,
        "response_marker": RESPONSE_MARKER,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mine-per-split", type=int, default=12000)
    parser.add_argument("--max-surfaces", type=int, default=5000)
    parser.add_argument("--equivalents-per-surface", type=int, default=3)
    parser.add_argument(
        "--quality-drills",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Hard negatives, prefer-cheap, decode/re-encode, long surfaces.",
    )
    args = parser.parse_args(argv)

    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    tok = CharacterTokenizer.from_manifest(VOCAB)
    if tok.vocab_sha256 != reg.vocab_sha256:
        raise RuntimeError(
            f"uml_mix_vocab_mismatch tok={tok.vocab_sha256} reg={reg.vocab_sha256}"
        )

    extra_surfaces = _load_extra_surfaces()
    surfaces = _phrases(
        tok,
        mine_per_split=int(args.mine_per_split),
        max_surfaces=int(args.max_surfaces),
    )
    dialogues = _dialogues(
        reg,
        surfaces,
        equivalents_per_surface=int(args.equivalents_per_surface),
        quality_drills=bool(args.quality_drills),
    )
    if len(dialogues) < 100:
        raise RuntimeError(f"uml_mix_too_few_dialogues:{len(dialogues)}")

    OUT_SLICE.mkdir(parents=True, exist_ok=True)
    examples = []
    for kept in surfaces:
        if not kept:
            continue
        eqs = reg.encode_text(kept)
        decoded = reg.decode_equations(eqs)
        if decoded != kept:
            raise RuntimeError(f"uml_parallel_roundtrip_fail:{kept!r}")
        examples.append(
            {
                "surface": kept,
                "uml_equations": eqs,
                "roundtrip_ok": True,
                "char_count": len(kept),
            }
        )
    slice_manifest = {
        "schema_version": "uml_parallel_slice_v1",
        "registry_schema_version": reg.schema_version,
        "bank_version": "v6_federation",
        "status": "PASS",
        "sandbox_only": True,
        "replaces_codex": False,
        "quality_drills": bool(args.quality_drills),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "registry_artifact": str(SANDBOX96_ARTIFACT).replace("\\", "/"),
        "registry_sha256": reg.registry_sha256(),
        "vocab_sha256": reg.vocab_sha256,
        "rows": len(examples),
        "examples_preview": examples[:32],
        "examples_total": len(examples),
    }
    body = json.dumps(
        {k: v for k, v in slice_manifest.items() if k != "examples_preview"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    slice_manifest["manifest_sha256"] = sha256(body.encode("utf-8")).hexdigest()
    with (OUT_SLICE / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(slice_manifest, ensure_ascii=False, indent=2, sort_keys=True, fp=handle)
        handle.write("\n")
    (OUT_SLICE / "surface.txt").write_text(
        "\n".join(e["surface"] for e in examples) + "\n", encoding="utf-8", newline="\n"
    )

    if OUT_MIX.exists():
        shutil.rmtree(OUT_MIX)
    OUT_MIX.mkdir(parents=True, exist_ok=True)
    n_val = max(32, len(dialogues) // 5)
    train_dialogues = dialogues[:-n_val]
    val_dialogues = dialogues[-n_val:]
    train_text = "".join(train_dialogues)
    val_text = "".join(val_dialogues)
    (OUT_MIX / "train_dialogues.txt").write_text(train_text, encoding="utf-8", newline="\n")
    (OUT_MIX / "val_dialogues.txt").write_text(val_text, encoding="utf-8", newline="\n")
    (OUT_MIX / "surfaces.json").write_text(
        json.dumps(
            {
                "count": len(surfaces),
                "surfaces": surfaces,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    def encode_split(text: str) -> tuple[list[list[int]], list[list[int]], list[list[bool]]]:
        ids = [int(tok.stoi[ch]) for ch in text]
        rmask = _response_char_mask(text)
        return _window_masked(ids, rmask, context_length=CONTEXT, stride=STRIDE)

    tr_in, tr_tg, tr_m = encode_split(train_text)
    va_in, va_tg, va_m = encode_split(val_text)
    if not tr_in or not va_in:
        raise RuntimeError("uml_mix_no_response_windows")

    tensor_dir = OUT_MIX / "tensor_dataset"
    train_meta = _write_masked_split(
        tensor_dir / "train",
        inputs=tr_in,
        targets=tr_tg,
        masks=tr_m,
        shard_examples=SHARD_EXAMPLES,
    )
    val_meta = _write_masked_split(
        tensor_dir / "validation",
        inputs=va_in,
        targets=va_tg,
        masks=va_m,
        shard_examples=SHARD_EXAMPLES,
    )
    resp_frac_train = sum(sum(1 for x in row if x) for row in tr_m) / max(
        sum(len(row) for row in tr_m), 1
    )
    ds_manifest = {
        "schema_version": "uml_equation_mix_masked_tensor_v5",
        "status": "COMPLETE",
        "bank_version": "v6_federation",
        "quality_drills": bool(args.quality_drills),
        "response_only_loss": True,
        "response_marker": RESPONSE_MARKER,
        "context_length": CONTEXT,
        "stride": STRIDE,
        "vocab_sha256": tok.vocab_sha256,
        "vocab_size": tok.vocab_size,
        "surface_count": len(surfaces),
        "dialogue_rows": len(dialogues),
        "splits": {"train": train_meta, "validation": val_meta},
        "train_response_token_fraction": round(resp_frac_train, 4),
    }
    with (tensor_dir / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(ds_manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    receipt = {
        "schema_version": "uml_equation_mix_build_v5",
        "status": "PASS",
        "bank_version": "v6_federation",
        "quality_drills": bool(args.quality_drills),
        "sandbox_only": True,
        "replaces_codex": False,
        "response_only_loss": True,
        "response_marker": RESPONSE_MARKER,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "registry_sha256": reg.registry_sha256(),
        "vocab_sha256": tok.vocab_sha256,
        "surface_count": len(surfaces),
        "dialogue_rows": len(dialogues),
        "train_dialogues": len(train_dialogues),
        "val_dialogues": len(val_dialogues),
        "parallel_rows": len(examples),
        "tensor_train_examples": train_meta["examples"],
        "tensor_val_examples": val_meta["examples"],
        "train_response_token_fraction": ds_manifest["train_response_token_fraction"],
        "mine_per_split": int(args.mine_per_split),
        "max_surfaces": int(args.max_surfaces),
        "equivalents_per_surface": int(args.equivalents_per_surface),
        "extra_surfaces_catalog": str(EXTRA_SURFACES).replace("\\", "/"),
        "extra_surfaces_available": len(extra_surfaces),
        "slice_dir": str(OUT_SLICE).replace("\\", "/"),
        "mix_dir": str(OUT_MIX).replace("\\", "/"),
        "tensor_dir": str(tensor_dir).replace("\\", "/"),
    }
    with (OUT_MIX / "BUILD.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    smoke = SANDBOX / "runs" / "uml_equation_mix_build_latest.json"
    smoke.parent.mkdir(parents=True, exist_ok=True)
    with smoke.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_EQUATION_MIX_BUILD_PASS v6_federation surfaces={len(surfaces)} "
        f"dialogues={len(dialogues)} train_ex={train_meta['examples']} "
        f"val_ex={val_meta['examples']} resp_frac={ds_manifest['train_response_token_fraction']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
