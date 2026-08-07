# Privacy Core v1

The existing `cpu_privacy_policy.py` already provides a fail-closed consent
gate: conversation learning is allowed by default, while passive, behavior,
and predictive learning require explicit full-auto consent.

This reconciliation adds the missing manual-defined planning surface in
`privacy_core.py`: normalized mode/retention/transparency settings, reversible
mode-change proposals, bounded retention plans, category-only transparency
reports, and explicit export/delete intents. The adapter composes these plans
without changing configuration or data.

Full-auto remains denied unless both consent flags and the explicit consent
argument are present. No file reads/writes, deletion, export, monitoring,
cloud access, or model authority is introduced by this slice.
