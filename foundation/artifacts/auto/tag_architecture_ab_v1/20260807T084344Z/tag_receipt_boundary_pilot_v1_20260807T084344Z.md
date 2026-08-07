# TAG_RECEIPT_BOUNDARY_PILOT_V1

- Schema: `tag_receipt_boundary_pilot_v1`
- Prior A/B: `TAG_ARCH_AB_V1` / `TIE_WITH_CONSTRAINTS`
- Verdict: **TIE_WITH_CONSTRAINTS**
- Material advantage: `False`
- Promote: `None`

## Material-advantage thresholds

- Adapter/migration steps ratio ≥ **2.0×** with no migration-risk increase and zero semantic ambiguity
- Or ≥ **20.0%** serialized-byte **and** validate-latency advantage with zero migration-risk increase
- Or clear seal/provenance hard-gate failure on exactly one arm
- Seal-first: any seal/destination/provenance loss is a hard fail for that arm

## Selected receipt

- Census: `L:/Continue/Viv/foundation/models/Training/current/viv_slm/model/test_training/runs/uml_speak_cheap_census/census_20260807T082414Z/census.json`
- Census sha256: `4e5cae2b14fb5de224e1dd672a94687d1a4ce0b8077249d1cb84009753bb60e6`
- Example: `SC77-000`
- Mode: `prefer_efficient_snap`
- Row sha256: `2d0c06ad8eefd1009c6fc4377060bc927ac16ad0c4de35226706ced3d5ceea3e`
- Selection score/reasons: `55` / `destination_match,sealed_destination,policy_mode,raw_vs_final_mode,raw_and_final,raw_ne_final,federation,cost,error,cheapest,kind,rid_available,plant_available,survivor_hash`
- Fields bound: `cheapest, cost, destination_match, error, federation, final_route, kind, plant_state, policy_mode, prompt, raw_route, rid_state, sealed_destination, source, survivor_hash, uml_domains`

## Metrics

| Metric | LAYERED_BRIDGE | UNIFIED_TYPED_REGISTRY |
| --- | --- | --- |
| hard_gate | PASS | PASS |
| seal_preserved | True | True |
| provenance_preserved | True | True |
| migration_steps | 3 | 4 |
| native_schema_rewrites | 0 | 1 |
| field_remaps_proxy | 0 | 11 |
| packet_seal_reconstruction_required | False | True |
| serialized_bytes | 9703 | 8225 |
| validate_p50_ms | 0.4665 | 0.3378 |
| serialize_p50_ms | 0.0869 | 0.0751 |
| lookup_p50_ms | 0.2617 | 0.1367 |
| appendix5_removal_rejected | True | True |

## Hard gates

- LAYERED_BRIDGE: **PASS**
- UNIFIED_TYPED_REGISTRY: **PASS**

## Decision reasons

- differences_below_material_threshold_or_risk_tradeoff
- layered_bridge_lower_migration_surface_but_not_alone_material_under_rule
- typed_registry_smaller_or_faster_but_not_alone_material_under_rule

## Secondary seal-failure observation

- Example: `SC77-000` mode `raw_no_snap`
- Note: Secondary observation only; primary comparison remains the sealed receipt. Included to clarify seal-preservation behavior under SEAL_GUARD_STOP / destination_match=false.
- LAYERED_BRIDGE: seal_preserved=`True` destination_match_preserved=`True` hard_fail=`False`
- UNIFIED_TYPED_REGISTRY: seal_preserved=`True` destination_match_preserved=`True` hard_fail=`False`

## Mutation guard

- Status: **PASS**
- Census unchanged: `True`
- Survivor checkpoint unchanged: `True`

## Reproducible command

```powershell
L:\Continue\.venv\Scripts\python.exe L:/Continue/Viv/foundation/scripts/tag_receipt_boundary_pilot_v1.py --run --census L:/Continue/Viv/foundation/models/Training/current/viv_slm/model/test_training/runs/uml_speak_cheap_census/census_20260807T082414Z/census.json
```

## Limitations

- Single-receipt pilot only; not a multi-window architecture bakeoff.
- Migration step / rewrite counts are explicit proxies for this binding, not full production cutover estimates.
- Latency is local Python timing; low-signal distributions are excluded from the material efficiency rule.
- Experiment-only names item77_receipt / cheap_route_example remain proposed and operator-gated.
- No production schema promotion, router change, training, or checkpoint mutation was performed.

## Recommended next action

Defer architecture choice; retain TIE_WITH_CONSTRAINTS. No second receipt class required unless operator wants a non-LIT federation sealed row as a follow-up observation (not a promotion gate).

