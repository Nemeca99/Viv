# Viv-SLM identity/personality version history

Status: living engineering record
Updated: 2026-08-04
Scope: the custom character-level Viv-SLM identity/personality lane

## What this document is tracking

This is the version-to-version record for the custom `Viv-SLM` lane. It is not a record of the separate mouth-recovery campaigns that also used numbers such as V3–V9 in the same session journal. Those campaign numbers belong to a different experiment family.

The SLM lane is a custom character transformer with a 96-character vocabulary, a 128-character context window, response-only supervision in the later lanes, and no world knowledge in the model corpus. The CPU foundation remains the authority. The SLM is an isolated renderer candidate. No version in this record has been promoted to the live runtime.

Evidence sources, in priority order:

- `foundation/artifacts/auto/agentic/CURRENT_TASK.json`
- `foundation/artifacts/audit/session_journal.md`
- version input manifests, tensor manifests, run manifests, checkpoints, and probes
- source and regression-test hashes recorded in those artifacts

Where an early version has a model artifact but the current canonical journal does not preserve a detailed design note, this document says so instead of reconstructing intent from guesswork.

## Current state

| Lane | Evidence | Disposition |
|---|---|---|
| V28 canonical disambiguation | 9/10 primary behavior, 6/6 legacy behavior, 0 telemetry leaks; checkpoint SHA-256 `99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0` | Best offline candidate; not promoted |
| V29 greeting focus | Lower validation loss, but 6/10 primary behavior, 6/6 legacy behavior, 0 telemetry leaks; checkpoint SHA-256 `0EADB14AFEA7F3BF52A6EC77A6B4C1BADA95B48BA364804655872AD259F78310` | Rejected challenger; do not use |
| CPU identity router/mouth | Greeting route and fallback are CPU-authored and regression-tested; renderer cannot gain authority | Governed speech path; live mutation false |
| V30 frozen-head greeting canary | Completed 250-step parameter-scoped correction; 9/10 primary, 6/6 legacy, validation NLL `0.14111439127179698`; greeting remained unresolved | Rejected/inconclusive challenger; preservation held, promotion closed |
| V31 balanced one-pass corpus | Completed 250-step canary on the full balanced V24/V17 input lane; 8/10 primary, 6/6 legacy, validation NLL `0.1424706606753508` | Rejected/inconclusive negative Pareto challenger; V28 retained |
| V32 balanced lower-LR ablation | Completed 250-step canary on unchanged V31 inputs from V28; validation NLL `0.13565050303587134`, 8/10 primary, 6/6 legacy, 0 telemetry leaks | Accepted Pareto metric-progress point and renderer parent under CPU gate; behavior refinement pending |
| V33 pairwise identity recursive nudge | Completed 250-step targeted identity repair; greeting/current-state repaired locally, but primary fell to 5/10 and validation NLL worsened to `0.14904492264504401` | Rejected/inconclusive negative Pareto diagnostic; V32 remains metric parent and V28 behavior reference |
| V34 conflict-aware identity with local AIFL feedback | Preflight-only as of 2026-08-04; source-derived AIFL sensor, conflict projection, recursive bounded nudges; no checkpoint or training result yet | Canary pending; no promotion, deployment, global AIFL-buffer write, or knowledge admission |

## Version timeline

### V1–V9: early custom SLM construction

These are the initial custom character-transformer experiments. The durable artifacts show a common 96-character vocabulary and causal next-character training. The early sequence expanded the training input and produced checkpoints in 250-step increments or continuations. The detailed later journal begins its fully reconstructed identity/personality account at V10, so the entries below are intentionally limited to what the manifests prove.

| Version | What changed from the preceding lane | Evidence-level result |
|---|---|---|
| V1 | Initial identity/personality SLM input lane. The input manifest records 16,125 train windows and 4,234 validation windows. | 1,000-step artifact exists. The saved sample is still visibly random character output; no world knowledge was included. |
| V2 | Early corpus successor with the explicit `<END>` termination marker. | 10,722 train and 2,882 validation windows are recorded. The version is historical, not the current behavior candidate. |
| V3 | Early corpus/format successor. A separate response-only V3 variant also exists. | 13,211 train and 3,885 validation windows are recorded for the base V3 input. |
| V4 | Further early corpus expansion. | 18,275 train and 3,885 validation windows are recorded. |
| V5 | Further early corpus expansion and longer continuation ladder. | 20,625 train and 4,482 validation windows are recorded. |
| V6 | Further early corpus expansion. | 23,864 train and 5,244 validation windows are recorded; checkpoints through 1,750 steps exist. |
| V7 | Larger early corpus. | 32,912 train and 5,244 validation windows are recorded. |
| V8 | Larger early corpus and longer continuation ladder. | 36,624 train and 5,981 validation windows are recorded. The 2,500-step artifact has a higher validation NLL than its best earlier step, so it is historical evidence, not a selected candidate. |
| V9 | Largest early pre-repair corpus in this group. | 44,314 train and 7,040 validation windows are recorded. The later design work moved to a source-grounded, explicitly evaluated lane rather than treating raw loss as sufficient. |

### V10: expose the split problem

V10 ran a fresh custom SLM through 2,000 steps as eight separately observed 250-step increments. The run was training-clean and isolated, but the resulting checkpoints were retained as negative baselines. The important change was methodological: every increment was recorded, and validation behavior was not allowed to hide behind a lower training loss.

The best V10 validation checkpoint was at step 750; the step-2,000 checkpoint was retained as a separate behavior comparison. The next change was not “more steps.” It was a corpus split repair.

### V11: balanced source-grounded identity/personality corpus

V11 rebuilt the corpus from `COLD_START.md`, `foundation/AIOS_ALPHA_MANUAL.md`, `foundation/docs/VIV_SLM_FOUNDATION_V1.md`, and the personality DNA artifact. It contained 392 unique prompts: 264 train, 64 validation, 32 frozen, and 32 adversarial. All 32 concepts appeared in training, while held-out splits used paraphrase forms.

The lane produced 35,330 train windows and 8,673 validation windows. The 250-step checkpoint was intentionally undertrained (`0/6` on the early six-case probe), so the run continued in observed 250-step increments through 2,500. A paraphrase-aware semantic probe was then added to distinguish cross-answering from mere lexical mismatch. V11 was the point where the evaluation contract became more meaningful than loss alone.

### V12: operator-mirroring repair

V12 added 24 train-only prompts that directly separated “mirror the Architect’s communication style” from identity, facts, evidence, CPU decisions, and authority. It preserved V11 and used a fresh optimizer lane. The semantic probe showed that the repair hypothesis needed to target cross-concept rendering, not simply repeat an indirect answer.

### V13: speech-style and missing-evidence repair

V13 added 12 narrow speech-style rows and 12 narrow missing-evidence rows. It preserved validation, frozen, and adversarial material. The 2,500-step checkpoint improved validation loss and was retained for behavior comparison; a 2,750 continuation did not justify replacing it. The result established that these two concepts were present but could still be rendered as the wrong neighboring concept.

### V14: generic speech-prefix repair

V14 targeted the shared `How do you speak?` prefix with 12 train-only prompts. The explicit style prompts worked, but the short generic prompt repeatedly returned identity language. V14 regressed validation and remained a hold (`4/6` semantic, `3/6` lexical), so it was not selected.

### V15: ordinary-conversation surface

V15 added 24 train-only interaction rows covering ordinary greetings, tone, brevity, frustration, and capability. This was the first explicit attempt to teach the model to answer a person in ordinary conversation rather than only answer identity questions.

The ten-case holdout fell from 6/10 on the comparison candidate to 5/10, despite a validation-NLL improvement. V15 demonstrated the recurring pattern: lower NLL can coexist with worse conversational behavior.

### V16: response-only loss

V16 kept the V15-derived source material but changed supervision to assistant-response and end-marker positions only. User prompts and separators were excluded from loss. The 250-step result improved the ten-case probe to 7/10 and the legacy semantic probe to 6/6 with zero telemetry leaks. An overlong continuation command accidentally executed 500 additional steps instead of 250; the discrepancy was recorded as an actual 750-step checkpoint rather than relabeled.

### V17: corrected targeted repair and behavioral parent

V17 added 18 disjoint train-only rows: 12 speech/greeting rows and 6 missing-evidence rows. A first build failed its own holdout-disjointness test because one prompt was inherited; that dataset was quarantined and rebuilt with an unseen prompt. The corrected lane produced 46,673 train windows and 8,672 validation windows.

The 250-step checkpoint scored 7/10 on the primary ten-case probe and 6/6 on the legacy probe with zero telemetry leaks. V17 became the stable behavior parent for the later controlled experiments.

### V18: broad surface balance

V18 added 60 train-only rows: 20 speech-style, 20 ordinary greeting, and 20 plain-language. It was a deliberately broader correction attempt. It lowered optimization loss but regressed the protected behavioral surface. Disposition: negative surface-balance result; no continuation.

### V19: lower learning rate

V19 reused the larger surface-balance idea with a lower learning rate (`0.0001`) to test whether gentler updates would protect identity and authority. They did not. The lower-LR hypothesis was rejected; the problem was not simply update magnitude.

### V20: protected rehearsal

V20 returned to the V17 parent and tested a protected-rehearsal corpus instead of continuing V18 oversampling. It remained below V17 behavior. The result was a pause on adding rows or repeating optimizer sweeps without a new mechanism.

### V21: dialogue alignment and chunking repair

V21 tested position-zero dialogue conditioning. The first input build was held because it truncated response targets. A position-aligned chunking repair was implemented and then a trainer schema mismatch was corrected before the retry. The clean run improved the legacy boundary but did not improve the fixed ten-case aggregate beyond V17. V21 was retained as evidence only.

### V22: CPU-route conditioning

V22 added a CPU route label before the prompt so the SLM could condition on the CPU-selected conversational category. The result was neutral on the ten-case comparison and did not establish a behavior gain. The paired test also exposed a confound: the dialogue-aligned lane supervised far fewer tokens than the packed response-only lane.

### V23: packed route conditioning

V23 kept the route idea but returned to the packed V17 response-only objective to remove the token-count confound. Route-conditioned output did not beat the unconditioned comparison; the legacy score fell below V17. Route labels were therefore not treated as a standalone solution.

### V24: canonical speech surface

V24 added 64 disjoint canonical anchors: 12 greeting, 16 speech-style, 12 plain-language, 8 presence, 8 capability, and 8 direct-identity rows. The input lane produced 53,314 train windows and the unchanged 8,672 validation windows.

V24 scored 7/10 and 5/6, with zero telemetry leaks. Speech-style improved, but greeting, missing-evidence, and plain-language still cross-answered. This was a mixed result, not a promotion candidate.

### V25: position-aligned target focus

V25 preserved V24 and added 712 focused windows from 83 rows across the six observed failure families. A shard-number collision was caught and repaired before training; no defective tensors were trained. V25 scored 7/10 and 5/6. It repaired speech-style and missing-evidence but lost the GPU-mouth renderer term and did not solve greeting or plain language.

### V26: narrow surface discrimination

V26 narrowed the focus to 57 rows repeated 24 times, producing 1,416 focus windows. It was designed to distinguish greeting, presence, plain language, speech style, and GPU renderer wording without another broad corpus layer.

V26 scored 5/10 and 4/6. Identity and speech-style regressed, so the concentrated full-weight update was rejected despite lower loss.

### V27: replay-anchored repair

V27 returned to the exact V17 replay lane: 46,673 replay windows plus 472 focus windows from 57 V24 rows, with eight focus repeats and unchanged validation. This restored the protected parent distribution while retaining a small repair signal.

V27 scored 8/10 and 6/6 with zero telemetry leaks. It repaired plain language and preserved identity, evidence, authority, and GPU-role behavior. The remaining same-ten failures were greeting cross-answering into speech-style and malformed speech-style wording. V27 became the best challenger at that point.

### V28: canonical greeting/style disambiguation

V28 inherited V27 unchanged and added 368 canonical windows from 23 V24 rows, repeated 16 times. The final training lane was 47,513 windows with 8,672 unchanged validation windows.

V28 scored 9/10 and 6/6 with zero telemetry leaks. It fixed the speech-style failure while preserving the rest of the established surface. Only the greeting case remained wrong: the model still returned operator-mirroring language. V28 became the best offline candidate and was frozen before the next experiment.

### V29: greeting-only weighting — rejected

V29 inherited V28 and added only the nine existing greeting rows whose responses were the two canonical listening acknowledgements. The focus view repeated 32 times and added 288 windows; validation remained the unchanged 8,672 V17 windows.

V29 completed 250 CUDA steps with lower training NLL (`0.11236786803212995`) and lower validation NLL (`0.13416705177757363`). That local optimization was misleading. The matched primary probe fell from V28 `9/10` to `6/10`; identity, speech style, current-state, and plain-language behavior regressed, while the greeting still failed. Legacy behavior stayed `6/6`, and telemetry leaks stayed at `0`.

Disposition: `INCONCLUSIVE_NEGATIVE_LOWER_LOSS_BEHAVIOR_REGRESSION_V29`. V29 is preserved as a rejected challenger. V28 remains frozen and recoverable. This is the evidence for changing the mechanism rather than increasing greeting repetition again.

### V30: frozen-head, CPU-gated greeting correction — rejected/inconclusive challenger

V30 is the first deliberately modular late correction. It does not edit V28. It reuses:

1. the V28 checkpoint as the immutable parent;
2. the V29 greeting-only focus shard as the minimal training delta;
3. response-only masks from the existing tensor contract;
4. a new preservation loss against the frozen parent logits;
5. a parameter scope limited to `lm_head.weight` and `lm_head.bias`.

All transformer representation parameters are frozen. A fixed replay anchor penalizes drift away from V28, and a prompt-position preservation penalty prevents the greeting focus from becoming a general prompt rewrite. The output is a separate offline checkpoint lane. It is not automatically selected for non-greeting queries and cannot gain CPU authority.

The new preflight and source regression passed:

- parent checkpoint SHA-256: `99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0`;
- greeting focus: 288 masked windows from the verified V29 focus shard;
- validation replay: unchanged from V17;
- trainable parameters: `lm_head.weight`, `lm_head.bias` only;
- training, run, promotion, and deployment flags: closed during preflight;
- the pre-run backup was verified before authorization.

The V30 canary then completed exactly 250 CUDA steps. The focus loss reached `0.09127199429635323`; the full training NLL was `0.12370883776717788`; validation NLL was `0.14111439127179698`; validation token accuracy was `0.9579070974084491`; and only two tensors changed. Preservation measurements were `anchor_logit_mse=0.00037586348480544984` and `prompt_preservation_loss=0.00019296749087516218`.

The preservation mechanism limited broad drift, but it did not repair the target surface. The matched primary probe scored `9/10`, exactly matching V28, with the greeting still failing. The legacy semantic probe remained `6/6`, telemetry leaks remained `0`, and the CPU router/mouth regression remained a pass. The direct V30 CPU render test routed all nine surface cases through CPU fallback (`fallback_used=true` for all nine), including the defective greeting; no model text gained authority.

The first probe invocation exposed a packaging detail: the V30 run directory does not contain a local `VOCAB.json`. Evaluation therefore used the verified V28 vocabulary file, whose vocabulary is unchanged for this lane. This did not alter weights or inputs, but the missing run-local vocabulary is recorded as an artifact-completeness follow-up rather than silently ignored.

Disposition: `INCONCLUSIVE_NO_GREETING_GAIN_V30_FROZEN_HEAD_PRESERVATION_HELD`. V30 is retained as a rejected challenger for lineage and rollback evidence. V28 remains the best offline candidate at `9/10` and `6/6`; the CPU-owned route remains the reliable greeting behavior. No promotion, deployment, live-model mutation, or world-knowledge admission occurred.

### V31: balanced one-pass corpus base — rejected/inconclusive challenger

V31 changed the corpus composition instead of adding another narrow greeting multiplier. It formalized the full V24 source-grounded corpus as a one-pass base: 366 original V17 parent rows plus 64 canonical surface rows covering six families. The resulting response-only lane contains 53,314 train windows and the unchanged 8,672-window V17 validation split. No world knowledge, telemetry, or repeated focus shard was admitted.

The run warm-started from V28 with a fresh AdamW optimizer for exactly 250 CUDA steps. Training NLL was `0.12395229388282396`; validation NLL was `0.1424706606753508`; validation perplexity was `1.153119248721067`; and validation token accuracy was `0.9578288138216045`. Compared with V28, the validation NLL and perplexity were worse (`0.14141843159924042` and `1.15190654125426` for V28), and accuracy was slightly lower (`0.9578652247922299` for V28).

The matched primary probe scored `8/10`, below V28's `9/10`. Greeting remained unresolved, and the current-state case shifted into a warmth/personality response. The legacy semantic probe remained `6/6`, telemetry leaks remained `0`, and the CPU router surface still passed. Direct V31 CPU rendering accepted all nine routed cases, with eight CPU fallbacks; the renderer gained no authority.

Disposition: `INCONCLUSIVE_NEGATIVE_PARETO_TRADEOFF_V31_BALANCED_BASE`. V31 is preserved as a corpus experiment and rejected as the current candidate because it did not improve the complete operating point. V28 remains the behavioral baseline. This does not mean the corpus is discarded; it establishes that one-pass balanced replay plus a fresh optimizer is not the best next update from V28. The next adjustment must be chosen from the evidence rather than from a demand for perfect probes.

### V32: balanced lower-update-magnitude ablation — accepted metric progress, behavior refinement pending

V32 is a controlled follow-up to V31. It keeps the V28 checkpoint, the V31 balanced response-only tensors, the unchanged V17 validation split, batch/evaluation sizes, seed, gradient clipping, context, sampling settings, and exactly 250 steps fixed. The only changed training variable is the full-model AdamW learning rate: `0.0001` instead of V31's `0.0003`.

The purpose is to test one bounded explanation for V31's negative movement: the update may have been too large for the already-established character surface. This is not a claim that lower learning rate will work; it is an isolated experiment that can distinguish update magnitude from corpus composition without adding rows or repeating greeting-only examples.

The governed trainer is `foundation/scripts/train_viv_slm_v32_balanced_low_lr.py` (SHA-256 `0561A533A481C75A5BA740613A7DE7AE9F216AEAFBD7EE4B293EF4DEA4581739`), with regression `foundation/scripts/test_viv_slm_v32_balanced_low_lr_training.py` (SHA-256 `1F0AB536794E9DA7EB1D1686C65A822B5EC13DD692B1E1D565C56C5343E3E753`). The regression passed with the V28 parent hash and all V31 input hashes verified; the wrapper rejects a missing explicit `--authorize` flag, fixes the learning rate to `0.0001`, and keeps promotion/deployment closed.

The boundary review intentionally added one new production trainer with zero removals and zero changed signatures. The reviewed registry has `569` frozen boundary modules, registry SHA-256 `0D3B6A0CF8BB73E3028F60A0F9E64FA4EFA0EB990F4CB86794D9E78A15569506`, review artifact SHA-256 `B0E88DA48C6AA9F2394B19E2A78C1AE752CD386D722382933A8FCCB8347BB200`, and registry backup `foundation/triad_boundary_registry.bak_20260804T190015Z.json`. Full foundation preflight passed with `1,994` parsed Python files, `1,108` architecture files at `100%` coverage, zero direct bridge violations, registry drift false, all configured suites green, and Rust security PASS.

A pre-edit backup was verified at `foundation/artifacts/auto/agentic/backups/pre_v32_lower_lr_20260804T185831Z/`: `24` files, `32,485,244` bytes, manifest SHA-256 `F6A157FB26571A36098B47C4A3B800128DD93D2EB5A54EAE04FCBE5F39800A94`, with every copied source matching its backup. A second pre-authorized-run backup was verified at `foundation/artifacts/auto/agentic/backups/pre_v32_authorized_run_20260804T190500Z/`: `25` files, `32,586,847` bytes, manifest SHA-256 `D99B8372CBB458467881E1CF835EECFA24900CB1840C10A639795EA55AAA144B`, with every copied source matching its backup.

The named V32 campaign then completed exactly `250` CUDA steps at `learning_rate=0.0001`. The checkpoint is `models/viv_slm_identity_personality_v32_balanced_low_lr/runs/balanced_low_lr_steps_0250/checkpoint.pt` (SHA-256 `EC7065B19C6630B7CF3DD64AE78FD92371A02A4A4E7465EF3206AB6CE30EE2F9`). Training NLL was `0.1263299111822614`; validation NLL was `0.13565050303587134`; validation perplexity was `1.1452815512144916`; and validation token accuracy was `0.9591669169920897`. Relative to V28, validation NLL improved by `0.005767928563369079`, perplexity by `0.0066249900397683525`, and token accuracy by `0.0013016921998597608`.

The metric improvement did not repair the full behavior surface: the primary probe scored `8/10` versus V28's `9/10`, with greeting and current-state still failing. The legacy semantic probe remained `6/6`, and telemetry leaks remained `0`. V32 therefore dominates V31 on the measured aggregate metrics while matching its `8/10` primary score, but it is not a Pareto replacement for V28 because the one-point behavioral regression remains.

The mouth boundary held. The V32 checkpoint routed through the CPU identity mouth with `9/9` accepted, `7` CPU fallbacks, `9` malicious renderer rejections, and `3` unrelated queries rejected before renderer invocation. The general CPU mouth contract also passed renderer equivalence, semantic-leak containment, unsupported-fact containment, stale-health containment, fresh-health acceptance, and live-state immutability. No live model, deployment, CPU authority, or knowledge source changed.

Disposition: `ACCEPTED_PARETO_METRIC_PROGRESS_BEHAVIOR_REFINEMENT_REQUIRED_V32`. V32 is retained as a valid metric-progress point and the parent for the next identity refinement, while V28 remains the behavior reference. This run proves the custom training path is operational and that lower update magnitude materially improves held-out likelihood. The remaining greeting/current-state distinction is a refinement target, not a reason to discard the metric gains.

### V33: pairwise identity refinement with recursive bounded nudging — targeted repair succeeded, broad surface regressed

V33 is the next layer on top of V32, not a reset to V28 and not a new knowledge run. It targets only the two V32 primary failures: greeting and current-state. The input lane contains exactly two pairs. Each chosen response comes from the CPU-authorized route; each rejected response is the observed V32 failure; rejected text is never an SFT target. The lane contains no world knowledge or telemetry, and the V31 balanced replay remains the preservation surface.

The objective combines chosen-response SFT, reference-free pairwise preference, V31 replay SFT, and a frozen-V32 replay anchor. The run adds the first automatic adjustment controller in this lineage. At each training step it recursively updates exponential moving averages of the observed chosen-versus-rejected log-probability margin and replay anchor logit MSE. Bounded equations then produce small scalar nudges to effective learning rate, pairwise pressure, and preservation pressure. The bounds are explicit: learning-rate scale `0.25..1.25`, pairwise scale `0.5..2.0`, and anchor scale `0.75..3.0`. No manual parameter edit is allowed during the run; the controller state and every effective value are logged in the training history and checkpoint metadata.

The governed sources are `foundation/scripts/build_viv_slm_v33_pairwise_identity_inputs.py` (SHA-256 `6CC2C14848B55B13A7D3A41C0173E6A8D34824AD572A199E5ECF352390193416`), `foundation/scripts/test_viv_slm_v33_pairwise_identity_inputs.py` (SHA-256 `336105F2147AD151CE36390BE93685A4820CB5D1E2B9085279C23D23118CEC1F`), `foundation/scripts/train_viv_slm_v33_pairwise_identity.py` (SHA-256 `311DD48A883819103C99EC09771AE09CBF17B0F61481A2AEAE0235E14A81B24F`), and `foundation/scripts/test_viv_slm_v33_pairwise_identity.py` (SHA-256 `F8D8982B831FF2F19892EC8282454EC6E49563EB2A08439758BB6FC0AD5CD1D9`). Focused tests passed, including parent hash checks, rejected-is-not-SFT checks, explicit authorization refusal, controller response, and bound checks.

The V33 input manifest is `models/viv_slm_identity_personality_v33_pairwise_identity/inputs/INPUT_MANIFEST.json` (SHA-256 `6091DD5B134C6ED7C524006DCC99DE3EC9EA7ADEE300CE0F59A10F00E960D5EC`); pair rows are `PAIRWISE_ROWS.jsonl` (SHA-256 `2BA367EE6B9989C067470790F3E321D93467F9910A90C7D0F8AF71F704A8C819`). The parent is the V32 checkpoint (SHA-256 `EC7065B19C6630B7CF3DD64AE78FD92371A02A4A4E7465EF3206AB6CE30EE2F9`) and V28 remains the behavior reference (SHA-256 `99D536EE2E0AB804B70B54B4C81C617468564F825EAE82E2F6296964796C1BF0`).

The full foundation preflight passed with `2,035` parsed Python files, `1,112` architecture files at `100%` coverage, `571` frozen boundary modules, zero direct bridge violations, registry drift false, all configured suites green, and Rust security PASS. The reviewed registry has two intentional additions, zero removals, zero changed signatures, registry SHA-256 `D4FB3961488B893E99341448D5EA1DA072C35468A9BB94A8198F91EB812105EA`, review artifact SHA-256 `05868719896CD8FA86851A54663719A6662FC42F68605A630999A27FB7B3F857`, and backup `foundation/triad_boundary_registry.bak_20260804T192326Z.json`.

The named scope was exactly one offline `250`-step CUDA canary, fresh AdamW, base learning rate `0.00005`, batch/evaluation size `64`, seed `42`, context `128`, response-only loss, gradient clipping `1.0`, temperature `0`, and top-k `40`. The V32 parent was retained as the metric parent. Training and run authority were recorded, but promotion and deployment remained closed. The pre-edit backup is `foundation/artifacts/auto/agentic/backups/pre_v33_pairwise_identity_20260804T192319Z/`: `25` files, `32,552,081` bytes, manifest SHA-256 `1FB3D01FBCCFCF2C63F46AAAB59667C8FFF54B17179B5DBF1390D756B55A313A`, with every copied source matching its backup. The pre-authorized snapshot is `foundation/artifacts/auto/agentic/backups/pre_v33_authorized_run_20260804T193100Z/`: `25` files, `32,567,483` bytes, manifest SHA-256 `7B34E9D0E2C4CDF123BC404C15BEBD00D832E53932101D2DD0D6CF9C8982B223`, with every copied source matching its backup.

The canary completed exactly `250` CUDA steps. The checkpoint is `models/viv_slm_identity_personality_v33_pairwise_identity/runs/pairwise_identity_steps_0250/checkpoint.pt` (SHA-256 `6C7D1EF8048105A0018473A54773CB487B63C6F9C1116CAB8235F3EEB73D793C`). Training NLL was `0.15133277290551983`; validation NLL was `0.14904492264504401`; validation perplexity was `1.160725130880954`; and validation token accuracy was `0.9557115158797346`. Relative to V32, validation NLL worsened by `0.013394419609172675`, perplexity worsened by `0.015443579666462481`, and token accuracy fell by `0.0034554011123556494`.

The targeted pairwise repair did work locally: greeting and current-state passed the V15 probe. It did not preserve the rest of the surface. The primary probe fell to `5/10`, with capability, plain-language, speech-style, operator-mirroring, and missing-evidence failures. The legacy semantic probe fell to `4/6`, with operator mirroring and missing evidence failing. Telemetry leaks remained `0`, and the CPU boundary still passed `9/9` routed cases with `7` CPU fallbacks, `9` malicious renderer rejections, and `3` unrelated queries unrouted. The general CPU mouth render contract also passed.

The controller's final measured state is evidence, not a success claim: pairwise margin `0.6128308773040771`, replay anchor logit MSE `1.2304797172546387`, margin EMA `0.5631521163503077`, anchor-drift EMA `1.212467350126766`, effective learning rate `0.0000125`, effective pairwise weight `0.375`, and effective anchor weight `3.0`. The drift ratio was `1212.467350126766`, so the controller reached its anchor-pressure maximum, pairwise-pressure minimum, and learning-rate minimum. This is a useful automatic-control diagnostic: the chosen pair learned, but the update was not compatible with the established surface at this scale and objective.

Run artifact hashes are `RUN_MANIFEST.json` `7665FAE08A775A4624C1290C6E4ACDAC552F5E3CC457C3B4D674FFF7E458E74A`, `RUN_REPORT.md` `C3A965FBB497721EDB79094D25B4F9CA316AB1A5EE1BBD520A3A61232AF38DAE`, `training_history.json` `CDCBE6824EB77C974498BE050D544FE4342CBCC210B34D9DEA33C4EFA06A0AF7`, `generation_comparison.json` `78FB956874A6AA801BE2731545E28413F15E1C2A1D94835A1292B039CE76F563`, and `AUTHORIZATION.json` `076A11DD9E9D608FAFF5DB98D61A16495E45F4E75B9643743C8D0E91F013CA75`. Probe hashes are V15 `8890048208300EB982E5956482CC244ABDB02D7860560CE68746D83DD60191B1`, legacy `6B8B80314751D43C9BDE9C8920286A5C234071CB8F79901DB06EB19536440C4E`, and CPU boundary `23712EF6F721E4068FCF7A223EF452FCF74A80DA2F0705657C48BA1F04B633FC`.

The post-run evidence backup is `foundation/artifacts/auto/agentic/backups/post_v33_pairwise_identity_0250_evidence_20260804T193600Z/`: `34` files, `48,170,538` bytes, manifest SHA-256 `AB0B773277A320193AF92C55B67938319633EAF7A38D9ABF39D2FC9F76303C93`, with every copied source matching its backup. Disposition: `INCONCLUSIVE_NEGATIVE_PARETO_TRADEOFF_V33_RECURSIVE_CONTROLLER_DIAGNOSTIC`. V33 is retained as evidence that the controller and pairwise mechanism can repair the selected cases, but it is not a replacement for V32 or V28. The next experiment must reduce the identity update's broad-surface interference; no knowledge admission, promotion, deployment, or live-model mutation occurred.

### V34: conflict-aware identity refinement with local AIFL feedback — preflight complete, canary pending

V34 is the next layer on the V32 metric-progress parent. It does not reset to V28 and does not treat V33's negative result as a new parent. The trainer computes the identity/focus gradient and the replay-preservation gradient separately; when their dot product is negative, it projects the focus gradient away from the replay-opposing component before combining them. A recursive controller then makes small bounded adjustments from measured gradient conflict, replay NLL drift, validation NLL drift, and internal feedback error. The configured bounds are focus scale `0.01..0.12`, effective learning-rate scale `0.10..1.05`, and replay scale `1.0..4.0`.

The AIFL integration uses the existing project contract pragmatically as a local read-only sensor. It reads the two CPU-authorized chosen rows from the hash-locked V33 `PAIRWISE_ROWS.jsonl`, generates three bounded drafts per case at temperatures `0.0`, `0.25`, and `0.5`, and calls `lib.viv_shadow_judge.score_draft` for Vidi/Intellexi/Vixi observations. A case is `REWARD` only when all three drafts pass the mind checks and remain telemetry-clean; otherwise it is `HOLD`. The resulting feedback error is used only as a bounded controller input and a guarded-state selection condition. V34 does not call `judge_and_select`, does not append to the historical global preference buffer, does not write the old global train gate, does not mutate Master `S_n`, and does not change live runtime state. The synthetic `S_n=0.5` value is explicitly offline sensor input, not accounting or authority.

This is intentionally not a claim that the older Qwen/OpenAster AIFL lane is already the custom SLM's training pipeline. It is a controlled bridge from the existing AIFL judgment semantics into the custom mouth experiment, with source and global-write boundaries tested. If the old sensor is too strict for a character-SLM identity response, its result remains `HOLD` and is recorded for criteria refinement rather than silently admitted as a training row.

The V34 trainer is `foundation/scripts/train_viv_slm_v34_conflict_aware_identity.py` (SHA-256 `45F4CB1BEB628B5EFD830CCFE68BD3C3DAB0E418A672EF63A2A721D65C8D494F`) and its focused regression is `foundation/scripts/test_viv_slm_v34_conflict_aware_identity.py` (SHA-256 `AF8848CE77E1F5F6506DDB7A501B45E21ABC797CF5876D7A3851B5A23FFCC967`). The boundary registry review recorded one intentional trainer addition, zero removals, and zero signature changes; the frozen registry SHA-256 is `2F4A0F4D6DF2652A19A1CB9397B5F4A8622BDE66A2F8EA16E42A57CF03E5DA81`, and the review artifact SHA-256 is `DA16DC84D6EF06E13B243A6D15DEC5603F63D8B3E8619850C00E16E790239B94`. Focused V34/V33 tests and full foundation preflight passed: `2,097` parsed Python files, `1,114` architecture files, `100%` coverage, `572` boundary modules, zero direct bridge violations, registry drift false, configured suites green, and Rust security PASS.

The current status is `PREFLIGHT_COMPLETE_AIFL_SENSOR_INTEGRATED_CANARY_PENDING`. The exact next scope is one offline `250`-step CUDA canary from V32, with fresh AdamW at base learning rate `0.00002`, response-only loss, context `128`, batch/evaluation size `64`, seed `42`, gradient clipping `1.0`, temperature `0`, and top-k `40`. The preflight record is in `foundation/artifacts/auto/agentic/CURRENT_TASK.json`; the record backup is `foundation/artifacts/auto/agentic/backups/pre_v34_aifl_records_20260804T200121Z/`. Training authority, promotion, deployment, and knowledge admission remain closed until the named canary is separately recorded and backed up.

## What changed between the versions

The progression is not “repeat the same training until loss is low.” The mechanism changed repeatedly:

```text
early character SLM
  -> source-grounded concept split
  -> paraphrase-aware evaluation
  -> operator-mirroring repair
  -> speech-style/evidence repair
  -> prompt-prefix conditioning
  -> ordinary-conversation corpus
  -> response-only supervision
  -> disjoint targeted repair
  -> surface balance
  -> lower-LR test
  -> protected rehearsal
  -> chunked dialogue alignment
  -> CPU-route conditioning
  -> packed route conditioning
  -> canonical surface anchors
  -> position-aligned focus
  -> narrow surface discrimination
  -> replay anchoring
  -> canonical disambiguation
  -> frozen, parameter-scoped late correction
  -> balanced one-pass corpus replay
  -> controlled lower-update-magnitude ablation
  -> pairwise identity refinement with recursive bounded nudging
  -> conflict-aware identity refinement with local AIFL feedback sensing
```

The important design lesson is that the custom architecture gives us control over the mechanism. It does not make every mechanism safe automatically. Each new equation, loss term, parameter scope, tokenizer rule, or routing choice must still earn its place through source inspection, deterministic tests, matched probes, and a reversible checkpoint.

## Backup and evidence policy

Every material version change is preceded by a backup of the files and artifacts that can be changed. V29 has a final state backup at:

`foundation/artifacts/auto/agentic/backups/final_v29_greeting_focus_state_20260804T193000Z/`

Its recorded 144-file source/backup verification includes matching `CURRENT_TASK.json` and `session_journal.md` hashes. Before V30 source changes, a separate backup was created at:

`foundation/artifacts/auto/agentic/backups/pre_v30_late_correction_canary_20260804T194500Z/`

It contains 14 explicitly listed source/state/model files totaling 17,133,184 bytes. Direct SHA-256 verification returned `PASS_SHA256_SOURCE_EQUALS_BACKUP`.

After the V30 run and probes, a 26-file evidence backup was created at:

`foundation/artifacts/auto/agentic/backups/post_v30_frozen_head_greeting_0250_evidence_20260804T183146Z/`

It contains 26,129,728 bytes. Every copied source file matched its backup by SHA-256, and the backup manifest SHA-256 is `9EA17D421713BE27ACA8A8C38C065DFBA5184FA74F2351AEBDADE562A128FF5C`.

No backup is a promotion decision. Backups preserve rollback and provenance; probes and CPU contracts decide whether a candidate is useful.

After the V31 run and matched probes, a 24-file evidence backup was created at:

`foundation/artifacts/auto/agentic/backups/post_v31_balanced_base_20260804T185207Z/`

It contains 32,476,534 bytes. Every copied source file matched its backup by SHA-256, and the backup manifest SHA-256 is `D55801DD34814D4A00698A63948F87668451378B1464A8F5F9477F3FE977CC3C`.

## Current next action

The V32 and V33 250-step offline canaries and comparisons are complete. V28 remains the behavior reference, and V32 remains the metric-progress parent. V33 repaired greeting/current-state locally but lost five primary cases, two legacy cases, and the V32 metric gains. The next controlled experiment should use a smaller, more selective identity nudge with metric-aware preservation, retaining V32 rather than resetting or admitting knowledge. No promotion or deployment is implied.

The completed comparison covered:

- V31 against V28 on the same ten-case primary probe;
- V31 against the legacy six-case probe;
- greeting and current-state behavior specifically;
- aggregate NLL, perplexity, and token accuracy;
- CPU router/mouth regressions, including malicious renderer rejection;
- telemetry leakage and live-state mutation flags.

The V31 result was an aggregate regression from V28, V32 established a valid metric-progress point, and V33 showed that pairwise identity pressure can repair selected cases while over-moving the broader surface. The CPU-owned route remained correct and contained throughout. The next experiment is a smaller behavior refinement from V32 with V28 as the behavior reference; it is not a reset to V28 and not a knowledge-layer run.
