# IDENTITY_UML_BRIDGE_SHADOW_V1

**Verdict:** `FIELD_SCOPED_WINS`

Field-scoped bridge preserves seal/provenance/fail-closed; scan-surface does not clear hard gates.

- Promotion: `False`
- Mutation: `False`
- Registry sha: `0cc5215c43a195b4…`
- Corpus: n=72 (valid=48, adv=24)

## Summaries

| Arm | Contract pass | Valid | Adversarial | Seal fails | False accepts | p50 ms | Hard gate |
|---|---:|---:|---:|---:|---:|---:|---|
| FIELD_SCOPED | 72/72 (1.000) | 48/48 | 24/24 | 0 | 0 | 2.324 | PASS |
| SCAN_SURFACE | 63/72 (0.875) | 40/48 | 23/24 | 0 | 1 | 2.320 | FAIL |

## Boundary contract

- byte/seal identity survives round trip
- no invented bindings
- correct domain/federation selected
- provenance survives both directions
- identity payload unchanged outside uml_resolved
- fail-closed on malformed/ambiguous/authority cases
- adapter latency recorded but never outranks correctness

Tag-architecture secondary: `PASS`

No promotion. No mutation. Defer scaffold-dependence / soft-0.99 until bridge is clean.
