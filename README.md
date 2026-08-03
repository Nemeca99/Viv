# Viv

Viv is a local-first AIOS rebuild: a CPU-governed system plane with a
replaceable, GPU-agnostic language-model mouth. The CPU-side contracts,
memory services, evaluators, security membrane, and evidence receipts are
authoritative; the language model is an interchangeable voice/interface.

## Current scope

This repository is an alpha engineering foundation, not a finished autonomous
system. Current work includes:

- three-source rebuild documentation and architecture mapping;
- Python foundation services and a Rust security core;
- bounded semantic retrieval and source-faithful knowledge routing;
- CPU-only decision-economy simulation for `idle`, `action`, and `restore`;
- independent answer verification, adversarial stress tests, and immutable
  evidence receipts.

Training, leases, promotion, deployment, and live-model mutation remain
separately governed. A passing simulator or test does not mean that Viv has
been trained, promoted, deployed, or granted autonomy.

## Repository layout

- `foundation/` — CPU system plane, contracts, scripts, tests, and artifacts.
- `security_core/` — Rust security and containment membrane.
- `memory_core/` — memory and retrieval services.
- `voice_core/` — replaceable mouth/model boundary.
- `COLD_START.md` — current rebuild map and operating boundaries.
- `artifacts/audit/` — human-readable journals and triangulation records.
- `artifacts/auto/` — machine-generated receipts, manifests, and checkpoints.

Historical or inactive source belongs in the separately managed legacy areas;
large Wikipedia datasets and model weights are external inputs and are not
committed to this repository.

## Local validation

Use the canonical Windows environment:

```powershell
& 'L:\Continue\.venv\Scripts\python.exe' foundation/scripts/run_foundation_preflight.py
```

The preflight is evidence collection. It does not authorize training or
deployment.

## Operating principles

1. Preserve live state, frozen incumbents, backups, hashes, and journals.
2. Prefer deterministic CPU-side authority over model claims.
3. Treat unsupported or stale information as unverified rather than inventing.
4. Keep training and deployment authorization explicit and separate.
5. Mark incomplete evidence as `HOLD` or `INCONCLUSIVE`.

## License

Released under the MIT License. See [LICENSE](LICENSE).
