# U_MD shape census (step 1 — no compile)

## Doctrine

Do **not** compile `U_MD` until exact-shape evidence shows a valuable irreducible composite. High MD-domain demand can be a canonicalization defect that `U` should eliminate.

Recommended order:

1. shape census (this step)
2. guarded U simplifier A/B
3. isolated `U_MD` service candidate — only if irreducible shapes win
4. shadow demand
5. authority

## Decisive gate

A compiled `U_MD` must beat **both** dynamic `U+M+D` **and** the cheapest valid structural simplification in `U`.

## Run

```powershell
L:\Continue\.venv\Scripts\python.exe `
  L:\Continue\Viv\foundation\models\Training\current\viv_slm\model\test_training\run_uml_md_shape_census.py
```

Receipt: `runs/uml_md_shape_census_latest.json`

## Latest result (sandbox, same workload family as U_AM shadow)

**Count note:** The first census receipt inflated absolute MD counts via re-entrant
`uml_cost→evaluate→observer`. Shape shares (~99% reducible) were valid. Fixed
census uses `ast_symbolic_cost`. Honest traffic scale matches shadow/A/B:
~12,380 evals / ~1,802 MD.

| Metric | Value |
|--------|------:|
| Distinct MD shapes | 4 |
| Reducible share | **~99.2–99.5%** |
| Irreducible share | **~0.50%** |
| `compile_u_md_now` | **false** |
| Follow-on A/B | **PASS_SUBTRACT_MD_DRAG** (`U_MD_GUARDED_CANCEL_AB.md`) |

Top shapes:

| Shape | Count | Class | Rule |
|-------|------:|-------|------|
| `div(mul($0,$1),$1)` | 371,892 | reducible_by_u | `(V*K)/K -> V` when `K!=0` |
| `div(mul($0,$1),$0)` | 211,839 | reducible_by_u | `(K*V)/K -> V` when `K!=0` |
| `div(mul($0,$0),$0)` | 3,282 | reducible_by_u | `(K*K)/K -> K` when `K!=0` |
| `div(mul($0,$1),$2)` | 2,953 | irreducible_md | — |

Seal checks on cancel rules: **0 failures** in this window.

## Interpretation

`U_MD` high demand is mostly **unnecessary work**, not a composite that deserves permanence. The cheapest expert for ~99% of this MD traffic is likely **no federation at all** — a guarded rewrite in `U`.

If the guarded simplifier wins the next A/B, the correct permanence result is **zero new composite** and removal of expensive MD federation routes for those shapes.

## Next (not done here)

Per-shape A/B of three routes:

1. dynamic `U+M+D`
2. compiled persistent `U_MD` (candidate only)
3. guarded structural reduction in `U`

Measure: invocation frequency by shape, dynamic cost, rewrite cost, compiled cost, creation amortization, Codex/seal parity.
