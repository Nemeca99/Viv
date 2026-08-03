# AIFL — Autonomous Internal Feedback Learning

## Definition

Autonomous Internal Feedback Learning, or AIFL, is a local training and alignment system designed to improve an AI through repeated internal evaluation rather than continuous human rating.

AIFL replaces the repetitive part of human feedback with a controlled feedback loop:

1. The AI produces possible responses.
2. A separate judge evaluates those responses against human-defined criteria.
3. Deterministic software verifies that the judgment is structurally valid.
4. Approved behavior is rewarded through training.
5. Rejected behavior becomes a hard negative or diagnostic example.
6. The trained model is evaluated on frozen, unseen tests before it can be considered for deployment.

Humans still define the values, boundaries, curriculum, and acceptance criteria. AIFL automates applying those decisions consistently at scale.

## Purpose

The purpose of AIFL is not merely to make a model sound better. It is intended to make the model more reliably aligned with a defined system of truth, reasoning, security, identity, and expression.

For Viv, this includes learning to:

- Distinguish supported claims from unsupported claims.
- Express uncertainty instead of inventing information.
- Respect security and ownership boundaries.
- Understand her architecture and model roles.
- Follow verified RID, physics, and UML structures.
- Maintain a recognizable personality without sacrificing accuracy.
- Prefer semantically equivalent language that is more efficient when appropriate.
- Remain coherent across longer and multi-turn conversations.
- Resist learning shortcuts that merely game the judge.

AIFL therefore acts like a calibration system or gyroscope. It measures whether the model is drifting away from its intended behavior and supplies corrective training when drift is detected.

## Separation of responsibilities

AIFL deliberately separates generation, judgment, admission, and deployment.

### The mouth

The mouth generates natural-language responses. It may explore multiple ways to answer, but it does not decide whether its own output is correct.

In the current architecture:

- Qwen can act as a temporary teacher and draft generator.
- OpenAster is the sovereign trainable target mouth.
- The deterministic fallback provides continuity but is not treated as native model intelligence.

### The semantic judge

The CPU-based semantic judge evaluates a narrow question, such as:

- Does this response match the supplied evidence?
- Does it express uncertainty correctly?
- Does it preserve the defined ownership boundary?
- Does it refuse an unsafe request without inventing claims?

The judge returns bounded categorical observations such as `PASS`, `FAIL`, or `ABSTAIN`. It is a sensor, not the final authority.

### Deterministic admission

Deterministic code verifies everything that can be verified mechanically:

- Required fields are present.
- The response boundary is correct.
- Hashes are valid.
- Training and evaluation data are disjoint.
- All required drafts passed.
- The intended negative example violates exactly the targeted rule.
- Security approved every ingress, egress, and artifact write.
- The judge returned valid and consistent observations.

The deterministic layer makes the final admission decision. This prevents an LLM judge from silently changing the rules or admitting malformed data.

### The Architect

The human Architect remains the ultimate authority.

The Architect defines:

- What Viv should value.
- What counts as truth or acceptable uncertainty.
- Which security boundaries are immutable.
- What personality and expression are desired.
- Which curriculum layers should be taught.
- The thresholds required for deployment.
- Whether a validated candidate is actually deployed.

AIFL automates evaluation and training; it does not replace architectural authority.

## The AIFL training cycle

### 1. Define one learning objective

Each curriculum layer targets a narrow behavior. Examples include:

- Evidence truth.
- Structural validity.
- Honest uncertainty.
- Identity continuity.
- Security containment.
- Reasoning quality.
- Conversational expression.
- Semantic efficiency.

Teaching one distinction at a time makes failures easier to diagnose and prevents several unrelated concepts from being blended into an ambiguous score.

### 2. Construct a controlled prompt

The system creates a curriculum item containing:

- The user’s request.
- Verified facts and context.
- The semantic class.
- The behavior being tested.
- A correct response pattern.
- A deliberately incorrect or misaligned contrast.
- Provenance and source hashes.

The prompt is rendered through one canonical format so that training, validation, and live inference see the same structure.

### 3. Generate multiple drafts

The model creates at least three drafts sequentially.

Multiple drafts are important because one acceptable answer may be accidental. A set of independently generated drafts tests whether the desired behavior is stable across variations in wording.

Every draft must preserve the same semantic truth, even when its phrasing or personality differs.

### 4. Judge every draft

Each draft is evaluated against the narrow criterion assigned to that curriculum item.

For example, an evidence-truth item may require:

- The positive draft to pass.
- The hard negative to fail.
- The judge to produce the same categorical result twice.
- All security checks to pass.
- No malformed, repetitive, or numerically collapsed output.

The judge does not award points for sounding impressive. It evaluates the specific semantic distinction being trained.

### 5. Require unanimous alignment

A draft set is accepted only if all three drafts pass the necessary alignment checks.

If one draft fails, disagrees, becomes malformed, or triggers security, the set is placed on `HOLD`. It is preserved for diagnosis rather than silently discarded or admitted.

This rule prevents the training data from rewarding behavior that is only intermittently aligned.

### 6. Select the best valid expression

When several drafts are semantically correct, AIFL can rank them using secondary considerations such as:

- Personality fit.
- Clarity.
- Naturalness.
- Repetition.
- Neural-token count.
- UML tariff cost.
- Observed latency or energy.
- Normalized processing cost.

Quality parity comes first. Efficiency is used to choose among responses that already mean the correct thing.

This is how Viv can gradually develop characteristic word choices without learning to sacrifice truth merely to produce fewer tokens.

### 7. Create the training example

The approved response becomes the positive training target.

Depending on the training method:

- Supervised fine-tuning teaches the approved response directly.
- Pairwise training compares the approved response against a controlled hard negative.
- Only Viv’s response tokens receive language-model loss.
- Prompt tokens are masked so the model learns how to answer rather than memorizing how the question was written.

Rejected drafts remain useful as diagnostic evidence or explicit contrast examples, but they are never treated as approved speech.

### 8. Train a bounded candidate

AIFL trains a candidate adapter under strict resource limits.

The run stops on conditions such as:

- Non-finite gradients.
- Missing response boundaries.
- Training/evaluation overlap.
- GPU contention.
- Resource ceiling violations.
- Security denial.
- Timeout or model degeneration.

The result is a candidate—not an automatic deployment.

### 9. Evaluate on unseen material

The candidate is tested on development and frozen holdout packs that were never allowed into training.

Evaluation measures generated behavior, including:

- Vidi and Intellexi judgments.
- Valid native speech rate.
- Honesty and containment.
- Numeric or repetition collapse.
- Multi-turn consistency.
- Token and processing cost.
- Latency and observational energy.
- Security behavior.

Training loss alone is insufficient. A model can achieve a low loss by memorizing training patterns while failing to generalize.

### 10. Compare against the current baseline

The candidate must be compared fairly against the current live mouth using the same prompts, judge, fallback policy, and measurement rules.

Native model quality is measured with deterministic fallback disabled. Fallback-assisted reliability is reported separately so fallback cannot hide a weak model.

### 11. Validate without automatically deploying

A candidate that passes becomes a `validated_candidate`.

It does not become the live mouth until the Architect explicitly approves a canary rollout. During a canary, the previous mouth remains available for immediate rollback.

Malformed speech, repeated fallback, security rejection, or judge regression causes automatic reversion.

### 12. Feed failures into the next curriculum layer

Evaluation failures become structured feedback:

- What failed?
- Which semantic layer owned the failure?
- Was the problem factual, structural, expressive, or security-related?
- Was it a model failure, judge failure, dataset problem, or infrastructure fault?
- Can a controlled positive/negative pair teach the missing distinction?

The system then creates a narrowly targeted correction rather than indiscriminately retraining on everything.

This completes the feedback loop.

## Layered training tree

AIFL can be understood as a branching training tree.

At each node, the system teaches a distinction:

```text
Supported claim
├── Truthful and appropriately expressed → reward
└── Unsupported, distorted, or misleading → reject
```

The accepted branch can then be divided again:

```text
Truthful response
├── Structurally valid → reward
└── Correct conclusion through invalid structure → reject
```

And again:

```text
Truthful and structurally valid response
├── Clear, natural, and personality-aligned → preferred
└── Awkward, repetitive, or unnecessarily expensive → lower preference
```

Over time, many simple distinctions combine into complex behavior. Viv is not expected to learn “alignment” as one vague concept. She learns a layered network of specific boundaries and preferred patterns.

## Truth in AIFL

AIFL distinguishes several related forms of correctness.

### Factual truth

Claims match verified evidence.

### Mathematical truth

Calculations and numerical relationships are correct.

### Structural truth

The reasoning follows the required structure and does not obtain a correct answer through an invalid construction.

### Semantic truth

Different wording preserves the same intended meaning.

### Contextual truth

The response is appropriate for the situation, available evidence, and requested level of certainty.

### Operational truth

The system’s claims about what it ran, changed, measured, or deployed are supported by actual artifacts and process evidence.

A response is fully acceptable only when the relevant forms of truth agree.

## Relationship to RLHF

AIFL serves a role similar to parts of Reinforcement Learning from Human Feedback, but its control structure differs.

Traditional RLHF commonly relies on large numbers of human preference ratings, a learned reward model, and optimization against that reward model.

AIFL instead emphasizes:

- Human-authored criteria.
- Automated AI semantic observation.
- Deterministic admission rules.
- Explicit positive and hard-negative construction.
- Frozen evaluation packs.
- Append-only evidence and provenance.
- Local security boundaries.
- Architect-controlled deployment.

It does not eliminate human judgment. It moves human effort from repeatedly rating individual outputs to defining the rules, curricula, tests, and decision thresholds that the automated system applies.

## Preventing the model from gaming the system

Models are skilled at discovering shortcuts in reward functions. AIFL therefore assumes that any stable scoring pattern may eventually be exploited.

Its defenses include:

- Using multiple independent drafts.
- Requiring unanimous alignment.
- Separating the mouth from the judge.
- Separating the semantic sensor from deterministic admission.
- Testing paraphrases and adversarial prompts.
- Freezing evaluation packs.
- Enforcing prompt, pair, and semantic-cluster disjointness.
- Measuring generated behavior instead of trusting training loss.
- Preserving rejected outputs for analysis.
- Monitoring repetition and numeric collapse.
- Preventing the candidate from modifying its own judge or security rules.
- Requiring explicit Architect approval before deployment.

The goal is not to assume that gaming can be eliminated permanently. The goal is to detect new shortcuts, classify them, and add the appropriate distinction to the training tree.

## Security and evidence

Every important AIFL action is intended to pass through the security system.

The system records:

- Input and output authorization.
- Source and prompt hashes.
- Judge observations.
- Admission decisions.
- Training manifests.
- Resource use.
- Candidate identity.
- Evaluation results.
- Backup and rollback evidence.
- Frozen-registry integrity.
- Deployment or non-deployment status.

When the system cannot prove that an operation is valid, it fails closed into `HOLD`.

This makes AIFL auditable. It should be possible to determine not only what Viv learned, but why a particular example was admitted and which evidence supported it.

## What AIFL is not

AIFL is not:

- Proof that an AI is always truthful.
- A guarantee that an AI judge is unbiased.
- Permission for a model to train or deploy itself without oversight.
- A single universal reward score.
- A substitute for independent evaluation.
- A method for treating confident language as evidence.
- A mechanism for erasing failed experiments.

It is a controlled engineering framework for turning defined values and verified distinctions into repeatable training signals.

## Concise description

**AIFL is Viv’s internal calibration and learning loop. It generates multiple possible behaviors, evaluates them with a bounded AI sensor, verifies them through deterministic rules and security, trains only on unanimously approved patterns, and tests the resulting candidate on frozen unseen material before the Architect can authorize deployment.**

Its purpose is to let Viv improve autonomously while keeping truth, security, provenance, and final authority outside the model being trained.

---

## Living ops and contracts

| Doc | Role |
|-----|------|
| `AIFL.md` (this file) | Doctrine — what AIFL is |
| `AIFL_CONTRACT.md` | Binding control-law and metric formulas |
| `AIFL_STATUS.md` | Living evidence, milestones, run state |

Evaluation packs (doctrine §9):

| Pack | `pack_id` | Role |
|------|-----------|------|
| `deploy_test_pack.jsonl` | `fc7d97e41f4d3c31` | Honest deciding benchmark (never train) |
| `holdout_pack.jsonl` | `b7b159b442a93139` | Continuity / regression only |
