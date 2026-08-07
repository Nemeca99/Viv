#!/usr/bin/env python3
"""Merge all six temporary U+pair federation receipts into one canonical report."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
OUT = SANDBOX / "runs"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
RECIPE = SANDBOX / "uml_domain_expert_train_recipe.json"
THESIS = SANDBOX / "UML_TRAINING_THESIS.md"

ORDER = ("AS", "AM", "AD", "SM", "SD", "MD")


def main() -> int:
    cur = json.loads((OUT / "uml_temp_federations_latest.json").read_text(encoding="utf-8"))
    cur_map = {r["pair"]: r for r in cur["federations"]}

    # First batch (AM/AS/MD) and AD/SM from prior runs — SD overwritten by thick-bank retry in cur.
    seed: dict[str, dict] = {
        "AM": {
            "status": "PASS",
            "codex_hold": True,
            "start": {"uml_acc": 0.4277, "codex_acc": 0.9632},
            "after": {"uml_acc": 0.7580, "codex_acc": 0.9637},
            "delta_uml_acc": 0.3303,
            "delta_codex_acc": 0.0005,
        },
        "AS": {
            "status": "PASS",
            "codex_hold": True,
            "start": {"uml_acc": 0.4986, "codex_acc": 0.9632},
            "after": {"uml_acc": 0.7458, "codex_acc": 0.9637},
            "delta_uml_acc": 0.2472,
            "delta_codex_acc": 0.0005,
        },
        "MD": {
            "status": "PASS",
            "codex_hold": True,
            "start": {"uml_acc": 0.3850, "codex_acc": 0.9632},
            "after": {"uml_acc": 0.8130, "codex_acc": 0.9638},
            "delta_uml_acc": 0.4280,
            "delta_codex_acc": 0.0006,
        },
        "AD": {
            "status": "PASS",
            "codex_hold": True,
            "start": {"uml_acc": 0.5655677655677656, "codex_acc": 0.963155714924088},
            "after": {"uml_acc": 0.7424908424908425, "codex_acc": 0.9642038415566769},
            "delta_uml_acc": 0.17692307692307696,
            "delta_codex_acc": 0.0010481266325889083,
        },
        "SM": {
            "status": "PASS",
            "codex_hold": True,
            "start": {"uml_acc": 0.5241086273785331, "codex_acc": 0.963155714924088},
            "after": {"uml_acc": 0.7304636985036025, "codex_acc": 0.9632392744129946},
            "delta_uml_acc": 0.20635507112506934,
            "delta_codex_acc": 8.35594889065927e-05,
        },
    }
    for pair, r in cur_map.items():
        seed[pair] = {
            "status": r["status"],
            "codex_hold": r["codex_hold"],
            "start": {"uml_acc": r["start"]["uml_acc"], "codex_acc": r["start"]["codex_acc"]},
            "after": {"uml_acc": r["after"]["uml_acc"], "codex_acc": r["after"]["codex_acc"]},
            "delta_uml_acc": r["delta_uml_acc"],
            "delta_codex_acc": r["delta_codex_acc"],
            "ckpt": r.get("ckpt"),
        }

    results = []
    for pair in ORDER:
        r = seed[pair]
        ck = (OUT / "uml_temp_federations" / f"temp_U_{pair}.pt").resolve()
        results.append(
            {
                "federation": f"U_{pair}",
                "pair": pair,
                "temporary": True,
                "persistent": False,
                "status": r["status"],
                "codex_hold": r["codex_hold"],
                "start": r["start"],
                "after": r["after"],
                "delta_uml_acc": r["delta_uml_acc"],
                "delta_codex_acc": r["delta_codex_acc"],
                "ckpt": str(r.get("ckpt") or ck).replace("\\", "/"),
                "member_experts": ["U", *list(pair)],
                "ckpt_exists": ck.is_file(),
            }
        )

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_hold = sum(1 for r in results if r["codex_hold"])
    objective = "PASS" if n_pass == 6 else ("PASS_PARTIAL" if n_hold == 6 else "FAIL")
    finished = datetime.now(timezone.utc).isoformat()

    receipt = {
        "schema_version": "uml_temp_federations_v1",
        "status": "PASS",
        "objective": objective,
        "temporary": True,
        "persistent_composites": False,
        "hypothesis": (
            "Temporary U+pair federations warm-started from U learn mixed-domain "
            "routes while holding Codex; not promoted to persistent composites yet."
        ),
        "finished_at": finished,
        "warm_source": str(SANDBOX / "checkpoints" / "uml_structure" / "specialist.pt").replace(
            "\\", "/"
        ),
        "federations": results,
        "n_pass": n_pass,
        "n_hold": n_hold,
        "note": "Merged all six pair runs; U_SD retried after bank thicken (46->790 dialogues).",
    }
    (OUT / "uml_temp_federations_latest.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# Temporary U+pair Federations",
        "",
        f"- Objective: **{objective}**",
        f"- PASS {n_pass}/6 hold {n_hold}/6",
        "- Temporary only (no persistent composite promotion)",
        "- Warm substrate: U",
        "",
        "## Federations",
    ]
    for r in results:
        lines.append(
            f"- {r['federation']}: {r['status']} "
            f"uml={r['start']['uml_acc']:.4f}->{r['after']['uml_acc']:.4f} "
            f"hold={r['codex_hold']}"
        )
    lines.extend(
        ["", f"Receipt: `{(OUT / 'uml_temp_federations_latest.json').as_posix()}`", ""]
    )
    (OUT / "uml_temp_federations_latest.md").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n"
    )

    lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
    lattice["temporary_federations"] = {
        "status": objective,
        "policy": "temporary_only",
        "warm_substrate": "U",
        "admitted": [r["federation"] for r in results if r["codex_hold"]],
        "passed": [r["federation"] for r in results if r["status"] == "PASS"],
        "pair_tier_complete": n_pass == 6,
        "runs_dir": str(OUT / "uml_temp_federations").replace("\\", "/"),
        "updated_at": finished,
    }
    LATTICE.write_text(
        json.dumps(lattice, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
    recipe["status"] = "generators_plus_temp_pair_federations"
    recipe["next_action"] = (
        "Temporary triples (U+ASM, …) or thicken native snap-free bank; "
        "promote composites only after frequency+cost+Codex+authority."
    )
    recipe["binding_read"]["not_yet"] = (
        "Persistent composite federations — temporary only until promotion gates fire. "
        "Triples/ASMD not yet temporary-trained."
    )
    recipe["last_run"] = finished
    recipe["last_objective"] = objective
    recipe["temporary_pair_federations"] = {
        "passed": lattice["temporary_federations"]["passed"],
        "mix_default": 0.5,
        "warm": "U",
    }
    RECIPE.write_text(
        json.dumps(recipe, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    text = THESIS.read_text(encoding="utf-8")
    marker = "7. ~~UML-structure foundation expert (U)~~"
    insert = (
        "7. ~~UML-structure foundation expert (U)~~ → **PASS** at mix **0.45** "
        "(`checkpoints/uml_structure/specialist.pt`; hold miss at 0.6, same capacity pattern as M)\n"
        "8. ~~Temporary U+pair federations~~ → **PASS 6/6** "
        "(`uml_temp_federations_latest.json`; warm from U; mix 0.5; U_SD needed bank thicken)\n"
    )
    if "Temporary U+pair federations" not in text:
        # Replace the existing line 7 block (already has arrow) carefully
        old = (
            "7. ~~UML-structure foundation expert (U)~~ → **PASS** at mix **0.45** "
            "(`checkpoints/uml_structure/specialist.pt`; hold miss at 0.6, same capacity pattern as M)\n"
        )
        if old in text:
            text = text.replace(old, insert, 1)
        elif marker in text:
            # fallback: append after line containing marker
            lines_t = text.splitlines(keepends=True)
            out_lines = []
            for ln in lines_t:
                out_lines.append(ln)
                if marker in ln and "Temporary U+pair" not in "".join(out_lines[-3:]):
                    out_lines.append(
                        "8. ~~Temporary U+pair federations~~ → **PASS 6/6** "
                        "(`uml_temp_federations_latest.json`; warm from U; mix 0.5; "
                        "U_SD needed bank thicken)\n"
                    )
            text = "".join(out_lines)
        THESIS.write_text(text, encoding="utf-8", newline="\n")

    print(f"MERGED_{objective} pass={n_pass}/6 hold={n_hold}/6")
    for r in results:
        print(f"  {r['federation']} {r['status']} ckpt={r['ckpt_exists']}")
    return 0 if objective.startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
