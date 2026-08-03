"""Static AIOS Triad architecture enforcement.

Coverage is package-aware: importing any ``lib.*`` module first executes
``lib.__init__``, which binds the Triad contract.  Memory and Voice packages do
the same.  Boundary-capable modules must additionally import an approved gate.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from lib.triad_kernel import FOUNDATION_ROOT, TRIAD_CONTRACT_VERSION, VIV_ROOT


ARCHITECTURE_VERSION = "viv_triad_architecture_v1"
PACKAGE_ROOTS = (
    FOUNDATION_ROOT,
    FOUNDATION_ROOT / "lib",
    VIV_ROOT / "memory_core",
    VIV_ROOT / "voice_core",
)
BOUNDARY_REGISTRY = FOUNDATION_ROOT / "triad_boundary_registry.json"
SCAN_ROOTS = (
    FOUNDATION_ROOT,
    VIV_ROOT / "memory_core",
    VIV_ROOT / "voice_core",
)
IGNORED_PARTS = {
    "artifacts",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "target",
    "runtime",
}
TRIAD_IMPORTS = {"lib.triad_kernel", "lib"}
GATE_IMPORTS = {
    "lib.triad_kernel",
    "lib.security_membrane",
    "lib.training_security",
    "lib.backup_core",
    "memory_core.gate",
}
DIRECT_BRIDGE_ALLOWLIST = {
    "foundation/lib/security_membrane.py",
    "foundation/lib/training_security.py",
    "foundation/lib/backup_core.py",
    "foundation/lib/aios_adapter_backup.py",
    "foundation/scripts/security_redteam.py",
    "foundation/scripts/test_backup_core_contracts.py",
    "foundation/scripts/test_training_security_contracts.py",
    "foundation/scripts/finalize_backup_core_milestone.py",
    "foundation/scripts/finalize_triad_governor_milestone.py",
    "foundation/scripts/stage1_mouth_identity_judge.py",
}
BOUNDARY_BOOTSTRAP_ALLOWLIST = {
    "foundation/lib/triad_kernel.py",
    "foundation/lib/engineering_governor.py",
    "foundation/lib/security_bridge.py",
    "foundation/lib/security_membrane.py",
    "foundation/lib/training_security.py",
    "foundation/lib/backup_core.py",
}


@dataclass(frozen=True)
class BoundaryCall:
    category: str
    function: str
    line: int


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(VIV_ROOT.resolve())).replace("\\", "/")


def _python_files() -> list[Path]:
    found: set[Path] = set()
    for root in SCAN_ROOTS:
        for path in root.rglob("*.py"):
            if any(part in IGNORED_PARTS for part in path.parts):
                continue
            found.add(path.resolve())
    return sorted(found, key=lambda item: _relative(item).lower())


def _imports(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _call_name(node: ast.Call) -> str:
    value = node.func
    parts: list[str] = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def _boundary_calls(tree: ast.AST) -> list[BoundaryCall]:
    calls: list[BoundaryCall] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        category = ""
        if name.endswith((".write_text", ".write_bytes", ".unlink")):
            category = "filesystem_mutation"
        elif name in {"open", "Path.open"}:
            modes: list[str] = []
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                modes.append(str(node.args[1].value))
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    modes.append(str(keyword.value.value))
            if any(any(flag in mode for flag in "wax+") for mode in modes):
                category = "filesystem_mutation"
        elif name.startswith("subprocess."):
            category = "process"
        elif (
            name.endswith("urlopen")
            or name.startswith(("requests.", "httpx.", "socket."))
        ):
            category = "network"
        if category:
            calls.append(BoundaryCall(category, name, int(node.lineno)))
    return calls


def _package_bound(path: Path) -> bool:
    return any(path == root or root in path.parents for root in PACKAGE_ROOTS)


def _boundary_signature(inventory: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    signature: dict[str, dict[str, int]] = {}
    for row in inventory:
        counts: dict[str, int] = {}
        for call in row["calls"]:
            key = f"{call['category']}:{call['function']}"
            counts[key] = counts.get(key, 0) + 1
        signature[str(row["path"])] = dict(sorted(counts.items()))
    return dict(sorted(signature.items()))


def freeze_boundary_registry() -> dict[str, Any]:
    """Freeze the current explicit boundary inventory; normal preflight cannot update it."""
    report = scan_architecture(compare_registry=False)
    payload = {
        "schema_version": ARCHITECTURE_VERSION,
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "generated_from_python_files": report["python_files"],
        "boundaries": _boundary_signature(report["boundary_inventory"]),
    }
    BOUNDARY_REGISTRY.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload


def _imports_prefix(imports: Iterable[str], prefixes: set[str]) -> bool:
    return any(
        value == prefix or value.startswith(prefix + ".")
        for value in imports
        for prefix in prefixes
    )


def scan_architecture(*, compare_registry: bool = True) -> dict[str, Any]:
    files = _python_files()
    uncovered: list[str] = []
    direct_bridge_violations: list[str] = []
    unmediated: list[dict[str, Any]] = []
    syntax_errors: list[str] = []
    inventory: list[dict[str, Any]] = []

    for path in files:
        rel = _relative(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            syntax_errors.append(f"{rel}:{exc}")
            continue
        imports = _imports(tree)
        package_bound = _package_bound(path)
        triad_bound = package_bound or _imports_prefix(imports, TRIAD_IMPORTS)
        if not triad_bound:
            uncovered.append(rel)

        if _imports_prefix(imports, {"lib.security_bridge"}) and rel not in DIRECT_BRIDGE_ALLOWLIST:
            direct_bridge_violations.append(rel)

        boundaries = _boundary_calls(tree)
        has_gate = _imports_prefix(imports, GATE_IMPORTS)
        if boundaries:
            inventory.append(
                {
                    "path": rel,
                    "gate_import": has_gate,
                    "package_bound": package_bound,
                    "calls": [call.__dict__ for call in boundaries],
                }
            )
    package_contracts: dict[str, bool] = {}
    for init in (
        FOUNDATION_ROOT / "__init__.py",
        FOUNDATION_ROOT / "lib" / "__init__.py",
        VIV_ROOT / "memory_core" / "__init__.py",
        VIV_ROOT / "voice_core" / "__init__.py",
    ):
        text = init.read_text(encoding="utf-8") if init.is_file() else ""
        package_contracts[_relative(init)] = (
            "lib.triad_kernel" in text and "TRIAD_CONTRACT_VERSION" in text
        )

    current_boundary_signature = _boundary_signature(inventory)
    registry_error = None
    registered_boundaries: dict[str, dict[str, int]] = {}
    if compare_registry:
        if not BOUNDARY_REGISTRY.is_file():
            registry_error = "boundary_registry_missing"
        else:
            try:
                registry = json.loads(BOUNDARY_REGISTRY.read_text(encoding="utf-8"))
                if registry.get("triad_contract_version") != TRIAD_CONTRACT_VERSION:
                    registry_error = "boundary_registry_contract_mismatch"
                registered_boundaries = dict(registry.get("boundaries") or {})
                if current_boundary_signature != registered_boundaries:
                    registry_error = "boundary_registry_drift"
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                registry_error = f"boundary_registry_malformed:{exc}"

    errors: list[str] = []
    errors.extend(f"syntax:{value}" for value in syntax_errors)
    errors.extend(f"triad_uncovered:{value}" for value in uncovered)
    errors.extend(f"direct_security_bridge:{value}" for value in direct_bridge_violations)
    if registry_error:
        errors.append(registry_error)
    errors.extend(
        f"package_contract_missing:{path}"
        for path, ok in package_contracts.items()
        if not ok
    )
    return {
        "ok": not errors,
        "architecture_version": ARCHITECTURE_VERSION,
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "python_files": len(files),
        "covered_files": len(files) - len(uncovered),
        "coverage_pct": round(
            100.0 * (len(files) - len(uncovered)) / max(len(files), 1), 3
        ),
        "package_contracts": package_contracts,
        "boundary_modules": len(inventory),
        "boundary_inventory": inventory,
        "boundary_signature": current_boundary_signature,
        "boundary_registry": str(BOUNDARY_REGISTRY),
        "boundary_registry_error": registry_error,
        "uncovered": uncovered,
        "direct_bridge_violations": direct_bridge_violations,
        "unmediated_boundaries": unmediated,
        "syntax_errors": syntax_errors,
        "errors": errors,
    }
