# Week1 Mouth-Alignment Local Scaffold

This directory provides a local-first Week 1 scaffold for mouth-alignment training support with auditable artifacts and no cloud dependencies.

## Layout

- `dvc.yaml`: local pipeline stages (`prepare -> align -> validate -> train_adapter -> eval`)
- `schema/alignment_manifest.schema.json`: schema contract for aligned labels
- `scripts/alignment_manifest_validator.py`: schema validator for alignment manifests
- `great_expectations/expectations/aligned_speech_labels_suite.json`: expectation suite for aligned labels
- `data/raw_samples.jsonl`: local sample input to run the scaffold offline

## Local Commands (exact)

From `L:/Continue/Viv/foundation/tools/week1`:

```powershell
L:/Continue/.venv/Scripts/python.exe scripts/prepare_data.py --input data/raw_samples.jsonl --output artifacts/week1/prepared/prepared_samples.json
L:/Continue/.venv/Scripts/python.exe scripts/align_labels.py --input artifacts/week1/prepared/prepared_samples.json --output artifacts/week1/aligned/alignment_manifest.json
L:/Continue/.venv/Scripts/python.exe scripts/validate_alignment.py --manifest artifacts/week1/aligned/alignment_manifest.json --schema schema/alignment_manifest.schema.json --suite great_expectations/expectations/aligned_speech_labels_suite.json --report artifacts/week1/validation/validation_report.json
L:/Continue/.venv/Scripts/python.exe scripts/train_adapter.py --manifest artifacts/week1/aligned/alignment_manifest.json --validation_report artifacts/week1/validation/validation_report.json --output artifacts/week1/model/adapter_model.json
L:/Continue/.venv/Scripts/python.exe scripts/eval_adapter.py --manifest artifacts/week1/aligned/alignment_manifest.json --model artifacts/week1/model/adapter_model.json --output artifacts/week1/eval/eval_report.json
```

If DVC is available locally, run the whole pipeline:

```powershell
dvc repro
```

## Lightweight Offline Checks

```powershell
L:/Continue/.venv/Scripts/python.exe -m py_compile scripts/*.py
L:/Continue/.venv/Scripts/python.exe scripts/alignment_manifest_validator.py --help
L:/Continue/.venv/Scripts/python.exe scripts/validate_alignment.py --help
```
