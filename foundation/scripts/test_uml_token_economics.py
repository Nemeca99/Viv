"""Test the UML token economics equation with explicit fixture energy."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.uml_engine import uml_cost  # noqa: E402
from lib.uml_token_economics import TokenEconomics  # noqa: E402


def main() -> int:
    shape = uml_cost("Viv")
    no_energy = TokenEconomics(
        symbolic_nodes=int(shape["ast_nodes"]),
        neural_tokens=2,
        dependency_depth=int(shape["max_depth"]),
        verified_value=3,
    ).calculate()
    fixture_energy = TokenEconomics(
        symbolic_nodes=1,
        neural_tokens=2,
        dependency_depth=1,
        verified_value=3,
        joules=0.42,
    ).calculate(joules_reference=1.0)
    assert no_energy["energy_observed"] is False
    assert fixture_energy["energy_observed"] is True
    assert fixture_energy["processing_cost"] == 4.42
    assert fixture_energy["energy_per_neural_token"] == 0.21
    print(json.dumps({"ok": True, "no_energy": no_energy, "fixture_energy": fixture_energy}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
