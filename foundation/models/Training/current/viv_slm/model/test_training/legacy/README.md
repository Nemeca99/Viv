# test_training/legacy

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

## mint_specialists CLI guard

Top-level `mint_specialists.py` still imports `main` for `run_sandbox_smoke`
auto-mint-if-missing. Bare CLI requires `--execute` so smoke-checks cannot
accidentally overwrite real specialists.
