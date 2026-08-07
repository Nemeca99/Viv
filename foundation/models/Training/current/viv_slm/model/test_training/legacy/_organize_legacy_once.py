#!/usr/bin/env python3
"""One-shot organizer: move high-confidence legacy scripts under legacy/.

Safe to re-run only if sources still at top level (aborts if dest exists).
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT / "legacy"

MOVES = [
    {
        "file": "run_rid_breakthrough.py",
        "rationale": (
            "Pre-UML RID breakthrough A/B campaign; superseded by UML mix / "
            "equation ladder. No recipe or thesis ladder pointer as active next "
            "step. No importers outside itself."
        ),
        "confidence": "high",
    },
    {
        "file": "run_rid_breakthrough_continue_4450.py",
        "rationale": (
            "Continuation of rid_breakthrough to 4450; campaign complete; only "
            "referenced by sibling RID/acc99 tools."
        ),
        "confidence": "high",
    },
    {
        "file": "run_rid_metric_sweep_4200.py",
        "rationale": (
            "RID/UML metric sweep to 4200 under old checkpoint campaign; "
            "superseded by uml_mix_layers metabolism."
        ),
        "confidence": "high",
    },
    {
        "file": "run_rid_adapter_ab.py",
        "rationale": (
            "Early RID adapter A/B on sandbox specialists; receipts under "
            "runs/rid_adapter_ab; not on active UML ladder."
        ),
        "confidence": "high",
    },
    {
        "file": "rerank_continue_4450_phase_a.py",
        "rationale": (
            "Receipts-only Phase-A re-score for continue-4450; tied to retired "
            "RID campaign."
        ),
        "confidence": "high",
    },
    {
        "file": "run_acc99_campaign.py",
        "rationale": (
            "Accuracy reach99/hold99 campaign on Codex specialists; prior to "
            "UML equation plant; no active callers."
        ),
        "confidence": "high",
    },
    {
        "file": "analyze_val_errors.py",
        "rationale": (
            "Ceiling audit hardwired to rid_breakthrough_continue_4450 "
            "efficient_final.pt; receipts-only tooling for retired campaign."
        ),
        "confidence": "high",
    },
    {
        "file": "run_wild_weighted_sweep.py",
        "rationale": (
            "Aggressive weighted-loss sweep on efficient/deep specialists; "
            "superseded campaign tooling; no UML recipe reference."
        ),
        "confidence": "high",
    },
    {
        "file": "mint_specialists.py",
        "rationale": (
            "README explicitly labels legacy 8/40-step smoke mint; still used "
            "optionally by run_sandbox_smoke — keep import/CLI shim at old path."
        ),
        "confidence": "high",
        "shim_style": "import_main",
    },
]

LEFT_IN_PLACE = [
    {
        "path": "runs/",
        "reason": (
            "Historical + live receipts; uml_mix_layers actively written by "
            "other agent. Recommend leave in place."
        ),
    },
    {
        "path": "checkpoints/",
        "reason": "Live specialist / U / domain checkpoints; do not relocate.",
    },
    {
        "path": "data/",
        "reason": "Active banks (mix, native, federations axioms).",
    },
    {
        "path": "run_uml_mix_layer.py",
        "reason": "Active continue_train surface; other agent hot.",
    },
    {
        "path": "uml_mix_recipe.json",
        "reason": (
            "Active recipe; other agent may edit; references mix_ads scripts."
        ),
    },
    {
        "path": "UML_TRAINING_THESIS.md",
        "reason": "Active thesis; other agent may edit; org note deferred.",
    },
    {
        "path": "run_uml_mix_ads.py",
        "reason": "Referenced by uml_mix_recipe.json as ADS script; production tooling.",
    },
    {
        "path": "run_uml_mix_ads_precision.py",
        "reason": "Set current mix_ratio in recipe; keep at top.",
    },
    {
        "path": "run_uml_equation_ab.py",
        "reason": "Shared train/eval library imported by many active runners.",
    },
    {
        "path": "run_increments_until_plateau.py",
        "reason": (
            "Ambiguous: still valid sandbox identity plateau tooling, not "
            "clearly retired."
        ),
    },
    {
        "path": "run_teacher_until_plateau.py",
        "reason": "Ambiguous: teacher-anchor plateau loop still useful.",
    },
    {
        "path": "mark_temp_lattice_complete.py",
        "reason": (
            "One-shot but edits thesis/recipe JSON — leave; risky while docs hot."
        ),
    },
    {
        "path": "merge_uml_temp_federations_receipt.py",
        "reason": "One-shot receipt merger that touches thesis/recipe — leave.",
    },
    {
        "path": "Completed UML ladder runners (temp federations, AM/MD, …)",
        "reason": (
            "PASS on ladder but remain canonical re-run / evidence scripts; "
            "not superseded aliases."
        ),
    },
]

OPERATOR_DECISIONS = [
    {
        "topic": "runs/ historical RID/acc99 receipt trees",
        "recommendation": (
            "Leave runs/ in place; only scripts/docs organized. Moving receipt "
            "trees risks broken relative paths and confuses live training layout."
        ),
        "status": "deferred_leave_in_place",
    },
    {
        "topic": "Completed one-shot UML ladder runners at top level",
        "recommendation": (
            "Keep at top for now (canonical ladder). Optional later: "
            "legacy/uml_ladder_pass/ only if operator wants a thinner top level."
        ),
        "status": "deferred_operator_optional",
    },
]


def _patch_sandbox(text: str, name: str) -> str:
    pat = re.compile(
        r"^SANDBOX\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\s*$",
        re.M,
    )
    new_text, n = pat.subn(
        "SANDBOX = Path(__file__).resolve().parents[1]  "
        "# legacy home: parents[1] = test_training/",
        text,
        count=1,
    )
    if n == 1:
        return new_text
    alt = re.compile(r"SANDBOX\s*=\s*Path\(__file__\)\.resolve\(\)\.parent")
    new_text, n2 = alt.subn(
        "SANDBOX = Path(__file__).resolve().parents[1]  "
        "# legacy home: parents[1] = test_training/",
        text,
        count=1,
    )
    if n2 != 1:
        raise SystemExit(f"failed to patch SANDBOX in {name} (matches={n}/{n2})")
    return new_text


def _write_shim(name: str, shim_style: str) -> None:
    if shim_style == "import_main":
        mod = Path(name).stem
        shim = f'''#!/usr/bin/env python3
"""Compatibility shim — implementation moved to legacy/{name}."""
from __future__ import annotations

import sys
from pathlib import Path

_SANDBOX = Path(__file__).resolve().parent
if str(_SANDBOX) not in sys.path:
    sys.path.insert(0, str(_SANDBOX))

from legacy.{mod} import main  # noqa: E402

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
'''
    else:
        shim = f'''#!/usr/bin/env python3
"""Compatibility shim — implementation moved to legacy/{name}."""
from __future__ import annotations

import runpy
from pathlib import Path

_LEGACY = Path(__file__).resolve().parent / "legacy" / "{name}"
runpy.run_path(str(_LEGACY), run_name="__main__")
'''
    (ROOT / name).write_text(shim, encoding="utf-8")


def main() -> int:
    LEGACY.mkdir(exist_ok=True)
    (LEGACY / "__init__.py").write_text(
        '"""Retired / superseded test_training scripts. Prefer top-level production runners."""\n',
        encoding="utf-8",
    )

    manifest_entries = []
    for item in MOVES:
        name = item["file"]
        src = ROOT / name
        dst = LEGACY / name
        if not src.is_file():
            raise SystemExit(f"missing source: {src}")
        if dst.exists():
            raise SystemExit(f"dest already exists: {dst}")
        # Refuse to move if source is already a tiny shim (idempotency guard)
        head = src.read_text(encoding="utf-8", errors="replace")[:200]
        if "Compatibility shim" in head and "legacy/" in head:
            raise SystemExit(f"source already looks like a shim: {src}")

        shutil.move(str(src), str(dst))
        text = dst.read_text(encoding="utf-8")
        dst.write_text(_patch_sandbox(text, name), encoding="utf-8")

        shim_style = item.get("shim_style", "runpy")
        _write_shim(name, shim_style)
        manifest_entries.append(
            {
                "old_path": name,
                "new_path": f"legacy/{name}",
                "shim_path": name,
                "shim_style": shim_style,
                "sandbox_fix": "Path(__file__).resolve().parents[1]",
                "rationale": item["rationale"],
                "confidence": item["confidence"],
                "moved_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    manifest = {
        "schema_version": "test_training_legacy_move_manifest_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_root": str(ROOT),
        "policy": {
            "legacy_home": "legacy/",
            "non_destructive": True,
            "shims_at_old_paths": True,
            "do_not_move": [
                "runs/",
                "checkpoints/",
                "data/",
                "active mix survivor ckpts",
                "uml_mix_recipe.json",
                "UML_TRAINING_THESIS.md",
            ],
        },
        "moved": manifest_entries,
        "left_in_place": LEFT_IN_PLACE,
        "operator_decisions_needed": OPERATOR_DECISIONS,
    }
    (LEGACY / "MOVE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (LEGACY / "README.md").write_text(
        """# test_training/legacy

Retired / superseded sandbox scripts moved out of the production top level.

## Policy

- **Production / active** tooling stays at `test_training/` top level.
- **Legacy** = high-confidence retired campaigns (pre-UML RID/acc99, tiny mint smoke)
  with no active recipe/ladder role.
- Moves are **non-destructive**: implementation lives here; a thin **compatibility
  shim** remains at the old top-level path.
- Do **not** put live checkpoints, active banks, or `runs/uml_mix_layers/` here.
- Do **not** delete files based on inventory guesses.

## Manifest

See `MOVE_MANIFEST.json` for old→new paths, shim style, and rationale.

## Path contract

Scripts in this folder resolve `SANDBOX` as `Path(__file__).resolve().parents[1]`
(the `test_training/` root), not this `legacy/` directory.
""",
        encoding="utf-8",
    )
    print(f"moved={len(manifest_entries)} -> {LEGACY}")
    for e in manifest_entries:
        print(f"  {e['old_path']} -> {e['new_path']} shim={e['shim_style']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
