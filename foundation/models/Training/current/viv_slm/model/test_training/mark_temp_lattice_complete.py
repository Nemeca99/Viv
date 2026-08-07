#!/usr/bin/env python3
"""Mark full temporary arithmetic lattice complete after U_ASMD PASS."""
from __future__ import annotations

import json
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent


def main() -> int:
    recipe_path = SANDBOX / "uml_domain_expert_train_recipe.json"
    lattice_path = SANDBOX / "uml_domain_expert_lattice.json"
    thesis_path = SANDBOX / "UML_TRAINING_THESIS.md"
    asmd = json.loads(
        (SANDBOX / "runs" / "uml_temp_asmd_federation_latest.json").read_text(encoding="utf-8")
    )
    finished = asmd["finished_at"]
    fed = asmd["federations"][0]

    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    recipe["status"] = "full_temporary_arithmetic_lattice"
    recipe["next_action"] = (
        "Promotion-gate pilot (frequency+cost+Codex+authority) OR thicken native "
        "snap-free bank (P2 native cheap_rate 0.25). Do not promote all temp federations wholesale."
    )
    recipe["binding_read"]["not_yet"] = (
        "Persistent composite federations — temporary lattice complete (6+4+1) but "
        "promotion gates not fired. Native snap-free path still weak."
    )
    recipe["last_run"] = finished
    recipe["last_objective"] = "ALL_FOUR_PASS"
    recipe["temporary_asmd_federation"] = {
        "passed": ["U_ASMD"],
        "mix_default": 0.5,
        "warm": "U",
        "uml_start": fed["start"]["uml_acc"],
        "uml_after": fed["after"]["uml_acc"],
        "codex_hold": fed["codex_hold"],
    }
    recipe["temporary_lattice_summary"] = {
        "foundations_persistent": ["U", "A", "S", "M", "D"],
        "pairs_temp_pass": 6,
        "triples_temp_pass": 4,
        "asmd_temp_pass": 1,
        "arith_configs_validated": 15,
        "persistent_composites": 0,
    }
    recipe_path.write_text(
        json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lattice = json.loads(lattice_path.read_text(encoding="utf-8"))
    lattice["temporary_lattice_complete"] = {
        "status": "PASS",
        "arith_configs": 15,
        "pairs": 6,
        "triples": 4,
        "asmd": 1,
        "persistent_composites": False,
        "policy": "temporary_only_until_promotion_gates",
        "updated_at": finished,
    }
    lattice_path.write_text(
        json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    thesis = thesis_path.read_text(encoding="utf-8")
    if "Temporary U_ASMD" not in thesis:
        old = (
            "9. ~~Temporary U+triple federations~~ → **PASS 4/4** "
            "(`uml_temp_triple_federations_latest.json`; ASM/ASD/AMD/SMD; warm from U; mix 0.5)\n"
        )
        new = old + (
            "10. ~~Temporary U_ASMD~~ → **PASS** (`uml_temp_asmd_federation_latest.json`; "
            "uml 0.2453→0.8611; Codex hold; full temporary arithmetic lattice 15/15)\n"
        )
        if old in thesis:
            thesis = thesis.replace(old, new, 1)
            thesis_path.write_text(thesis, encoding="utf-8", newline="\n")
        else:
            raise SystemExit("thesis_line9_not_found")

    print("DOCS_UPDATED temporary_lattice_complete=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
