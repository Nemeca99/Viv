"""AIOS systems registry — the real 20+ cores from V1 and V2.

Stops pretending Viv sandbox toys are the organism.
Sources:
  V1 archive: D:/LocalAi/AIOS_V1/
  V2 live:    L:/Continue/FSAA/Luna/AIOS_V2/
  Viv alpha:  L:/Continue/Viv/
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT, VIV_ROOT

V1_ROOT = Path(r"D:/LocalAi/AIOS_V1")
V2_ROOT = Path(r"L:/Continue/FSAA/Luna/AIOS_V2")
REGISTRY_DIR = AUTO_ARTIFACTS / "systems"
REGISTRY_JSON = REGISTRY_DIR / "AIOS_SYSTEMS_REGISTRY.json"
REGISTRY_MD = REGISTRY_DIR / "AIOS_SYSTEMS_REGISTRY.md"

# Viv capability that covers (or partially covers) each legacy core.
# status: wired | partial | legacy | missing | deferred
_V1_CORES: list[dict[str, Any]] = [
    {"id": "backup_core", "role": "self-heal / LKG backups", "priority": 40},
    {"id": "carma_core", "role": "semantic memory STM/LTM", "priority": 5, "viv": "memory_core + lib/carma_memory.py"},
    {"id": "consciousness_core", "role": "pulse / fragments / hemispheres", "priority": 20, "viv": "lib/aios_organism.py (partial)"},
    {"id": "containment", "role": "filesystem boundary guard", "priority": 8, "viv": "security_core + security_membrane"},
    {"id": "data_core", "role": "persistent data stores", "priority": 35, "viv": "artifacts/ + sandbox/work"},
    {"id": "dream_core", "role": "REM idle consolidation", "priority": 15, "viv": "lib/aios_dream.py"},
    {"id": "fractal_core", "role": "recursive multi-scale reason", "priority": 50, "deferred": True},
    {"id": "game_core", "role": "game / sim interactions", "priority": 90, "deferred": True},
    {"id": "infra_core", "role": "deploy / monitor", "priority": 55, "deferred": True},
    {"id": "luna_core", "role": "personality / converse layer", "priority": 25, "viv": "voice_core + personality DNA (partial)"},
    {"id": "main_core", "role": "OS routing / kernel", "priority": 12, "viv": "aios_main.py + three mains"},
    {"id": "marketplace_core", "role": "plugin marketplace", "priority": 95, "deferred": True},
    {"id": "music_core", "role": "music generation", "priority": 95, "deferred": True},
    {"id": "privacy_core", "role": "privacy controls", "priority": 45, "deferred": True},
    {"id": "rag_core", "role": "document RAG / ManualOracle", "priority": 6, "viv": "lib/aios_knowledge.py"},
    {"id": "security_core", "role": "immutable laws", "priority": 1, "viv": "Viv/security_core (Rust)"},
    {"id": "streamlit_core", "role": "Streamlit UI", "priority": 90, "deferred": True},
    {"id": "support_core", "role": "embed / cache / health bus", "priority": 30},
    {"id": "template_core", "role": "plugin template", "priority": 80, "deferred": True},
    {"id": "utils_core", "role": "bridges / monitoring utils", "priority": 35},
    {"id": "tools", "role": "dev tooling / codegraph", "priority": 40},
    {"id": "inbox_outbox", "role": "message I/O lanes", "priority": 18, "viv": "lib/aios_inbox.py"},
]

_V2_CORES: list[dict[str, Any]] = [
    {"id": "rid_core", "role": "FIDF physics RSR×LTP×RLE→S_n", "priority": 2, "viv": "foundation rid_main + master_rid"},
    {"id": "consciousness_core", "role": "heart/brainstem/soul/mirror", "priority": 20, "viv": "organism beat (partial)"},
    {"id": "luna_core", "role": "conscious prompt layer", "priority": 25, "viv": "voice intent packets (partial)"},
    {"id": "steel_brain_core", "role": "adversarial refinery + equilibrium judge", "priority": 4, "viv": "lib/steel_judge.py (CPU port; 3-LLM refinery still LEGACY)"},
    {"id": "governance_core", "role": "encrypted courtroom vote bus", "priority": 45, "deferred": True},
    {"id": "carma_core", "role": "Nomic vector semantic memory", "priority": 5, "viv": "memory_core phase1 (keyword)"},
    {"id": "security_core", "role": "moral governor AST+laws", "priority": 1, "viv": "Viv/security_core"},
    {"id": "tool_core", "role": "gated read/write/list/run", "priority": 3, "viv": "security_membrane.tool_gate (partial)"},
    {"id": "input_core", "role": "multimodal input normalizer", "priority": 28},
    {"id": "main_core", "role": "kernel / LTP capacity", "priority": 12, "viv": "aios_main + auto_main"},
    {"id": "audit_core", "role": "structured event audit", "priority": 22, "viv": "organism_events + auto journals (partial)"},
    {"id": "mirror_core", "role": "dashboard / introspection", "priority": 40, "viv": "aios_main status (partial)"},
    {"id": "data_core", "role": "session/data stores", "priority": 35, "viv": "artifacts/"},
    {"id": "backup_core", "role": "backup/restore", "priority": 40},
    {"id": "dream_core", "role": "idle dream cycles", "priority": 15, "viv": "lib/aios_dream.py"},
    {"id": "vision_core", "role": "stereoscopic vision/effector", "priority": 35},
    {"id": "dataset_core", "role": "global index / datasets", "priority": 10},
    {"id": "knowledge_core", "role": "knowledge absorb / harmonic filter", "priority": 7, "viv": "lib/aios_knowledge.py"},
    {"id": "sandbox_core", "role": "contained execution", "priority": 16, "viv": "Viv/sandbox + aios_coder"},
    {"id": "slm_core", "role": "small LM lane", "priority": 50, "deferred": True},
    {"id": "nox_forge_core", "role": "Rust sensory/governor DLL", "priority": 30},
]

# Current foundation adapters are the canonical skeleton wiring for cores that
# have no historical ``viv`` mapping yet. Keep explicit partial mappings above
# authoritative; this table only prevents the registry from calling an
# adapter-backed core "legacy" because the old survey predates the adapter.
_ADAPTER_FILES: dict[str, str] = {
    "backup_core": "aios_adapter_backup.py",
    "dataset_core": "aios_adapter_dataset.py",
    "input_core": "aios_adapter_input.py",
    "nox_forge_core": "aios_adapter_nox.py",
    "support_core": "aios_adapter_support.py",
    "tools": "aios_adapter_tool.py",
    "tool_core": "aios_adapter_tool.py",
    "utils_core": "aios_adapter_utils.py",
    "vision_core": "aios_adapter_vision.py",
}


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _exists(root: Path, name: str) -> bool:
    if name == "inbox_outbox":
        return (root / "inbox").is_dir() or (root / "outbox").is_dir()
    if name == "containment":
        return (root / "containment").is_dir()
    if name == "tools":
        return (root / "tools").is_dir()
    return (root / name).is_dir()


def _viv_status(entry: dict[str, Any]) -> str:
    if entry.get("deferred"):
        return "deferred"
    viv = entry.get("viv") or ""
    if not viv:
        return "legacy"
    lower = viv.lower()

    if "steel_judge" in lower:
        code = (FOUNDATION_ROOT / "lib" / "steel_judge.py").is_file()
        eq = (AUTO_ARTIFACTS / "steel_judge" / "equilibrium.json").is_file()
        if code and eq:
            return "partial"  # CPU judge live; 3-LLM refinery still LEGACY
        if code:
            return "partial"
        return "legacy"

    if "aios_knowledge" in lower:
        code = (FOUNDATION_ROOT / "lib" / "aios_knowledge.py").is_file()
        idx = (AUTO_ARTIFACTS / "knowledge" / "absorb_index.json").is_file()
        if code and idx:
            return "partial"
        if code:
            return "partial"
        return "legacy"

    checks = [
        ("security_core", VIV_ROOT / "security_core"),
        ("memory_core", VIV_ROOT / "memory_core"),
        ("voice_core", VIV_ROOT / "voice_core"),
        ("sandbox", VIV_ROOT / "sandbox"),
        ("aios_main", FOUNDATION_ROOT / "aios_main.py"),
        ("rid_main", FOUNDATION_ROOT / "rid_main.py"),
        ("aios_dream", FOUNDATION_ROOT / "lib" / "aios_dream.py"),
        ("aios_organism", FOUNDATION_ROOT / "lib" / "aios_organism.py"),
        ("aios_inbox", FOUNDATION_ROOT / "lib" / "aios_inbox.py"),
        ("carma_memory", FOUNDATION_ROOT / "lib" / "carma_memory.py"),
        ("security_membrane", FOUNDATION_ROOT / "lib" / "security_membrane.py"),
    ]
    for key, path in checks:
        if key in lower.replace("\\", "/"):
            if path.exists():
                return "partial" if "partial" in lower else "wired"
            return "missing_viv_target"
    return "partial" if "partial" in lower else "wired"


def _adapter_viv_map(core_id: str) -> str | None:
    filename = _ADAPTER_FILES.get(str(core_id))
    if not filename or not (FOUNDATION_ROOT / "lib" / filename).is_file():
        return None
    return f"foundation/lib/{filename}"


def scan_systems() -> dict[str, Any]:
    """Scan V1 + V2 trees and classify against Viv wiring."""
    v1_rows = []
    for e in _V1_CORES:
        viv_map = e.get("viv") or _adapter_viv_map(e["id"])
        classified = {**e, "viv": viv_map} if viv_map else e
        row = {
            **e,
            "generation": "V1",
            "path": str((V1_ROOT / (e["id"] if e["id"] != "inbox_outbox" else "inbox"))).replace("\\", "/"),
            "on_disk": _exists(V1_ROOT, e["id"]),
            "viv_map": viv_map,
            "status": _viv_status(classified) if viv_map or e.get("deferred") else "legacy",
        }
        if not row["on_disk"] and e["id"] != "inbox_outbox":
            row["status"] = "missing_source"
        v1_rows.append(row)

    v2_rows = []
    for e in _V2_CORES:
        viv_map = e.get("viv") or _adapter_viv_map(e["id"])
        classified = {**e, "viv": viv_map} if viv_map else e
        row = {
            **e,
            "generation": "V2",
            "path": str(V2_ROOT / e["id"]).replace("\\", "/"),
            "on_disk": _exists(V2_ROOT, e["id"]),
            "viv_map": viv_map,
            "status": _viv_status(classified) if viv_map or e.get("deferred") else "legacy",
        }
        if not row["on_disk"]:
            row["status"] = "missing_source"
        v2_rows.append(row)

    all_rows = v1_rows + v2_rows
    counts: dict[str, int] = {}
    for r in all_rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    # Absorb queue: legacy/missing_viv_target, not deferred, on_disk, lowest priority first
    queue = [
        r
        for r in all_rows
        if r["on_disk"]
        and r["status"] in {"legacy", "missing_viv_target", "partial"}
        and not r.get("deferred")
        and r["status"] != "wired"
    ]
    # Prefer pure legacy (nothing in Viv yet) over partial
    queue.sort(key=lambda r: (0 if r["status"] == "legacy" else 1, int(r.get("priority") or 99), r["id"]))

    return {
        "at": _utc(),
        "v1_root": str(V1_ROOT).replace("\\", "/"),
        "v2_root": str(V2_ROOT).replace("\\", "/"),
        "viv_root": str(VIV_ROOT).replace("\\", "/"),
        "counts": counts,
        "v1": v1_rows,
        "v2": v2_rows,
        "absorb_queue": [
            {"id": r["id"], "generation": r["generation"], "priority": r["priority"], "role": r["role"], "status": r["status"], "path": r["path"]}
            for r in queue[:15]
        ],
        "next": queue[0] if queue else None,
    }


def write_registry(report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = report or scan_systems()
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = [
        "# AIOS Systems Registry (V1 + V2 → Viv)",
        "",
        f"Generated: `{report['at']}`",
        "",
        f"- V1: `{report['v1_root']}`",
        f"- V2: `{report['v2_root']}`",
        f"- Viv: `{report['viv_root']}`",
        "",
        "## Counts",
        "",
    ]
    for k, v in sorted((report.get("counts") or {}).items()):
        lines.append(f"- **{k}**: {v}")
    lines.extend(["", "## Absorb queue (next real work)", ""])
    for q in report.get("absorb_queue") or []:
        lines.append(f"- `{q['generation']}/{q['id']}` p={q['priority']} [{q['status']}] — {q['role']}")
    nxt = report.get("next")
    if nxt:
        lines.extend(["", f"**NEXT:** `{nxt['generation']}/{nxt['id']}` — {nxt['role']}", ""])
    lines.extend(["", "## V1 cores", ""])
    for r in report.get("v1") or []:
        disk = "ON" if r.get("on_disk") else "OFF"
        lines.append(f"- `{r['id']}` [{r['status']}|{disk}] — {r['role']}")
    lines.extend(["", "## V2 cores", ""])
    for r in report.get("v2") or []:
        disk = "ON" if r.get("on_disk") else "OFF"
        lines.append(f"- `{r['id']}` [{r['status']}|{disk}] — {r['role']}")
    REGISTRY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["registry_json"] = str(REGISTRY_JSON).replace("\\", "/")
    report["registry_md"] = str(REGISTRY_MD).replace("\\", "/")
    return report


def next_absorb_target() -> dict[str, Any] | None:
    rep = scan_systems()
    return rep.get("next")
