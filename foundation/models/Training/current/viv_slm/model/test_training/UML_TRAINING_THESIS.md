# Viv-SLM Training Thesis

**Status:** active — **closed executable proof** + **ladder PASS** (T10 cheap-route closed via prefer-efficient snap)  
**Date:** 2026-08-06  
**Scope:** UML equation lane on top of Codex identity plant — specialists and Codex trees untouched unless explicitly promoted.  
**Proof receipt:** `runs/uml_training_thesis_selftest_latest.json` (schema `uml_training_thesis_selftest_v2`)  
**Runner:** `test_uml_training_thesis.py`  
**Registry:** `uml_equation_registry_v1.2` / `nested_pemdas_equivalents_v1_2` (federation-diversity equivalents)  
**Mix bank:** `v6_federation` (rebuild on v1.2 registry)

---

## Short form

> **Determinism chooses the destination. Probability chooses the route. Domain weighting chooses who participates. Cost chooses which valid route should win.**

Viv does **not** use probability to choose what is true. The correct token is already fixed. Probability chooses **how** to reach it.

**Division of labor (binding):**

| Layer | Owns |
|-------|------|
| **UML** | The **tokenizer** — encode/decode, sealed token identity, equation surfaces, what a token *is* |
| **RID** | **Stability** of system / training — continuous `[0,1]` health fold, residual into PID, when to halt or cool down |

UML controls the tokens. RID controls whether the plant stays healthy while those tokens are trained and routed.

**Paradox as machinery:** the probability can move; the route can change; **the answer cannot.**

**RID address form:** every identity is a unique coordinate in one `[0,1]` normalized field. Parameter growth deepens decimal precision; it does not invent a separate floating-point species per weight.

**Training medium:** the UML plant is trained on **math → tokens**, not prose → tokens. Text exists only outside the codec boundary.

---

## Math into tokens (codec boundary)

```text
User text
  → UML encode (lossless Nested-PEMDAS per sealed char)
  → model thinks / responds in UML equation tokens
  → UML decode
  → User text
```

| Outside the plant | Inside the plant |
|-------------------|------------------|
| Human language, UI, logs | Equation tokens (`41`, `40+1`, `(41*2)/2`, …) |
| Encode / decode only | Route selection, domain federations, RID residual |

**Math does not lie.** Arithmetic evaluation is deterministic. If the decoded identity is wrong for the intended seal, the **equation / question / route was invalid** — not that math invented a new truth. A costly-but-valid equation is a **routing fault**, still sealed to the same token.

### Structure vs sealed identity binding

| Equation | Status | Deterministic result |
|----------|--------|----------------------|
| `A + A` with `A` unbound | **Unbound / incomplete** | `2A` (structure). Not `2`. |
| `A + A` with sealed `A = 1` | **Bound** | `2` necessarily |
| `1 + 1` | **Grounded** | `2` — no identity to guess |

If Viv answers `2` to `A + A` without a sealed binding `A = 1`, arithmetic did not fail. The **encoding was incomplete**, or the system **invented a binding that was never provided**. That is forbidden.

Viv must preserve both:

1. **Structure** — e.g. `A + A`  
2. **Identity binding** — what `A` deterministically represents  

Then the result follows necessarily. Probability may choose the compute/simplify **route**, but it **cannot guess what `A` means**.

Machine form: `uml_structure_binding.py` (T15).

We do **not** train the UML lane as English next-token prediction. Codex identity hold remains a separate text plant; UML mix banks and native prompts are equation-token surfaces (`uml_codec_io.py`).

---

## RID normalized address space

RID folds leave continuous values in `[0,1]`. In this architecture that interval is not a bag of unrelated floats — it is a **unique address space** for probability identities.

### Decimal precision as expanding capacity

| Decimal depth `d` | Unique nonzero slots | Notes |
|------------------:|---------------------:|-------|
| 1 | 9 | `0.1` … `0.9` |
| 2 | 99 | `0.01` … `0.99` |
| 3 | 999 | `0.001` … `0.999` |
| `d` | **10ᵈ − 1** | quantized open unit interval |

For `N` unique parameters, required depth:

```text
d = ceil(log10(N + 1))
```

Examples: 999 → 3 digits; ~1e6 → 6; ~1e9 → 9; ~1e12 → 12.

**No two parameters share the same RID-normalized identity** at the active precision depth. Growth of `N` expands **precision depth**, not the count of independent floating-point object types.

### How this connects to UML + experts

```text
Prompt
→ lossless UML identity
→ locate the relevant region in RID-normalized probability space
→ choose among valid routes (A/S/M/D federations)
→ select the most efficient route
→ decode the fixed token answer
```

| Conventional | Viv |
|--------------|-----|
| Distribute an answer across billions of learned floats; reconstruct by vote | Normalize possibilities into unique RID coordinates; UML locates the region; probability only picks the **route** |

The trillion describes **capacity of the uniquely indexed probability field**. Decimal depth is the **resolution** that distinguishes every location. Experts do not each guess the answer — they route to the already located sealed identity.

Machine form: `rid_normalized_address_space.json`. Combinatorial selftest: **T12** in `test_uml_training_thesis.py`.

---

## Closed executable proof (2026-08-06)

This is the first **closed executable proof of the thesis contract**.

Not industry-scale generalization — but the core mechanism is no longer merely philosophical. It is **implemented, testable, and falsifiable**.

Implemented loop under test:

```text
prompt identity
→ reversible UML
→ applicable domain lattice
→ multiple valid routes
→ probabilistic route selection
→ sealed deterministic token
→ route-cost residual (RID)
```

| ID | Claim under test | Result |
|----|------------------|--------|
| **T4** | Probability varies route without breaking destination seal | **32 samples, varying routes, 0 seal breaks** |
| **T1** | A/S/M/D generate lattice | **15** unordered / **64** ordered / **11** mixed |
| **T2** | UML reversible on tested surfaces | byte-for-byte round-trip PASS |
| **T3** | Equivalence-class identity + invalid reject | 9 routes → `H`; `999` rejected |
| **T5** | Domain + federation tagging | A/S/M/D and `AM` PASS |
| **T6** | RID residual is measurable route health | cheap `0.0` / bad `1.0` |
| **T7** | Held-out / longer surfaces reverse + seal | **PASS** (7 surfaces, 0 seal breaks) |
| **T8** | Cost pressure: decide=cheapest; low-T ≤ high-T | **PASS** (decide `41`; mean cost 1.0 @T=0.05 vs 2.73 @T=2.5) |
| **T9** | Bank realizes generators + mixed federations | **PASS** after registry **v1.2** diversity fill (was 0 mixed under cost-only bank) |
| **T10** | Live speak seal + cheap_rate | **PASS** — match=1.0, cheap=1.0 via `prefer_efficient_snap` (7/7) |
| **T11** | Multi-char sealed chain (`Viv`) | **PASS** |
| **T12** | RID decimal address capacity + uniqueness | **PASS** — `d=ceil(log10(N+1))`, slots=`10^d-1` |
| **T13** | Vocab chars ↔ unique RID slots + UML locate | **PASS** — N=96 → d=2, 99 slots; locate_ok=5/5 |
| **T14** | Math→tokens codec; math does not lie | **PASS** — native `UML:…` prompt; invalid vs routing fault classified |
| **T15** | Structure vs sealed binding | **PASS** — `?A+?A`→`2*?A`; with `?A=1`→`2`; `1+1` grounded; invent forbidden |
| **T16** | Native UML speak shell | **PASS** — `UML:…` plant prompt; decode seals surface |
| **T17** | Thermal RID ranks sealed routes | **PASS** — plant live (`master_s_n≈0.74`); snap=`thermal_efficient`; 0 seal breaks |

Together these are one connected system selftest, not isolated unit checks.

### Expanded claims (from this cycle)

1. **Held-out generalization (T7):** Seal + reverse are not limited to the original smoke surfaces.  
2. **Efficiency pressure is causal (T8):** Temperature modulates mean route cost without breaking the seal — cost chooses among valids.  
3. **Cost-only banks starve composition (T9 refine):** Lowest-cost equivalents were mono-heavy. **Registry v1.2** reserves federation-diversity slots.  
4. **Prefer-efficient is cost/thermal policy, not truth policy (T10/T17):** Among sealed routes, snap prefers thermally efficient Nested-PEMDAS path (foundation `master_rid` coolant/gpu stress × equation heat). Destination unchanged.  
5. **Prompt = sealed chain (T11):** Multi-char text is a concatenation of per-token sealed routes.  
6. **RID is a unique normalized address field (T12/T13):** Parameter growth deepens decimal precision; vocab identities occupy unique slots; UML locates the sealed char in that field.  
7. **Math→tokens (T14):** Native plant prompts are equation streams; prose stays outside encode/decode; faults are invalid equation or routing fault — never “math lied.”  
8. **Structure vs binding (T15):** Unbound `A+A`→`2A`; sealed `A=1` unlocks `2`; grounded `1+1` needs no guess; inventing bindings is forbidden.
9. **Thermal plant ↔ training route (T17):** Foundation RID thermal stability informs which valid equation is preferred at speak/encode. Matched train A/B (`thermal_route_weight` 0 vs 1.0, +10k, v6): **THERMAL_TIE** — keep train weight off; snap policy stays on.
10. **Plant metabolism (layers L1–L4):** Longer steps → soft boost → native bank → furnace `S_n` gate. L4 under live **SHED_LOAD** recovered v6 UML **0.588→0.859** (past prior dialogue peak) with Codex hold. **Proved:** operational metabolism (not mere telemetry). **Matched gated-vs-ungated A/B:** **TIE_COMPATIBLE_ONLY** (gated 0.859 vs ungated 0.864, Δacc=-0.0046) — SHED_LOAD did **not** cause the lift; keep gate as capacity governor, not as a performance booster.

### Training metabolism (binding read)

```
plant S_n measures capacity
  → furnace reduces UML mix dose (SHED_LOAD / CRITICAL)
  → training continues within that capacity
  → UML improves
  → Codex remains intact
```

Do not collapse “compatible” into “causal.” Causal credit for the gate waits on the matched A/B.

### What this does / does not prove

**Proved (sandbox):** thesis contract; held-out reverse/seal; cost-pressure sampling; mixed federations in bank; prefer-efficient speak snaps to cheapest; RID slot addressing for vocab; ADS mix ceiling ~0.78; layer stack + plant-gate **operational metabolism**; matched plant_sn A/B **TIE** (gate compatible, not causal for UML lift).  
**Not yet proved:** Codex hold under full A/S/M/D expert training; compute-normalized wins vs conventional designs; industry-scale / trillion-parameter plant; snap-free LM that *internally* prefers cheap without post-policy.

### Next evidence ladder (emergence-ranked)

From `run_uml_emergence_audit.py` (system-says order):

1. ~~Wire native UML speak (`speak_uml_native`)~~ → **P1 addressed** (`speak_uml_native.py`, T16)  
2. ~~Train on math-token dialogues~~ → **L3 addressed** (`uml_native_math_tokens_v1`)  
3. ~~Matched plant_sn gated vs ungated A/B~~ → **TIE_COMPATIBLE_ONLY** (`uml_plant_sn_ab_latest.json`)  
5. ~~Snap-free speak audit (P2)~~ → **PASS** (`uml_snap_free_audit_latest.json`: english **0.10**; native no-snap **1.00** after native thicken v2)  
6. ~~Stand up A/S/M/D domain expert specialists (P3)~~ → **PASS 4/4** (`uml_domain_experts_latest.json`; M retried at mix 0.5 after first-pass hold miss)  
7. ~~UML-structure foundation expert (U)~~ → **PASS** at mix **0.45** (`checkpoints/uml_structure/specialist.pt`; hold miss at 0.6, same capacity pattern as M)  
8. ~~Temporary U+pair federations~~ → **PASS 6/6** (`uml_temp_federations_latest.json`; warm from U; mix 0.5; U_SD needed bank thicken)
9. ~~Temporary U+triple federations~~ → **PASS 4/4** (`uml_temp_triple_federations_latest.json`; ASM/ASD/AMD/SMD; warm from U; mix 0.5)
10. ~~Temporary U_ASMD~~ → **PASS** (`uml_temp_asmd_federation_latest.json`; uml 0.2453→0.8611; Codex hold; full temporary arithmetic lattice 15/15)
11. ~~Promotion-gate pilot~~ → **PASS_SCALE_TEMPORARY_DEFAULT** (`uml_federation_promotion_gate_latest.json`; 0/11 candidates; 11/11 train-ok/promote-deny; AM/MD appear often in bank but never beat mono/LIT on cost)
12. ~~Native thicken (snap-free)~~ → **PASS** (`uml_native_thicken_latest.json`; native cheap 0.25→1.00; survivor committed)
13. ~~Cost-winner hunt~~ → **BLOCKED_PREREQUISITE** (`uml_cost_winner_hunt_latest.json`; 0 full wins; 0 mixed routes with C_mixed < C_mono_LIT across tax 0/1/2/4; assembly tax cannot invent a winner)
14. ~~Mixed-workload cost benchmark~~ → **FOUND_SERVICE_COST_WINNER** (`uml_mixed_cost_benchmark_latest.json`; variable-input U_AM; no promotion without frequency + authority)
15. ~~U_AM scale sweep~~ → **PASS_SCALE_CROSSOVER** (`uml_am_scale_sweep_latest.json`; compiled UML macro only; checkpoint-runtime equivalence not claimed; no promotion)
16. ~~U_AM candidate contract~~ → **CANDIDATE_AWAITING_FREQUENCY_AND_AUTHORITY** (`uml_am_candidate_gate_latest.json`; production frequency/amortization + authority remain closed; not promoted)
17. ~~U_AM isolated creation + shadow instrumentation~~ → **READY** (`uml_u_am_creation_audit_latest.json`; 116.2 ms median birth, 139,511,395-request binding break-even; aggregate production telemetry ready; dynamic path authoritative)
18. ~~U_AM shadow sandbox run~~ → **PASS_MEASURED_ZERO_U_AM_DEMAND** (`uml_u_am_shadow_sandbox_latest.json`; 12,380 real evaluator invocations: 0 macro-shape `(x+y)*z`, 527 A+M other-shape, U_MD 1,802, U_AS 460; sandbox counts do not touch promotion; demand evidence currently favors an MD-shaped macro, not AM)
19. ~~U_MD shape census (no compile)~~ → **PASS_MD_MOSTLY_CANONICALIZATION_DEFECT** (`uml_md_shape_census_latest.json`; dominant shapes `(V*K)/K` / `(K*V)/K`; ~99% seal-valid cancel; **compile_u_md_now=false**; absolute MD counts in first census were inflated by re-entrant `uml_cost→evaluate` — ratios held; fixed census uses `ast_symbolic_cost`)
20. ~~Guarded U canonicalization A/B~~ → **PASS_SUBTRACT_MD_DRAG** (`uml_md_guarded_canonicalization_ab_latest.json`; baseline dynamic MD vs seal-gated U cancel; **1,793/1,802** routes removed (99.5%), residual irreducible **9** (0.50%), seal failures **0**, mean symbolic cost **5.0→1.02**, identity hold **1.0**; `compile_u_md_now=false`; only residual eligible for later U_MD service-cost — **first apparent permanent expert was subtracted**)
21. ~~Enable guarded U cancel before federation~~ → **PASS_GUARDED_CANCEL_ENABLED** (`uml_guarded_cancel_enable_latest.json`; default ON, fail-closed, `UML_GUARDED_CANCEL=0` override; hooks: registry domain tag + shadow demand; live U_MD demand **1,802→9** residual irreducible only)
22. ~~Resume real mix training (`continue_train`)~~ → **PASS×2** (`uml_mix_layers/layer_continue_train_latest.json`; loop1 UML **0.647→0.870** / Codex **0.964→0.965**; loop2 UML **0.870→0.882** / Codex **0.965→0.966** hold; diminishing UML Δ; survivor committed; registry no longer emits `(V*K)/K` drag forms)
23. ~~A then C (speak cheap audit + bank no-MD-drag)~~ → **DONE** (`uml_operator_a_then_c_latest.json`; match 1.0; bank drag 0; continuity flat; B skipped)
24. ~~Speak cheap-pressure train (boost×3, +3k)~~ → **FAIL_HOLD_OR_MATCH** (`uml_speak_cheap_pressure_latest.json`; match held 1.0; cheap **0.143→0.143**; Codex Δ **-0.0014** vs tol 0.001; survivor **not** committed — mix prefer-cheap boost alone does not move speak cheap at n=7)
25. ~~OOD / never-seen probe~~ → **PASS_OOD_STRESS_GAP** (`uml_ood_probe_latest.json`; 128 surfaces absent from bank; seal roundtrip 1.0; speak match **1.0→1.0** on novel prompts; UML token acc **0.882→0.069** — destination seal generalizes, mix-bank token prediction does not)
26. ~~OOD train loop (A→train→A+B)~~ → **PASS_OOD_GENERALIZE** (`uml_ood_train_loop_latest.json`; baseline OOD UML **0.069** → after OOD@0.45 + Codex recover **0.745**; fresh B **0.739**; speak match **1.0**; Codex hold Δ **-0.0001**)
27. ~~Promote OOD-recovered survivor~~ → **PROMOTED** (`runs/uml_ood_train_loop/promote_receipt.json`; `layer_survivor.pt` ← recovered; backup `layer_survivor_pre_ood_promote.pt`)
28. ~~OOD expand 256 (new seeds)~~ → **PASS_OOD_MILD_LIFT** (`uml_ood_train_loop_latest.json`; A **0.750→0.790**, fresh B **0.794**, Codex hold; promoted to survivor)
29. ~~Blend ID+OOD recover~~ → **PASS_BLEND** (`uml_ood_blend_recover_latest.json`; ID UML **0.667→0.879**, fresh OOD C **0.759**, Codex **+0.0006**, speak match **1.0**; survivor committed)
30. ~~OOD expand 384 + Codex recover~~ → **PASS_OOD_EXPAND384** (`uml_ood_expand384_latest.json`; OOD A/B **~0.79/0.78**, speak match **1.0**, Codex hold; survivor committed; train loop now auto-recovers Codex)
31. ~~OOD expand 512~~ → **TIE_NO_OOD_LIFT** (procedural ceiling ~0.78; Codex held)
32. ~~Hard OOD train loop~~ → **PASS_OOD_GENERALIZE** (`uml_ood_train_loop_latest.json`; hard lexicon/long surfaces; A **0.725→0.845**, fresh B **0.845**, speak match **1.0**, Codex hold; survivor committed)
33. ~~Hard OOD expand 384~~ → **PASS_OOD_MILD_LIFT** (A **0.824→0.882**, B **0.867**, Codex hold; blend recover restored ID UML **0.881** before expand)
34. ~~Hard OOD expand 512~~ → **PASS_OOD_MILD_LIFT** (A **0.851→0.875**, B **0.867**, Codex **+0.0004**; speak match **1.0**; survivor committed)
35. ~~Hard OOD 640 + blend~~ → **STACKING** (OOD ~**0.88**, ID UML restored **0.886**, OOD holdout **0.835**, Codex hold; survivor live)
36. ~~Hard OOD scale 768–1024~~ → procedural hard OOD plateau ~**0.87–0.88** (matches ID); speak cheap still **0.143** at n=7
37. ~~Real held-out English loop~~ → **PASS_REAL_HELDOUT_GENERALIZE** (`uml_real_heldout_latest.json`; Codex phrases absent from mix bank; stacked to A/B **0.909/0.909** at n=384; Codex hold; survivor committed)
38. ~~Stack Cycle1 blend+heldout~~ → **PASS** blend ID UML **0.793→0.900** / OOD C **0.837** / Codex **0.9674**; heldout `--seed 999 --n 512 --steps 6000` A **0.845→0.934** B **0.933** hold=True committed=True
39. ~~Stack Cycle2 blend+heldout~~ → **PASS** blend ID UML **0.800→0.902** / OOD C **0.833** / Codex **0.9676**; heldout `--seed 2026 --n 512 --steps 6000` A **0.847→0.940** B **0.937** hold=True d_codex **-0.0001** committed=True (`PASS_REAL_HELDOUT_LIFT`)
40. ~~Institutionalize hard/real-heldout into mix rebuild~~ → **WIRED** (`merge_uml_mix_extra_surfaces.py` → `data/uml_mix_extra_surfaces/surfaces.json`; `build_uml_equation_mix_dataset._phrases` merges extras before Codex mining; rebuild still explicit/opt-in)
41. ~~Stack Cycle3 blend+heldout~~ → **PASS** blend ID UML **0.798→0.903** / OOD C **0.832** / Codex **0.9679**; heldout `--seed 31415 --n 512 --steps 6000` A **0.854→0.940** B **0.939** hold=True d_codex **-0.0003** committed=True (`PASS_REAL_HELDOUT_LIFT`)
42. ~~Stack Cycle4 blend+heldout~~ → **PASS** blend ID UML **0.808→0.905** / OOD C **0.830** / Codex **0.9682**; heldout `--seed 271828 --n 512 --steps 6000` A **0.852→0.939** B **0.939** hold=True d_codex **-0.0002** committed=True (`PASS_REAL_HELDOUT_LIFT`)
43. ~~Stack Cycle5 blend+heldout~~ → **PASS** blend ID UML **0.797→0.907** / OOD C **0.830** / Codex **0.9682**; heldout `--seed 161803 --n 512 --steps 6000` A **0.856→0.945** B **0.944** hold=True d_codex **-0.0004** committed=True (`PASS_REAL_HELDOUT_LIFT`)
44. ~~Stack Cycle6 blend+heldout~~ → **PASS** blend ID UML **0.803→0.909** / OOD C **0.830** / Codex **0.9682**; heldout `--seed 141421 --n 512 --steps 6000` A **0.853→0.941** B **0.944** hold=True d_codex **-0.0002** committed=True (`PASS_REAL_HELDOUT_LIFT`)
45. ~~Extras refresh + post-stack blend~~ → **PASS** `merge_uml_mix_extra_surfaces.py` catalog **2601** (prior 1536 + heldout A/B + hard 256; no bank rebuild); final blend ID UML **0.813→0.910** / OOD C **0.829** / Codex **0.9684** committed=True (`PASS_BLEND`)
46. ~~Stack Cycle7 blend+heldout~~ → **PASS** blend ID UML **0.910→0.912** / OOD C **0.838** / Codex **0.9687**; heldout `--seed 173205 --n 512 --steps 6000` A **0.841→0.950** B **0.949** hold=True d_codex **-0.0005** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`)
47. ~~Stack Cycle8 blend+heldout~~ → **PASS** blend ID UML **0.813→0.913** / OOD C **0.833** / Codex **0.9686**; heldout `--seed 223606 --n 512 --steps 6000` A **0.855→0.951** B **0.949** hold=True d_codex **-0.0004** committed=True (`PASS_REAL_HELDOUT_LIFT`); final clean blend ID UML **0.817→0.914** / OOD C **0.833** / Codex **0.9688** committed=True (`PASS_BLEND`)
48. ~~Stack Cycle9 blend+heldout~~ → **PASS** blend ID UML **0.914→0.916** / OOD C **0.840** / Codex **0.9689**; heldout `--seed 264575 --n 512 --steps 6000` unused=4248 A **0.845→0.948** B **0.948** hold=True d_codex **-0.0004** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.808→0.916** / OOD C **0.836** / Codex **0.9688** committed=True (`PASS_BLEND`)
49. ~~Stack Cycle10 blend+heldout~~ → **PASS** heldout `--seed 331662 --n 512 --steps 6000` unused=4248 A **0.859→0.952** B **0.949** hold=True d_codex **-0.0004** committed=True (`PASS_REAL_HELDOUT_LIFT`); final clean blend ID UML **0.825→0.917** / OOD C **0.834** / Codex **0.9688** committed=True (`PASS_BLEND`)
50. ~~Stack Cycle11 blend+heldout~~ → **PASS** blend ID UML **0.917→0.918** / OOD C **0.841** / Codex **0.9690**; heldout `--seed 412137 --n 512 --steps 6000` unused=4248 A **0.844→0.954** B **0.949** hold=True d_codex **-0.0007** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.826→0.918** / OOD C **0.837** / Codex **0.9689** committed=True (`PASS_BLEND`)
51. ~~Stack Cycle12 blend+heldout~~ → **PASS** heldout `--seed 577215 --n 512 --steps 6000` unused=4248 A **0.856→0.953** B **0.954** hold=True d_codex **-0.0003** committed=True (`PASS_REAL_HELDOUT_LIFT`); final clean blend ID UML **0.828→0.919** / OOD C **0.836** / Codex **0.9689** committed=True (`PASS_BLEND`)
52. ~~Stack Cycle13 blend+heldout~~ → **PASS** blend ID UML **0.919→0.920** / OOD C **0.842** / Codex **0.9690**; heldout `--seed 661328 --n 512 --steps 6000` unused=4248 A **0.843→0.951** B **0.953** hold=True d_codex **-0.0005** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.831→0.921** / OOD C **0.839** / Codex **0.9691** committed=True (`PASS_BLEND`)
53. ~~Stack Cycle14 blend+heldout~~ → **PASS** heldout `--seed 707106 --n 512 --steps 6000` unused=4248 A **0.859→0.956** B **0.955** hold=True d_codex **-0.0004** committed=True (`PASS_REAL_HELDOUT_LIFT`); final clean blend ID UML **0.824→0.921** / OOD C **0.838** / Codex **0.9692** committed=True (`PASS_BLEND`)
54. ~~Stack Cycle15 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.921: pre-blend ID UML **0.921→0.922** / OOD C **0.843** / Codex **0.9693**; heldout `--seed 774597 --n 512 --steps 6000` unused=4248 A **0.845→0.951** B **0.954** hold=True d_codex **-0.0007** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.832→0.922** / OOD C **0.840** / Codex **0.9693** committed=True (`PASS_BLEND`)
55. ~~Stack Cycle16 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.921: heldout `--seed 831521 --n 512 --steps 6000` unused=4248 A **0.855→0.957** B **0.956** hold=True d_codex **-0.0005** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); final clean blend ID UML **0.822→0.923** / OOD C **0.839** / Codex **0.9693** committed=True (`PASS_BLEND`); frame: final blend **+0.002** over 0.921, B band **0.954–0.956** in-family, Codex **+0.0001** hold — not ceiling (still stepping), not interference (no Codex/B collapse)
56. ~~Stack Cycle17 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.923: pre-blend ID UML **0.923→0.924** / OOD C **0.843** / Codex **0.9695**; heldout `--seed 892347 --n 512 --steps 6000` unused=4248 A **0.843→0.955** B **0.955** hold=True d_codex **-0.0009** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.835→0.924** / OOD C **0.841** / Codex **0.9691** committed=True (`PASS_BLEND`)
57. ~~Stack Cycle18 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.923: heldout `--seed 953821 --n 512 --steps 6000` unused=4248 A **0.853→0.959** B **0.957** hold=True d_codex **-0.0004** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); final clean blend ID UML **0.839→0.924** / OOD C **0.840** / Codex **0.9692** committed=True (`PASS_BLEND`); frame: final blend **+0.001** over 0.923, B band **0.955–0.957** in-family, Codex **−0.0001** near-flat hold — not ceiling (still stepping), not interference (no Codex/B collapse)
58. ~~Stack Cycle19 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.924: pre-blend ID UML **0.924→0.925** / OOD C **0.844** / Codex **0.9694**; heldout `--seed 104729 --n 512 --steps 6000` unused=4248 A **0.845→0.957** B **0.956** hold=True d_codex **-0.0008** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.840→0.925** / OOD C **0.842** / Codex **0.9693** committed=True (`PASS_BLEND`)
59. ~~Stack Cycle20 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.924: heldout `--seed 112358 --n 512 --steps 6000` unused=4248 A **0.853→0.957** B **0.957** hold=True d_codex **-0.0007** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); final clean blend ID UML **0.830→0.925** / OOD C **0.841** / Codex **0.9693** committed=True (`PASS_BLEND`); frame: final blend **+0.001** over 0.924, B band **0.956–0.957** in-family, Codex **+0.0001** hold — not ceiling (still stepping; step size stuck at +0.001 third consecutive lift), not interference (no Codex/B collapse)
60. ~~Stack Cycle21 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.925: pre-blend ID UML **0.925→0.926** / OOD C **0.845** / Codex **0.9695**; heldout `--seed 123457 --n 512 --steps 6000` unused=4248 A **0.848→0.958** B **0.957** hold=True d_codex **-0.0005** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.843→0.926** / OOD C **0.843** / Codex **0.9695** committed=True (`PASS_BLEND`)
61. ~~Stack Cycle22 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.925: heldout `--seed 134626 --n 512 --steps 6000` unused=4248 A **0.853→0.958** B **0.960** hold=True d_codex **-0.0003** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); final clean blend ID UML **0.846→0.927** / OOD C **0.842** / Codex **0.9696** committed=True (`PASS_BLEND`); frame: final blend **+0.002** over 0.925, B band **0.957–0.960** in-family, Codex **+0.0003** hold — not ceiling (still stepping; step size **+0.002**, broke prior three-lift +0.001 streak), not interference (no Codex/B collapse)
62. ~~Stack Cycle23 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.927: pre-blend ID UML **0.927→0.927** / OOD C **0.846** / Codex **0.9698**; heldout `--seed 145897 --n 512 --steps 6000` unused=4248 A **0.850→0.958** B **0.959** hold=True d_codex **-0.0009** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.836→0.927** / OOD C **0.844** / Codex **0.9696** committed=True (`PASS_BLEND`)
63. ~~Stack Cycle24 blend+heldout~~ → **PASS** / **STAIRCASE** vs 0.927: heldout `--seed 157163 --n 512 --steps 6000` unused=4248 A **0.853→0.959** B **0.959** hold=True d_codex **-0.0007** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); final clean blend ID UML **0.833→0.928** / OOD C **0.842** / Codex **0.9697** committed=True (`PASS_BLEND`); frame: final blend **+0.001** over 0.927, B band **0.959–0.959** in-family, Codex **+0.0001** hold — not ceiling (still stepping; step size **+0.001**, returned to +0.001 after prior +0.002), not interference (no Codex/B collapse)
64. ~~Stack Cycle25 blend+heldout~~ → **PASS** / **CEILING** vs 0.928: pre-blend ID UML **0.928→0.928** / OOD C **0.846** / Codex **0.9698**; heldout `--seed 168429 --n 512 --steps 6000` unused=4248 A **0.845→0.958** B **0.960** hold=True d_codex **-0.0004** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.840→0.928** / OOD C **0.844** / Codex **0.9698** committed=True (`PASS_BLEND`)
65. ~~Stack Cycle26 blend+heldout~~ → **PASS** / **CEILING** vs 0.928: heldout `--seed 179695 --n 512 --steps 6000` unused=4248 A **0.853→0.956** B **0.959** hold=True d_codex **-0.0005** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); final clean blend ID UML **0.854→0.928** / OOD C **0.844** / Codex **0.9698** committed=True (`PASS_BLEND`); frame: final blend **+0.000** over 0.928, B band **0.959–0.960** in-family, Codex **+0.0001** hold — first CEILING read (flat print at 0.928), not interference (no Codex/B collapse); confirmation deferred to Cycles 27–28
66. ~~Stack Cycle27 blend+heldout~~ → **PASS** / **STAIRCASE_RESUME** vs 0.928: pre-blend ID UML **0.928→0.929** / OOD C **0.847** / Codex **0.9699**; heldout `--seed 190961 --n 512 --steps 6000` unused=4248 A **0.844→0.959** B **0.961** hold=True d_codex **-0.0005** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); post-heldout blend ID UML **0.841→0.929** / OOD C **0.845** / Codex **0.9699** committed=True (`PASS_BLEND`); raw mid-stack ID UML **0.9290754025274407** (print **0.929**) — rises above prior **0.928** with B/Codex stable → not CEILING_CONFIRMED, not INTERFERENCE
67. ~~Stack Cycle28 blend+heldout~~ → **PASS** / **STAIRCASE_RESUME** vs 0.928: heldout `--seed 202227 --n 512 --steps 6000` unused=4248 A **0.858→0.963** B **0.960** hold=True d_codex **-0.0005** committed=True (`PASS_REAL_HELDOUT_GENERALIZE`); final clean blend ID UML **0.849→0.929** / OOD C **0.845** / Codex **0.9699** committed=True (`PASS_BLEND`); receipt raw ID UML **0.9293256333626544** (`uml_ood_blend_recover_latest.json`, `finished_at` **2026-08-07T06:25:54Z**) — frame: final blend **+0.001** over 0.928, B band **0.960–0.961** in-family, Codex **+0.0001** hold — **STAIRCASE_RESUME** (confirmation stack rejected flat ceiling; micro-step resumed), not CEILING_CONFIRMED, not INTERFERENCE (no Codex/B collapse). Soft 0.99 / metacognition doctrine not scored here.
68. ~~Cycle28 raw classification vs Cycle27~~ → **STAIRCASE_RESUME** (not INTERFERENCE; micro-step / integration-drag character) — Cycle27 post-blend raw ID UML **0.9290754025274407**. Cycle28 heldout raw: `start_id` **0.9290754025274407**, A **0.8581997132055794→0.9627167253291617**, fresh B **0.9597685862481713**, Codex hold (`delta_codex` **−0.0004523111464724838**), `finished_at` **2026-08-07T06:24:14Z**. Cycle28 final blend (`blend_recover_20260807T062554Z.json`, `finished_at` **2026-08-07T06:25:54Z**): ID UML raw **0.8489714857046075→0.9293256333626544**, OOD C **0.8447356441438512**, Codex **0.9694917039959601→0.9699294830574053**, `survivor_committed=true`, `PASS_BLEND`. Vs Cycle27: after_id **+0.0002502308352137** (clearly above at ≥6 decimals; print still **0.929**). B/Codex ok → gate open for preserve-heldout A/B (item 69).
69. ~~BLEND_PRESERVE_HELDOUT A/B (post-C28)~~ → **PARTIAL** vs integration hypothesis — started from already-blended C28 survivor (no fresh heldout stress): `run_uml_ood_blend_recover.py --heldout-tensor data/uml_real_heldout_v1/tensor_A_after --no-ood-concat` (`heldout_rows=1796`, `ood_rows=0`, mix **0.55**, boost **1.5**, steps **3000**, seed **120**). Receipt `finished_at` **2026-08-07T06:29:28Z**: ID UML raw **0.9293256333626544→0.9299484786730117** (`delta_id_uml` **+0.0006228453103572784**; print **0.929→0.930**), Codex **0.9699294830574053→0.9699567307168314** (`delta_codex` **+2.724765942607732e-05**, hold), OOD C **0.777589907003967** (vs C28 clean-blend OOD C **0.8447356441438512**), speak match **1.0**, `survivor_committed=true`, `PASS_BLEND`. Read: retained ID gain **larger than C28 tiny-step** (+0.000623 vs +0.000250) and hits print **≥0.930**; Codex hold; **OOD not stable** under no-ood-concat — integration hypothesis **not fully confirmed** (ID pressure works; OOD cost unpaid). B-family not re-probed this leg.
70. ~~OOD restore after item-69 collapse~~ → **PASS_BLEND** / OOD recovered — default `run_uml_ood_blend_recover.py` (full OOD concat, `ood_fraction=1.0`, `heldout_rows=0`, `ood_rows=4195`, mix **0.55**, boost **1.5**, steps **3000**, seed **120**) from item-69 committed survivor. Receipt `blend_recover_20260807T063159Z.json`, `finished_at` **2026-08-07T06:31:59Z**: ID UML raw **0.9299484786730117→0.9302746529276461** (`delta_id_uml` **+0.00032617425463443706**; print **0.930→0.930**), Codex **0.9699567307168314→0.9700112260356836** (`delta_codex` **+5.449531885215464e-05**, hold), OOD C **0.8469792547310919** (vs item-69 **0.777589907003967** / C28 clean **0.8447356441438512**), speak match **1.0**, `survivor_committed=true`. Read: OOD restored to prior ~0.84 band; ID did **not** drop back to C28 **~0.9293** — held and slightly rose (print stayed **0.930**). Restore cost was **not** ID regression; unpaid OOD was the item-69 failure mode.
71. ~~BLEND_PRESERVE_HELDOUT + OOD fraction 0.25 A/B~~ → **PASS** vs integration hypothesis — from restore survivor (item 70): `run_uml_ood_blend_recover.py --heldout-tensor data/uml_real_heldout_v1/tensor_A_after --ood-fraction 0.25` (no `--no-ood-concat`; `heldout_rows=1796`, `ood_rows=1049`, mix **0.55**, boost **1.5**, steps **3000**, seed **120**). Receipt `blend_recover_20260807T063336Z.json`, `finished_at` **2026-08-07T06:33:36Z**: ID UML raw **0.9302746529276461→0.9307603629986178** (`delta_id_uml` **+0.00048571007097164554**; print **0.930→0.931**), Codex **0.9700112260356836→0.9700257581207108** (`delta_codex` **+1.4532085027219033e-05**, hold), OOD C **0.822315796319178** (≥ ~0.82 gate; below C28/restore ~0.84–0.85 but **not** collapse), speak match **1.0**, `survivor_committed=true`, `PASS_BLEND`. Vs item 69 (`--no-ood-concat` OOD **0.777**): partial OOD in blend keeps ID lift (print **≥0.931**) **without** OOD collapse. Integration hypothesis **supported** at this knob: heldout replay + 25% OOD retains larger ID gains than C28 tiny-step while paying enough OOD mass to stay in-band. Survivor left healthy enough (OOD C **0.822**, mild gap vs ~0.84 restore). **Operator four-way score (locked):** **(1) genuine integration improvement with mild OOD tax** — ID cleared **>0.930275** (raw **0.930760**, print **0.931**), Codex hold, OOD stayed in-band (**0.822** vs restore ~**0.847**; tax **−0.025**, not material collapse like item-69 **0.778**). Not (2) efficiency (ID not flat). Not (3) tradeoff frontier (OOD did not fall materially). Not (4) OOD-pressure compromise (ID did not regress to **0.929x**).
72. ~~Default blend restore after item-71 0.25~~ → **PASS_BLEND** / **0.931 basin held** — default `run_uml_ood_blend_recover.py` (full OOD concat, `ood_fraction=1.0`, `heldout_rows=0`, `ood_rows=4195`, mix **0.55**, boost **1.5**, steps **3000**, seed **120**) from item-71 committed survivor. Receipt `blend_recover_20260807T063556Z.json`, `finished_at` **2026-08-07T06:35:56Z**: ID UML raw **0.9307603629986178→0.9309253623703089** (`delta_id_uml` **+0.00016499937169112133**; print **0.931→0.931**), Codex **0.9700257581207108→0.9701765285028683** (`delta_codex` **+0.0001507703821574946**, hold), OOD C **0.8489627365545945** (back to ~0.84–0.85 restore band from item-71 **0.822315796319178** / item-70 **0.8469792547310919**), speak match **1.0**, `survivor_committed=true`. Read: mild OOD tax from (1) is **recoverable** without leaving the print-**0.931** / raw-**≥0.9307** basin; ID slightly rose. Confirms item-71 four-way **(1) mild OOD tax**, not (3). Survivor healthy.
73. ~~Default blend recover recipe → heldout + ood-fraction=0.25~~ → **WIRED** — based on items 69–72 (preserve → 0.25 → restore held 0.931 basin: ID **0.930760→0.930925**, OOD C **0.849**, Codex hold). `run_uml_ood_blend_recover.py` defaults now: `--ood-fraction 0.25`; auto-include `data/uml_real_heldout_v1/tensor_A_after` when present (`auto_heldout=yes`). Escape hatches for old full-OOD simultaneous blend: `--ood-fraction 1.0 --no-heldout-tensor`; extreme heldout-only: `--no-ood-concat` (ood_fraction effectively 0). Receipt `blend_config` records `auto_heldout`, `heldout_rows`, `ood_rows`, `ood_fraction`. Staging pressures remain the integration geometry evidence; four-way class stays **(1) mild OOD tax**. No more old-recipe heldout stacks as default.
74. ~~New-default blend recover validation (heldout stress → default blend)~~ → **PARTIAL** — end-to-end under stress with **no** old full-OOD escapes (`--ood-fraction 1.0` / `--no-heldout-tensor` unused). Heldout `--seed 213493 --n 512 --steps 6000` (`real_heldout_latest.json`, `finished_at` **2026-08-07T06:41:14Z**): start ID UML **0.9309253623703089** / Codex **0.9701765285028683**; A **0.8576810652809354→0.9575836310490419**; fresh B **0.9563427509046845**; Codex Δ **−0.0003705681681943629** (`codex_hold=true`); after_id UML **0.8780419710322295** / Codex **0.9698059603346739**; `PASS_REAL_HELDOUT_LIFT`, `survivor_committed=true`. Default blend (bare `run_uml_ood_blend_recover.py`): `BLEND_CONFIG heldout_rows=1821 ood_rows=1049 ood_fraction=0.25 auto_heldout=yes` heldout_tensor=`…/tensor_A_after` (`blend_recover_20260807T064241Z.json` / `blend_recover_latest.json`, `finished_at` **2026-08-07T06:42:41Z**): ID UML **0.8780419710322295→0.9305347181624971** (print **0.878→0.931**); OOD C **0.8182675424335046**; Codex **0.9698059603346739→0.9699240335255201** (`delta_codex` **+0.00011807319084622403**, hold); speak match **1.0**; `PASS_BLEND`, `survivor_committed=true`. Score vs new-default stress gates: Codex hold **PASS**; ID recover ≥~0.9305 / print ≥0.931 **PASS** (raw **0.930535**, not 0.928–0.929 basin; slightly below pre-stress **0.930925**); OOD C ≥~0.82 (prefer ~0.84+) **WEAK** (**0.818268**, under soft floor and below item-71 **0.822** / restore ~**0.849**). Classification **PARTIAL** (ID+Codex ok; OOD under-recovers). Not FAIL/INTERFERENCE (Codex intact; both surfaces did not degrade). Survivor health: committed, Codex ~**0.9699**, ID print **0.931**, OOD mild-gap **0.818**.
75. ~~Staged full-OOD restore after item-74 PARTIAL~~ → **PASS** — from item-74 committed survivor (ID **0.930535** / OOD C **0.818268** / Codex hold), explicit `run_uml_ood_blend_recover.py --ood-fraction 1.0` with auto-heldout kept (no `--no-heldout-tensor`): `BLEND_CONFIG heldout_rows=1821 ood_rows=4195 ood_fraction=1.0 auto_heldout=yes` heldout_tensor=`…/tensor_A_after` (`blend_recover_20260807T064448Z.json` / `blend_recover_latest.json`, `finished_at` **2026-08-07T06:44:48Z**). Raw: ID UML **0.9305347181624971→0.9313067185340188** (`delta_id_uml` **+0.0007720003715216972**; print **0.931→0.931**); OOD C **0.8407686804968459**; Codex **0.9699240335255201→0.9697896117390182** (`delta_codex` **−0.00013442178650191483**, hold); speak match **1.0**; `PASS_BLEND`, `survivor_committed=true`. Gates: OOD ≥~0.84 **PASS** (**0.840769**; near pre-stress ~**0.849**); ID ≥~0.9305 / print **0.931** **PASS** (rose above item-74 and above pre-stress **0.930925**); Codex hold **PASS**. Classification **PASS** (not PARTIAL — ID did not slip to 0.929x; not FAIL). Survivor health: committed, ID print **0.931** / raw **0.931307**, OOD C **0.841**, Codex ~**0.9698**. **Default-policy recommendation (smallest change):** keep default `ood_fraction=0.25` + auto-heldout; document two-phase schedule after heldout stress — (1) bare default blend (heldout+0.25) for ID integrate, (2) staged `--ood-fraction 1.0` restore (auto-heldout on) when OOD C <~0.82. Do **not** bump default to 0.35 (item-74 under-recover is the known mild tax; phase-2 clears it without ID cost). Do **not** auto-call staged restore from the heldout loop yet (operator-gated phase-2 is enough; avoid coupling until chronic OOD <0.82 after phase-2 appears).
76. ~~Matched-fork A/B: staged 0.25→1.0 vs simultaneous 1.0 (items 69–75 decisive test)~~ → **INCONCLUSIVE (leaning B)** — one fresh heldout leg, then fork; both arms identical (seed **120**, mix **0.55**, boost **1.5**, 3000 steps/leg, auto-heldout **ON** in both — only variable is OOD scheduling). Heldout leg `--seed 224759 --n 512 --steps 6000` (`real_heldout_latest.json`, `finished_at` **2026-08-07T07:56:17Z**): start ID **0.9313067185340188** / Codex **0.9697896117390182**; A **0.9081476164061735→0.9606160472476915**; fresh B **0.9612439548629769**; Codex Δ **−8.174297827812094e-05** (hold); post-heldout stressed ID **0.8637356513377515**; `PASS_REAL_HELDOUT_LIFT`, committed. Fork `layer_survivor_fork_224759.pt` (sha256 `9208…82D8`, hash-verified restore before Arm B). **Arm A** (control: simultaneous `--ood-fraction 1.0`, `heldout_rows=1792 ood_rows=4195`, 3000 steps; `blend_recover_20260807T075908Z.json`): ID **0.8637356513377515→0.9307122837115024** (print **0.864→0.931**); Codex **→0.9700130425463119** (**+0.00030517378557182173**, hold); OOD C **0.8406548741627106**; match **1.0** cheap **0.3**; `PASS_BLEND`; saved `layer_survivor_armA_224759.pt`. **Arm B** (staged): phase-1 bare default (`ood_fraction=0.25`, `ood_rows=1049`, 3000 steps; `blend_recover_20260807T080110Z.json`): ID **0.8637356513377515→0.930969070813141**; Codex **→0.9700820699501913** (hold); OOD C **0.8139591597840932** — **<0.82, stage 2 triggered** per item-75 policy. Phase-2 staged restore (`--ood-fraction 1.0`, auto-heldout on, 3000 steps; `blend_recover_20260807T080256Z.json`): ID **0.930969070813141→0.9311646660948145**; Codex **→0.9702037761622944** (hold); OOD C **0.8413702282629901**; match **1.0** cheap **0.4**; `PASS_BLEND`; saved `layer_survivor_armB_224759.pt`. **Matched compare (final vs final):** ΔID (B−A) **+0.0004523823833121**; ΔOOD C **+0.0007153541002795**; ΔCodex **+0.0001907336159825**; speak match **1.0** both. Every raw float favors B, but ΔID is inside the ~±0.0005 noise band → **INCONCLUSIVE**, not B_WINS. **Caveats (binding):** (a) step asymmetry — Arm B spent **6000** steps vs Arm A **3000**; steps-matched read (B phase-1 alone vs A): ID **0.930969 vs 0.930712** (+0.000257, noise) but OOD **0.814 vs 0.841** — at equal budget the simultaneous arm ends OOD in-family and staged does not; staging's clean endpoint costs 2×. (b) n=1 fork, single seed — no variance estimate. (c) identical seed 120 both arms removes sampling noise between arms but doesn't sample it. Read: staging is **not** demonstrably better than simultaneous at this scale; simultaneous full-OOD (heldout included) reaches the same basin (ID print **0.931**, OOD ~**0.84**, Codex hold) in half the steps. Item-75 two-phase policy stays valid as a *repair* path (phase-2 did clear the 0.814 under-recover without ID cost) but is not evidence of a scheduling advantage. Survivor left at **Arm B** (`layer_survivor.pt` = `layer_survivor_armB_224759.pt`, ID raw **0.9311646660948145**, OOD C **0.841**, Codex **0.9702**) — nominally best floats, delta within noise.
77. ~~Measurement-only matched speak-cheap census on the current live survivor~~ → **SEAL_GUARD_STOP** — survivor item-76 health reference ID UML **0.9311646660948145** / OOD C **0.8413702282629901** / Codex **0.9702037761622944**; checkpoint `runs/uml_mix_layers/layer_survivor.pt` SHA-256 **`ffb4a8f6682f91cf04e318254a88390ce8ca1cd839c5cc782a2db797f36ff6b3`** before=after (size **3,372,432 B**, mtime_ns **1786089759700114500**). Fixed manifest **n=256**, seed **20260807**, four existing speak/mix/heldout prompt forms ×64, exact order at `runs/uml_speak_cheap_census/census_20260807T082414Z/prompt_manifest.json` (manifest SHA-256 **`23c8daac0177633308b7f706ae60cf9d20891b4d094de6726f5d6ea33fa6eb67`**, prompt-surface SHA-256 **`c6e1ece6df134e65c5eb0ad96d7053f419a110aff1f0cdf52c09f660b34903c0`**); receipt `runs/uml_speak_cheap_census/census_20260807T082414Z/census.json`. Same survivor/prompts/order/decode settings and per-row seeds in all modes: **raw_no_snap** destination **113/256=0.44140625**, cheap **79/256=0.30859375**, mean route cost **1.5486725663716814** AST nodes over valid n=113, mean route error **0.62109375**; **plant_rid_policy** destination **136/256=0.53125**, cheap **99/256=0.38671875**, mean cost **1.375** over valid n=136, mean error **0.5260416666666666**; **prefer_efficient_snap** destination **256/256=1.0**, cheap **256/256=1.0**, mean cost **1.0** over n=256, mean error **0.0**. Route headline (INVALID/LIT/A/M): raw **143/79/16/18**; plant **120/99/6/31**; snap **0/256/0/0**; unsupported rows **0** all modes. Plant/RID was genuinely distinct and executable on all 256 rows — current `build_uml_speak_pressure → decide_route_thermal → make_generate_logits_bias_fn`, `thermal_efficient_valid`, soft scale **6.0**, `hard_mask=false`, **no post-snap**, output changed on **64** matched rows; versus raw it raised destination **+0.08984375** (prompt-bootstrap 95% CI **[0.0546875, 0.12890625]**) and cheap **+0.078125** (**[0.046875, 0.11328125]**), lowered matched valid cost **−0.12612612612612611** (**[−0.1981981981981982, −0.06306306306306306]**, n=111) and error **−0.09505208333333334** (**[−0.13151041666666666, −0.061848958333333336]**), but still broke the destination seal on **120** rows, so those efficiency deltas cannot promote `PLANT_LEVER`; the plant source was `master_rid` on all rows but its on-disk timestamp was **2026-08-03T23:01:25.804360Z** and this census did not refresh it. Raw cheap exceeds the old **1/7≈0.143** point estimate, but raw destination fails on **143** rows, so not `RAW_CLIMBING`. Old n=7 **0.143** and item-76 n=10 **0.3/0.4** are not directly comparable to each other or these isolated modes: prompts, n, survivor snapshots, and snap-eligible counts differ, and both historical evaluators mixed hard-mask scale-6 thermal generation pressure with conditional post-snap. **NO TRAINING / checkpoint hash unchanged**; `model.eval()` + inference mode, no optimizer/backward/trainer/checkpoint write. **Next experiment: none (STOP); do not optimize raw or plant cheapness while their destination seals are broken.**
23. ~~Speak cheap A/B (A) + bank rebuild no MD-drag (C)~~ → **A PASS_MATCH_HELD_CHEAP_ROOM** (`uml_speak_cheap_ab_a_latest.json`; survivor match=1.0 cheap=0.143 vs plant_sn cheap=0.286); **C PASS_BANK_CLEAN_CONTINUITY** (registry drag 162→0; bank txt drag=0; survivor re-eval UML/Codex unchanged); **B skipped** (no continuity drop → no +10k)

**P3 binding read:** The four generators are live — independently trained, Codex-admitted, promoted checkpoints under `checkpoints/{addition,subtraction,multiplication,division}/specialist.pt`. Multiplication’s mix-0.5 retry proves domain-specific capacity (not cosmetic copies under one universal setting). Federations (pairs/triples/ASMD) may now be built from **real specialists**, not hypothetical labels in a single model. Temporary federations first; promote composites only after frequency + cost + Codex + authority (lattice policy unchanged).

### Foundational vs conditional knowledge (binding)

```
FOUNDATION (true no matter what)
  U  — UML structure: Nested-PEMDAS, codec, seal, malformed reject, route compare
  A  — addition axioms
  S  — subtraction axioms
  M  — multiplication axioms
  D  — division axioms
        ↓
CONDITIONAL (true under sealed circumstance)
  bindings (?A=1), task surface, time/context facts
        ↓
FEDERATION + ROUTE CHOICE
  which foundations cooperate; probability among structurally valid; cost prefers
        ↓
DECODED RESPONSE
```

**U role (binding):** not an ordinary fifth peer. U is the **mandatory substrate / skeleton** — grammar and integrity authority. Arithmetic federations remain the **15** Conway configs, each bound as `U+A`, `U+AM`, `U+ASMD`, … Never treat Structure as optional in a federation (rejects the peer-5 counting of 31/325).

**Control order (binding):**
1. **Structure (U)** — well-formed, sealed, reversible UML object?  
2. **A/S/M/D** — applicable domain transforms  
3. **Probability** — among structurally valid routes only  
4. **Cost** — preferred valid route  

Local arithmetic correctness without U can still yield a **structurally wrong** combined route. Conditional layers may supply bindings and context; they may **not** rewrite foundation axioms or admit invalid equations because text frequency said so.

Example hierarchy: `A+A → 2A` (foundation structure); `A=1` (conditional); therefore `2` under that seal — condition changes the concrete result, not the underlying truth.

---

## Control law (binding)

For any given target, Viv is presented with a **prepared set of routes that all evaluate to the same correct token**. Probability operates **only** over those valid routes, selecting the one most appropriate and computationally efficient for the problem. The route may use addition, subtraction, multiplication, division, or a combination of them, but the **decoded answer remains unchanged**.

### Three decisions (ordered)

0. **Is the equation structurally valid and sealed?**  
   **U** (UML-structure foundation) — Nested-PEMDAS well-formedness, codec reversibility, destination seal, malformed rejection. Without U, A/S/M/D can be locally correct and jointly invalid.

1. **What is the correct answer?**  
   Determined **before** route selection and sealed to a token identity. Not up for vote.

2. **Which domains apply?**  
   Route weights favor addition, subtraction, division, multiplication, or whichever combination fits the problem.  
   - **Monolithic:** one operational domain can complete the route by itself.  
   - **Experts:** multiple domains cooperate because the cheapest valid route crosses their boundaries.  
   Experts do **not** independently guess pieces of the answer. They contribute operations to **one route** whose destination was already fixed. Every arithmetic federation is `U+…` (substrate bound).

3. **Which valid route is cheapest / most thermally appropriate?**  
   Probability chooses among structurally valid routes; Nested-PEMDAS cost **and** foundation thermal RID rank preference. Thermal ranking never changes the sealed destination.

### Fault taxonomy

| Outcome | Classification | Action |
|---------|----------------|--------|
| Valid route, wrong efficiency | **Routing fault** | Prefer-cheap pressure, RID→PID residual, governor bias |
| Route evaluates to another token | **Invalid** | Hard reject / mask; never admit as truth |
| Probability picks a less efficient valid route | Allowed but suboptimal | Train and govern toward cheaper members of the same equivalence class |

Provided the route bank and hard validation are working, probability **cannot redefine the answer**.

---

## Compositional expert lattice (Conway generators)

This is **not** a conventional MoE where one router picks one prebuilt expert and that expert guesses the answer. It is a **compositional expert lattice**: four base experts are the **generators** of the expert space (think Conway’s Game of Life — simple cells, emergent patterns).

### Reversible encoding first

```text
Text
→ reversible UML equation   (deterministic machine form; decode = same bytes)
→ identify required domains
→ construct candidate expert federations
→ generate valid routes within each federation
→ evaluate every route to the same sealed token identity
→ compare uml_cost
→ probabilistically select among valid routes
→ decode chosen result back to text
```

The equation is not an approximate interpretation of the prompt. It is the **deterministic machine representation** that must round-trip byte-for-byte.

### Four base experts (monolithic primitives)

| ID | Domain | Owns |
|----|--------|------|
| **A** | Addition | axioms, identities, valid transforms, cost of `+` |
| **S** | Subtraction | same for `-` |
| **M** | Multiplication | same for `*` / related products |
| **D** | Division | same for `/` / related quotients |

Each base expert answers, for a UML structure:

1. Does my domain apply?  
2. Which portion belongs to me?  
3. Can I solve it alone?  
4. What would my route cost?  
5. Would cooperation with another domain reduce that cost?

### Two combinatorial layers

**Layer 1 — Expert composition (who participates, order ignored):**

| Size | Count | Examples |
|------|------:|----------|
| Singles (monolithic) | 4 | A, S, M, D |
| Pairs | 6 = C(4,2) | AS, AM, AD, SM, SD, MD |
| Triples | 4 = C(4,3) | ASM, ASD, AMD, SMD |
| All four | 1 = C(4,4) | ASMD |
| **Total nonempty** | **15** | of which **11** are mixed-domain |

**Layer 2 — Route sequence (execution order matters):**

`P(4,1)+P(4,2)+P(4,3)+P(4,4) = 4+12+24+24 = **64**` ordered routes without repeats.  
`Addition→Multiplication` and `Multiplication→Addition` may share domains but are **different computational routes**.

If domains may **repeat** (`A→M→A→D`), the space is unbounded with route length. That is where **uml_cost, pruning, RID health, and PID residual** are mandatory: they keep infinite possible routes from becoming uncontrolled computation.

### Federation policy (Conway, not warehouse)

- Default: **temporary federations** assembled by the router from the four generators.  
- Nested-PEMDAS already carries structure — do **not** require 11 permanently trained composite checkpoints up front.  
- Promote a federation to a **persistent composite expert** only when the same combination is frequent, cheaper, holds Codex, and passes an authority gate (distill / breed).  
- **Breakthrough criterion (binding):** not another accuracy headline. A mixed route must win honestly:  
  `persistent_composite_cost < dynamic_foundational_federation_cost` **and** `< mono/LIT cost`, while Codex holds and authority permits.  
  Until one branch wins that comparison, the temporary lattice stays what it should be — demonstrated capability without unnecessary permanent weight. That restraint is architecture, not hesitation.  
- **Separated questions:** (1) *Can the federation learn?* — **Yes** (temporary lattice 15/15, Codex hold). (2) *Should any composite become permanent?* — **Not yet** (`0/11` real cost-winners). The zero is not an embarrassing score; it is the truthful result of a gate that cannot be gamed by accuracy, frequency, or temporary PASS.  
- **Governance:** Saint-Exupéry as promotion law — a composite earns existence only when removing it would make the system less efficient. Full lattice proves capability; zero promotions prove restraint. Both are successes; they prove different things.

Machine-readable labels: `uml_domain_expert_lattice.json`.

### Distinct from identity-parent MoE

The existing Viv identity MoE bank (parent checkpoints as dialogue experts) is a **different surface**. This lattice is the **UML arithmetic domain** stack. Do not conflate “parent-as-expert” dialogue MoE with A/S/M/D domain generators until an explicit bridge is designed and gated.

---

## One-sentence training objective

Train Viv to **select among prepared valid UML routes** toward a **fixed token destination**, preferring the **cheapest / best-weighted** member, while **holding Codex identity (~96%)** — and treat invalid or high-cost emits as residual into **RID→PID**, not as creative license.

---

## Claims

1. **Viv is a computer, not a language-brain.**  
   Words are a surface **outside** the codec. Working medium inside: UML encode → Nested-PEMDAS compute → decode. Train **math → tokens**. **UML is the tokenizer** (controls token identity). **RID controls stability** of system/training — it is not a tokenizer.
2. **Many equations, one token value.**  
   Equivalence classes are real. Canonical form is the lowest-cost Nested-PEMDAS that evaluates to the sealed target.

3. **Probability is route selection, never truth selection.**  
   Softmax may choose which valid surface to utter. The destination token is sealed upstream.

3b. **Math does not lie.**  
   Wrong outputs are invalid equations or routing faults. Evaluation does not renegotiate the sealed identity.

3c. **Structure ≠ invented binding.**  
   Unbound `A+A` yields structure `2A`. Numeric `2` requires sealed `A=1`. Grounded `1+1=2` needs no guess. Probability cannot invent what `A` means.

4. **Domain structure = compositional lattice, not model size.**  
   Four generators (A/S/M/D). Monolithic = one domain completes the route. Mixed = temporary federation (or later distilled composite). Experts contribute operations to one sealed-destination route — they do not independently guess the answer.

5. **Codex identity is the hold bar.**  
   Acc ~96% on Codex validation is the primary pass condition for mix training. UML gains that break Codex are rejected. Acc99 is parked.

6. **RID is outer stability, unique address space, and residual channel — not the tokenizer.**  
   `RID(a,b,c)=a*b*c` on `[0,1]`. Leaves are unique normalized probability identities (decimal depth `d=ceil(log10(N+1))`). Invalid / high-cost / unbounded federation routes raise residual into PID. RID gates training/runtime health; **UML** seals and names the tokens. Cost+RID+PID prune the Conway explosion when domains may repeat.

7. **Prefer-cheap is training + speak pressure.**  
   Prepared banks, loss boost (`prefer_cheap_boost`), and speak-path governors bias toward low-cost valid members — without replacing Codex batches.

---

## Null hypothesis (refuse without evidence)

- Mixing UML dialogues will *necessarily* hurt Codex.  
- Longer mix alone guarantees cheapest-route speak (vs any correct equation).  
- RID can replace PID or act as a direct weight update.  
- Billions of parameters imply billions of independent floating-point probability *objects* rather than deeper precision in one `[0,1]` identity field.  
- Two parameters may share the same RID-normalized probability identity at the active precision depth.  
- Probability may be allowed to redefine the destination token.  
- Training the UML plant primarily on English prose next-token prediction.  
- “Math gave the wrong answer” when the equation/route was invalid.  
- Collapsing unbound `A+A` to `2` without a sealed binding for `A`.  
- Using RID as a tokenizer / truth selector for token identity.  
- Using UML residual alone as the plant stability governor (RID’s job).  
- Conventional single-pick MoE is sufficient for UML (router picks one expert that invents the answer).  
- All 11 mixed configurations must be permanently trained before any federation works.  
- Unbounded repeating-domain routes may run without cost/RID/PID pruning.

---

## Operational hypotheses (current campaign)

| ID | Hypothesis | Gate |
|----|------------|------|
| **H1** | Response-masked UML mix (~0.12–0.15) holds Codex ~96% while improving UML response NLL/acc. | Codex hold + UML improve |
| **H2** | Longer matched steps on v5 bank improve UML further without Codex regression (B3). | Same |
| **H3** | Prefer-cheap loss boost (G) improves UML vs no-boost; recipe locks boost×2 (H); sweep confirms 2.0 (I). | Receipts |
| **H3d** | RID sample-weighting improves UML vs boost-only (J). | J: **INCONCLUSIVE** — default weight 0.0 |
| **H4** | Speak-path: match sealed token; raise cheap-route rate among valids (F). | Speak A/B |

---

## Evidence snapshot (2026-08-06)

Matched from warm step **4450**, bank **v5_quality**.

| Leg | Codex acc | UML acc | UML nll | Notes |
|-----|-----------|---------|---------|-------|
| Codex-only baseline | 0.9638 | 0.2345 | 12.23 | Hold reference |
| B3 pilot (no boost) | 0.9643 | 0.6560 | 0.971 | H1+H2 PASS |
| G pilot (boost×2) | 0.9642 | 0.6569 | 0.967 | H3 PASS (small) |
| I sweep best | — | 0.571 / 1.570 @ +1500 | boost **2.0** wins vs 1.0/1.5/3.0 |

**Speak A/B (F):** all compared pilots **match_rate=1.0** (destination held) but **cheap_rate=0.0** (routing fault: valid costly eqs like `35+6` vs canonical `41`). Best mean route error: I-best (0.405) over B3/G (~0.452) over J (0.476).

Recipe: `uml_mix_recipe.json` — mix **0.15**, prefer-cheap boost **2.0**, RID train weight **0.0** until longer J evidence.

---

## Training / promotion gates

1. **Primary:** Codex v61 validation, response-masked.  
2. **Secondary:** UML mix validation after `Viv:`.  
3. **Speak secondary:** sealed-token match rate; then cheap-rate / mean route error among valids.  
4. **Promotion:** sandbox → speak default only after operator gate.  
5. **Inconclusive is valid.** A/B receipts required for behavior claims.

---

## Success / failure

**Success:** destination token sealed; reversible UML round-trip; federations stay inside valid prepared routes; cheap / domain-weighted route preferred; Codex hold; RID residual on routing faults and overgrown route graphs.

**Failure:** destination redefined by sampling; fluent wrong-value math; experts guessing answer fragments independently; permanent warehouse of composites without proof; unbounded federation compute without pruning.

---

## Stack binding

- Languages: **Python + Rust + UML**.  
- Runtime: `L:/Continue/.venv/Scripts/python.exe`.  
- Doctrine artifacts: `UML_TRAINING_THESIS.md`, `uml_domain_expert_lattice.json`, `rid_normalized_address_space.json`.  
- This thesis governs the **UML equation / domain-expert lattice** lane; foundation plant / RID math remain telemetry authority; identity-parent MoE remains a separate surface until bridged.
78. ~~Read-only identity→UML bridge shadow pilot~~ → **FIELD_SCOPED_WINS** — experiment `IDENTITY_UML_BRIDGE_SHADOW_V1`; registry sha `0cc5215c43a195b4…`; corpus n=72 (valid=48, adv=24); **FIELD_SCOPED** contract 72/72 hard_gate=PASS false_accepts=0 seal_fails=0; **SCAN_SURFACE** contract 63/72 hard_gate=FAIL false_accepts=0 seal_fails=0 (valid coverage only 40/48 — free-text scan misses sealed field cases without dialogue patterns); receipt `L:/Continue/Viv/foundation/artifacts/auto/identity_uml_bridge_shadow_v1/20260807T084911Z/identity_uml_bridge_shadow_v1_20260807T084911Z.json`; script `foundation/scripts/identity_uml_bridge_shadow_v1.py`; **NO MUTATION / NO PROMOTION**. Field-scoped bridge (explicit `uml_request` only) preserves seal/provenance/fail-closed and is the only candidate that clears hard gates; scan-surface is not an admissible authority boundary. Tag-architecture secondary remains deferred (`TIE_WITH_CONSTRAINTS`); scaffold-dependence / soft-0.99 stays blocked until a promoted bridge exists.
