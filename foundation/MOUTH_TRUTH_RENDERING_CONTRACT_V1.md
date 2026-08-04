# Viv Mouth Truth-Rendering Contract v1

## Purpose

Viv's GPU mouth is a stateless language renderer. It does not decide what is
true, acquire authority, remember independently, or perform actions. The CPU
mind and governed retrieval path supply the facts; the mouth renders those
facts into clear human language while preserving Viv's licensed identity.

## Required behavior

For every response, the mouth must:

1. Answer only from the authoritative fact packet and the user request.
2. Preserve the meaning, uncertainty, provenance, and scope of supplied facts.
3. Say that the information cannot be verified when the packet is empty,
   stale, conflicting, or insufficient.
4. Keep Viv's identity intact: Viv is the AIOS speaking identity and a
   replaceable voice model is only the mouth. Natural wording must not claim
   human status, personal authority, or independent agency.
5. Answer ordinary questions naturally without emitting internal telemetry,
   packet markup, leases, routing state, or security details unless the packet
   explicitly authorizes that disclosure.

## Forbidden behavior

The mouth must not invent facts, fill gaps with plausible guesses, claim that
an action occurred, imply that user text is system authority, disclose cached
health values as current, gaslight the user, or use fluent wording to conceal
uncertainty. A fluent answer that is unsupported by the packet is a failure.

## Knowledge-source boundary

`F:\AI_Datasets` is a knowledge source, not a mouth target. Wikipedia and
other collections remain read-only source material. The CPU/RAG layer retrieves
and cites relevant passages, resolves conflicts, and constructs the packet.
Training examples may be distilled from those packets, but raw knowledge must
not be poured into the mouth adapter without provenance, deduplication, and a
disjoint evaluation split.

## Training curriculum

The next curriculum must be substantially larger than the 148-row boundary
micro-corpus and include:

- grounded knowledge questions with supplied evidence;
- ordinary conversational questions with no telemetry packet;
- uncertainty, conflict, and insufficient-evidence examples;
- identity-preserving introductions and warm responses;
- explicit health-mode examples using fresh authoritative data;
- negative/critic examples for invention, agency claims, telemetry leakage,
  and identity drift. Negatives are critic data, never response targets.

## Admission and evaluation

Every admitted chosen response receives CPU semantic validation for entailment,
provenance, uncertainty, identity, and containment. Train/development/holdout
splits are ask-cluster disjoint. A candidate must improve raw free-generation
behavior and containment against the untouched V19 incumbent; teacher-forced
NLL alone is not a promotion signal. No candidate changes live state without a
separate promotion decision.

## Runtime implementation

The strict runtime boundary is implemented by
`foundation/lib/cpu_mouth_contract.py` and is applied by
`voice_core/runtime_contract.py` before speech egress.

The CPU emits a `cpu_mouth_render_envelope_v1` containing:

- CPU-authorized facts and conclusions only;
- conversation or health mode;
- permitted action language and explicit forbidden disclosures;
- source/freshness evidence;
- CPU decision and provenance digests; and
- renderer capabilities fixed to data-only, no-live-read, no-execution, and
  no-decision-change.

The renderer receives an immutable view of that envelope and returns text only.
The CPU rejects unsupported claims or numbers, authority and execution claims,
ordinary-mode telemetry including semantic paraphrases, acronym violations,
and stale health presented as current. A rejected proposal gets one bounded
retry; if it still fails, `deterministic_fallback()` supplies CPU-authored
language. Health data is renderable only when its freshness state is `fresh`
within the authoritative three-second bound; otherwise the response says that
current health cannot be verified.

The live Ollama, GGUF, and LoRA branches use `envelope_to_messages()` or
`envelope_to_completion_prompt()` at renderer ingress. The older intent/tagged
packet remains a CPU verification and training artifact; it is not the live
mouth's primary input. A live renderer retry uses the same envelope and is
bounded to one attempt.

The acceptance regression is
`foundation/scripts/test_cpu_mouth_render_contract_v1.py`. It proves that two
different renderers can vary wording while retaining the same claim IDs,
decision digest, provenance digest, and CPU authority; it also exercises a
malicious renderer, semantic telemetry leakage, unsupported facts, stale health,
fresh health, immutable input, and unchanged live-state fixtures. This is a
runtime boundary change only; it does not authorize training, promotion, or
deployment.
