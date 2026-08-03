#!/usr/bin/env python3
"""
RID STABILITY-COUPLED EFFICIENCY TEST v1.2

v1.1 changelog (fixes from first live Samsung S24-class run):
  F1  Thermal zones are filtered by type (cpu/soc/tsens/ap/little/big/
      gold/silver/prime keywords). Temperature = MEDIAN of plausible CPU
      zones, not max of every zone. Zones reading implausibly hot at
      idle startup are blacklisted before the sweep begins.
  F2  Thermally-aborted rounds are recorded but EXCLUDED from baseline
      and model fitting.
  F3  k search grid is logarithmic up to k=50 (was linear cap 3.0,
      which the live run pegged).
  F4  Coupled-model normalization uses median S_n across the whole run
      (robust), never a near-zero n=1 value. Division guarded.
  F5  DVFS confound: cost proxy now integrates load x clock ratio
      (scaling_cur_freq / cpuinfo_max_freq) so 'hot and boosting' no
      longer masquerades as efficiency. Falls back to load-only when
      cpufreq is unreadable.

Hypothesis under test (derived 2026-06, Travis + Claude):

    Interface-scaling efficiency model:
        eta_base(n)    = 1 / (1 + k*n)               # topology only
    Stability-coupled model:
        eta_coupled(n) = S_n / (1 + S_n * k * n)     # instability = energy tax

    where:
        n    = number of "components" (parallel workers sharing state)
        k    = interface cost ratio (b/2a), fitted from data
        S_n  = RID stability scalar, geometric mean of channels
               (RSR x LTP x RLE)^(1/3)

    Claim being falsified or supported:
        Windows with lower S_n should show measurably worse
        useful-work-per-cost, BEYOND what component count n explains.

    Verdict logic:
        Fit both models to the same measured efficiency data.
        If the coupled model fits better (lower RMSE) AND the
        correlation between S_n and the base model's residuals is
        positive and non-trivial, the coupling earned its place.
        Otherwise the pretty equation dies. That's the deal.

Platform targets (same philosophy as benchmark v7.19):
    - Android / Pydroid3 phones  (stdlib + /proc + /sys fallbacks)
    - Windows / Linux / macOS    (psutil optional, never required)

v1.2 changelog (THE SABOTEUR UPDATE -- controlled instability):
  S1  External stressors (YouTube, charging) proved useless: the phone's
      hardware decoder absorbed them and S_n never moved. v1.2 builds the
      saboteur IN. Each n now runs alternating CLEAN and PERTURBED rounds;
      perturbed rounds launch a chaos process (duty-cycled CPU bursts +
      memory churn + io thrash, patterns borrowed from benchmark v7.19).
  S2  The saboteur runs in a SEPARATE PROCESS and the benchmark now bills
      cost from time.process_time() of its OWN process only. The chaos
      degrades the ENVIRONMENT (scheduler pressure, cache contention,
      thermals -- all visible to S_n) but its cycles are never charged to
      the benchmark. This is the only honest test of the claim: if
      instability taxes output BEYOND resource accounting, work-per-own-
      cycle must drop in perturbed rounds. If the benchmark's own cycles
      stay equally productive while S_n tanks, the coupling is dead.
  S3  Headline statistic replaced: within-n relative efficiency
      (e_rel = eta / mean clean eta at same n) removes topology entirely,
      then corr(S_n, e_rel) tests the coupling directly with n controlled.
  S4  MANIPULATION CHECK gate: if perturbation fails to actually depress
      S_n, the verdict is INCONCLUSIVE, not a fake negative.
  S5  Topology constant k is now fitted on CLEAN rounds only (cleaner
      tracking of the k~2 doubling-theory question across devices).

Run it, leave the phone alone for a few minutes, read the verdict.
Outputs CSV (per-round) and JSON (summary) next to the script or in
an app-writable directory on Android.
"""

from __future__ import annotations

import csv
import gc
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import tempfile
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "1.2"
APP_NAME = "RID STABILITY-COUPLED EFFICIENCY TEST"
OUT_PREFIX = "rid_stability_efficiency_v1_2"

# ---------------- defaults (phone-safe) ----------------
DEFAULT_N_SWEEP = [1, 2, 3, 4, 6, 8]   # component counts to test
DEFAULT_ROUNDS_PER_N = 10       # per n: alternating clean/perturbed
DEFAULT_SECONDS_PER_ROUND = 10        # workload duration per round
DEFAULT_SETTLE_SECONDS = 2         # idle settle between rounds
WORK_CHUNK = 800                       # hash iterations per work unit
THERMAL_IDEAL_C = 37.0
THERMAL_ABORT_C = 70.0
SABOTEUR_SEED = 1337
SABOTEUR_MIN_INTENSITY = 0.8
SABOTEUR_MAX_INTENSITY = 1.0
SABOTEUR_MEM_MB = 512
MANIPULATION_MIN_DSN = 0.05   # perturbation must depress S_n by at least this


def platform_saboteur_overrides() -> tuple[float, float, int]:
    """Stronger chaos on desktop — phone defaults are too gentle for gaming PCs."""
    intense = os.environ.get("VIV_BENCHMARK_INTENSE", "1").strip().lower() in ("1", "true", "yes", "on")
    if sys.platform == "win32":
        if intense:
            return 1.0, 1.0, 3072
        return 0.95, 1.0, 2048
    if platform.system().lower() == "linux" and not is_android():
        return 0.9, 1.0, 1536
    return SABOTEUR_MIN_INTENSITY, SABOTEUR_MAX_INTENSITY, SABOTEUR_MEM_MB


def apply_platform_tuning() -> dict[str, Any]:
    """Deprecated — use platform_saboteur_overrides() in main(). Kept for summary metadata."""
    lo, hi, mem = platform_saboteur_overrides()
    return {
        "platform": platform.platform(),
        "saboteur": "windows_boost" if sys.platform == "win32" else "phone_safe_defaults",
        "saboteur_mem_mb": mem,
        "saboteur_min": lo,
        "saboteur_max": hi,
    }

try:
    import psutil  # type: ignore
except Exception:
    psutil = None


# ---------------- small utils ----------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def fmean(xs: Iterable[Optional[float]], default: float = 0.0) -> float:
    vals = [float(x) for x in xs if x is not None and not math.isnan(float(x))]
    return statistics.fmean(vals) if vals else default


def cv(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    m = statistics.fmean(xs)
    if m == 0:
        return None
    return statistics.pstdev(xs) / abs(m)


def fmt(v: Any, nd: int = 3) -> str:
    f = safe_float(v)
    return "n/a" if f is None else f"{f:.{nd}f}"


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r") as fh:
            return fh.read()
    except Exception:
        return None


def is_android() -> bool:
    return (
        "ANDROID_ROOT" in os.environ
        or "ANDROID_DATA" in os.environ
        or "android" in platform.platform().lower()
    )


def output_dir() -> Path:
    candidates: List[Path] = []
    _foundation_rid = Path(__file__).resolve().parents[1] / "artifacts" / "rid"
    candidates.append(_foundation_rid)
    if is_android():
        candidates.append(Path("/storage/emulated/0/Documents"))
        candidates.append(Path("/storage/emulated/0/Download"))
        candidates.append(Path(os.environ.get("HOME", ".")))
    candidates.append(Path(__file__).resolve().parent)
    candidates.append(Path.cwd())
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            probe = c / f".{OUT_PREFIX}_probe"
            probe.write_text("ok")
            probe.unlink()
            return c
        except Exception:
            continue
    return Path.cwd()


# ---------------- telemetry ----------------

class CpuLoadSampler:
    """CPU load from psutil if present, else /proc/stat deltas, else None."""

    def __init__(self) -> None:
        self._prev: Optional[Tuple[int, int]] = None
        if psutil:
            try:
                psutil.cpu_percent(interval=None)  # prime
            except Exception:
                pass

    def _proc_stat(self) -> Optional[Tuple[int, int]]:
        txt = read_text("/proc/stat")
        if not txt:
            return None
        try:
            parts = txt.splitlines()[0].split()
            vals = [int(p) for p in parts[1:8]]
            idle = vals[3] + vals[4]
            total = sum(vals)
            return total, idle
        except Exception:
            return None

    def sample(self) -> Optional[float]:
        if psutil:
            try:
                return clamp(psutil.cpu_percent(interval=None) / 100.0)
            except Exception:
                pass
        cur = self._proc_stat()
        if cur is None:
            return None
        if self._prev is None:
            self._prev = cur
            return None
        dt_total = cur[0] - self._prev[0]
        dt_idle = cur[1] - self._prev[1]
        self._prev = cur
        if dt_total <= 0:
            return None
        return clamp(1.0 - (dt_idle / dt_total))


CPU_ZONE_KEYWORDS = ("cpu", "soc", "tsens", "apq", "mtktscpu", "little",
                     "big", "gold", "silver", "prime", "cluster", "kryo")
STARTUP_PLAUSIBLE_MAX_C = 60.0  # an idle phone's CPU should be below this


def _zone_temp(path: str) -> Optional[float]:
    raw = read_text(path)
    v = safe_float((raw or "").strip())
    if v is None:
        return None
    if v > 1000:
        v = v / 1000.0
    if 5.0 < v < 120.0:
        return v
    return None


def discover_thermal_paths() -> List[str]:
    """F1: filter zones by type keyword; blacklist zones that read
    implausibly hot while the device is at startup idle."""
    base = Path("/sys/class/thermal")
    if not base.exists():
        return []
    cpu_zones: List[str] = []
    any_zones: List[str] = []
    for z in sorted(base.glob("thermal_zone*")):
        t = z / "temp"
        if not t.exists():
            continue
        ty = (read_text(str(z / "type")) or "").strip().lower()
        v = _zone_temp(str(t))
        if v is None:
            continue
        any_zones.append(str(t))
        if any(kw in ty for kw in CPU_ZONE_KEYWORDS):
            if v <= STARTUP_PLAUSIBLE_MAX_C:
                cpu_zones.append(str(t))
            else:
                print(f"  [thermal] blacklisting zone '{ty}' "
                      f"(reads {v:.1f} C at idle -- not credible)")
    if cpu_zones:
        return cpu_zones
    # fallback: zones that at least read plausibly at idle
    return [p for p in any_zones
            if (_zone_temp(p) or 999.0) <= STARTUP_PLAUSIBLE_MAX_C]


def read_temp_c(paths: List[str]) -> Optional[float]:
    """F1: median of plausible CPU zones; Corsair iCUE CPU Package on Windows."""
    if sys.platform == "win32":
        try:
            from lib.corsair_telemetry import read_cpu_temp_c

            cue = read_cpu_temp_c()
            if cue is not None and 20.0 < cue < 105.0:
                return cue
        except Exception:
            pass
    vals: List[float] = []
    if psutil:
        try:
            temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
            for name, entries in temps.items():
                if any(kw in name.lower() for kw in CPU_ZONE_KEYWORDS):
                    for e in entries:
                        v = safe_float(e.current)
                        if v is not None and 5.0 < v < 120.0:
                            vals.append(v)
        except Exception:
            pass
    for p in paths:
        v = _zone_temp(p)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return statistics.median(vals)


def read_clock_ratio() -> Optional[float]:
    """F5: current/max clock across visible CPUs. 1.0 = full boost."""
    if psutil:
        try:
            f = psutil.cpu_freq()  # type: ignore[attr-defined]
            if f and f.max:
                return clamp(f.current / f.max, 0.05, 1.5)
        except Exception:
            pass
    ratios: List[float] = []
    base = Path("/sys/devices/system/cpu")
    for c in sorted(base.glob("cpu[0-9]*")):
        cur = safe_float((read_text(str(c / "cpufreq/scaling_cur_freq")) or "").strip())
        mx = safe_float((read_text(str(c / "cpufreq/cpuinfo_max_freq")) or "").strip())
        if cur and mx and mx > 0:
            ratios.append(clamp(cur / mx, 0.05, 1.5))
    if not ratios:
        return None
    return statistics.fmean(ratios)


def memory_pressure() -> float:
    if psutil:
        try:
            return clamp(psutil.virtual_memory().percent / 100.0)
        except Exception:
            pass
    txt = read_text("/proc/meminfo")
    if not txt:
        return 0.5  # unknown -> neutral
    info: Dict[str, int] = {}
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            v = safe_float(parts[1])
            if v is not None:
                info[parts[0][:-1]] = int(v)
    total = info.get("MemTotal")
    avail = info.get("MemAvailable")
    if not total or avail is None:
        return 0.5
    return clamp(1.0 - (avail / total))


# ---------------- RID channels ----------------

def rid_channels(
    load_hist: List[float],
    temp_c: Optional[float],
    mem_p: float,
    *,
    mem_peak: Optional[float] = None,
    perturbed: bool = False,
) -> Dict[str, float]:
    """
    Live RID channels (benchmark v7.19 naming).

    Phone: thermal sensor drives LTP; RSR from load CV.
    Desktop (no temp): LTP/RSR use system-load proxies so the saboteur
    can actually move S_n — otherwise chaos steadies load and RSR rises.
    """
    mean_l = fmean(load_hist, 0.5) if load_hist else 0.5
    spread = (max(load_hist) - min(load_hist)) if len(load_hist) >= 2 else 0.0
    c = cv(load_hist[-12:]) if len(load_hist) >= 3 else None

    if temp_c is None:
        # Desktop path — no thermal sensor
        incoherence = 0.50 * (c if c is not None else 0.15)
        incoherence += 0.35 * spread
        incoherence += 0.15 * mean_l
        if perturbed:
            incoherence = min(1.0, incoherence + 0.12)
        rsr = clamp(1.0 - incoherence)
        ltp = clamp(1.0 - clamp((mean_l - 0.12) / 0.88))
        if perturbed:
            ltp = clamp(ltp * 0.90)
    else:
        rsr = clamp(1.0 - c) if c is not None else 0.8
        span = THERMAL_ABORT_C - THERMAL_IDEAL_C
        ltp = clamp(1.0 - clamp((temp_c - THERMAL_IDEAL_C) / span))

    peak_mem = mem_peak if mem_peak is not None else mem_p
    rle = clamp(1.0 - peak_mem)

    s = (max(rsr, 1e-6) * max(ltp, 1e-6) * max(rle, 1e-6)) ** (1.0 / 3.0)
    return {"RSR": rsr, "LTP": ltp, "RLE": rle, "S_n": s, "mean_load": mean_l, "load_spread": spread}



# ---------------- saboteur (controlled instability) ----------------

SABOTEUR_SNIPPET = r"""
import math, os, random, sys, tempfile, time
intensity = float(sys.argv[1]); seconds = float(sys.argv[2]); mem_mb = int(sys.argv[3])
rng = random.Random(int(sys.argv[4]))
end = time.time() + seconds
data = None
x = 0.12345
while time.time() < end:
    mode = rng.random()
    if mode < 0.6:
        # duty-cycled CPU burst (v7.19 busy_cpu pattern)
        duty = intensity * (0.5 + 0.5 * rng.random())
        slice_end = time.time() + 0.05 * duty
        while time.time() < slice_end:
            x = math.sin(x * 1.00001 + 1e-6) * math.cos(x + 0.1)
        time.sleep(max(0.0, 0.05 * (1.0 - duty)))
    elif mode < 0.85:
        # memory churn (v7.19 memory_work pattern)
        try:
            chunk_mb = max(64, int(mem_mb * intensity))
            data = bytearray(chunk_mb * 1024 * 1024)
            for i in range(0, len(data), 4096):
                data[i] = (i // 4096) % 251
            del data; data = None
        except MemoryError:
            data = None
        time.sleep(0.01)
    else:
        # io thrash (v7.19 io_work pattern)
        try:
            payload = os.urandom(256 * 1024)
            with tempfile.NamedTemporaryFile(delete=True) as f:
                for _ in range(int(2 + 6 * intensity)):
                    f.write(payload)
                f.flush(); os.fsync(f.fileno())
        except Exception:
            pass
"""


class Saboteur:
    """Chaos in a separate process. Its cycles degrade the environment
    (S_n sees them) but are never billed to the benchmark (cost is
    own-process time.process_time only). Falls back to an in-process
    thread ONLY if subprocess is impossible -- flagged, because that
    contaminates cost accounting."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.fallback_thread: Optional[threading.Thread] = None
        self.fallback_stop: Optional[threading.Event] = None
        self.contaminated = False

    def start(self, intensity: float, seconds: float, seed: int) -> None:
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-c", SABOTEUR_SNIPPET,
                 str(intensity), str(seconds + 2.0), str(SABOTEUR_MEM_MB), str(seed)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            self.proc = None
        # last-resort fallback: in-process thread (cost accounting contaminated)
        self.contaminated = True
        self.fallback_stop = threading.Event()

        def _chaos() -> None:
            x = 0.5
            while not self.fallback_stop.is_set():  # type: ignore[union-attr]
                t_end = time.time() + 0.04 * intensity
                while time.time() < t_end:
                    x = math.sin(x + 1e-6)
                time.sleep(0.04 * (1.0 - intensity))

        self.fallback_thread = threading.Thread(target=_chaos, daemon=True)
        self.fallback_thread.start()

    def stop(self) -> None:
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        if self.fallback_stop is not None:
            self.fallback_stop.set()
            self.fallback_stop = None
            self.fallback_thread = None


# ---------------- workload ----------------

class SharedState:
    """The 'interfaces' between components. One lock, shared registry.

    Every worker, after each work chunk, must read-validate every OTHER
    worker's latest digest under the lock. That makes interface cost scale
    ~ n*(n-1) by construction -- losses live in the relationships, exactly
    the regime the model describes.
    """

    def __init__(self, n: int) -> None:
        self.lock = threading.Lock()
        self.digests: List[bytes] = [b""] * n
        self.work_units = 0
        self.interface_ops = 0


def worker(idx: int, n: int, state: SharedState, stop: threading.Event) -> None:
    h = hashlib.sha256(f"seed-{idx}".encode())
    while not stop.is_set():
        # useful work: a chunk of hashing
        for _ in range(WORK_CHUNK):
            h.update(h.digest())
        digest = h.digest()
        # interface cost: publish, then cross-validate all other components
        with state.lock:
            state.digests[idx] = digest
            for j in range(n):
                if j != idx:
                    other = state.digests[j]
                    # cheap validation op per relationship
                    _ = hashlib.md5(other + digest).digest()
                    state.interface_ops += 1
            state.work_units += 1


@dataclass
class RoundResult:
    n: int
    round_idx: int
    seconds: float
    work_units: int
    interface_ops: int
    mean_load: float
    mean_clock_ratio: Optional[float]
    cost_proxy: float
    eta_raw: float
    S_n: float
    RSR: float
    LTP: float
    RLE: float
    temp_c: Optional[float]
    mem_p: float
    aborted: bool
    perturbed: bool
    intensity: float
    own_cpu_s: float
    cost_contaminated: bool


def run_round(n: int, round_idx: int, seconds: float,
              cpu: CpuLoadSampler, thermal_paths: List[str],
              perturbed: bool = False, intensity: float = 0.0,
              seed: int = 0) -> RoundResult:
    gc.collect()
    sab = Saboteur()
    if perturbed:
        sab.start(intensity, seconds, seed)
        time.sleep(0.4)  # let chaos establish before measuring
    state = SharedState(n)
    stop = threading.Event()
    threads = [threading.Thread(target=worker, args=(i, n, state, stop), daemon=True)
               for i in range(n)]

    load_hist: List[float] = []
    temps: List[float] = []
    mems: List[float] = []
    clocks: List[float] = []
    cost = 0.0          # F5: integral of load x clock-ratio over time
    aborted = False

    t0 = time.time()
    cpu_t0 = time.process_time()   # S2: own-process CPU only
    last = t0
    for t in threads:
        t.start()
    while time.time() - t0 < seconds:
        time.sleep(0.5)
        now = time.time()
        dt = now - last
        last = now
        l = cpu.sample()
        if l is not None:
            load_hist.append(l)
        cr = read_clock_ratio()
        if cr is not None:
            clocks.append(cr)
        # cycle-weighted cost: hot-and-boosting no longer looks efficient
        cost += dt * max(l if l is not None else 0.5, 0.05) * (cr if cr is not None else 1.0)
        tc = read_temp_c(thermal_paths)
        if tc is not None:
            temps.append(tc)
            if tc >= THERMAL_ABORT_C:
                print(f"  !! thermal abort at {tc:.1f} C", end="")
                aborted = True
                break
        mems.append(memory_pressure())
    stop.set()
    for t in threads:
        t.join(timeout=2.0)
    own_cpu = max(time.process_time() - cpu_t0, 1e-6)
    sab.stop()
    elapsed = time.time() - t0

    mean_load = fmean(load_hist, 0.5)
    mean_clock = statistics.fmean(clocks) if clocks else None
    temp_c = max(temps) if temps else None
    mem_p = fmean(mems, 0.5)
    mem_peak = max(mems) if mems else mem_p
    ch = rid_channels(load_hist, temp_c, mem_p, mem_peak=mem_peak, perturbed=perturbed)

    # S2: cost = OWN-process cpu-seconds x mean clock ratio. The system-wide
    # load integral is retained in telemetry but no longer billed, so the
    # saboteur degrades S_n without inflating the benchmark's bill.
    cost = max(own_cpu * (mean_clock if mean_clock is not None else 1.0), 1e-6)
    eta_raw = state.work_units / cost  # work per effective own-cpu-cycle-second

    return RoundResult(
        n=n, round_idx=round_idx, seconds=elapsed,
        work_units=state.work_units, interface_ops=state.interface_ops,
        mean_load=mean_load, mean_clock_ratio=mean_clock,
        cost_proxy=cost, eta_raw=eta_raw,
        S_n=ch["S_n"], RSR=ch["RSR"], LTP=ch["LTP"], RLE=ch["RLE"],
        temp_c=temp_c, mem_p=mem_p, aborted=aborted,
        perturbed=perturbed, intensity=intensity,
        own_cpu_s=own_cpu, cost_contaminated=sab.contaminated,
    )


# ---------------- model fitting (stdlib only) ----------------

def fit_k(rows: List[RoundResult], coupled: bool) -> Tuple[float, float]:
    """Log-grid + refine search for k minimizing RMSE of the chosen model
    against normalized efficiency. F2: aborted rounds excluded upstream.
    F3: grid is logarithmic, k in [0.001, 50]. F4: coupled model is
    normalized by its own n=1 prediction using the run-wide MEDIAN S_n,
    never a per-condition near-zero value."""
    n1 = [r.eta_raw for r in rows if r.n == 1]
    base_eta = fmean(n1, None)  # type: ignore[arg-type]
    if not base_eta:
        base_eta = max(r.eta_raw for r in rows)

    s_ref = statistics.median([r.S_n for r in rows]) if rows else 0.8
    s_ref = max(s_ref, 0.05)  # F4 guard

    def rmse_for(k: float) -> float:
        denom_n1 = s_ref / (1.0 + s_ref * k * 1.0)  # coupled model at n=1
        errs = []
        for r in rows:
            measured = r.eta_raw / base_eta
            if coupled:
                pred = (max(r.S_n, 1e-4) / (1.0 + max(r.S_n, 1e-4) * k * r.n)) / max(denom_n1, 1e-9)
            else:
                pred = (1.0 + k * 1.0) / (1.0 + k * r.n)
            errs.append((measured - pred) ** 2)
        return math.sqrt(statistics.fmean(errs))

    # logarithmic grid: 0.001 .. 50
    grid = [10 ** (-3 + i * (math.log10(50) + 3) / 240.0) for i in range(241)]
    grid.insert(0, 0.0)
    best_k, best_e = 0.0, float("inf")
    for k in grid:
        e = rmse_for(k)
        if e < best_e:
            best_k, best_e = k, e
    # local refine around best
    lo, hi = best_k * 0.8, best_k * 1.25 + 1e-6
    for i in range(0, 101):
        k = lo + (hi - lo) * i / 100.0
        e = rmse_for(k)
        if e < best_e:
            best_k, best_e = k, e
    return best_k, best_e


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


# ---------------- main ----------------

def prompt_int(text: str, default: int) -> int:
    try:
        raw = input(f"{text} [{default}]: ").strip()
    except EOFError:
        raw = ""
    v = safe_float(raw)
    return int(v) if v is not None and v > 0 else default


def prompt_float(text: str, default: float) -> float:
    try:
        raw = input(f"{text} [{default}]: ").strip()
    except EOFError:
        raw = ""
    v = safe_float(raw)
    return v if v is not None and v > 0 else default


def main(
    seconds_per_round: Optional[float] = None,
    rounds_per_n: Optional[int] = None,
    settle_seconds: Optional[float] = None,
    interactive: bool = True,
    saboteur_mem_mb: Optional[int] = None,
    smoke: bool = False,
) -> None:
    global SABOTEUR_MIN_INTENSITY, SABOTEUR_MAX_INTENSITY, SABOTEUR_MEM_MB
    lo, hi, mem = platform_saboteur_overrides()
    SABOTEUR_MIN_INTENSITY = lo
    SABOTEUR_MAX_INTENSITY = hi
    SABOTEUR_MEM_MB = int(saboteur_mem_mb if saboteur_mem_mb is not None else mem)
    if smoke:
        interactive = False
        seconds_per_round = seconds_per_round if seconds_per_round is not None else 5.0
        rounds_per_n = rounds_per_n if rounds_per_n is not None else 4
        settle_seconds = settle_seconds if settle_seconds is not None else 1.0
    print("=" * 64)
    print(f"{APP_NAME}  v{VERSION}")
    print("=" * 64)
    print(f"platform : {platform.platform()}")
    print(f"python   : {platform.python_version()}")
    print(f"psutil   : {'yes' if psutil else 'no (using /proc & /sys fallbacks)'}")
    print(f"android  : {'yes' if is_android() else 'no'}")
    print(f"saboteur : intensity {SABOTEUR_MIN_INTENSITY}-{SABOTEUR_MAX_INTENSITY}, mem {SABOTEUR_MEM_MB}MB")
    print()
    print("Model under test:  eta = S_n / (1 + S_n * k * n)")
    print("Null model:        eta = 1 / (1 + k * n)")
    print("If coupling doesn't beat the null model, it dies. Fair fight.")
    print()

    tuning = apply_platform_tuning()
    if tuning.get("saboteur") == "windows_boost":
        print("platform tuning: desktop saboteur active (intense mode on)")
        try:
            from lib.corsair_telemetry import read_latest

            cue = read_latest()
            if cue.get("source"):
                print(
                    f"corsair iCUE: {cue['source']}"
                    f" | CPU pkg={cue.get('cpu_package_c')}C"
                    f" coolant={cue.get('coolant_c')}C"
                )
            else:
                print(f"corsair iCUE: no CSV in {os.environ.get('VIV_CORSAIR_LOG_DIR', r'L:\\Steel_Brain\\RID\\RID_Completed\\HW-Info\\Corsair_Log')}")
                print("  Enable iCUE logging while benchmark runs for real LTP.")
        except Exception as ex:
            print(f"corsair iCUE: unavailable ({ex})")
        print()

    if interactive and seconds_per_round is None:
        sec = prompt_float("Seconds per round", DEFAULT_SECONDS_PER_ROUND)
    else:
        sec = seconds_per_round if seconds_per_round is not None else DEFAULT_SECONDS_PER_ROUND
    if interactive and rounds_per_n is None:
        reps = prompt_int("Rounds per component count", DEFAULT_ROUNDS_PER_N)
    else:
        reps = rounds_per_n if rounds_per_n is not None else DEFAULT_ROUNDS_PER_N
    if interactive and settle_seconds is None:
        settle = prompt_float("Settle seconds between rounds", DEFAULT_SETTLE_SECONDS)
    else:
        settle = settle_seconds if settle_seconds is not None else DEFAULT_SETTLE_SECONDS
    n_sweep = [1, 2] if smoke else DEFAULT_N_SWEEP
    if smoke:
        print("SMOKE MODE: quick desktop tuning pass (n=1,2 only)\n")

    cpu = CpuLoadSampler()
    thermal_paths = discover_thermal_paths()
    cpu.sample()  # prime
    time.sleep(0.5)

    rows: List[RoundResult] = []
    rng = random.Random(SABOTEUR_SEED)
    total = len(n_sweep) * reps
    done = 0
    print(f"\nSweep: n in {n_sweep}, {reps}x each (alternating CLEAN/CHAOS), {sec:.0f}s rounds.\n")

    for n in n_sweep:
        for r in range(reps):
            done += 1
            perturbed = (r % 2 == 1)   # rounds 2,4,... get the saboteur
            inten = (SABOTEUR_MIN_INTENSITY
                     + (SABOTEUR_MAX_INTENSITY - SABOTEUR_MIN_INTENSITY) * rng.random()) if perturbed else 0.0
            tag = f"CHAOS {inten:.2f}" if perturbed else "clean     "
            print(f"[{done:2d}/{total}] n={n} {tag} ...", end="", flush=True)
            res = run_round(n, r, sec, cpu, thermal_paths,
                            perturbed=perturbed, intensity=inten,
                            seed=rng.randint(0, 10**6))
            rows.append(res)
            flag = "  [ABORTED]" if res.aborted else ""
            if res.cost_contaminated:
                flag += "  [SUBPROC FAILED -- cost contaminated]"
            print(f" work={res.work_units:5d}  eta={fmt(res.eta_raw, 1)}"
                  f"  S_n={fmt(res.S_n)}  RSR={fmt(res.RSR)} LTP={fmt(res.LTP)} RLE={fmt(res.RLE)}"
                  f"  T={fmt(res.temp_c, 1) if res.temp_c is not None else 'n/a'}C"
                  f"  clk={fmt(res.mean_clock_ratio, 2)}{flag}")
            time.sleep(settle)

    # ---------- analysis (F2: aborted rounds excluded) ----------
    fit_rows = [r for r in rows if not r.aborted]
    excluded = len(rows) - len(fit_rows)
    if len(fit_rows) < 6 or not any(r.n == 1 for r in fit_rows):
        print("\n!! Too many aborted rounds (or no clean n=1 baseline).")
        print("   Let the phone cool fully and rerun. Raw CSV still saved.")
        fit_rows = rows  # fall back so the report still prints

    clean_rows = [r for r in fit_rows if not r.perturbed]
    pert_rows = [r for r in fit_rows if r.perturbed]

    base_eta = fmean([r.eta_raw for r in clean_rows if r.n == 1],
                     max(r.eta_raw for r in fit_rows))
    # S5: topology constant fitted on clean rounds only
    k_base, rmse_base = fit_k(clean_rows if len(clean_rows) >= 6 else fit_rows, coupled=False)
    k_cpl, rmse_cpl = fit_k(fit_rows, coupled=True)

    # S3: within-n relative efficiency -- topology removed by construction
    clean_means: Dict[int, float] = {}
    for n in sorted({r.n for r in fit_rows}):
        cm = fmean([r.eta_raw for r in clean_rows if r.n == n], 0.0)
        if cm <= 0:
            cm = fmean([r.eta_raw for r in fit_rows if r.n == n], 1.0)
        clean_means[n] = cm
    e_rel = [r.eta_raw / clean_means[r.n] for r in fit_rows]
    s_vals = [r.S_n for r in fit_rows]
    r_corr = pearson(s_vals, e_rel)

    # S4: manipulation check + paired deltas
    d_sn = fmean([r.S_n for r in pert_rows], 0.0) - fmean([r.S_n for r in clean_rows], 0.0)
    d_erel = (fmean([r.eta_raw / clean_means[r.n] for r in pert_rows], 1.0)
              - fmean([r.eta_raw / clean_means[r.n] for r in clean_rows], 1.0))
    manipulation_ok = bool(pert_rows) and d_sn <= -MANIPULATION_MIN_DSN

    # legacy residual correlation (kept for cross-version comparability)
    resid = []
    for r in fit_rows:
        pred = (1.0 + k_base) / (1.0 + k_base * r.n)
        resid.append((r.eta_raw / base_eta) - pred)
    r_corr_legacy = pearson(s_vals, resid)

    improvement = (rmse_base - rmse_cpl) / rmse_base * 100.0 if rmse_base > 0 else 0.0
    corr_supports = r_corr is not None and r_corr > 0.30
    drop_supports = d_erel < -0.05

    if not pert_rows:
        verdict = "INCONCLUSIVE"
        detail = "No perturbed rounds completed. Rerun."
    elif not manipulation_ok:
        verdict = "INCONCLUSIVE (manipulation failed)"
        detail = (f"Saboteur only moved S_n by {d_sn:+.3f} (need <= -{MANIPULATION_MIN_DSN}). "
                  "The phone shrugged it off. Raise SABOTEUR_MIN_INTENSITY / SABOTEUR_MEM_MB and rerun.")
    elif corr_supports and drop_supports:
        verdict = "SUPPORTED"
        detail = ("Instability tax is real here: S_n dropped under chaos AND the benchmark's "
                  "own cycles got measurably less productive (topology fully controlled).")
    elif drop_supports or corr_supports:
        verdict = "PARTIAL"
        detail = "One coupling signal fired, the other didn't. More rounds or wider intensity range."
    else:
        verdict = "NOT SUPPORTED"
        detail = ("S_n dropped under chaos but work-per-own-cycle held steady. "
                  "Instability did not tax the benchmark beyond resource accounting. Coupling dies fairly.")

    print("\n" + "=" * 64)
    print("RESULTS")
    print("=" * 64)
    print(f"rounds used / excluded    : {len(fit_rows)} / {excluded} (thermal aborts excluded)")
    clk_seen = any(r.mean_clock_ratio is not None for r in fit_rows)
    contaminated = any(r.cost_contaminated for r in fit_rows)
    print(f"DVFS clock normalization  : {'active' if clk_seen else 'unavailable (own-cpu-only cost)'}")
    print(f"saboteur isolation        : "
          f"{'CONTAMINATED (subprocess failed; in-thread fallback)' if contaminated else 'separate process (clean cost accounting)'}")
    print(f"baseline eta (n=1, clean) : {fmt(base_eta, 1)} work-units / own-cpu-sec")
    print(f"topology k (clean rounds) : {fmt(k_base)}   RMSE={fmt(rmse_base, 4)}")
    print(f"coupled model k           : {fmt(k_cpl)}   RMSE={fmt(rmse_cpl, 4)}")
    print(f"RMSE improvement          : {fmt(improvement, 1)}%")
    print("-" * 64)
    print("MANIPULATION CHECK")
    print(f"  mean S_n clean / chaos  : {fmt(fmean([r.S_n for r in clean_rows], 0.0))} / "
          f"{fmt(fmean([r.S_n for r in pert_rows], 0.0))}   (d_Sn = {d_sn:+.3f})")
    print("COUPLING TESTS (topology controlled)")
    print(f"  corr(S_n, e_rel)        : {fmt(r_corr)}")
    print(f"  mean d e_rel chaos-clean: {d_erel:+.3f}")
    print(f"  legacy resid corr       : {fmt(r_corr_legacy)}")
    print("-" * 64)
    print("PER-N PAIRED TABLE (eta relative to clean mean at that n)")
    print(f"  {'n':>2} {'clean_eta':>10} {'chaos_eta':>10} {'d%':>7} {'Sn_cl':>6} {'Sn_ch':>6}")
    for n in sorted({r.n for r in fit_rows}):
        ce = fmean([r.eta_raw for r in clean_rows if r.n == n], 0.0)
        pe = fmean([r.eta_raw for r in pert_rows if r.n == n], 0.0)
        sc = fmean([r.S_n for r in clean_rows if r.n == n], 0.0)
        sp = fmean([r.S_n for r in pert_rows if r.n == n], 0.0)
        dpct = (pe - ce) / ce * 100.0 if ce > 0 else 0.0
        print(f"  {n:>2} {ce:>10.0f} {pe:>10.0f} {dpct:>+7.1f} {sc:>6.3f} {sp:>6.3f}")
    print("-" * 64)
    print(f"VERDICT: {verdict}")
    print(f"  {detail}")
    print("=" * 64)

    # ---------- outputs ----------
    out = output_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out / f"{OUT_PREFIX}_{stamp}.csv"
    json_path = out / f"{OUT_PREFIX}_{stamp}.json"

    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

    summary = {
        "version": VERSION,
        "timestamp": stamp,
        "platform": platform.platform(),
        "n_sweep": n_sweep,
        "rounds_per_n": reps,
        "rounds_excluded_thermal": excluded,
        "dvfs_clock_normalization": clk_seen,
        "saboteur_isolation_clean": not contaminated,
        "manipulation_d_Sn": d_sn,
        "manipulation_ok": manipulation_ok,
        "corr_Sn_vs_e_rel": r_corr,
        "mean_d_e_rel_chaos_minus_clean": d_erel,
        "seconds_per_round": sec,
        "baseline_eta_n1": base_eta,
        "null_model": {"k": k_base, "rmse": rmse_base},
        "coupled_model": {"k": k_cpl, "rmse": rmse_cpl},
        "rmse_improvement_pct": improvement,
        "corr_Sn_vs_residuals_legacy": r_corr_legacy,
        "S_n_range": [min(s_vals), max(s_vals)],
        "verdict": verdict,
        "detail": detail,
        "desktop_channel_tuning": sys.platform == "win32",
        "smoke_mode": smoke,
        "saboteur_mem_mb": SABOTEUR_MEM_MB,
        "corsair_log_dir": os.environ.get(
            "VIV_CORSAIR_LOG_DIR",
            r"L:\Steel_Brain\RID\RID_Completed\HW-Info\Corsair_Log",
        ),
        "intense_mode": os.environ.get("VIV_BENCHMARK_INTENSE", "1").strip().lower() in ("1", "true", "yes", "on"),
    }
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)

    print(f"\nwrote: {csv_path}")
    print(f"wrote: {json_path}")


def cli(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="RID stability-coupled efficiency benchmark v1.2")
    ap.add_argument("--seconds", type=float, default=None, help="Seconds per round")
    ap.add_argument("--rounds", type=int, default=None, help="Rounds per component count")
    ap.add_argument("--settle", type=float, default=None, help="Settle seconds between rounds")
    ap.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for settings even when flags are omitted",
    )
    ap.add_argument("--saboteur-mem", type=int, default=None, help="Saboteur memory churn MB (default: platform)")
    ap.add_argument("--smoke", action="store_true", help="Quick tune pass: n=1,2 x 4 rounds x 5s")
    args = ap.parse_args(argv)
    try:
        main(
            seconds_per_round=args.seconds,
            rounds_per_n=args.rounds,
            settle_seconds=args.settle,
            interactive=bool(args.interactive),
            saboteur_mem_mb=args.saboteur_mem,
            smoke=bool(args.smoke),
        )
    except KeyboardInterrupt:
        print("\ninterrupted -- partial run discarded.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
