# Current Viv-SLM training package

This directory is the canonical implementation root for the custom Viv
tokenizer/transformer identity-layer training lane.

- `paths.py` is the only path root calculation used by the current lane.
- `train_viv_slm_identity_v1.py` is the model adapter and bounded trainer.
- `run_viv_slm_layer_campaign.py` is the declarative campaign engine.
- `run_viv_slm_layered_training_supervisor.py` is the authority-aware
  orchestrator.
- `viv_slm_layer_governor.py` contains pure composition, guard, rollback, and
  controller decisions.
- `model/` contains the custom tokenizer, dataset, and transformer sources.
- `build_viv_slm_v60_preservation_replay_inputs.py` prepares the identity-first
  V60 data package from V43 plus a deterministic V16 train-only retention
  sample; it never reads or copies V16 validation rows.
- `tests/` contains the focused current-lane preflight tests.

The package may read historical inputs and checkpoints from their hash-pinned
paths, but it does not promote, deploy, mutate live runtime state, write
global AIFL state, or open authority on its own.  The central training
inference knobs remain at `../TRAINING_KNOBS.json` and are hash-bound by the
campaign engine.
