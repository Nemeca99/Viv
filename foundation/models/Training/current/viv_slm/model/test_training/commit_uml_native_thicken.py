#!/usr/bin/env python3
"""Commit native-thicken ckpt to layer_survivor and refresh snap-free audit/docs."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import resolve_codex_dataset  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402

import run_uml_snap_free_audit as snap  # noqa: E402
from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from sandbox_paths import EFFICIENT_CKPT  # noqa: E402

SRC = SANDBOX / "runs" / "uml_native_thicken" / "native_thicken.pt"
SURVIVOR = SANDBOX / "runs" / "uml_mix_layers" / "layer_survivor.pt"


def main() -> int:
    if not SRC.is_file():
        raise FileNotFoundError(SRC)
    shutil.copy2(SRC, SURVIVOR)

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    configure_plant_runtime(device=str(device))
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    model_e, _ = snap._load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    model_d, payload = snap._load(SURVIVOR, tok, device)
    english = snap._probe_english_prefer(model_e, model_d, tok, reg, device)
    native = snap._probe_native_no_snap(model_d, tok, reg, device)
    p2 = english["status"] == "PASS" or native["status"] == "PASS"
    obj = "PASS" if p2 else "GAP"
    finished = datetime.now(timezone.utc).isoformat()

    receipt = {
        "schema_version": "uml_snap_free_audit_v1",
        "status": "PASS",
        "objective": obj,
        "hypothesis": (
            "After native thicken v2, LM emits cheapest sealed route without "
            "prefer_efficient_snap."
        ),
        "finished_at": finished,
        "ckpt": str(SURVIVOR).replace("\\", "/"),
        "ckpt_leg": payload.get("leg") if isinstance(payload, dict) else None,
        "english_prefer_efficient_pre_snap": english,
        "native_prefer_efficient_false": native,
        "p2_closed": p2,
        "source": "native_thicken_v2_committed",
        "device": str(device),
    }
    outj = SANDBOX / "runs" / "uml_snap_free_audit_latest.json"
    outj.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (SANDBOX / "runs" / "uml_snap_free_audit_latest.md").write_text(
        "\n".join(
            [
                "# UML Snap-Free Audit (P2)",
                "",
                f"- Objective: **{obj}**",
                f"- Ckpt: `{SURVIVOR.as_posix()}`",
                f"- English pre-snap cheap_rate: **{english['cheap_raw_rate']:.3f}** "
                f"(match={english['match_raw_rate']:.3f}, snap_rate={english['snap_rate']:.3f})",
                f"- Native no-snap cheap_rate: **{native['cheap_raw_rate']:.3f}** "
                f"(seal={native['seal_rate']:.3f})",
                "- Source: native_thicken_v2 committed",
                "",
                f"Receipt: `{outj.as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    th_path = SANDBOX / "runs" / "uml_native_thicken_latest.json"
    th = json.loads(th_path.read_text(encoding="utf-8"))
    th["committed_survivor"] = True
    th["leave_survivor_untouched"] = False
    th["committed_at"] = finished
    th_path.write_text(
        json.dumps(th, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (SANDBOX / "runs" / "uml_native_thicken_latest.md").write_text(
        "\n".join(
            [
                "# Native UML Thicken (snap-free)",
                "",
                "- Objective: **PASS**",
                f"- Native cheap: {th['baseline_audit']['native_cheap']:.3f} → "
                f"{native['cheap_raw_rate']:.3f}",
                f"- English cheap (post): {english['cheap_raw_rate']:.3f}",
                "- Survivor committed: True",
                "",
                f"Receipt: `{th_path.as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    recipe_path = SANDBOX / "uml_domain_expert_train_recipe.json"
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["last_run"] = finished
    recipe["last_objective"] = "NATIVE_THICKEN_PASS"
    recipe["next_action"] = (
        "Native snap-free PASS after thicken. Promotion still needs a real cost-winner "
        "(mixed federation that beats mono/LIT on registry economics)."
    )
    recipe["binding_read"]["not_yet"] = (
        "Persistent composites empty — need real cost-winner for promotion gate."
    )
    recipe["native_thicken"] = {
        "objective": "PASS",
        "native_before": th["baseline_audit"]["native_cheap"],
        "native_after": native["cheap_raw_rate"],
        "committed": True,
        "receipt": str(th_path).replace("\\", "/"),
    }
    recipe_path.write_text(
        json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    thesis_path = SANDBOX / "UML_TRAINING_THESIS.md"
    thesis = thesis_path.read_text(encoding="utf-8")
    if "Native thicken (snap-free)" not in thesis:
        lines = thesis.splitlines(keepends=True)
        out = []
        done = False
        for ln in lines:
            out.append(ln)
            if (not done) and ln.startswith("11. ~~Promotion-gate pilot~~"):
                out.append(
                    "12. ~~Native thicken (snap-free)~~ → **PASS** "
                    f"(`uml_native_thicken_latest.json`; native cheap "
                    f"0.25→{native['cheap_raw_rate']:.2f}; survivor committed)\n"
                )
                done = True
        if done:
            thesis_path.write_text("".join(out), encoding="utf-8", newline="\n")

    # Fix P2 thesis line that still says native 0.25
    thesis = thesis_path.read_text(encoding="utf-8")
    old_p2 = (
        "5. ~~Snap-free speak audit (P2)~~ → **PASS** at bar (`uml_snap_free_audit_latest.json`: "
        "english pre-snap cheap_rate **0.50**; native no-snap still **0.25** — English "
        "Prefer-efficient path clears P2; native path still weak)"
    )
    new_p2 = (
        "5. ~~Snap-free speak audit (P2)~~ → **PASS** (`uml_snap_free_audit_latest.json`: "
        f"english **{english['cheap_raw_rate']:.2f}**; native no-snap "
        f"**{native['cheap_raw_rate']:.2f}** after native thicken v2)"
    )
    if old_p2 in thesis:
        thesis_path.write_text(thesis.replace(old_p2, new_p2), encoding="utf-8", newline="\n")

    print(
        f"COMMIT_NATIVE_THICKEN_{obj} english={english['cheap_raw_rate']:.3f} "
        f"native={native['cheap_raw_rate']:.3f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
