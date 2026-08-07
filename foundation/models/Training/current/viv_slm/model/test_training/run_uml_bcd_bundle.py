#!/usr/bin/env python3
"""Selftest: UML auto target inference + quality bank smoke + short preference A/B."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))
if str(MODEL) not in sys.path:
    sys.path.insert(0, str(MODEL))

from uml_speak_pressure import infer_uml_target_from_prompt  # noqa: E402

RECEIPT = SANDBOX / "runs" / "uml_bcd_bundle_latest.json"


def main() -> int:
    failures: list[str] = []

    # C: auto target
    cases = [
        ("User: UML equivalent for H\nViv: ", "H"),
        ("User: UML encode\nSurface: Viv\nViv: ", "V"),
        ("please encode X for me", "X"),
    ]
    for prompt, want in cases:
        got = infer_uml_target_from_prompt(prompt)
        if not got.get("matched") or got.get("target_char") != want:
            failures.append(f"auto_target:{prompt!r}->{got}")

    # D: rebuild quality bank
    build = subprocess.run(
        [str(PY), "-B", str(SANDBOX / "build_uml_equation_mix_dataset.py")],
        cwd=str(SANDBOX),
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        failures.append(f"bank_build:{build.stderr[-500:]}")
    else:
        meta = json.loads(
            (SANDBOX / "data" / "uml_equation_mix_v1" / "BUILD.json").read_text(
                encoding="utf-8"
            )
        )
        if meta.get("bank_version") != "v5_quality":
            failures.append(f"bank_version:{meta.get('bank_version')}")
        if not meta.get("quality_drills"):
            failures.append("quality_drills_false")
        if int(meta.get("dialogue_rows") or 0) < 20000:
            failures.append(f"dialogue_rows_low:{meta.get('dialogue_rows')}")

    # B: short matched preference-bank A/B (uses v5 via ensure)
    ab = subprocess.run(
        [
            str(PY),
            "-B",
            str(SANDBOX / "run_uml_equation_ab.py"),
            "--steps",
            "1500",
            "--mix-ratio",
            "0.15",
            "--batch-size",
            "64",
            "--log-every",
            "500",
        ],
        cwd=str(SANDBOX),
        capture_output=True,
        text=True,
    )
    ab_tail = (ab.stdout or "")[-800:]
    if ab.returncode != 0:
        failures.append(f"ab_fail:{ab.stderr[-500:]}{ab_tail}")
    ab_receipt = SANDBOX / "runs" / "uml_equation_ab_v2_latest.json"
    ab_payload = {}
    if ab_receipt.is_file():
        ab_payload = json.loads(ab_receipt.read_text(encoding="utf-8"))
        if ab_payload.get("objective_hold_plus_uml") not in ("PASS", "HOLD_ONLY"):
            failures.append(f"ab_objective:{ab_payload.get('objective_hold_plus_uml')}")

    status = "PASS" if not failures else "FAIL"
    receipt = {
        "schema_version": "uml_bcd_bundle_v1",
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "C_auto_target_cases": len(cases),
        "D_bank": {
            "bank_version": (meta.get("bank_version") if build.returncode == 0 else None),
            "dialogue_rows": (meta.get("dialogue_rows") if build.returncode == 0 else None),
            "tensor_train_examples": (
                meta.get("tensor_train_examples") if build.returncode == 0 else None
            ),
        },
        "B_ab": {
            "objective": ab_payload.get("objective_hold_plus_uml"),
            "verdict_codex": ab_payload.get("verdict_primary_codex"),
            "delta": ab_payload.get("delta_pilot_minus_baseline"),
            "bank_version": ab_payload.get("bank_version"),
            "tail": ab_tail.strip(),
        },
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"UML_BCD_BUNDLE_{status} failures={len(failures)}")
    if failures:
        for item in failures[:20]:
            print("FAIL", item)
        return 1
    print(
        f"bank={receipt['D_bank']} "
        f"ab_obj={receipt['B_ab'].get('objective')} "
        f"delta={receipt['B_ab'].get('delta')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
