"""Bulk manual contract map for the AIOS core rebuild.

This is the shared skeleton for the bulk pass.  It records the acceptance
surface for every manual-defined core and reports whether Viv has a concrete
adapter, a partial adapter, or only a referenced source.  It is an inventory
and test contract, not a claim that a missing implementation is complete.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lib.paths import FOUNDATION_ROOT, VIV_ROOT


MANUAL_SOURCE = "F:/AIOS_Clean/AIOS_MANUAL.md"


@dataclass(frozen=True)
class CoreContract:
    core_id: str
    role: str
    acceptance: tuple[str, ...]
    source_paths: tuple[str, ...]
    viv_surfaces: tuple[str, ...]
    priority: int


CORE_CONTRACTS: tuple[CoreContract, ...] = (
    CoreContract("luna_core", "identity and response planning", ("identity", "routing", "budget", "containment"), ("F:/AIOS_Clean/luna_core", "D:/LocalAi/AIOS_V1/luna_core"), ("foundation/lib/luna_core.py",), 25),
    CoreContract("carma_core", "semantic memory and consolidation", ("fragment", "retrieve", "stm_ltm", "provenance"), ("F:/AIOS_Clean/carma_core", "D:/LocalAi/AIOS_V1/carma_core"), ("foundation/lib/carma_core.py", "memory_core"), 5),
    CoreContract("dream_core", "idle consolidation and optimization", ("schedule", "consolidate", "archive", "metrics"), ("F:/AIOS_Clean/dream_core", "D:/LocalAi/AIOS_V1/dream_core"), ("foundation/lib/aios_dream.py",), 15),
    CoreContract("data_core", "durable structured data stores", ("schema", "integrity", "provenance", "recovery"), ("F:/AIOS_Clean/data_core", "D:/LocalAi/AIOS_V1/data_core"), ("foundation/artifacts",), 35),
    CoreContract("support_core", "shared health and model support", ("health", "cache", "diagnostics"), ("F:/AIOS_Clean/support_core", "D:/LocalAi/AIOS_V1/support_core"), ("foundation/lib/aios_adapter_support.py",), 30),
    CoreContract("utils_core", "bridges and monitoring utilities", ("bridge", "monitor", "bounded_io"), ("F:/AIOS_Clean/utils_core", "D:/LocalAi/AIOS_V1/utils_core"), ("foundation/lib/aios_adapter_utils.py",), 35),
    CoreContract("enterprise_core", "enterprise policy and integrations", ("policy", "integration", "audit"), ("F:/AIOS_Clean/enterprise_core", "D:/LocalAi/AIOS_V1/enterprise_core"), ("foundation/lib/cpu_enterprise_policy.py", "foundation/lib/aios_adapter_audit.py"), 70),
    CoreContract("rag_core", "provenance-preserving document retrieval", ("index", "retrieve", "source_hash", "abstain"), ("F:/AIOS_Clean/rag_core", "D:/LocalAi/AIOS_V1/rag_core"), ("foundation/lib/manual_oracle.py", "foundation/lib/aios_adapter_knowledge.py"), 6),
    CoreContract("streamlit_core", "operator UI", ("status", "read_only", "audit"), ("F:/AIOS_Clean/streamlit_core", "D:/LocalAi/AIOS_V1/streamlit_core"), (), 90),
    CoreContract("backup_core", "immutable backup and restore", ("snapshot", "hash", "restore", "rollback"), ("F:/AIOS_Clean/backup_core", "D:/LocalAi/AIOS_V1/backup_core"), ("foundation/lib/backup_core.py",), 40),
    CoreContract("fractal_core", "recursive multi-scale reasoning", ("recursion", "bounded_depth", "cost"), ("F:/AIOS_Clean/fractal_core", "D:/LocalAi/AIOS_V1/fractal_core"), ("foundation/lib/cpu_fractal_reasoner.py", "foundation/lib/cpu_reasoning_pipeline.py"), 50),
    CoreContract("game_core", "simulation and interaction", ("simulation", "determinism", "sandbox"), ("F:/AIOS_Clean/game_core", "D:/LocalAi/AIOS_V1/game_core"), ("foundation/lib/cpu_choice_simulator.py", "foundation/lib/agentic_runtime.py"), 90),
    CoreContract("marketplace_core", "plugin discovery and policy", ("manifest", "trust", "install_gate"), ("F:/AIOS_Clean/marketplace_core", "D:/LocalAi/AIOS_V1/marketplace_core"), (), 95),
    CoreContract("music_core", "music peripheral", ("routing", "sandbox", "output_gate"), ("F:/AIOS_Clean/music_core", "D:/LocalAi/AIOS_V1/music_core"), (), 95),
    CoreContract("privacy_core", "privacy controls", ("redaction", "consent", "audit"), ("F:/AIOS_Clean/privacy_core", "D:/LocalAi/AIOS_V1/privacy_core"), ("foundation/lib/cpu_privacy_policy.py", "foundation/lib/aios_adapter_privacy.py"), 45),
    CoreContract("template_core", "extension templates", ("schema", "validation", "isolation"), ("F:/AIOS_Clean/template_core", "D:/LocalAi/AIOS_V1/template_core"), (), 80),
    CoreContract("main_core", "kernel routing", ("boot", "queue", "health", "shutdown"), ("F:/AIOS_Clean/main_core", "D:/LocalAi/AIOS_V1/main_core"), ("foundation/aios_main.py", "foundation/auto_main.py"), 12),
    CoreContract("infra_core", "deployment and monitoring", ("health", "lkg", "rollback"), ("F:/AIOS_Clean/infra_core", "D:/LocalAi/AIOS_V1/infra_core"), ("foundation/lib/cpu_infra_ops_judge.py", "foundation/lib/foundation_health.py"), 55),
    CoreContract("consciousness_core", "pulse, fragments, memory, mirror", ("pulse", "fragments", "stm_ltm", "mirror", "drift"), ("F:/AIOS_Clean/consciousness_core", "D:/LocalAi/AIOS_V1/consciousness_core"), ("foundation/lib/consciousness_core.py", "foundation/lib/aios_adapter_consciousness.py"), 20),
    CoreContract("rid_core", "stability physics", ("freshness", "sn", "lease", "receipts"), ("F:/AIOS_Clean/rid_core", "D:/LocalAi/AIOS_V1/rid_core"), ("foundation/rid_main.py", "foundation/lib/master_rid.py"), 2),
    CoreContract("security_core", "immutable laws and membrane", ("deny", "audit", "rollback", "authority"), ("F:/AIOS_Clean/security_core", "D:/LocalAi/AIOS_V1/security_core"), ("security_core", "foundation/lib/security_membrane.py"), 1),
    CoreContract("tool_core", "gated tools", ("read", "write", "list", "run", "deny"), ("F:/AIOS_Clean/tool_core", "D:/LocalAi/AIOS_V1/tool_core"), ("foundation/lib/aios_adapter_tool.py",), 3),
    CoreContract("input_core", "input normalization", ("schema", "normalize", "provenance"), ("F:/AIOS_Clean/input_core", "D:/LocalAi/AIOS_V1/input_core"), ("foundation/lib/aios_adapter_input.py",), 28),
    CoreContract("audit_core", "structured audit events", ("append", "chain", "query", "evidence"), ("F:/AIOS_Clean/audit_core", "D:/LocalAi/AIOS_V1/audit_core"), ("foundation/artifacts/audit",), 22),
    CoreContract("mirror_core", "introspection dashboard", ("read_only", "state", "drift", "evidence"), ("F:/AIOS_Clean/mirror_core", "D:/LocalAi/AIOS_V1/mirror_core"), ("foundation/lib/aios_adapter_consciousness.py",), 40),
    CoreContract("vision_core", "vision peripheral", ("input", "normalization", "sandbox"), ("F:/AIOS_Clean/vision_core", "D:/LocalAi/AIOS_V1/vision_core"), ("foundation/lib/aios_adapter_vision.py",), 35),
    CoreContract("dataset_core", "dataset indexing and provenance", ("manifest", "hash", "scope", "replay"), ("F:/AIOS_Clean/dataset_core", "D:/LocalAi/AIOS_V1/dataset_core"), ("foundation/lib/aios_adapter_dataset.py",), 10),
    CoreContract("knowledge_core", "knowledge absorption", ("source", "verify", "route", "abstain"), ("F:/AIOS_Clean/knowledge_core", "D:/LocalAi/AIOS_V1/knowledge_core"), ("foundation/lib/aios_knowledge.py",), 7),
    CoreContract("sandbox_core", "contained execution", ("contain", "budget", "rollback", "evidence"), ("F:/AIOS_Clean/sandbox_core", "D:/LocalAi/AIOS_V1/sandbox_core", "F:/AIOS_Clean/main_core/audit_core/sandbox_security.py", "D:/LocalAi/AIOS_V1/containment/filesystem_guard.py"), ("sandbox", "foundation/lib/cpu_sandbox_boundary.py", "foundation/lib/aios_coder.py"), 16),
    CoreContract("steel_brain_core", "adversarial CPU judge", ("compare", "deny", "equilibrium", "non_authority"), ("F:/AIOS_Clean/steel_brain_core", "D:/LocalAi/AIOS_V1/steel_brain_core"), ("foundation/lib/steel_judge.py",), 4),
    CoreContract("governance_core", "authority and votes", ("quorum", "authority", "audit", "deny"), ("F:/AIOS_Clean/governance_core", "D:/LocalAi/AIOS_V1/governance_core"), ("foundation/lib/autonomy_gate.py",), 45),
    CoreContract("nox_forge_core", "Rust sensory governor", ("ffi", "hash", "safety", "rollback"), ("F:/AIOS_Clean/nox_forge_core", "D:/LocalAi/AIOS_V1/nox_forge_core"), ("foundation/lib/aios_adapter_nox.py",), 30),
    CoreContract("slm_core", "small model peripheral", ("catalog", "cpu", "non_authority"), ("F:/AIOS_Clean/slm_core", "D:/LocalAi/AIOS_V1/slm_core"), ("foundation/lib/cpu_model_registry.py",), 50),
)


def _exists(relative: str) -> bool:
    if relative.startswith("foundation/"):
        return (VIV_ROOT / relative).exists()
    return (VIV_ROOT / relative).exists()


def contract_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for contract in CORE_CONTRACTS:
        surfaces = [surface for surface in contract.viv_surfaces if _exists(surface)]
        state = "wired" if surfaces and len(surfaces) == len(contract.viv_surfaces) else ("partial" if surfaces else "source_only")
        rows.append({**asdict(contract), "acceptance": list(contract.acceptance), "source_paths": list(contract.source_paths), "viv_surfaces": list(contract.viv_surfaces), "present_surfaces": surfaces, "state": state})
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return {"ok": True, "manual_source": MANUAL_SOURCE, "contract_count": len(rows), "counts": counts, "cores": rows, "training_authorized": False, "llm_authority": False}


def get_contract(core_id: str) -> dict[str, Any] | None:
    for contract in CORE_CONTRACTS:
        if contract.core_id == str(core_id):
            return asdict(contract)
    return None
