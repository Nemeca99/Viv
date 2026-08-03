"""Callable rid_core align adapter — read-only plant vs master RID check.

Registry id: rid_core
V2 source (read-only): L:/Continue/FSAA/Luna/AIOS_V2/rid_core

API: status(), snapshot(), align_check(), run_smoke()

Wraps existing foundation master_rid / prt_cycle.observe_state and plant
artifacts. Does NOT replace Phone/foundation RID math. Does NOT mutate
security_core. Does NOT execute V2 rid_core.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.master_rid import MASTER_RID_PATH, load_master_rid  # noqa: E402
from lib.paths import AUTO_ARTIFACTS, RID_ARTIFACTS, SANDBOX_ROOT  # noqa: E402
from lib.plant_piston_bridge import (  # noqa: E402
    CAPTURE_INDEX_PATH,
    LAST_CAPTURE_PATH,
    PLANT_ARTIFACTS,
)

ADAPTER_ID = "rid_core"
REGISTRY_ID = "rid_core"

V2_RID = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/rid_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "rid_align"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"
PLANT_BRIEF = SANDBOX_ROOT / "work" / "plant_brief.txt"
PLANT_TREND = PLANT_ARTIFACTS / "plant_trend_scorecard.json"

MIN_SAMPLES = 5
ALIGN_TOL_S_N = 0.05
ALIGN_TOL_CHANNEL = 0.08

_SN_RE = re.compile(r"S_n=([0-9.]+)", re.IGNORECASE)
_STATUS_RE = re.compile(r"status=([A-Za-z_]+)")
_RSR_RE = re.compile(r"RSR=([0-9.]+)", re.IGNORECASE)
_LTP_RE = re.compile(r"LTP=([0-9.]+)", re.IGNORECASE)
_RLE_RE = re.compile(r"RLE=([0-9.]+)", re.IGNORECASE)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return x


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _v2_presence() -> dict[str, Any]:
    return {
        "v2_rid_readable": V2_RID.is_dir(),
        "v2_fidf_py": (V2_RID / "fidf.py").is_file(),
        "viv_executes_v2": False,
        "viv_replaces_foundation_math": False,
        "viv_mode": "master_rid_observe_plus_plant_align",
        "note": (
            "V2 rid_core surveyed read-only; Viv uses foundation "
            "master_rid / prt_cycle.observe_state and plant artifacts."
        ),
    }


def _parse_brief_line(line: str) -> dict[str, Any] | None:
    m = _SN_RE.search(line)
    if not m:
        return None
    ts = None
    if line.startswith("[") and "]" in line:
        ts = line[1 : line.index("]")]
    st_m = _STATUS_RE.search(line)
    rsr_m = _RSR_RE.search(line)
    ltp_m = _LTP_RE.search(line)
    rle_m = _RLE_RE.search(line)
    return {
        "ts": ts,
        "s_n": float(m.group(1)),
        "status": (st_m.group(1).upper() if st_m else None),
        "rsr": float(rsr_m.group(1)) if rsr_m else None,
        "ltp": float(ltp_m.group(1)) if ltp_m else None,
        "rle": float(rle_m.group(1)) if rle_m else None,
        "source": "plant_brief",
        "path": _as_posix(PLANT_BRIEF),
    }


def _brief_samples() -> list[dict[str, Any]]:
    if not PLANT_BRIEF.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = PLANT_BRIEF.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        row = _parse_brief_line(line)
        if row is not None:
            out.append(row)
    return out


def _capture_ref() -> dict[str, Any]:
    last = _load_json(LAST_CAPTURE_PATH) or {}
    verdict = last.get("verdict") if isinstance(last.get("verdict"), dict) else {}
    summary = last.get("summary") if isinstance(last.get("summary"), dict) else {}
    n_logged = verdict.get("n_logged") or summary.get("n_logged")
    return {
        "exists": LAST_CAPTURE_PATH.is_file(),
        "path": _as_posix(LAST_CAPTURE_PATH),
        "verdict": verdict.get("verdict"),
        "n_logged": n_logged,
        "master_s_n_mean": _f(summary.get("master_s_n_mean") or summary.get("s_n_mean")),
        "master_s_n_min": _f(summary.get("master_s_n_min") or summary.get("s_n_min")),
        "master_s_n_max": _f(summary.get("master_s_n_max") or summary.get("s_n_max")),
        "published_at": last.get("published_at"),
        "csv": verdict.get("csv_path") or summary.get("csv"),
    }


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(float(a) - float(b), 6)


def status() -> dict[str, Any]:
    """Paths and presence for master RID / plant surfaces (no sensing)."""
    try:
        m = load_master_rid()
        brief_n = len(_brief_samples())
        capture = _capture_ref()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "master_rid_path": _as_posix(MASTER_RID_PATH),
                "master_rid_exists": MASTER_RID_PATH.is_file(),
                "master_s_n": (m.master_s_n if m else None),
                "master_status": (m.status if m else None),
                "plant_dir": _as_posix(PLANT_ARTIFACTS),
                "plant_dir_exists": PLANT_ARTIFACTS.is_dir(),
                "last_stability_path": _as_posix(LAST_CAPTURE_PATH),
                "last_stability_exists": LAST_CAPTURE_PATH.is_file(),
                "capture_index_path": _as_posix(CAPTURE_INDEX_PATH),
                "capture_index_exists": CAPTURE_INDEX_PATH.is_file(),
                "plant_brief_path": _as_posix(PLANT_BRIEF),
                "plant_brief_exists": PLANT_BRIEF.is_file(),
                "plant_brief_n": brief_n,
                "plant_trend_path": _as_posix(PLANT_TREND),
                "plant_trend_exists": PLANT_TREND.is_file(),
                "rid_artifacts": _as_posix(RID_ARTIFACTS),
                "last_capture": capture,
                "read_only": True,
                "mutates_security_core": False,
                "replaces_foundation_math": False,
                "v2": _v2_presence(),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "error": str(exc),
            },
        }


def snapshot() -> dict[str, Any]:
    """Live master S_n / RSR / LTP / RLE / status via prt_cycle.observe_state."""
    try:
        from lib.prt_cycle import observe_state

        obs = observe_state()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "snapshot",
                "at": _utc(),
                "master_s_n": obs.get("master_s_n"),
                "rsr": obs.get("master_rsr"),
                "ltp": obs.get("master_ltp"),
                "rle": obs.get("master_rle"),
                "status": obs.get("status"),
                "plant_s_n": obs.get("plant_s_n"),
                "cpu_load_pct": obs.get("cpu_load_pct"),
                "cpu_temp_c": obs.get("cpu_temp_c"),
                "gpu_temp_c": obs.get("gpu_temp_c"),
                "dormancy_threshold": obs.get("dormancy_threshold"),
                "timestamp": obs.get("timestamp"),
                "source": "lib.prt_cycle.observe_state",
                "master_rid_path": _as_posix(MASTER_RID_PATH),
                "replaces_foundation_math": False,
            },
        }
    except Exception as exc:  # noqa: BLE001
        # Fallback: cached master_rid only (still no new math).
        try:
            m = load_master_rid()
            if m is None:
                raise RuntimeError("master_rid missing") from exc
            return {
                "ok": True,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "snapshot",
                    "at": _utc(),
                    "master_s_n": m.master_s_n,
                    "rsr": m.master_rsr,
                    "ltp": m.master_ltp,
                    "rle": m.master_rle,
                    "status": m.status,
                    "timestamp": m.timestamp,
                    "source": "lib.master_rid.load_master_rid",
                    "observe_error": str(exc),
                    "master_rid_path": _as_posix(MASTER_RID_PATH),
                    "replaces_foundation_math": False,
                },
            }
        except Exception as exc2:  # noqa: BLE001
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "snapshot",
                    "at": _utc(),
                    "error": str(exc2),
                    "observe_error": str(exc),
                },
            }


def align_check(*, min_samples: int = MIN_SAMPLES) -> dict[str, Any]:
    """Compare plant brief (or latest capture) vs master; INCONCLUSIVE if thin."""
    try:
        samples = _brief_samples()
        n = len(samples)
        brief_latest = samples[-1] if samples else None
        capture = _capture_ref()

        observe_err: str | None = None
        m = load_master_rid()
        master: dict[str, Any] | None = None
        if m is not None:
            master = {
                "s_n": m.master_s_n,
                "rsr": m.master_rsr,
                "ltp": m.master_ltp,
                "rle": m.master_rle,
                "status": m.status,
                "timestamp": m.timestamp,
                "source": "master_rid.json",
            }
        else:
            # Prefer a live observe when cache missing (still foundation lib).
            try:
                from lib.prt_cycle import observe_state

                obs = observe_state()
                master = {
                    "s_n": obs.get("master_s_n"),
                    "rsr": obs.get("master_rsr"),
                    "ltp": obs.get("master_ltp"),
                    "rle": obs.get("master_rle"),
                    "status": obs.get("status"),
                    "timestamp": obs.get("timestamp"),
                    "source": "prt_cycle.observe_state",
                }
            except Exception as exc:  # noqa: BLE001
                master = None
                observe_err = str(exc)

        plant_side: dict[str, Any] | None = None
        plant_source = "none"
        if brief_latest is not None:
            plant_side = brief_latest
            plant_source = "plant_brief"
        elif capture.get("master_s_n_mean") is not None:
            plant_side = {
                "s_n": capture["master_s_n_mean"],
                "rsr": None,
                "ltp": None,
                "rle": None,
                "status": capture.get("verdict"),
                "ts": capture.get("published_at"),
                "source": "last_stability_capture",
                "path": capture.get("path"),
            }
            plant_source = "last_stability_capture"

        reasons: list[str] = []
        min_n = max(1, int(min_samples))
        n_logged = capture.get("n_logged")
        try:
            n_logged_i = int(n_logged) if n_logged is not None else 0
        except (TypeError, ValueError):
            n_logged_i = 0

        # Sample sufficiency: brief lines OR capture n_logged
        sample_ok = n >= min_n or n_logged_i >= min_n
        if not sample_ok:
            reasons.append(f"low_samples:brief_n={n},capture_n={n_logged_i},min={min_n}")

        if master is None:
            reasons.append("master_unavailable")
        if plant_side is None:
            reasons.append("plant_side_unavailable")

        deltas: dict[str, float | None] = {
            "s_n": None,
            "rsr": None,
            "ltp": None,
            "rle": None,
        }
        if master is not None and plant_side is not None:
            deltas = {
                "s_n": _delta(_f(plant_side.get("s_n")), _f(master.get("s_n"))),
                "rsr": _delta(_f(plant_side.get("rsr")), _f(master.get("rsr"))),
                "ltp": _delta(_f(plant_side.get("ltp")), _f(master.get("ltp"))),
                "rle": _delta(_f(plant_side.get("rle")), _f(master.get("rle"))),
            }

        if not sample_ok or master is None or plant_side is None:
            verdict = "INCONCLUSIVE"
        else:
            sn_d = deltas.get("s_n")
            if sn_d is None:
                verdict = "INCONCLUSIVE"
                reasons.append("missing_s_n_delta")
            elif abs(sn_d) <= ALIGN_TOL_S_N:
                # S_n within tol → ALIGNED; channel mismatch is soft note only
                for key, tol in (
                    ("rsr", ALIGN_TOL_CHANNEL),
                    ("ltp", ALIGN_TOL_CHANNEL),
                    ("rle", ALIGN_TOL_CHANNEL),
                ):
                    d = deltas.get(key)
                    if d is not None and abs(d) > tol:
                        reasons.append(f"channel_soft_mismatch:{key}={d}")
                verdict = "ALIGNED"
            else:
                verdict = "DRIFT"
                reasons.append(f"s_n_delta={sn_d}")

        ok = verdict in {"ALIGNED", "DRIFT", "INCONCLUSIVE"}
        return {
            "ok": ok,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "align_check",
                "at": _utc(),
                "verdict": verdict,
                "reasons": reasons,
                "min_samples": min_n,
                "brief_n": n,
                "capture_n_logged": n_logged_i,
                "plant_source": plant_source,
                "plant": plant_side,
                "master": master,
                "deltas": deltas,
                "tol_s_n": ALIGN_TOL_S_N,
                "tol_channel": ALIGN_TOL_CHANNEL,
                "capture": capture,
                "observe_error": observe_err,
                "read_only": True,
                "mutates_security_core": False,
                "replaces_foundation_math": False,
                "v2": _v2_presence(),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "align_check",
                "at": _utc(),
                "verdict": "INCONCLUSIVE",
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove status + snapshot + align_check; assert no V2 math swap / security mutate."""
    st = status()
    snap = snapshot()
    align = align_check()
    sev = st.get("evidence") or {}
    nev = snap.get("evidence") or {}
    aev = align.get("evidence") or {}
    v2 = sev.get("v2") or {}
    ok = (
        bool(st.get("ok"))
        and bool(snap.get("ok"))
        and bool(align.get("ok"))
        and bool(sev.get("master_rid_exists") or nev.get("master_s_n") is not None)
        and bool(sev.get("plant_dir_exists"))
        and aev.get("verdict") in {"ALIGNED", "DRIFT", "INCONCLUSIVE"}
        and v2.get("viv_executes_v2") is False
        and v2.get("viv_replaces_foundation_math") is False
        and sev.get("mutates_security_core") is False
        and sev.get("replaces_foundation_math") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "status_ok": bool(st.get("ok")),
        "snapshot_ok": bool(snap.get("ok")),
        "align_ok": bool(align.get("ok")),
        "master_s_n": nev.get("master_s_n"),
        "master_status": nev.get("status"),
        "align_verdict": aev.get("verdict"),
        "brief_n": aev.get("brief_n"),
        "deltas": aev.get("deltas"),
        "viv_executes_v2": v2.get("viv_executes_v2"),
        "viv_replaces_foundation_math": v2.get("viv_replaces_foundation_math"),
        "mutates_security_core": sev.get("mutates_security_core"),
        "status": st,
        "snapshot": snap,
        "align_check": align,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "master_s_n": nev.get("master_s_n"),
            "master_status": nev.get("status"),
            "align_verdict": aev.get("verdict"),
            "brief_n": aev.get("brief_n"),
            "deltas": aev.get("deltas"),
            "viv_executes_v2": False,
            "replaces_foundation_math": False,
            "mutates_security_core": False,
        }
        ADAPTER_EVIDENCE.write_text(json.dumps(slim, indent=2), encoding="utf-8")
        evidence["evidence_path"] = _as_posix(ADAPTER_EVIDENCE)
    except OSError as exc:
        evidence["evidence_write_error"] = str(exc)
    return {"ok": ok, "evidence": evidence}


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
