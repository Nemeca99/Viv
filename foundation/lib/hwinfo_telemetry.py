#!/usr/bin/env python3
"""HWiNFO CSV telemetry reader — admit only named meter columns with numeric samples.

Default log path (operator-configured logging target):
  L:/Continue/Viv/foundation/lib/sensors/hwinfo.CSV

Honesty:
  - Missing / empty / non-numeric → None (not 0, not 1).
  - Native amp sensors preferred.
  - When no GPU [A] column exists, i_gpu may be reconstructed via Ohm identity
    from *simultaneously measured* same-rail Power[W] and Voltage[V] pairs
    (software-best). That reconstruction is stamped and is NOT an independent
    live axis (see reject_derived_live_axes / origins).
  - Never invents V from assumed 12 V; never uses wrong-domain P/V pairs.
  - Ambiguous duplicate headers (e.g. bare \"Current (IOUT) [A]\") are refused.
"""
from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path
from typing import Any, Optional

DEFAULT_CSV = Path(
    os.environ.get(
        "VIV_HWINFO_CSV",
        r"L:\Continue\Viv\foundation\lib\sensors\hwinfo.CSV",
    )
)

# Exact preferred headers (HWiNFO English defaults). First match wins.
CHANNEL_COLUMNS: dict[str, tuple[str, ...]] = {
    "w_cpu": ("CPU Package Power [W]",),
    "v_cpu": ("Vcore [V]",),
    "i_cpu": ("VR VCC Current (SVID IOUT) [A]",),
    "w_gpu": ("GPU Power [W]",),
    "v_gpu": ("GPU Core Voltage [V]",),
    # Native GPU current column — empty on this plant; see GPU_RAIL_PAIRS.
    "i_gpu": (),
}

# Board-input rail pairs for software Ohm reconstruction of i_gpu.
# PCIe + 8-pin only: on this plant P_pcie + P_8pin ≈ GPU Power; Misc0 double-counts.
GPU_RAIL_PAIRS: tuple[tuple[str, str], ...] = (
    ("GPU PCIe +12V Input Power [W]", "GPU PCIe +12V Input Voltage [V]"),
    ("GPU 8-pin #1 Input Power [W]", "GPU 8-pin #1 Input Voltage [V]"),
)
I_GPU_ORIGIN_NATIVE = "native_hwinfo_column"
I_GPU_ORIGIN_OHM = "software_ohm_from_measured_hwinfo_rails"

# Explicitly refuse known bad / ambiguous headers even if fuzzy matching is added later.
REFUSED_COLUMNS: frozenset[str] = frozenset(
    {
        "+12V [V]",  # observed garbage (~0.05 V) on this plant
        "Current (IOUT) [A]",  # duplicate ambiguous VR rails
        "Current (IIN) [A]",
    }
)

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_TAIL_CACHE: dict[str, Any] = {"path": None, "mtime": 0.0, "headers": None, "last_row": None}


def _norm_header(h: str) -> str:
    return str(h).strip().strip('"').strip()


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in {"n/a", "na", "-", "—", "yes", "no"}:
        return None
    m = _NUM.search(s.replace(",", ""))
    if not m:
        return None
    try:
        x = float(m.group())
    except ValueError:
        return None
    if x != x or x in (float("inf"), float("-inf")):  # NaN/inf
        return None
    return x


def csv_path(path: Path | None = None) -> Optional[Path]:
    p = path or DEFAULT_CSV
    if p.is_file():
        return p
    return None


def _read_csv_tail(path: Path) -> tuple[list[str], list[str]] | None:
    """Header + last data row; cache by mtime (Corsair-style)."""
    global _TAIL_CACHE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _TAIL_CACHE
    if cached["path"] == path and cached["mtime"] == mtime and cached["last_row"] is not None:
        return cached["headers"], cached["last_row"]

    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size < 2:
                return None
            read_size = min(65536, size)
            fh.seek(-read_size, 2)
            chunk = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    lines = [ln for ln in chunk.splitlines() if ln.strip()]
    if not lines:
        return None

    if cached["path"] != path or cached["headers"] is None:
        try:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
                headers = next(csv.reader(fh), None)
        except OSError:
            headers = None
        if not headers:
            return None
        cached["headers"] = [_norm_header(h) for h in headers]
    else:
        headers = cached["headers"]

    last_line = lines[-1]
    # Skip if last line looks like a header (rare partial rewrite)
    if last_line.lower().startswith("date,"):
        if len(lines) < 2:
            return None
        last_line = lines[-2]
    row = next(csv.reader(io.StringIO(last_line)), None)
    if not row:
        return None
    cached.update({"path": path, "mtime": mtime, "last_row": row})
    return headers, row


def _find_exact(headers: list[str], preferred: tuple[str, ...]) -> int:
    index = {_norm_header(h): i for i, h in enumerate(headers)}
    for name in preferred:
        if name in REFUSED_COLUMNS:
            continue
        i = index.get(name)
        if i is not None:
            return i
    return -1


def _col_value(headers: list[str], row: list[str], name: str) -> float | None:
    idx = _find_exact(headers, (name,))
    if idx < 0 or idx >= len(row):
        return None
    return _safe_float(row[idx])


def reconstruct_i_gpu_from_rails(
    headers: list[str],
    row: list[str],
    *,
    pairs: tuple[tuple[str, str], ...] = GPU_RAIL_PAIRS,
) -> dict[str, Any]:
    """Sum I=P/V over measured GPU board-input rails.

    Requires measured V>0 and finite P on each included rail. Skips incomplete
    pairs. Returns null if no rail contributes — never invents voltage.
    """
    rails: list[dict[str, Any]] = []
    total = 0.0
    for power_col, volt_col in pairs:
        p = _col_value(headers, row, power_col)
        v = _col_value(headers, row, volt_col)
        if p is None or v is None or v <= 0.0:
            rails.append(
                {
                    "power_col": power_col,
                    "volt_col": volt_col,
                    "power_w": p,
                    "volt_v": v,
                    "i_a": None,
                    "included": False,
                    "reason": "incomplete_or_nonpositive_v",
                }
            )
            continue
        i = float(p) / float(v)
        rails.append(
            {
                "power_col": power_col,
                "volt_col": volt_col,
                "power_w": float(p),
                "volt_v": float(v),
                "i_a": i,
                "included": True,
                "reason": None,
            }
        )
        total += i
    included = [r for r in rails if r["included"]]
    if not included:
        return {
            "i_gpu": None,
            "origin": None,
            "independent_axis": False,
            "rails": rails,
            "rail_count_used": 0,
        }
    return {
        "i_gpu": total,
        "origin": I_GPU_ORIGIN_OHM,
        "independent_axis": False,
        "rails": rails,
        "rail_count_used": len(included),
        "source": "hwinfo_ohm_sum:PCIe+8pin",
    }


def read_electrical(path: Path | None = None) -> dict[str, Any]:
    """Return electrical channel samples from latest HWiNFO CSV row.

    Missing channels stay None. Native columns preferred; i_gpu may be
    Ohm-reconstructed from measured rail P/V when no native [A] exists.
    """
    out: dict[str, Any] = {
        "w_cpu": None,
        "w_gpu": None,
        "v_cpu": None,
        "v_gpu": None,
        "i_cpu": None,
        "i_gpu": None,
        "sources": {},
        "origins": {},
        "independent_axes": {},
        "i_gpu_rails": None,
        "path": None,
        "date": None,
        "time": None,
        "ok": False,
        "error": None,
    }
    p = csv_path(path)
    if p is None:
        out["error"] = "csv_not_found"
        return out
    out["path"] = str(p).replace("\\", "/")
    tail = _read_csv_tail(p)
    if not tail:
        out["error"] = "csv_tail_unreadable"
        return out
    headers, row = tail
    if len(row) >= 1:
        out["date"] = row[0].strip() if row[0] else None
    if len(row) >= 2:
        out["time"] = row[1].strip() if row[1] else None

    for channel, preferred in CHANNEL_COLUMNS.items():
        if not preferred:
            out["sources"][channel] = None
            continue
        idx = _find_exact(headers, preferred)
        if idx < 0 or idx >= len(row):
            out["sources"][channel] = None
            continue
        sample = _safe_float(row[idx])
        out[channel] = sample
        out["sources"][channel] = (
            f"hwinfo_csv:{preferred[0]}" if sample is not None else None
        )
        if sample is not None:
            out["origins"][channel] = "native_hwinfo_column"
            out["independent_axes"][channel] = True

    # Native i_gpu column (if ever configured) wins; else Ohm rail reconstruction.
    native_i = CHANNEL_COLUMNS.get("i_gpu") or ()
    if native_i and out.get("i_gpu") is not None:
        out["origins"]["i_gpu"] = I_GPU_ORIGIN_NATIVE
        out["independent_axes"]["i_gpu"] = True
    else:
        recon = reconstruct_i_gpu_from_rails(headers, row)
        out["i_gpu_rails"] = recon
        if recon.get("i_gpu") is not None:
            out["i_gpu"] = float(recon["i_gpu"])
            out["sources"]["i_gpu"] = str(recon.get("source") or I_GPU_ORIGIN_OHM)
            out["origins"]["i_gpu"] = I_GPU_ORIGIN_OHM
            out["independent_axes"]["i_gpu"] = False

    out["ok"] = True
    out["error"] = None
    out["notes"] = (
        "Admits exact preferred HWiNFO columns. "
        "i_gpu: native [A] if present; else software Ohm sum of measured "
        "PCIe+8-pin Input Power/Voltage pairs (not an independent axis). "
        "Assumed 12 V and wrong-domain P/V pairs are forbidden."
    )
    return out


def inventory_probe(path: Path | None = None) -> dict[str, Any]:
    """Inventory-shaped probe: per-channel found/not_found with samples."""
    row = read_electrical(path)
    channels: dict[str, Any] = {}
    for key in ("w_cpu", "w_gpu", "v_cpu", "v_gpu", "i_cpu", "i_gpu"):
        sample = row.get(key)
        preferred = CHANNEL_COLUMNS.get(key) or ()
        origin = (row.get("origins") or {}).get(key)
        independent = (row.get("independent_axes") or {}).get(key)
        if sample is None:
            channels[key] = {
                "status": "not_found",
                "sample": None,
                "preferred_columns": list(preferred),
                "source": row.get("sources", {}).get(key),
                "origin": origin,
                "independent_axis": False,
                "notes": (
                    "No native GPU [A] and rail Ohm reconstruction failed"
                    if key == "i_gpu"
                    else None
                ),
            }
        else:
            status = "found"
            if key == "i_gpu" and origin == I_GPU_ORIGIN_OHM:
                status = "found_software_ohm"
            channels[key] = {
                "status": status,
                "sample": float(sample),
                "unit": {
                    "w_cpu": "W",
                    "w_gpu": "W",
                    "v_cpu": "V",
                    "v_gpu": "V",
                    "i_cpu": "A",
                    "i_gpu": "A",
                }[key],
                "preferred_columns": list(preferred),
                "source": row.get("sources", {}).get(key),
                "origin": origin,
                "independent_axis": bool(independent) if independent is not None else True,
            }
            if key == "i_gpu" and row.get("i_gpu_rails"):
                channels[key]["rails"] = row["i_gpu_rails"].get("rails")
                channels[key]["rail_count_used"] = row["i_gpu_rails"].get(
                    "rail_count_used"
                )
    return {
        "status": "found" if row.get("ok") else "denied_or_error",
        "api": "lib.hwinfo_telemetry.read_electrical",
        "path": row.get("path"),
        "date": row.get("date"),
        "time": row.get("time"),
        "error": row.get("error"),
        "channels": channels,
        "notes": row.get("notes"),
    }
