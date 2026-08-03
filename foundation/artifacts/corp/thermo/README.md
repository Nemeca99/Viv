# Thermo guide corpus (plant-local)

Bounded facts only — what Viv needs to **guide** PRT choices on a living PC plant.

Not a Wikipedia dump. No general encyclopedia training here.

## Contents

- `guide_facts.jsonl` — curated stems + correct answers + distractors
- Built gold: `artifacts/models/thermo_choice_gold.jsonl` (via `lib/prt_thermo_guide.py`)
- Hardware compare-against: `artifacts/corp/hardware/` (merged into same gold file)

## Mix policy

Fold a **small** thermo + hardware MC slice into PRT LoRA builds
(`thermo_choice_gold` / `hardware_choice_gold`). Must not drown PHYSICS / STRUCTURE rows.
