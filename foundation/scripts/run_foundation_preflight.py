"""Cross-layer CPU preflight for the Viv hardening milestone."""
from __future__ import annotations

import ast
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
VENV_PYTHON = ROOT.parents[1] / ".venv" / "Scripts" / "python.exe"
PYTHON = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
PYTHON_ROOTS = (ROOT, REPO / "memory_core", REPO / "voice_core")


def _load_json_strict(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def _run_check(command: list[str], *, timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(REPO),
            env={**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + str(REPO)},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-240:],
            "stderr_tail": proc.stderr[-240:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "error": f"timeout_after_{timeout}s",
            "stdout_tail": (exc.stdout or "")[-240:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-240:] if isinstance(exc.stderr, str) else "",
        }
    except OSError as exc:
        return {"returncode": None, "error": f"launch_failed:{exc}"}


def _python_quality_errors(path: Path, tree: ast.AST) -> list[str]:
    """Return high-confidence defects that Python otherwise accepts silently."""
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults)
            defaults.extend(value for value in node.args.kw_defaults if value is not None)
            if any(isinstance(value, (ast.Dict, ast.List, ast.Set)) for value in defaults):
                errors.append(f"mutable_default:{path}:{node.lineno}:{node.name}")
        elif isinstance(node, ast.Dict):
            seen: dict[object, int] = {}
            for key in node.keys:
                if not isinstance(key, ast.Constant):
                    continue
                try:
                    duplicate = key.value in seen
                    if not duplicate:
                        seen[key.value] = key.lineno
                except TypeError:
                    continue
                if duplicate:
                    errors.append(
                        f"duplicate_dict_key:{path}:{key.lineno}:{key.value!r}"
                    )

        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        definitions: dict[str, int] = {}
        for child in body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if child.name in definitions:
                errors.append(
                    f"duplicate_definition:{path}:{child.lineno}:{child.name}"
                )
            definitions[child.name] = child.lineno
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Viv foundation preflight contracts and static checks."
    )
    parser.parse_args()

    errors: list[str] = []
    checked = 0
    for scan_root in PYTHON_ROOTS:
        for path in sorted(scan_root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                checked += 1
                errors.extend(_python_quality_errors(path, tree))
            except (OSError, SyntaxError) as exc:
                errors.append(f"syntax:{path}:{exc}")

    try:
        config = _load_json_strict(ROOT / "model_config.json")
        policy = _load_json_strict(
            ROOT / "artifacts/auto/shadow_judge/admission_policy.json"
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"config_load:{exc}")
        config = {}
        policy = {}
    if bool(config.get("lora_admission", {}).get("auto_train")):
        errors.append("config:auto_train_must_be_false")
    if bool(policy.get("auto_train")):
        errors.append("policy:auto_train_must_be_false")
    if config.get("shadow_judge", {}).get("aggregate") != "product_and":
        errors.append("config:shadow_judge_aggregate_must_be_product_and")
    if config.get("triad", {}).get("contract_version") != "viv_triad_contract_v1":
        errors.append("config:triad_contract_version")
    if config.get("triad", {}).get("security_authority") != "rust_security_core":
        errors.append("config:triad_security_authority")
    if not config.get("triad", {}).get("gpu_mouth_must_return_through_cpu"):
        errors.append("config:gpu_mouth_must_return_through_cpu")

    tests = [
        "test_triad_kernel_contracts.py",
        "test_triad_architecture.py",
        "test_master_rid_freshness.py",
        "test_uml_structural_contract.py",
        "validate_uml_tariff_registry.py",
        "test_semantic_choice.py",
        "test_uml_token_economics.py",
        "test_aifl_contracts.py",
        "test_openaster_parity_contracts.py",
        "test_training_tree_contracts.py",
        "test_cpu_semantic_judge.py",
        "test_pairwise_objective.py",
        "test_training_security_contracts.py",
        "test_backup_core_contracts.py",
        "test_stage1_curriculum_contracts.py",
        "test_stage1_generation_contracts.py",
        "test_stage1_generation_bootstrap_contracts.py",
        "test_stage1_generation_bootstrap_postmortem.py",
        "test_stage1_mouth_identity_curriculum.py",
        "test_stage1_mouth_identity_judge.py",
        "test_staged_semantic_adapter_v1.py",
    ]
    results = []
    for name in tests:
        check = _run_check([str(PYTHON), "-B", str(ROOT / "scripts" / name)])
        results.append({"test": name, **check})
        if check["returncode"] != 0:
            errors.append(
                f"test:{name}:{check['returncode']}:"
                f"{check.get('error') or check.get('stderr_tail', '')}"
            )

    cargo = shutil.which("cargo")
    if cargo and (REPO / "security_core" / "Cargo.toml").is_file():
        check = _run_check(
            [cargo, "test", "--manifest-path", str(REPO / "security_core" / "Cargo.toml"), "--quiet"]
        )
        results.append({"test": "security_core:cargo_test", **check})
        if check["returncode"] != 0:
            errors.append(
                f"test:security_core:cargo_test:{check['returncode']}:"
                f"{check.get('error') or check.get('stderr_tail', '')}"
            )
    else:
        errors.append("test:security_core:cargo_test:cargo_or_manifest_missing")

    result = {"ok": not errors, "parsed_python_files": checked, "tests": results, "errors": errors}
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
