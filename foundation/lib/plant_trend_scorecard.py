"""Plant trend scorecard — last-N Master S_n / dormancy / load from plant artifacts.

Tranche 1 item 5: reads foundation/artifacts/auto/plant/ (+ linked RID CSVs),
computes a simple trend, writes evidence under artifacts/auto/. Never fakes PASS
when sample count is below threshold (INCONCLUSIVE).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.dormancy_config import load_threshold  # noqa: E402
from lib.paths import AUTO_ARTIFACTS, RID_ARTIFACTS, SANDBOX_ROOT  # noqa: E402
from lib.plant_piston_bridge import CAPTURE_INDEX_PATH, LAST_CAPTURE_PATH, PLANT_ARTIFACTS  # noqa: E402

MODULE_ID = "plant_trend"
DEFAULT_N = 30
MIN_SAMPLES_PASS = 5

EVIDENCE_PATH = AUTO_ARTIFACTS / "plant" / "plant_trend_scorecard.json"
EVIDENCE_LATEST = AUTO_ARTIFACTS / "plant_trend_scorecard_latest.json"
PLANT_BRIEF = SANDBOX_ROOT / "work" / "plant_brief.txt"

_SN_RE = re.compile(r"S_n=([0-9.]+)", re.IGNORECASE)
_STATUS_RE = re.compile(r"status=([A-Za-z_]+)")
_RSR_RE = re.compile(r"RSR=([0-9.]+)")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _resolve_csv(raw: str | None) -> Path | None:
    if not raw:
        return None
    p = Path(str(raw))
    if p.is_file():
        return p
    # Tolerate drive-letter / slash variants under RID artifacts
    name = p.name
    cand = RID_ARTIFACTS / name
    return cand if cand.is_file() else None


def _csv_from_last_capture() -> Path | None:
    if not LAST_CAPTURE_PATH.is_file():
        return None
    try:
        data = json.loads(LAST_CAPTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    verdict = data.get("verdict") if isinstance(data.get("verdict"), dict) else {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    for key in ("csv_path", "csv"):
        p = _resolve_csv(verdict.get(key) or summary.get(key))
        if p is not None:
            return p
    return None


def _csv_from_index() -> Path | None:
    if not CAPTURE_INDEX_PATH.is_file():
        return None
    rows: list[dict[str, Any]] = []
    for line in CAPTURE_INDEX_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    # Prefer most recent PASS / PASS_FLAT with a readable CSV
    for row in reversed(rows):
        v = str(row.get("verdict") or "")
        if v not in {"PASS", "PASS_FLAT"}:
            continue
        p = _resolve_csv(row.get("csv"))
        if p is not None:
            return p
    for row in reversed(rows):
        p = _resolve_csv(row.get("csv"))
        if p is not None:
            return p
    return None


def _samples_from_csv(path: Path, n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sn = _f(row.get("master_s_n") or row.get("s_n"))
            if sn is None:
                continue
            status = str(row.get("master_status") or row.get("status") or "").upper() or None
            load = _f(row.get("cpu_load_pct") or row.get("cpu_load"))
            out.append(
                {
                    "ts": row.get("timestamp") or row.get("t_s"),
                    "s_n": sn,
                    "status": status,
                    "dormant": status == "DORMANT" if status else None,
                    "load_pct": load,
                    "source": "csv",
                    "path": str(path).replace("\\", "/"),
                }
            )
    if len(out) > n:
        out = out[-n:]
    return out


def _samples_from_plant_brief(n: int) -> list[dict[str, Any]]:
    if not PLANT_BRIEF.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in PLANT_BRIEF.read_text(encoding="utf-8").splitlines():
        m = _SN_RE.search(line)
        if not m:
            continue
        sn = float(m.group(1))
        st_m = _STATUS_RE.search(line)
        status = (st_m.group(1).upper() if st_m else None)
        ts = None
        if line.startswith("[") and "]" in line:
            ts = line[1 : line.index("]")]
        out.append(
            {
                "ts": ts,
                "s_n": sn,
                "status": status,
                "dormant": status == "DORMANT" if status else (sn < load_threshold()),
                "load_pct": None,
                "source": "plant_brief",
                "path": str(PLANT_BRIEF).replace("\\", "/"),
            }
        )
    if len(out) > n:
        out = out[-n:]
    return out


def _samples_from_index(n: int) -> list[dict[str, Any]]:
    if not CAPTURE_INDEX_PATH.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in CAPTURE_INDEX_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        load = _f(row.get("cpu_load_max_pct"))
        # Index rows lack per-tick S_n; keep load/verdict as weak samples only
        out.append(
            {
                "ts": row.get("ts"),
                "s_n": None,
                "status": str(row.get("verdict") or ""),
                "dormant": None,
                "load_pct": load,
                "source": "capture_index",
                "path": str(CAPTURE_INDEX_PATH).replace("\\", "/"),
                "n_logged": row.get("n_logged"),
                "verdict": row.get("verdict"),
            }
        )
    if len(out) > n:
        out = out[-n:]
    return out


def collect_samples(n: int = DEFAULT_N) -> dict[str, Any]:
    """Gather last-N plant samples. Prefer RID CSV, then plant_brief, then index."""
    n = max(1, int(n))
    sources_tried: list[str] = []
    samples: list[dict[str, Any]] = []
    primary = "none"

    csv_path = _csv_from_last_capture() or _csv_from_index()
    if csv_path is not None:
        sources_tried.append(str(csv_path).replace("\\", "/"))
        samples = _samples_from_csv(csv_path, n)
        if samples:
            primary = "csv"

    if len(samples) < MIN_SAMPLES_PASS:
        sources_tried.append(str(PLANT_BRIEF).replace("\\", "/"))
        brief = _samples_from_plant_brief(n)
        if brief:
            # Prefer brief S_n series when CSV thin; else merge load-only gaps
            if primary != "csv" or len(samples) < MIN_SAMPLES_PASS:
                samples = brief
                primary = "plant_brief"

    index_rows = _samples_from_index(n)
    if CAPTURE_INDEX_PATH.is_file():
        sources_tried.append(str(CAPTURE_INDEX_PATH).replace("\\", "/"))

    plant_present = PLANT_ARTIFACTS.is_dir() and (
        LAST_CAPTURE_PATH.is_file() or CAPTURE_INDEX_PATH.is_file() or bool(samples)
    )

    sn_samples = [s for s in samples if s.get("s_n") is not None]
    return {
        "n_requested": n,
        "n_samples": len(sn_samples) if sn_samples else len(samples),
        "n_s_n": len(sn_samples),
        "primary_source": primary,
        "sources_tried": sources_tried,
        "plant_present": plant_present,
        "csv_path": str(csv_path).replace("\\", "/") if csv_path else None,
        "index_rows": len(index_rows),
        "samples": sn_samples if sn_samples else samples,
        "index_tail": index_rows[-min(5, len(index_rows)) :] if index_rows else [],
    }


def _series_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    first, last = values[0], values[-1]
    mean = sum(values) / len(values)
    # Simple end-minus-start slope proxy over sample index
    slope = (last - first) / max(1, len(values) - 1)
    return {
        "n": len(values),
        "first": round(first, 6),
        "last": round(last, 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(mean, 6),
        "delta": round(last - first, 6),
        "slope_per_sample": round(slope, 8),
    }


def compute_trend(collected: dict[str, Any]) -> dict[str, Any]:
    """Compute S_n / dormancy / load trend stats from collected samples."""
    samples = list(collected.get("samples") or [])
    thr = load_threshold()
    sns = [float(s["s_n"]) for s in samples if s.get("s_n") is not None]
    loads = [float(s["load_pct"]) for s in samples if s.get("load_pct") is not None]
    dorm_flags: list[bool] = []
    for s in samples:
        if s.get("dormant") is not None:
            dorm_flags.append(bool(s["dormant"]))
        elif s.get("s_n") is not None:
            dorm_flags.append(float(s["s_n"]) < thr)

    dorm_rate = (sum(1 for d in dorm_flags if d) / len(dorm_flags)) if dorm_flags else None
    return {
        "dormancy_threshold": thr,
        "s_n": _series_stats(sns),
        "load_pct": _series_stats(loads),
        "dormancy": {
            "n": len(dorm_flags),
            "dormant_count": sum(1 for d in dorm_flags if d) if dorm_flags else 0,
            "active_count": sum(1 for d in dorm_flags if not d) if dorm_flags else 0,
            "dormant_rate": round(dorm_rate, 6) if dorm_rate is not None else None,
        },
    }


def _verdict(collected: dict[str, Any], trend: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    n_sn = int(collected.get("n_s_n") or 0)
    plant_present = bool(collected.get("plant_present"))

    if not plant_present and n_sn == 0:
        return "INCONCLUSIVE", ["no_plant_artifacts"]

    if n_sn < MIN_SAMPLES_PASS:
        reasons.append(f"low_s_n_samples:{n_sn}<{MIN_SAMPLES_PASS}")
        return "INCONCLUSIVE", reasons

    sn = trend.get("s_n") or {}
    if int(sn.get("n") or 0) < MIN_SAMPLES_PASS:
        reasons.append("trend_s_n_empty")
        return "INCONCLUSIVE", reasons

    reasons.append(f"samples_ok:{n_sn}")
    reasons.append(f"source:{collected.get('primary_source')}")
    return "PASS", reasons


def write_evidence(report: dict[str, Any]) -> dict[str, str]:
    """Persist scorecard JSON under artifacts/auto/ (plant/ + latest pointer)."""
    PLANT_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    AUTO_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    body = json.dumps(report, indent=2, default=str)
    EVIDENCE_PATH.write_text(body, encoding="utf-8")
    EVIDENCE_LATEST.write_text(body, encoding="utf-8")
    return {
        "evidence": str(EVIDENCE_PATH).replace("\\", "/"),
        "latest": str(EVIDENCE_LATEST).replace("\\", "/"),
    }


def scorecard(*, n: int = DEFAULT_N, persist: bool = True) -> dict[str, Any]:
    """Build plant trend scorecard. Verdict PASS only with enough real S_n samples."""
    collected = collect_samples(n=n)
    trend = compute_trend(collected)
    verdict, reasons = _verdict(collected, trend)
    # Slim samples in evidence (keep last 8 for audit, not full N)
    slim = list(collected.get("samples") or [])[-8:]
    report: dict[str, Any] = {
        "module": MODULE_ID,
        "at": _utc(),
        "verdict": verdict,
        "ok": verdict == "PASS",
        "reasons": reasons,
        "min_samples_pass": MIN_SAMPLES_PASS,
        "n_requested": collected.get("n_requested"),
        "n_s_n": collected.get("n_s_n"),
        "n_samples": collected.get("n_samples"),
        "primary_source": collected.get("primary_source"),
        "plant_present": collected.get("plant_present"),
        "csv_path": collected.get("csv_path"),
        "sources_tried": collected.get("sources_tried"),
        "index_rows": collected.get("index_rows"),
        "trend": trend,
        "samples_tail": slim,
        "index_tail": collected.get("index_tail"),
    }
    if persist:
        paths = write_evidence(report)
        report["evidence_path"] = paths["evidence"]
        report["evidence_latest"] = paths["latest"]
    return report


def run_smoke(*, n: int = DEFAULT_N) -> dict[str, Any]:
    """Smoke: real plant data → PASS; low samples → INCONCLUSIVE (never fake PASS)."""
    report = scorecard(n=n, persist=True)
    return {
        "ok": bool(report.get("ok")),
        "verdict": report.get("verdict"),
        "evidence": report,
    }


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    # Exit 0 for PASS or honest INCONCLUSIVE; 1 only on unexpected hard fail
    verdict = str(result.get("verdict") or "")
    if verdict == "PASS":
        raise SystemExit(0)
    if verdict == "INCONCLUSIVE":
        raise SystemExit(0)
    raise SystemExit(1)
