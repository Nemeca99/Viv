# Viv CPU RAG Core v1

## Purpose

`foundation/lib/rag_core.py` is the CPU-owned retrieval facade for the AIOS
rebuild. It joins the useful behavior found in the `rag_core` sources under
`F:/AIOS_Clean` and `D:/LocalAi/AIOS_V1` without copying their mutable index or
filesystem layout into the active foundation.

The RAG core supplies evidence to the CPU reasoning pipeline. It does not
decide unsupported facts, train a model, write a persistent semantic index, or
grant authority to a GPU/API renderer.

## Routes

| Route | Source | Boundary |
|---|---|---|
| `manual` | `ManualOracle` over `AIOS_ALPHA_MANUAL.md` | Hash-verified section lookup; abstains on source drift |
| `adapter` | `aios_adapter_knowledge` | Bounded keyword/index retrieval with source scope |
| `staged_semantic` | `knowledge_staged_adapter` | Explicit staged vectors; source files are re-hashed before admission |
| `wikipedia_local` | Read-only SQLite article index | Bounded article lookup with optional redirect resolution |
| `auto` | Adapter, then local Wikipedia fallback | Preserves the existing CPU fallback order |

Every admitted hit must contain a readable source reference and a SHA-256
binding. Citations expose a logical `source_token`, root, kind, claim, and
source hash; physical source paths are not passed through the renderer packet.
Missing hashes, malformed hits, source drift, embedding failures, and
conflicts fail closed as `INCONCLUSIVE`, `ABSTAIN`, or `CONFLICT`.

## CPU-to-mouth boundary

`foundation/lib/cpu_reasoning_pipeline.py` now calls the RAG facade before the
CPU judge and containment stages. The returned packet records:

```text
retrieval evidence -> source citations -> CPU judge -> renderer packet
```

The result explicitly records:

```text
writes_performed=false
persistent_index_written=false
training_authorized=false
llm_authority=false
```

The model can render supplied evidence later, but it cannot create evidence or
change the retrieval decision.

## Verification

Canonical runtime:

```text
L:/Continue/.venv/Scripts/python.exe
```

Focused checks:

```text
L:/Continue/.venv/Scripts/python.exe foundation/scripts/test_rag_core_v1.py
L:/Continue/.venv/Scripts/python.exe foundation/scripts/test_cpu_reasoning_pipeline_v1.py
L:/Continue/.venv/Scripts/python.exe foundation/scripts/test_manual_oracle_v1.py
L:/Continue/.venv/Scripts/python.exe foundation/scripts/test_staged_semantic_adapter_v1.py
```

The v1 slice passed with manual, staged-semantic, and local-Wikipedia retrieval
verified; missing-source-hash rejection verified; and persistent-index and
renderer-authority flags closed. Full foundation preflight after the slice
passed with `1,393` parsed Python files, `1,010` architecture files at `100%`
coverage, `553` boundary modules, zero direct bridge violations, configured
Python suites green, and Rust security green.

## Remaining boundary

The RAG core is a verified CPU slice, not a claim that every semantic runtime
is available. The staged semantic route requires an explicitly compatible local
embedding model. The current Ollama `viv-embed` runtime has not established a
working embedding endpoint, so that route must return `INCONCLUSIVE` when no
compatible local backend is configured. The full corpus remains read-only and
source-faithful; persistent semantic-index admission is still closed.
