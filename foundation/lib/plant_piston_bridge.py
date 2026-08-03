"""Bridge plant stability captures into AIOS piston / supervisor artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.piston_engine import SUPERVISOR_PATH
from lib.stability_capture import CaptureVerdict, validate_summary

PLANT_ARTIFACTS = AUTO_ARTIFACTS / "plant"
LAST_CAPTURE_PATH = PLANT_ARTIFACTS / "last_stability_capture.json"
CAPTURE_INDEX_PATH = PLANT_ARTIFACTS / "capture_index.jsonl"


def publish_capture(summary: dict[str, Any], verdict: CaptureVerdict) -> Path:
    """Write capture verdict + summary refs for piston layer and automation spine."""
    PLANT_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict.to_dict(),
        "summary": summary,
        "piston_inputs": {
            "pair": summary.get("pair"),
            "a_label": "cpu_package_c",
            "b_label": "coolant_c" if summary.get("pair") == "cpu_coolant" else summary.get("pair"),
            "rle_min": summary.get("rle_min"),
            "s_n_mean": summary.get("s_n_mean"),
            "early_warning_t_s": summary.get("early_warning_t_s"),
        },
    }
    LAST_CAPTURE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    line = json.dumps(
        {
            "ts": payload["published_at"],
            "verdict": verdict.verdict,
            "csv": verdict.csv_path,
            "stress": verdict.stress,
            "n_logged": verdict.n_logged,
            "cpu_load_max_pct": verdict.cpu_load_max_pct,
        }
    )
    with CAPTURE_INDEX_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    _patch_supervisor(payload)
    return LAST_CAPTURE_PATH


def _patch_supervisor(payload: dict[str, Any]) -> None:
    if not SUPERVISOR_PATH.is_file():
        return
    try:
        sup = json.loads(SUPERVISOR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    v = payload["verdict"]
    sup["plant_last_capture_verdict"] = v["verdict"]
    sup["plant_last_capture_ts"] = payload["published_at"]
    sup["plant_last_capture_csv"] = v["csv_path"]
    sup["plant_cpu_load_max_pct"] = v.get("cpu_load_max_pct")
    sup["plant_stability_rle_min"] = payload.get("summary", {}).get("rle_min")
    sup["plant_stability_s_n_mean"] = payload.get("summary", {}).get("s_n_mean")
    SUPERVISOR_PATH.write_text(json.dumps(sup, indent=2), encoding="utf-8")


def finalize_from_summary_path(summary_path: Path) -> CaptureVerdict:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    verdict = validate_summary(summary, summary_path=summary_path)
    summary["capture_verdict"] = verdict.verdict
    summary["capture_reasons"] = verdict.reasons
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    publish_capture(summary, verdict)
    return verdict
