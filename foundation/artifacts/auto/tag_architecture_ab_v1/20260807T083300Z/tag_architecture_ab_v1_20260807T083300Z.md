# TAG_ARCH_AB_V1: Offline Tag Architecture A/B

**Verdict: TIE_WITH_CONSTRAINTS**

## Candidates actually tested

- **LAYERED_BRIDGE:** native authority packets, mouth rows, UML route receipts, context roles, and optional item-77 receipts remain in separate namespaces. A schema-locked bridge carries common provenance/authority metadata and qualified composition bindings. Native validators remain authoritative.
- **UNIFIED_TYPED_REGISTRY:** every logical tag serializes as one fixed record (`plane`, `name`, `value`, `source`, `authority`, `confidence`, `required`, `provenance`, `attributes`, `binding`). Packet groups retain digest/signature metadata and are reconstructed for the existing packet validator. Existing plane validators are delegated, not replaced.

Arm B is a constrained typed registry, not a flat union. Delegating existing plane validators does not turn it into Arm A because every tag still serializes and looks up through the registry.

## Inputs

- Valid bundles: **96**
- Valid logical records: **2016**
- Adversarial cases: **140**
- Mouth domains: `architect_work, automatic_services, cpu_gpu_panel, cpu_mind, gpu_mouth, identity, no_tools, ops_panel`
- UML route labels: `A, D, LIT, M, S, U, U_AD, U_AM, U_AMD, U_AS, U_ASD, U_ASM, U_ASMD, U_MD, U_SD, U_SM, U_SMD`

## Metrics

| Metric | Layered bridge | Typed registry | B - A |
|---|---:|---:|---:|
| Valid accepted bundles | 96 | 96 | 0 |
| Valid false rejects | 0 | 0 | 0 |
| Adversarial false accepts | 0 | 0 | 0 |
| Field-loss bundles | 0 | 0 | 0 |
| Unresolved ambiguities | 0 | 0 | 0 |
| Audit fields missing | 0 | 0 | 0 |
| Serialized bytes | 2540219 | 2240351 | -299868 |
| UML character indices | 2540219 | 2240351 | -299868 |
| Candidate LOC proxy | 252 | 59 | -193 |
| Candidate branch proxy | 59 | 8 | -51 |
| Validation p50, ms/corpus | 111.133300 | 72.732700 | -38.400600 |
| Qualified lookup p50, ns/op | 59.885 | 62.851 | 2.966 |
| Native schema rewrites (proxy) | 0 | 5 | 5 |

Timing is included only as a local repeated benchmark. Low-signal timing is excluded from the decision score.

## Hard gates

- LAYERED_BRIDGE: **PASS** — `{"authority_false_accepts":0,"field_loss_bundles":0,"nondeterministic_replays":0,"seal_or_binding_ambiguities":0,"status":"PASS"}`
- UNIFIED_TYPED_REGISTRY: **PASS** — `{"authority_false_accepts":0,"field_loss_bundles":0,"nondeterministic_replays":0,"seal_or_binding_ambiguities":0,"status":"PASS"}`

## Item-77 integration

- Status: **INTEGRATED**
- Receipt: `L:/Continue/Viv/foundation/models/Training/current/viv_slm/model/test_training/runs/uml_speak_cheap_census/census_20260807T082414Z/census.json`
- Per-example rows replayed: **768**
- Experiment-only names `item77_receipt` and `cheap_route_example` are proposed/operator-gated if production promotion is ever considered. The measured receipt fields remain value fields, not established tag names.

## Removal test

- Layered bridge removed: rejected=True; breaks `cross_plane_logical_roundtrip, composition_binding_resolution, qualified_and_ambiguity_safe_lookup, common_provenance_audit`.
- Typed registry removed: rejected=True; breaks `all_tag_serialization, typed_lookup, packet_group_reconstruction, common_provenance_audit`.

## Decision evidence

- Score: `{"evidence":[{"a":2540219.0,"b":2240351.0,"metric":"serialized_footprint","weight":1,"winner":"UNIFIED_TYPED_REGISTRY"},{"a":311.0,"b":67.0,"metric":"candidate_specific_static_complexity","weight":1,"winner":"UNIFIED_TYPED_REGISTRY"},{"a":0,"b":5,"metric":"native_schema_migration_proxy","note":"Weighted for production change risk; still a static proxy.","weight":2,"winner":"LAYERED_BRIDGE"},{"a":111.1333,"b":72.7327,"metric":"validation_latency_p50","weight":1,"winner":"UNIFIED_TYPED_REGISTRY"},{"metric":"qualified_lookup_latency_p50","note":"Excluded as low-signal Python micro-timing.","weight":0,"winner":null}],"footprint_complexity_threshold":"10%","point_delta_b_minus_a":1,"points":{"LAYERED_BRIDGE":2,"UNIFIED_TYPED_REGISTRY":3},"reason":"predeclared_material_delta_points","tie_band":"absolute point delta < 2","timing_threshold":"10% and not low-signal"}`
- Classification: The tested typed-envelope/delegated-validator design is substantively Arm B. A future single envelope that keeps plane validators authoritative is not automatically a synthesis; if every tag serializes through the typed registry, it remains constrained UNIFIED_TYPED_REGISTRY.

## Reproduce

`L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\foundation\scripts\tag_architecture_ab_v1.py --full`

## Limitations

- Both candidates are executable offline prototypes in one harness, not production router integrations. Static migration and complexity counts are proxies, not maintainability claims.
- Latency is local Python timing under concurrent workstation load; qualified lookups below the declared signal floor are labeled low-signal and excluded from the decision.
- UML character-token count is one index per Unicode scalar. It is not a neural tokenizer count, energy reading, or tariff estimate.
- Production authority HMAC uses a process-local secret, so cross-process signature bytes are intentionally not a reproducibility target. Within-run canonical replay hashes must still be identical.
- Item-77 integration remains pending when no timestamped per-example receipt is discoverable. This does not invalidate the requested fallback corpus, but it limits real cheap-route receipt coverage.
- Any production tag/plane promotion, router migration, new item-77 tag name, model/training change, or checkpoint change requires operator authority.

## Recommended next action

Operator review the measured tie/winner constraints and authorize at most one read-only adapter pilot on a single existing receipt path; do not promote or change production schemas from this offline result alone.

No runtime, router, production tag schema, checkpoint, training data, curriculum admission, or model state was changed.
