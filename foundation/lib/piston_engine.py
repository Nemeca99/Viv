"""RID piston-core thermal control — per-core S_n and pair firing logic."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
except ImportError as exc:
    raise SystemExit("piston_core requires psutil") from exc

from lib.corsair_telemetry import read_latest, read_per_core_temps
from lib.governor_params import GovernorParams, append_history, load_params
from lib.paths import AUTO_ARTIFACTS, AUTOMATION_ROOT

PISTON_ARTIFACTS = AUTO_ARTIFACTS / "piston"
PISTON_STATE_PATH = PISTON_ARTIFACTS / "piston_state.json"
RID_LOGS = AUTOMATION_ROOT / "3_body" / "rid_logs"
SUPERVISOR_PATH = RID_LOGS / "supervisor_state.json"

# i7-11700F — 8 logical cores
# Hardware-agnostic: 0 = use every core the machine exposes. No magic core count.
MAX_CORES = int(os.environ.get("VIV_PISTON_MAX_CORES", "0"))
DORMANCY_THRESHOLD = 0.45
# Containment: presence of this flag forces the whole layer into safe state.
HALT_FLAG = AUTO_ARTIFACTS / "halt.flag"


def detect_hardware() -> dict[str, Any]:
    """Probe the machine so the layer scales to whatever hardware it runs on."""
    logical = psutil.cpu_count(logical=True) or 1
    physical = psutil.cpu_count(logical=False) or logical
    per_core = False
    package = False
    try:
        cue = read_latest()
        package = cue.get("cpu_package_c") is not None
    except (OSError, ValueError):
        pass
    try:
        temps = read_per_core_temps(n_cores=logical)
        per_core = any(t and t > 0 for t in temps)
    except (OSError, ValueError):
        pass
    if not package and hasattr(psutil, "sensors_temperatures"):
        try:
            package = bool(psutil.sensors_temperatures())
        except (OSError, AttributeError, NotImplementedError):
            pass
    return {
        "logical_cores": logical,
        "physical_cores": physical,
        "per_core_temp": per_core,
        "package_temp": package,
        "thermal": per_core or package,
    }


def make_pairs(n_cores: int) -> list[tuple[int, int]]:
    """Pair consecutive cores for any core count; odd tail pairs with itself."""
    pairs = [(i, i + 1) for i in range(0, n_cores - 1, 2)]
    if n_cores % 2 == 1:
        pairs.append((n_cores - 1, n_cores - 1))
    return pairs


def halt(reason: str = "operator") -> Path:
    """Containment: force the layer to safe state. Survives restart until resumed."""
    HALT_FLAG.parent.mkdir(parents=True, exist_ok=True)
    HALT_FLAG.write_text(
        json.dumps({"halted": True, "reason": reason, "ts": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    return HALT_FLAG


def resume() -> bool:
    """Lift containment. Returns True if a halt flag was cleared."""
    if HALT_FLAG.is_file():
        HALT_FLAG.unlink()
        return True
    return False


def is_halted() -> bool:
    return HALT_FLAG.is_file()


def sn_to_budget(s_n: float, params: GovernorParams | None = None) -> float:
    """Map S_n to allowed CPU fraction. S_n=1 -> 100%, S_n=0 -> 0% (or floor).

    Below the dormancy threshold the budget collapses to the floor (fail-closed).
    """
    p = params or load_params()
    if s_n < DORMANCY_THRESHOLD:
        return _clamp(p.budget_floor)
    return _clamp(max(p.budget_floor, s_n))


@dataclass
class CoreRid:
    core: int
    temp_c: float
    load_pct: float
    rsr: float
    ltp: float
    rle: float
    s_n: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PistonState:
    timestamp: str
    beat: int
    n_cores: int
    pairs: list[tuple[int, int]]
    active_by_pair: dict[str, int]
    firing_order: list[int]
    cores: list[CoreRid]
    package_s_n: float
    package_budget_pct: float = 100.0
    budget_by_core: dict[str, float] = field(default_factory=dict)
    thermal_mode: str = "real"
    halted: bool = False
    swaps: list[dict[str, Any]] = field(default_factory=list)
    coolant_c: Optional[float] = None
    stress_pid: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cores"] = [c.to_dict() if isinstance(c, CoreRid) else c for c in self.cores]
        d["pairs"] = [list(p) for p in self.pairs]
        return d


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_core_rid(
    core: int,
    temp_c: float,
    prev_temp_c: float,
    load_pct: float,
    partner_load_pct: float,
    *,
    thermal: bool = True,
    params: GovernorParams | None = None,
) -> CoreRid:
    p = params or load_params()
    rle = _clamp(1.0 - abs(load_pct - partner_load_pct) / 100.0)
    if thermal:
        delta_t = temp_c - prev_temp_c
        rsr = _clamp(1.0 - delta_t / max(p.max_delta_c, 0.1))
        ltp = _clamp(1.0 - temp_c / max(p.t_max_c, 1.0))
    else:
        rsr = 1.0
        ltp = _clamp(1.0 - load_pct / 100.0)
    sn = (max(rsr, 1e-6) * max(ltp, 1e-6) * max(rle, 1e-6)) ** (1.0 / 3.0)
    return CoreRid(core=core, temp_c=temp_c, load_pct=load_pct, rsr=rsr, ltp=ltp, rle=rle, s_n=sn)


def read_loads(n_cores: int) -> list[float]:
    per = psutil.cpu_percent(interval=0.15, percpu=True)
    if not per:
        return [0.0] * n_cores
    out = [float(x) for x in per[:n_cores]]
    while len(out) < n_cores:
        out.append(0.0)
    return out


class PistonController:
    def __init__(
        self,
        pairs: list[tuple[int, int]] | None = None,
        *,
        n_cores: int | None = None,
    ) -> None:
        cap = detect_hardware()
        self.capabilities = cap
        avail = cap["logical_cores"]
        if n_cores is not None:
            self.n_cores = n_cores
        elif MAX_CORES > 0:
            self.n_cores = min(MAX_CORES, avail)
        else:
            self.n_cores = avail  # hardware-agnostic: use all cores
        self.pairs = pairs or make_pairs(self.n_cores)
        self.thermal_mode = "real" if cap["thermal"] else "degraded_load_only"
        self.active_by_pair: dict[int, int] = {i: p[0] for i, p in enumerate(self.pairs)}
        self._prev_temps: list[float] = [0.0] * self.n_cores
        self._beat = 0
        self._firing_index = 0
        self._ema_budget: dict[int, float] = {}
        self._params = load_params()

    def reload_params(self) -> GovernorParams:
        self._params = load_params()
        return self._params

    def _partner(self, core: int) -> int:
        for a, b in self.pairs:
            if core == a:
                return b
            if core == b:
                return a
        return core

    def _pair_index(self, core: int) -> int:
        for i, (a, b) in enumerate(self.pairs):
            if core in (a, b):
                return i
        return -1

    def _sanitize_temps(self, temps: list[float]) -> list[float]:
        """A phantom <=0C reading is stale telemetry, never real for a live core.

        Fail-closed: substitute last-good temp, else the hottest observed core,
        else T_MAX. Never let a 0C phantom unlock CPU budget.
        """
        valid = [t for t in temps if t and t > 0]
        fallback = max(valid) if valid else self._params.t_max_c
        out: list[float] = []
        for i, t in enumerate(temps):
            if t and t > 0:
                out.append(t)
            elif self._prev_temps[i] > 0:
                out.append(self._prev_temps[i])
            else:
                out.append(fallback)
        return out

    def tick(self) -> PistonState:
        self._beat += 1
        p = self._params
        halted = is_halted()
        thermal = self.capabilities["thermal"]
        temps = read_per_core_temps(n_cores=self.n_cores)
        if thermal:
            temps = self._sanitize_temps(temps)
        loads = read_loads(self.n_cores)
        cue = read_latest()
        swaps: list[dict[str, Any]] = []

        cores: list[CoreRid] = []
        for i in range(self.n_cores):
            partner = self._partner(i)
            prev = self._prev_temps[i] if self._prev_temps[i] > 0 else temps[i]
            cores.append(
                compute_core_rid(
                    i, temps[i], prev, loads[i], loads[partner], thermal=thermal, params=p
                )
            )

        for pair_idx, (a, b) in enumerate(self.pairs):
            active = self.active_by_pair[pair_idx]
            partner = b if active == a else a
            active_rid = cores[active]
            if active_rid.s_n < p.swap_s_n:
                self.active_by_pair[pair_idx] = partner
                swaps.append(
                    {
                        "pair": pair_idx,
                        "from_core": active,
                        "to_core": partner,
                        "s_n": round(active_rid.s_n, 4),
                        "reason": "s_n_below_threshold",
                    }
                )

        self._prev_temps = list(temps)

        # Staggered firing order: rotate which pair is "lead" each beat
        self._firing_index = (self._firing_index + 1) % max(1, len(self.pairs))
        firing_order = []
        for offset in range(len(self.pairs)):
            idx = (self._firing_index + offset) % len(self.pairs)
            firing_order.append(self.active_by_pair[idx])

        pkg_sn = sum(c.s_n for c in cores) / max(1, len(cores))

        # Governor: S_n -> allowed CPU budget per core, EMA-smoothed to damp oscillation.
        # Containment override: a halt flag forces every budget to the floor.
        budget_by_core: dict[str, float] = {}
        for c in cores:
            target = 0.0 if halted else sn_to_budget(c.s_n, p)
            prev_b = self._ema_budget.get(c.core, target)
            smoothed = target if halted else (1.0 - p.budget_ema) * prev_b + p.budget_ema * target
            self._ema_budget[c.core] = smoothed
            budget_by_core[str(c.core)] = round(smoothed * 100.0, 1)
        package_budget = 0.0 if halted else sn_to_budget(pkg_sn, p) * 100.0

        return PistonState(
            timestamp=datetime.now(timezone.utc).isoformat(),
            beat=self._beat,
            n_cores=self.n_cores,
            pairs=self.pairs,
            active_by_pair={str(k): v for k, v in self.active_by_pair.items()},
            firing_order=firing_order,
            cores=cores,
            package_s_n=pkg_sn,
            package_budget_pct=round(package_budget, 1),
            budget_by_core=budget_by_core,
            thermal_mode=self.thermal_mode,
            halted=halted,
            swaps=swaps,
            coolant_c=cue.get("coolant_c"),
        )

    def core_budget(self, core: int) -> float:
        """Latest smoothed allowed CPU fraction [0,1] for a core."""
        return self._ema_budget.get(core, 1.0)

    def set_affinity(self, pid: int, core: int) -> bool:
        try:
            psutil.Process(pid).cpu_affinity([core])
            return True
        except (psutil.Error, OSError, AttributeError):
            return False


def write_piston_state(state: PistonState) -> Path:
    PISTON_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2)
    tmp = PISTON_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(PISTON_STATE_PATH)
    params = load_params()
    max_temp = max((c.temp_c for c in state.cores), default=0.0)
    append_history(
        {
            "ts": state.timestamp,
            "beat": state.beat,
            "package_s_n": round(state.package_s_n, 4),
            "package_budget_pct": state.package_budget_pct,
            "max_temp_c": round(max_temp, 1),
            "thermal_mode": state.thermal_mode,
            "halted": state.halted,
            "swaps": state.swaps,
            "params_version": params.version,
        }
    )
    return PISTON_STATE_PATH


def journal_piston_event(state: PistonState) -> None:
    import sys

    body = str(AUTOMATION_ROOT / "3_body")
    if body not in sys.path:
        sys.path.insert(0, body)
    from rid_core import RIDTriple
    from rid_event_schema import RIDEvent, append_event
    from rid_supervisor import write_state

    events_path = RID_LOGS / "events.jsonl"
    worst = min(state.cores, key=lambda c: c.s_n)
    rid = RIDTriple(
        rsr=worst.rsr,
        ltp=worst.ltp,
        rle=worst.rle,
        s_n=worst.s_n,
        verdict="danger" if worst.s_n < DORMANCY_THRESHOLD else "stable",
        control="throttle" if worst.s_n < load_params().swap_s_n else "allow",
    )
    event = RIDEvent(
        run_id="viv_piston",
        subsystem="runtime",
        source="piston_core",
        phase="firing_tick",
        risk="low",
        reversible=True,
        rid=rid,
        metrics={
            "beat": state.beat,
            "firing_order": state.firing_order,
            "active_by_pair": state.active_by_pair,
            "package_s_n": round(state.package_s_n, 4),
            "cpu_budget_pct": state.package_budget_pct,
            "budget_by_core": state.budget_by_core,
            "thermal_mode": state.thermal_mode,
            "halted": state.halted,
            "swaps": state.swaps,
            "s_n_by_core": {str(c.core): round(c.s_n, 4) for c in state.cores},
            "temp_by_core": {str(c.core): round(c.temp_c, 1) for c in state.cores},
            "coolant_c": state.coolant_c,
        },
        notes=[f"piston beat {state.beat} swaps={len(state.swaps)}"],
    )
    events_path.parent.mkdir(parents=True, exist_ok=True)
    append_event(events_path, event)
    write_state(events_path, SUPERVISOR_PATH)


def piston_pulse(*, journal: bool = True) -> dict[str, Any]:
    """One piston tick for automation spine integration."""
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = PistonController()
    state = _CONTROLLER.tick()
    path = write_piston_state(state)
    if journal:
        journal_piston_event(state)
    return {
        "beat": state.beat,
        "firing_order": state.firing_order,
        "package_s_n": round(state.package_s_n, 4),
        "cpu_budget_pct": state.package_budget_pct,
        "budget_by_core": state.budget_by_core,
        "swaps": state.swaps,
        "state_path": str(path),
        "line": format_status_line(state),
    }


_CONTROLLER: PistonController | None = None


def format_status_line(state: PistonState) -> str:
    active = ",".join(str(c) for c in state.firing_order)
    worst = min(state.cores, key=lambda c: c.s_n)
    swap = f" swaps={len(state.swaps)}" if state.swaps else ""
    flags = ""
    if state.halted:
        flags += " HALTED"
    if state.thermal_mode != "real":
        flags += f" thermal={state.thermal_mode}"
    return (
        f"[PISTON] beat={state.beat} firing=[{active}] "
        f"pkg_S_n={state.package_s_n:.3f} cpu_budget={state.package_budget_pct:.0f}% "
        f"min_core={worst.core}@{worst.s_n:.3f}{swap}{flags}"
    )
