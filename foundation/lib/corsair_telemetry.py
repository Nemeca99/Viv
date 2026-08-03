"""Corsair iCUE CSV reader for H100i coolant + CPU temps during RID benchmark."""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any, Optional

DEFAULT_LOG_DIR = Path(
    os.environ.get(
        "VIV_CORSAIR_LOG_DIR",
        r"L:\Steel_Brain\RID\RID_Completed\HW-Info\Corsair_Log",
    )
)

_TAIL_CACHE: dict[str, Any] = {"path": None, "mtime": 0.0, "headers": None, "last_row": None}

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _safe_float(val: str, default: float = 0.0) -> float:
    if not val:
        return default
    m = _NUM.search(str(val).replace(",", ""))
    if not m:
        return default
    try:
        return float(m.group())
    except ValueError:
        return default


def _find_col(headers: list[str], *keywords: str) -> int:
    for i, h in enumerate(headers):
        hl = h.lower()
        if all(k.lower() in hl for k in keywords):
            return i
    return -1


def latest_csv(log_dir: Path | None = None) -> Optional[Path]:
    root = log_dir or DEFAULT_LOG_DIR
    if not root.is_dir():
        return None
    files = list(root.glob("*.csv")) + list(root.glob("*.CSV"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _read_csv_tail(path: Path) -> tuple[list[str], list[str]] | None:
    """Read header + last data row without scanning huge logs each poll."""
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
            read_size = min(16384, size)
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
        cached["headers"] = headers
    else:
        headers = cached["headers"]

    # tail chunk may omit header; last line is data
    import io

    last_line = lines[-1]
    row = next(csv.reader(io.StringIO(last_line)), None)
    if not row:
        return None
    cached.update({"path": path, "mtime": mtime, "last_row": row})
    return headers, row


def read_latest(log_dir: Path | None = None) -> dict[str, Optional[float]]:
    """Return cpu_package_c, coolant_c, cpu_load_pct from newest Corsair log row."""
    path = latest_csv(log_dir)
    out: dict[str, Optional[float]] = {
        "cpu_package_c": None,
        "coolant_c": None,
        "cpu_load_pct": None,
        "source": None,
    }
    if path is None:
        return out
    tail = _read_csv_tail(path)
    if not tail:
        return out
    headers, last = tail
    try:
        pkg_i = _find_col(headers, "cpu", "package")
        cool_i = _find_col(headers, "coolant")
        load_i = _find_col(headers, "cpu", "load")
        if pkg_i >= 0 and pkg_i < len(last):
            out["cpu_package_c"] = _safe_float(last[pkg_i], 0.0) or None
        if cool_i >= 0 and cool_i < len(last):
            out["coolant_c"] = _safe_float(last[cool_i], 0.0) or None
        if load_i >= 0 and load_i < len(last):
            out["cpu_load_pct"] = _safe_float(last[load_i], 0.0) or None
        out["source"] = str(path)
    except (IndexError, ValueError):
        return out
    return out


def read_cpu_temp_c(log_dir: Path | None = None) -> Optional[float]:
    """Best CPU die proxy for LTP: CPU Package from iCUE log."""
    row = read_latest(log_dir)
    return row.get("cpu_package_c")


def read_per_core_temps(log_dir: Path | None = None, n_cores: int = 8) -> list[float]:
    """Per-logical-core temps from iCUE CSV; fallback to package temp."""
    path = latest_csv(log_dir)
    fallback = read_cpu_temp_c(log_dir) or 0.0
    temps = [fallback] * n_cores
    if path is None:
        return temps
    tail = _read_csv_tail(path)
    if not tail:
        return temps
    headers, last = tail
    for i, h in enumerate(headers):
        hl = h.lower()
        if "cpu core" not in hl:
            continue
        m = re.search(r"#\s*(\d+)", h)
        if not m:
            continue
        core_num = int(m.group(1))
        idx = core_num - 1
        if 0 <= idx < n_cores and i < len(last):
            temps[idx] = _safe_float(last[i], fallback)
    return temps
