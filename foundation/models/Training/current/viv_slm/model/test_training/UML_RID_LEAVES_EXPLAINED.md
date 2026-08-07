# UML Nested PEMDAS leaves for RID (plain-language)

This explains UML itself and the two UML numbers that feed RID: **x_in** and **x_out**.
They are continuous health values in **[0, 1]** (not binary).
**1.0** = healthy/full structure signal. **0.0** = empty/dead/no structure.

## What UML is (operator design)

**UML = Universal Mathematical Language** and **Universal Machine Language** at the same time
(not diagram “UML”).

- **Machine language:** indexed tokens / character address space the computer addresses.  
- **Mathematical language:** Nested-PEMDAS equations the computer builds, computes in, and codes in.

See also: `foundation/docs/UML_DUAL_LANGUAGE_V1.md`.

Core idea:

1. **Each token/character is defined mathematically** and can be **indexed**.
2. The system **computes in math**, not in natural language first.
3. UML **encodes text into math** for train/think/speak, then **decodes math back into words** deterministically.

### Training / compute objective (binding)

The plant must **learn to build UML math** that:

1. **forms responses** (spoken/written answer = decode of that math), and  
2. **is what it computes in** (internal work = equation structure, not English drafting).

Not: generate language then sprinkle math on top.  
Yes: construct Nested-PEMDAS / indexed equations → compute/verify → decode to words when needed.

```
goal/state  →  build UML math  →  compute/verify  →  decode to response words
```

### Enigma / cryptography mental model

Think **Enigma-style machinery**, not a brain writing English.

- **Encode:** plaintext (words) → cipher domain (UML math equations), via deterministic machine settings (token index, Nested PEMDAS, canonical = most efficient form).
- **Operate:** the computer works **in the cipher/math domain** (build equations, verify, control with PID/RID).
- **Decode:** math → words again, same machine path reversed (1:1 if the equation form is kept).

Same concept as classical cryptography transforms: message in → machine → transformed form → reverse machine → message out.  
Here the “ciphertext” is **UML math for computing**, not secrecy theater — though the structure is the same kind of deterministic encode/decode engine.

```
words  --encode-->  UML math  --compute-->  UML math  --decode-->  words
         (machine)              (computer)              (machine)
```

### UML as a coding language (binding)

UML is not only an encoding for speech. It is also a **coding language you are building**.

Implementation stack for AIOS:

- **Python** — tooling, training, adapters, plant scripts  
- **Rust** — authority, gates, performance-critical runtime  
- **UML** — math/compute/coding surface the computer builds and (as it matures) executes  

So: train the plant to **write UML** the way one writes code — structured, indexed, Nested-PEMDAS, canonical = most efficient — then decode to words when a human-facing response is needed, or keep it as code when the machine is computing.

### Concrete example (A = 1)

Suppose character **A** indexes to value **1**.

Then all of these are valid math encodings of A, because they evaluate to 1:

- `0+1`
- `1*1`
- `1/1`
- `2-1`
- (and many more Nested-PEMDAS forms)

So the plant can generate / train on **equations that equal the token’s value**, not on “English thinking.”

Flow:

```
words/sentence  →  encode  →  math equation(s) indexed to tokens
math equation   →  decode  →  words/sentence  (1:1 reverse of the chosen form)
```

**Important computer rule for 1:1 reverse:**  
Many equations share the same value (`… = 1 = A`).  
If you only keep the number `1`, you cannot uniquely reverse which equation was spoken.  
So UML must carry the **equation form** for lossless decode — evaluation alone is many→one; form↔text is the 1:1 map.

**Canonical form (binding):** among all valid equations that equal a token’s value, the **canonical** form is the **most efficient form needed to add to the equation** — lowest Nested-PEMDAS / structural cost (see `uml_cost` / `uml_token_economics`), not the longest, prettiest, or most verbose. Prefer that form when encoding for train/speak unless a non-canonical equivalent is explicitly required.

**Generation-time pressure:** `uml_route_governor.decide_route` turns that offline rule into an active gate — reject invalid routes, confirm the fixed answer, keep the cheapest valid path (`pressure_weights` ready for later sampling/logit bias).

```
indexed math equation form  ←→  token/character id  ←→  spoken/written words
         ↑                              ↑
   Nested PEMDAS structure         deterministic map
   (canonical = most efficient)
```

Related foundation pieces:

- Character address space / index: `foundation/lib/uml_character_tokenizer.py`
- Math calculator / Nested PEMDAS trees: `foundation/lib/uml_engine.py`
- Token cost equations: `foundation/lib/uml_token_economics.py`

The per-token equation registry (index → canonical + allowed equivalent eqs → word surface)
for sandbox96 is live: `foundation/lib/uml_equation_registry.py` +
`foundation/lib/data/uml_registry_v1_sandbox96.json`.

## Nested PEMDAS

When UML looks at an expression like `(2+3)*4`, it builds a **tree**:

- leaves = numbers / atoms
- operators = `+`, `*`, …
- nesting = how deep the form goes

Same text → same tree → same metrics. That is Nested PEMDAS determinism.

## RID big picture

```
input math/structure   →  x_in  ─┐
output math/structure  →  x_out ─┼─→ RID(x_in, x_out, p) = x_in * x_out * p
PID (internal)         →  p     ─┘
```

RID multiplies three continuous [0,1] health values.
Low any channel → product soft-falls toward 0 (less “alive”).
High all channels → healthier stability score.

## x_in — input structure depth

- Raw: **max depth** of the Nested-PEMDAS / AST tree.
- Normalize: `x_in = clamp(max_depth / 12, 0, 1)`.
- Plain words: how deep is the **input** math form?

## x_out — output math structure amount

- Raw: **symbolic_cost** = AST node count (structural steps, not GPU time).
- Normalize: `x_out = clamp(symbolic_cost / 10, 0, 1)`.
- Plain words: how much **structured math** is on the **output** side?

### Why two different UML eyes?

- **x_in** watches nesting shape (depth of the form).
- **x_out** watches how much math structure was produced (node count).

Same law (continuous [0,1]), different sensors. Tunable later without changing
`RID = a * b * c`.

## Examples (approximate)

| Expression | depth | nodes | x_in | x_out |
|---|---|---|---|---|
| `2+3` | 2 | 3 | 0.167 | 0.30 |
| `(2+3)*4` | 3 | 5 | 0.250 | 0.50 |
| `[+ 2 3]` | 2 | 2 | 0.167 | 0.20 |

Exact values: `uml_nested_pemdas_leaves(expr)` in `rid_pid.py`.

## How this joins PID and training

1. **Warm-up:** first metrics call wakes PID once from residual so `p` is not stuck dead.
2. Each train step: loss → PID (P,I,D) → **u** and **p**.
3. **S_RID = x_in * x_out * p** scales adapter gain (stability).
4. **u** scales optimizer LR (coupled): fighting hard → lower LR; settled → nearer normal.
   Continuous band (~0.55–1.15), never binary on/off.

## What “thinks in math, speaks in words” means for Viv

This is a **COMPUTER**, not a language generator and not a brain.

- Primary mode: **computation** (indexed math, Nested PEMDAS structure, PID/RID control).
- Words/speech: a **deterministic render/surface** of that computation — not “thinking in language.”
- Do not treat Viv as an LLM-style language-brain that invents language the way humans do.
- Prefer computer / control / telemetry language over anthropomorphic framing.

- Internal control / structure / indexing: **math (UML)**.
- Mouth / characters people read: **deterministic render of that math**.
- RID does not replace UML; RID **scores stability** of UML input/output + PID health
  while the plant learns.

Next build step when you want it: a per-token equation registry
(index → Nested-PEMDAS equation → word surface) fully wired into the sandbox
train path, not only the Unicode id map.
