"""Selftest for backup_core automation exclusions and uml_lane planning."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.aios_adapter_backup import plan_automation  # noqa: E402
from lib.backup_core import (  # noqa: E402
    WEIGHT_PACK_SUFFIXES,
    _expand_files,
    _weight_pack_exclusion_reason,
    automation_snapshot_roots,
    uml_evidence_snapshot_roots,
)


def main() -> int:
    thesis = (
        FOUNDATION
        / "models"
        / "Training"
        / "current"
        / "viv_slm"
        / "model"
        / "test_training"
        / "UML_TRAINING_THESIS.md"
    )
    evidence = FOUNDATION / "models" / "Training" / "evidence"
    assert thesis.is_file(), thesis
    assert evidence.is_dir(), evidence

    gpu_dummy = FOUNDATION / "models" / "gpu" / "_automation_deny_probe.gguf"
    assert _weight_pack_exclusion_reason(gpu_dummy) == "excluded_models_gpu"
    assert _weight_pack_exclusion_reason(Path("L:/Continue/Viv/foundation/x.pt")) == "excluded_weight_suffix:.pt"
    assert (
        _weight_pack_exclusion_reason(
            FOUNDATION
            / "models"
            / "Training"
            / "current"
            / "viv_slm"
            / "model"
            / "test_training"
            / "runs"
            / "step.pt"
        )
        in {"excluded_weight_suffix:.pt", "excluded_test_training_runs"}
    )

    probe_root = FOUNDATION.parent / "sandbox" / "backup_automation_selftest"
    try:
        if probe_root.exists():
            for child in probe_root.rglob("*"):
                if child.is_file():
                    child.unlink()
        probe_root.mkdir(parents=True, exist_ok=True)
        keep = probe_root / "keep.txt"
        keep.write_text("ok", encoding="utf-8")
        weight = probe_root / "dump.pt"
        weight.write_bytes(b"weight")
        files, skipped = _expand_files([probe_root], deny_weight_packs=True)
        assert keep.resolve() in {path.resolve() for path in files}, files
        assert any(row["reason"] == "excluded_weight_suffix:.pt" for row in skipped), skipped
        assert not any(path.suffix.lower() in WEIGHT_PACK_SUFFIXES for path in files), files
    finally:
        if probe_root.exists():
            for child in sorted(probe_root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            probe_root.rmdir()

    uml_roots = uml_evidence_snapshot_roots()
    assert any("UML_TRAINING_THESIS.md" in str(path) for path in uml_roots), uml_roots
    assert any("Training" in path.parts and path.name == "evidence" for path in uml_roots), uml_roots

    safe_roots = automation_snapshot_roots(profile="safe")
    assert not any("openaster_training_tree" in str(path).replace("\\", "/") for path in safe_roots), safe_roots

    plan = plan_automation(trigger="selftest", profile="uml_lane", catalog_models=False)
    assert plan["ok"], plan
    assert plan["deny_weight_packs"] is True, plan
    assert plan["catalog_models"] is False, plan
    assert plan["aios_runtime_started"] is False, plan
    assert plan["file_count"] >= 1, plan
    assert plan["execution_approved"] is False, plan
    # No GPU / weight packs in the planned copy set.
    for reason in (plan.get("exclusion_counts") or {}):
        assert reason.startswith("excluded_") or reason == "missing", reason
    report = {
        "ok": True,
        "uml_lane_files": plan["file_count"],
        "uml_lane_bytes": plan["logical_bytes"],
        "exclusion_counts": plan.get("exclusion_counts"),
        "deny_weight_packs": True,
        "catalog_models": False,
        "aios_runtime_started": False,
        "weight_suffixes": sorted(WEIGHT_PACK_SUFFIXES),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
