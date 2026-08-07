"""Thin AIOS skeleton integration bus — slots for later compute-core wire-in.

Compute core (operator: "brain") = UML Nested-PEMDAS + RID/PID plant +
mouth/security surfaces. This module only defines wiring slots; it does not
start AIOS, train, or sample the plant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from lib.aios_skeleton_stub import skeleton_cpu_plan

SCHEMA_VERSION = "aios_skeleton_bus_v1"

# Canonical slots the compute core will plug into later.
BUS_SLOTS: tuple[str, ...] = (
    "security_in",
    "security_out",
    "uml_invoke",
    "rid_sample",
    "mouth_render",
    "memory_plan",
    "dream_plan",
    "subagent_spawn",
    "plant_health",
    # Phase 5 / 7 / 8 structural slots (overnight gap fill; plan-only stubs).
    "perception_plan",
    "ethics_plan",
    "federation_plan",
    "hardware_plan",
)

# Which cores / adapters currently fill a slot (honest: vacant = compute wire-in).
_SLOT_BINDINGS: dict[str, dict[str, Any]] = {
    "security_in": {
        "bound": True,
        "source": "lib.security_membrane / security_core (Rust)",
        "adapter": "aios_adapter_security",
        "fill": "PARTIAL",
        "note": "Membrane present; bus calls adapter cpu_plan only",
    },
    "security_out": {
        "bound": True,
        "source": "lib.security_membrane / security_core (Rust)",
        "adapter": "aios_adapter_security",
        "fill": "PARTIAL",
        "note": "Same envelope as security_in; OUT path not separately wired here",
    },
    "uml_invoke": {
        "bound": True,
        "source": "lib.uml_engine via lib.aios_adapter_uml_invoke",
        "adapter": "aios_adapter_uml_invoke",
        "fill": "PARTIAL",
        "note": "Bound: evaluate+verify one expression; speak solve path attaches evidence facts",
    },
    "rid_sample": {
        "bound": True,
        "source": "lib.aios_adapter_rid",
        "adapter": "aios_adapter_rid",
        "fill": "PARTIAL",
        "note": "status/observe only — no 120s stress from bus",
    },
    "mouth_render": {
        "bound": True,
        "source": "lib.aios_adapter_luna / voice_core",
        "adapter": "aios_adapter_luna",
        "fill": "PARTIAL",
        "note": "communication_plan / cpu_plan; no speak",
    },
    "memory_plan": {
        "bound": True,
        "source": "lib.aios_adapter_carma",
        "adapter": "aios_adapter_carma",
        "fill": "PARTIAL",
        "note": "plan-only fixtures; no live remember",
    },
    "dream_plan": {
        "bound": True,
        "source": "lib.aios_adapter_dream",
        "adapter": "aios_adapter_dream",
        "fill": "PARTIAL",
        "note": "cycle_plan / cpu_plan; no dream execute",
    },
    "subagent_spawn": {
        "bound": True,
        "source": "lib.aios_subagent_v1 / scripts/run_aios_subagent_v1.py",
        "adapter": "aios_subagent_v1",
        "fill": "BOUND",
        "note": "Skeleton worker bus: plan-only/SKIP spawn with receipts; not deep cognition",
    },
    "plant_health": {
        "bound": True,
        "source": "lib.foundation_health / rid plant observe",
        "adapter": "aios_adapter_rid",
        "fill": "PARTIAL",
        "note": "Cheap gate only; no stressed 120s capture",
    },
    "perception_plan": {
        "bound": True,
        "source": "lib.aios_adapter_perception (multi-sense skeleton)",
        "adapter": "aios_adapter_perception",
        "fill": "PARTIAL",
        "note": "Phase 5: vision/text may be PARTIAL; hearing SKELETON; no capture",
    },
    "ethics_plan": {
        "bound": True,
        "source": "lib.aios_adapter_ethics (ethics+adaptive skeleton)",
        "adapter": "aios_adapter_ethics",
        "fill": "PARTIAL",
        "note": "Phase 7 vacant ethics/adaptive; dream stays on service bus",
    },
    "federation_plan": {
        "bound": True,
        "source": "lib.aios_adapter_federation (node_federation* survey)",
        "adapter": "aios_adapter_federation",
        "fill": "PARTIAL",
        "note": "Phase 8: plan-only HOLD; no endpoint activation",
    },
    "hardware_plan": {
        "bound": True,
        "source": "lib.aios_adapter_infra (hardware-agnostic CI/deploy plan)",
        "adapter": "aios_adapter_infra",
        "fill": "PARTIAL",
        "note": "Phase 8: reuse infra_core; no multi-node execute",
    },
}


@dataclass
class SkeletonBus:
    """Callable-or-None slots + receipt fields."""

    slots: dict[str, Callable[..., Any] | None] = field(default_factory=dict)
    meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in BUS_SLOTS:
            self.slots.setdefault(name, None)
            self.meta.setdefault(name, dict(_SLOT_BINDINGS.get(name) or {}))

    def bind(self, slot: str, fn: Callable[..., Any] | None, *, note: str | None = None) -> None:
        if slot not in BUS_SLOTS:
            raise KeyError(f"unknown bus slot: {slot}")
        self.slots[slot] = fn
        info = self.meta.setdefault(slot, {})
        info["bound"] = fn is not None
        info["fill"] = "BOUND" if fn is not None else "VACANT"
        if note:
            info["note"] = note

    def wire_status(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        bound = vacant = partial = 0
        for name in BUS_SLOTS:
            fn = self.slots.get(name)
            info = dict(self.meta.get(name) or _SLOT_BINDINGS.get(name) or {})
            is_bound = fn is not None or bool(info.get("bound"))
            fill = str(info.get("fill") or ("BOUND" if fn is not None else "VACANT"))
            # Prefer live callable binding over static declaration.
            if fn is not None:
                fill = "BOUND" if fill == "VACANT" else fill
                is_bound = True
            elif fill == "PARTIAL" and info.get("bound"):
                is_bound = True
            if fill == "VACANT" or not is_bound:
                vacant += 1
                fill = "VACANT"
                is_bound = False
            elif fill == "PARTIAL":
                partial += 1
            else:
                bound += 1
                fill = "BOUND"
            rows.append(
                {
                    "slot": name,
                    "bound": is_bound,
                    "fill": fill,
                    "callable_present": fn is not None,
                    "source": info.get("source"),
                    "adapter": info.get("adapter"),
                    "note": info.get("note"),
                    "for_compute_core_wire_in": fill == "VACANT",
                }
            )
        total = len(BUS_SLOTS)
        filled = total - vacant
        return {
            "schema_version": SCHEMA_VERSION,
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "slots_total": total,
            "slots_bound_or_partial": filled,
            "slots_vacant": vacant,
            "slots_bound": bound,
            "slots_partial": partial,
            "pct_filled": round(100.0 * filled / total, 1) if total else 0.0,
            "pct_vacant": round(100.0 * vacant / total, 1) if total else 0.0,
            "vacant_for_compute_core": [r["slot"] for r in rows if r["fill"] == "VACANT"],
            "rows": rows,
        }


def _try_import_cpu_plan(module: str) -> Callable[..., Any] | None:
    try:
        import importlib

        mod = importlib.import_module(module)
        fn = getattr(mod, "cpu_plan", None)
        if callable(fn):
            return fn  # type: ignore[return-value]
        # Fallbacks used by some adapters.
        for alt in ("cycle_plan", "communication_plan", "status"):
            alt_fn = getattr(mod, alt, None)
            if callable(alt_fn):
                return alt_fn  # type: ignore[return-value]
    except Exception:  # noqa: BLE001 — bus must stay fail-soft
        return None
    return None


def _subagent_spawn_slot(
    profile: str = "selftest_ping",
    *,
    plan_only: bool = True,
    write: bool = False,
    objective_id: str | None = None,
    parent_turn_token_id: str | None = None,
    timeout_s: float | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Bus slot callable → real skeleton subagent runner (plan-first)."""
    from lib.aios_subagent_v1 import run_subagent

    return run_subagent(
        profile,
        objective_id=objective_id,
        parent_turn_token_id=parent_turn_token_id,
        timeout_s=timeout_s,
        plan_only=plan_only,
        execute=False,
        write=write,
    )


def default_bus() -> SkeletonBus:
    """Build bus with existing automation as filled slots; leave compute slots vacant."""
    bus = SkeletonBus()
    # security_in / security_out share adapter when present
    sec = _try_import_cpu_plan("lib.aios_adapter_security")
    bus.bind("security_in", sec, note=_SLOT_BINDINGS["security_in"]["note"])
    bus.bind("security_out", sec, note=_SLOT_BINDINGS["security_out"]["note"])
    from lib.aios_adapter_uml_invoke import uml_invoke_slot

    bus.bind(
        "uml_invoke",
        uml_invoke_slot,
        note=_SLOT_BINDINGS["uml_invoke"]["note"],
    )
    bus.meta["uml_invoke"]["source"] = _SLOT_BINDINGS["uml_invoke"]["source"]
    bus.meta["uml_invoke"]["adapter"] = _SLOT_BINDINGS["uml_invoke"]["adapter"]
    bus.meta["uml_invoke"]["fill"] = "PARTIAL"
    bus.meta["uml_invoke"]["bound"] = True
    rid = _try_import_cpu_plan("lib.aios_adapter_rid")
    bus.bind("rid_sample", rid, note=_SLOT_BINDINGS["rid_sample"]["note"])
    mouth = _try_import_cpu_plan("lib.aios_adapter_luna")
    bus.bind("mouth_render", mouth, note=_SLOT_BINDINGS["mouth_render"]["note"])
    mem = _try_import_cpu_plan("lib.aios_adapter_carma")
    bus.bind("memory_plan", mem, note=_SLOT_BINDINGS["memory_plan"]["note"])
    dream = _try_import_cpu_plan("lib.aios_adapter_dream")
    bus.bind("dream_plan", dream, note=_SLOT_BINDINGS["dream_plan"]["note"])
    # subagent_spawn → real skeleton worker bus (aios_subagent_v1)
    bus.bind(
        "subagent_spawn",
        _subagent_spawn_slot,
        note=_SLOT_BINDINGS["subagent_spawn"]["note"],
    )
    bus.meta["subagent_spawn"]["source"] = _SLOT_BINDINGS["subagent_spawn"]["source"]
    bus.meta["subagent_spawn"]["adapter"] = _SLOT_BINDINGS["subagent_spawn"]["adapter"]
    plant = rid
    bus.bind("plant_health", plant, note=_SLOT_BINDINGS["plant_health"]["note"])
    perception = _try_import_cpu_plan("lib.aios_adapter_perception")
    bus.bind("perception_plan", perception, note=_SLOT_BINDINGS["perception_plan"]["note"])
    ethics = _try_import_cpu_plan("lib.aios_adapter_ethics")
    bus.bind("ethics_plan", ethics, note=_SLOT_BINDINGS["ethics_plan"]["note"])
    federation = _try_import_cpu_plan("lib.aios_adapter_federation")
    bus.bind("federation_plan", federation, note=_SLOT_BINDINGS["federation_plan"]["note"])
    hardware = _try_import_cpu_plan("lib.aios_adapter_infra")
    bus.bind("hardware_plan", hardware, note=_SLOT_BINDINGS["hardware_plan"]["note"])
    # Restore static fill labels for partial bindings even when callable exists.
    # Never wipe BOUND callables (e.g. subagent_spawn, uml_invoke).
    for slot, info in _SLOT_BINDINGS.items():
        if info.get("fill") == "PARTIAL" and bus.slots.get(slot) is not None:
            bus.meta[slot]["fill"] = "PARTIAL"
            bus.meta[slot]["bound"] = True
        elif info.get("fill") == "BOUND" and bus.slots.get(slot) is not None:
            bus.meta[slot]["fill"] = "BOUND"
            bus.meta[slot]["bound"] = True
        elif info.get("fill") == "VACANT":
            bus.meta[slot]["fill"] = "VACANT"
            bus.meta[slot]["bound"] = False
            bus.slots[slot] = None
    return bus


def vacant_slot_stub(slot: str) -> dict[str, Any]:
    return skeleton_cpu_plan(
        core_id=f"bus:{slot}",
        role=f"skeleton bus slot {slot}",
        build_state="SKELETON",
        notes=f"VACANT — reserved for compute-core wire-in ({slot})",
        bus_slots=[slot],
    )
