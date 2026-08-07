#!/usr/bin/env python3
"""Build a tiny parallel UML-equation dataset slice (does NOT replace Codex v61)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402

OUT_DIR = SANDBOX / "data" / "uml_parallel_slice_v1"
SOURCE_LINES = [
    "Viv",
    "Hello",
    "I am an Adaptive Intelligent Operating System",
    "User: Who are you?\nViv:",
]


def main() -> int:
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    skipped_chars = 0
    for line in SOURCE_LINES:
        kept = "".join(ch for ch in line if ch in reg.entries)
        skipped_chars += len(line) - len(kept)
        eqs = reg.encode_text(kept)
        decoded = reg.decode_equations(eqs)
        rows.append(
            {
                "surface": kept,
                "uml_equations": eqs,
                "roundtrip_ok": decoded == kept,
                "char_count": len(kept),
            }
        )
        if decoded != kept:
            raise RuntimeError(f"uml_parallel_slice_roundtrip_fail:{kept!r}")

    manifest = {
        "schema_version": "uml_parallel_slice_v1",
        "registry_schema_version": reg.schema_version,
        "status": "PASS",
        "sandbox_only": True,
        "replaces_codex": False,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "registry_artifact": str(SANDBOX96_ARTIFACT).replace("\\", "/"),
        "registry_sha256": reg.registry_sha256(),
        "vocab_sha256": reg.vocab_sha256,
        "rows": len(rows),
        "skipped_chars_outside_vocab": skipped_chars,
        "examples": rows,
    }
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = sha256(body.encode("utf-8")).hexdigest()

    out_json = OUT_DIR / "MANIFEST.json"
    with out_json.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    # Flat parallel files for smoke loaders
    (OUT_DIR / "surface.txt").write_text(
        "\n".join(row["surface"] for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (OUT_DIR / "uml_equations.jsonl").write_text(
        "\n".join(json.dumps(row["uml_equations"], ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    smoke = {
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows),
        "all_roundtrip_ok": all(row["roundtrip_ok"] for row in rows),
        "path": str(out_json).replace("\\", "/"),
    }
    smoke_path = SANDBOX / "runs" / "uml_parallel_slice_v1_smoke_latest.json"
    smoke_path.parent.mkdir(parents=True, exist_ok=True)
    with smoke_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(smoke, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    print(
        f"UML_PARALLEL_SLICE_PASS rows={len(rows)} "
        f"skipped_outside_vocab={skipped_chars} out={OUT_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
