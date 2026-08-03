# Viv SPRT v0 — Semantic Predictive Reasoning Training (contract)

**Status:** DESIGN ONLY — do not run until PRT speak forecasts are mostly REWARD.  
**Meaning here:** Aria-style **Semantic** PRT (KEEP / REVISE / DISCARD on knowledge), not “dump harmful acts into base.”  
**Python:** `L:/Continue/.venv/Scripts/python.exe`

Related: `FSAA/UML/docs/PRT_Predictive_Reasoning_Training.md` Phase 4, `aria_sprt.py`, `ARCHITECT_TRIAD_THEORY.md`.

---

## Precondition (graduation soft bar)

Before enabling SPRT collect:

- Recent PRT speak cycles: ≥60% **REWARD** over last N≥20 speak acts (configurable)  
- Unified adapter continued under PRT without unbroken PUNISH streak  
- Security membrane armed; auto-speak still gated unless Architect opts in  

If bar fails → keep PRT `apply`; do not open corpus rewrite.

---

## Scope v0 (tiny, local)

| In | Out |
| -- | --- |
| `artifacts/carma/live/*.txt` chunks (and small tagged notes) | Full Wikipedia dump |
| Explicit `artifacts/sprt/inbox.jsonl` curated by Architect | Silent mass delete of CARMA |
| Read-only audit report | Auto-apply DISCARD to disk without confirm |

---

## Loop

1. CPU samples Master S_n; if dormant → observe-only, no SPRT GPU call  
2. CPU feeds one knowledge chunk + plant context into **allowlisted** GPU prompt: judge KEEP|REVISE|DISCARD + short reason  
3. Security OUT on reason text  
4. Append judgment to `artifacts/sprt/judgments.jsonl`  
5. Delta report: `artifacts/sprt/delta_latest.json` (counts only)  
6. **Promote:** human/Architect reviews; optional copy REVISE text to inbox — never silent wipe  

Shadow Predictive (train on labeled *unstable speech*) stays a **separate** later lane under allowlist; not this file.

---

## CPU owns stamp

GPU proposes KEEP/REVISE/DISCARD. CPU may veto DISCARD if chunk is `[live][cpu]` foundation provenance or Law-protected. Architect override always wins.

---

## CLI sketch (future)

```text
prt_main.py   # physics PRT — already exists
sprt_main.py status | audit --limit 20 | report
```

No `sprt_main.py` until precondition met + Architect says go.

---

## Honesty

SPRT without PRT sense is just another LLM editing notes. Plant first; semantic audit second.
