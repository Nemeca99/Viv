#!/usr/bin/env python3
"""Read-only inventory of CPU/GPU electrical meters — never fabricates values.

Probes foundation APIs and a few Windows discovery paths. Records found /
not_found / denied. Does not write Master RID and does not invent 12 V rails.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_meter_inventory.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
LATEST = OUT_DIR / "meter_inventory_latest.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _probe_gpu_nvml() -> dict[str, Any]:
    try:
        from lib.gpu_plant import read_gpu

        g = read_gpu(0)
        return {
            "status": "found",
            "api": "lib.gpu_plant.read_gpu.power_w",
            "channel": "w_gpu",
            "sample": float(g.power_w),
            "unit": "W",
            "notes": "NVML package power",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "denied_or_error",
            "api": "lib.gpu_plant.read_gpu.power_w",
            "channel": "w_gpu",
            "sample": None,
            "error": str(exc),
        }


def _probe_foundation_cpu_power() -> dict[str, Any]:
    """No foundation CPU package-power API exists today — record honestly."""
    return {
        "status": "not_found",
        "api": "foundation_cpu_package_power",
        "channel": "w_cpu",
        "sample": None,
        "notes": "No lib/*.py API exposes CPU package watts on this plane.",
    }


def _probe_corsair_power_columns() -> dict[str, Any]:
    try:
        from lib.corsair_telemetry import latest_csv

        path = latest_csv()
        if path is None:
            return {
                "status": "not_found",
                "api": "lib.corsair_telemetry.latest_csv",
                "channel": "w_cpu|v|i",
                "sample": None,
                "notes": "No Corsair CSV log found",
            }
        # Read header only
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            header = fh.readline()
        headers = [h.strip().lower() for h in header.split(",")]
        powerish = []
        for h in headers:
            # Avoid substring traps (e.g. "amp" inside "timestamp")
            if any(k in h for k in ("power", "watt", "volt", "amper", "current_a", "psu")):
                powerish.append(h)
            elif h == "amp" or h.endswith(" amp") or f" {h} ".find(" amp ") >= 0:
                powerish.append(h)
        return {
            "status": "found" if powerish else "not_found",
            "api": "lib.corsair_telemetry.latest_csv",
            "channel": "corsair_electrical_columns",
            "sample": None,
            "path": str(path).replace("\\", "/"),
            "matching_headers": powerish[:40],
            "notes": (
                "Corsair CSV has electrical-named columns"
                if powerish
                else "Corsair CSV present but no power/volt/amp headers"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "denied_or_error",
            "api": "lib.corsair_telemetry",
            "channel": "corsair_electrical_columns",
            "sample": None,
            "error": str(exc),
        }


def _probe_windows_power_meter_counter() -> dict[str, Any]:
    """Discover if Windows exposes Power Meter counters — do not invent values.

    Uses typeperf -qx listing only (no sustained sampling). Absence is not_found.
    """
    try:
        proc = subprocess.run(
            ["typeperf", "-qx", "Power Meter"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        # typeperf -qx prints counter paths when the object exists
        useful = [ln for ln in lines if "power meter" in ln.lower() or "\\\\" in ln]
        if proc.returncode != 0 and not useful:
            return {
                "status": "not_found",
                "api": "typeperf -qx Power Meter",
                "channel": "w_cpu|psu",
                "sample": None,
                "returncode": proc.returncode,
                "notes": "Power Meter counter object not available or empty",
                "stderr_tail": out[-400:],
            }
        return {
            "status": "found" if useful else "not_found",
            "api": "typeperf -qx Power Meter",
            "channel": "w_cpu|psu",
            "sample": None,
            "counter_paths_sample": useful[:20],
            "notes": (
                "Counters listed only — not wired as foundation meters; "
                "no value admitted into triad"
            ),
        }
    except FileNotFoundError:
        return {
            "status": "not_found",
            "api": "typeperf",
            "channel": "w_cpu|psu",
            "sample": None,
            "notes": "typeperf.exe not found",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "denied_or_error",
            "api": "typeperf -qx Power Meter",
            "channel": "w_cpu|psu",
            "sample": None,
            "error": str(exc),
        }


def _probe_nvml_voltage_current() -> dict[str, Any]:
    """NVML package power exists; voltage/current rails are typically absent."""
    try:
        import pynvml

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        probes: dict[str, Any] = {}
        for name, fn in (
            ("power_w", lambda: float(pynvml.nvmlDeviceGetPowerUsage(h)) / 1000.0),
        ):
            try:
                probes[name] = {"status": "found", "sample": fn()}
            except Exception as exc:  # noqa: BLE001
                probes[name] = {"status": "denied_or_error", "error": str(exc)}
        # Explicitly note voltage/current APIs not used / not admitted
        return {
            "status": "partial",
            "api": "pynvml",
            "channel": "gpu_electrical",
            "probes": probes,
            "v_gpu": {"status": "not_found", "notes": "No admitted NVML rail voltage path in foundation"},
            "i_gpu": {"status": "not_found", "notes": "No admitted NVML rail current path in foundation"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "denied_or_error",
            "api": "pynvml",
            "channel": "gpu_electrical",
            "error": str(exc),
        }


def _probe_hwinfo_csv() -> dict[str, Any]:
    try:
        from lib.hwinfo_telemetry import inventory_probe

        return inventory_probe()
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "denied_or_error",
            "api": "lib.hwinfo_telemetry.inventory_probe",
            "channel": "w_cpu|v|i|gpu",
            "sample": None,
            "error": str(exc),
        }


def inventory() -> dict[str, Any]:
    probes = {
        "w_gpu_nvml": _probe_gpu_nvml(),
        "w_cpu_foundation": _probe_foundation_cpu_power(),
        "hwinfo_csv": _probe_hwinfo_csv(),
        "corsair_electrical_headers": _probe_corsair_power_columns(),
        "windows_power_meter": _probe_windows_power_meter_counter(),
        "nvml_voltage_current": _probe_nvml_voltage_current(),
    }

    # Only admit a channel into "wired_candidates" if we have a foundation-ready sample
    wired: dict[str, Any] = {}
    if probes["w_gpu_nvml"].get("status") == "found" and probes["w_gpu_nvml"].get("sample") is not None:
        wired["w_gpu"] = {
            "source": probes["w_gpu_nvml"]["api"],
            "sample": probes["w_gpu_nvml"]["sample"],
            "admitted_to_observe": True,
        }

    # HWiNFO CSV: admit numeric samples from preferred columns or stamped Ohm i_gpu.
    hw = probes.get("hwinfo_csv") or {}
    for key, ch in (hw.get("channels") or {}).items():
        if not isinstance(ch, dict):
            continue
        status = ch.get("status")
        if status not in ("found", "found_software_ohm") or ch.get("sample") is None:
            continue
        # Prefer live NVML for w_gpu when already wired; still record HWiNFO as alt.
        if key == "w_gpu" and key in wired:
            wired[key]["hwinfo_crosscheck"] = {
                "source": ch.get("source"),
                "sample": ch["sample"],
            }
            continue
        entry: dict[str, Any] = {
            "source": ch.get("source") or "lib.hwinfo_telemetry",
            "sample": float(ch["sample"]),
            "admitted_to_observe": True,
            "origin": ch.get("origin"),
            "independent_axis": bool(ch.get("independent_axis", True)),
        }
        if key == "i_gpu" and ch.get("rails") is not None:
            entry["rails"] = ch.get("rails")
            entry["rail_count_used"] = ch.get("rail_count_used")
        wired[key] = entry

    # CPU W / all V/I: require an explicit foundation API with a numeric sample.
    # typeperf listing alone is NOT enough to wire (discovery ≠ metering).
    missing = [
        c
        for c in ("w_cpu", "w_gpu", "v_cpu", "v_gpu", "i_cpu", "i_gpu")
        if c not in wired
    ]

    payload = {
        "ok": True,
        "at": _utc(),
        "authority": "inventory_readonly",
        "fabricates_values": False,
        "probes": probes,
        "wired_candidates": wired,
        "missing_for_complete_triad": missing,
        "complete_triad": len(missing) == 0,
        "policy": (
            "Discovery listings (typeperf -qx) do not admit values. "
            "Only foundation-ready numeric samples enter wired_candidates. "
            "HWiNFO admits exact preferred columns only. "
            "Derived I=W/V is forbidden as an independent live axis."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _utc().replace(":", "").replace("+", "p")
    stamped = OUT_DIR / f"meter_inventory_{stamp}.json"
    text = json.dumps(payload, indent=2)
    stamped.write_text(text, encoding="utf-8")
    LATEST.write_text(text, encoding="utf-8")
    payload["artifact"] = str(stamped).replace("\\", "/")
    payload["latest"] = str(LATEST).replace("\\", "/")
    return payload


def main() -> int:
    out = inventory()
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
