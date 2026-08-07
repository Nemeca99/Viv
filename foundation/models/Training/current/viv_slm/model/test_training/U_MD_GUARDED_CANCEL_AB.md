# Guarded U canonicalization A/B (U_MD drag subtraction)

## Arms

| Arm | Route |
|-----|--------|
| Baseline | Dynamic `U+M+D` on raw MD AST |
| Candidate | Seal-gated U cancel before federation (`(V*K)/K -> V`, …) |

## Hard conditions

- Seal validity
- `K != 0`
- Exact output identity
- No changed arithmetic semantics
- Zero seal failures

## Run

```powershell
L:\Continue\.venv\Scripts\python.exe `
  L:\Continue\Viv\foundation\models\Training\current\viv_slm\model\test_training\run_uml_md_guarded_canonicalization_ab.py
```

Library: `foundation/lib/uml_guarded_canonicalize.py`  
Receipt: `runs/uml_md_guarded_canonicalization_ab_latest.json`

## Latest result

| Metric | Value |
|--------|------:|
| Objective | **PASS_SUBTRACT_MD_DRAG** |
| MD invocations | 1,802 |
| Routes removed | **1,793 (99.5%)** |
| Residual irreducible MD | **9 (0.50%)** |
| Seal failures | **0** |
| Identity hold | **1.0** |
| Mean symbolic cost | **5.0 → 1.02** |
| `compile_u_md_now` | **false** |
| U_MD-eligible share | residual only (0.50%) |

Removed shapes: `div(mul($0,$1),$1)`, `div(mul($0,$1),$0)`, `div(mul($0,$0),$0)`.  
Residual shape: `div(mul($0,$1),$2)` only.

## Doctrine

Frequency does not prove usefulness. Trainability does not justify persistence. A fast composite is still inferior to no computation when UML seals a valid reduction.

Saint-Exupéry: the first apparent permanent expert was not improved — it was subtracted.

## Enabled

Default **ON** (fail-closed). Override: `UML_GUARDED_CANCEL=0`.

Hooks:
- `lib.uml_guarded_canonicalize.federation_domains_for` / `federation_route_node`
- `lib.uml_equation_registry._domains_in_expr` (MD-only subtract)
- `uml_u_am_shadow.UAMShadowObserver` (federation demand)

Verify: `run_uml_guarded_cancel_enable_verify.py` → `PASS_GUARDED_CANCEL_ENABLED`  
Live demand after enable: U_MD **1,802 → 9** (residual irreducible only).

Only that residual may enter a later `U_MD` service-cost investigation.
