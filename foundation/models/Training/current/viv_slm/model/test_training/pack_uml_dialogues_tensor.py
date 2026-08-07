#!/usr/bin/env python3
"""Pack UML dialogue text into response-masked tensor_dataset (same schema as mix v6)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
for p in (MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from sandbox_codex_identity import resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import build_uml_equation_mix_dataset as mix  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dialogues", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="tensor_dataset directory")
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument(
        "--repeat",
        type=int,
        default=32,
        help="Repeat dialogue corpus to fill context windows (native banks are small).",
    )
    args = parser.parse_args()

    if not args.dialogues.is_file():
        raise FileNotFoundError(args.dialogues)
    raw = args.dialogues.read_text(encoding="utf-8")
    if "Viv:" not in raw:
        raise RuntimeError("dialogues_missing_Viv_marker")

    # Ensure response marker has trailing space form used by masker.
    text = raw
    if "Viv: " not in text and "Viv:" in text:
        text = text.replace("Viv:", "Viv: ")

    # Split by lines into dialogue rows, then train/val.
    rows = [ln + "\n" for ln in text.splitlines() if ln.strip()]
    if len(rows) < 8:
        raise RuntimeError(f"too_few_dialogue_rows:{len(rows)}")
    n_val = max(4, int(len(rows) * float(args.val_fraction)))
    n_val = min(n_val, len(rows) // 2)
    val_rows = rows[-n_val:]
    train_rows = rows[:-n_val]
    train_text = "".join(train_rows) * max(1, int(args.repeat))
    val_text = "".join(val_rows) * max(1, max(4, int(args.repeat) // 4))

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    unknown = sorted({ch for ch in train_text + val_text if ch not in tok.stoi})
    if unknown:
        raise RuntimeError(f"vocab_unknown_chars:{unknown[:20]}")

    def encode_split(body: str):
        ids = [int(tok.stoi[ch]) for ch in body]
        rmask = mix._response_char_mask(body)
        return mix._window_masked(
            ids, rmask, context_length=mix.CONTEXT, stride=mix.STRIDE
        )

    tr_in, tr_tg, tr_m = encode_split(train_text)
    va_in, va_tg, va_m = encode_split(val_text)
    if not tr_in or not va_in:
        raise RuntimeError("pack_no_response_windows")

    out = Path(args.out)
    if out.exists():
        import shutil

        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    train_meta = mix._write_masked_split(
        out / "train",
        inputs=tr_in,
        targets=tr_tg,
        masks=tr_m,
        shard_examples=mix.SHARD_EXAMPLES,
    )
    val_meta = mix._write_masked_split(
        out / "validation",
        inputs=va_in,
        targets=va_tg,
        masks=va_m,
        shard_examples=mix.SHARD_EXAMPLES,
    )
    resp_frac = sum(sum(1 for x in row if x) for row in tr_m) / max(
        sum(len(row) for row in tr_m), 1
    )
    manifest = {
        "schema_version": "uml_equation_mix_masked_tensor_v5",
        "status": "COMPLETE",
        "bank_version": "uml_native_math_tokens_v1",
        "quality_drills": False,
        "response_only_loss": True,
        "response_marker": mix.RESPONSE_MARKER,
        "context_length": mix.CONTEXT,
        "stride": mix.STRIDE,
        "vocab_sha256": tok.vocab_sha256,
        "vocab_size": tok.vocab_size,
        "dialogue_rows": len(rows),
        "repeat": int(args.repeat),
        "splits": {"train": train_meta, "validation": val_meta},
        "train_response_token_fraction": round(resp_frac, 4),
        "packed_at": datetime.now(timezone.utc).isoformat(),
        "source_dialogues": str(args.dialogues).replace("\\", "/"),
    }
    with (out / "MANIFEST.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"PACK_UML_DIALOGUES_PASS rows={len(rows)} train_ex={train_meta['examples']} "
        f"val_ex={val_meta['examples']} resp_frac={manifest['train_response_token_fraction']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
