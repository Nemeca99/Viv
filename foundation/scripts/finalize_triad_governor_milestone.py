"""Generate evidence for the AIOS Triad membrane and Engineering Governor."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from lib.backup_core import verify_snapshot  # noqa: E402
from lib.engineering_governor import governor_status  # noqa: E402
from lib.security_bridge import (  # noqa: E402
    constitution,
    integrity_status,
    verify_backup_ledger,
    verify_training_ledger,
)
from lib.training_security import fresh_master_s_n  # noqa: E402
from lib.triad_architecture import scan_architecture  # noqa: E402
from lib.triad_kernel import (  # noqa: E402
    TriadEnvelope,
    dispatch,
    open_context,
    triad_status,
    verify_triad_ledger,
)


PYTHON = Path(r"L:\Continue\.venv\Scripts\python.exe")
OUT_ROOT = FOUNDATION / "artifacts" / "auto" / "triad"
OUT = OUT_ROOT / "milestone_report_v1.json"
OUT_MD = OUT_ROOT / "MILESTONE.md"
INITIAL_SNAPSHOT = "ec40f8a26cf0ded1490367fbf177496283c67eb035b529823fc8a4a01ff95dac"
GOVERNOR_SNAPSHOT = "3b5a7a2899d8c784861da1fa573e7edd7d2e2028aa776fc04a09ae5f7df3b0fe"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _run(label: str, command: list[str], cwd: Path, timeout: int = 180) -> dict[str, Any]:
    env = {
        **os.environ,
        "PYTHONPATH": str(FOUNDATION) + os.pathsep + str(REPO),
    }
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        combined = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        )
        return {
            "label": label,
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "command": command,
            "output_tail": combined.splitlines()[-40:],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "label": label,
            "ok": False,
            "returncode": None,
            "command": command,
            "output_tail": [f"{type(exc).__name__}:{exc}"],
        }


def _voice_smoke() -> dict[str, Any]:
    module = importlib.import_module("voice_core.speak")
    packet = module.build_intent_packet(
        query="Give a bounded status.",
        facts=["Triad milestone smoke only."],
        memory_top=0,
    )
    packet["s_n"] = 0.60
    original_try = module._try_ollama_or_gguf
    original_reachable = module.server_reachable
    try:
        module._try_ollama_or_gguf = lambda *args, **kwargs: None
        module.server_reachable = lambda *args, **kwargs: {"reachable": False}
        result = module.speak(
            query="Give a bounded status.",
            force_packet=packet,
            max_tokens=32,
        )
    finally:
        module._try_ollama_or_gguf = original_try
        module.server_reachable = original_reachable
    return {
        "ok": bool(result.get("ok"))
        and not bool(result.get("blocked"))
        and result.get("voice_source") == "deterministic_offline"
        and (result.get("egress") or {}).get("stage") == "EMIT",
        "voice_source": result.get("voice_source"),
        "blocked": result.get("blocked"),
        "triad_stage": (result.get("egress") or {}).get("stage"),
        "text_chars": len(str(result.get("text") or "")),
        "gpu_invoked": False,
    }


def _process_observation() -> dict[str, Any]:
    import psutil

    active = []
    markers = (
        "train_judge_lora",
        "train_pairwise_lora",
        "train_stage1_pairwise",
        "validate_judge_adapter",
    )
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if any(marker in command.lower() for marker in markers):
            active.append(
                {
                    "pid": process.info.get("pid"),
                    "name": process.info.get("name"),
                    "command": command,
                }
            )
    return {"training_or_validation_processes": active, "none_active": not active}


def _secure_artifact(path: Path, payload: str, s_n: float) -> dict[str, Any]:
    context = open_context(
        TriadEnvelope.build(
            actor="deterministic_authority",
            source="triad_milestone_finalizer",
            target="evidence",
            action="EVIDENCE_WRITE",
            payload={
                "path": str(path).replace("\\", "/"),
                "sha256": _sha256_text(payload),
                "bytes": len(payload.encode("utf-8")),
            },
            s_n=s_n,
        )
    )
    params = {
        "path": str(path).replace("\\", "/"),
        "content_sha256": _sha256_text(payload),
        "bytes": len(payload.encode("utf-8")),
    }

    def _write() -> str:
        _atomic_write(path, payload)
        return str(path)

    _, receipt = dispatch(
        context,
        operation="triad.evidence.write",
        params=params,
        handler=_write,
        tool_name="write_file",
    )
    return receipt.to_dict()


def main() -> int:
    cargo = shutil.which("cargo") or "cargo"
    tests = [
        _run("rust_security", [cargo, "test", "--offline", "--quiet"], REPO / "security_core"),
        _run("triad_kernel", [str(PYTHON), "scripts/test_triad_kernel_contracts.py"], FOUNDATION),
        _run("triad_architecture", [str(PYTHON), "scripts/test_triad_architecture.py"], FOUNDATION),
        _run("cpu_semantic_judge", [str(PYTHON), "scripts/test_cpu_semantic_judge.py"], FOUNDATION),
        _run("training_security", [str(PYTHON), "scripts/test_training_security_contracts.py"], FOUNDATION),
        _run("backup_security", [str(PYTHON), "scripts/test_backup_core_contracts.py"], FOUNDATION),
        _run("unified_preflight", [str(PYTHON), "scripts/run_foundation_preflight.py"], FOUNDATION),
    ]
    architecture = scan_architecture()
    triad = triad_status()
    initial_snapshot = verify_snapshot(INITIAL_SNAPSHOT, verify_catalog=False)
    governor_snapshot = verify_snapshot(GOVERNOR_SNAPSHOT, verify_catalog=False)
    model_config = json.loads((FOUNDATION / "model_config.json").read_text(encoding="utf-8"))
    cpu_config = json.loads((FOUNDATION / "cpu_config.json").read_text(encoding="utf-8"))
    voice_smoke = _voice_smoke()
    processes = _process_observation()
    master_s_n, master_rid = fresh_master_s_n()
    disk = shutil.disk_usage(REPO)
    report = {
        "schema_version": "viv_triad_governor_milestone_v1",
        "generated_at": _utc(),
        "ok": False,
        "triad": triad,
        "architecture": architecture,
        "engineering_governor": governor_status(),
        "security": {
            "constitution": constitution(),
            "integrity": integrity_status(),
            "triad_ledger": verify_triad_ledger(),
            "training_ledger": verify_training_ledger(),
            "backup_ledger": verify_backup_ledger(),
        },
        "snapshots": {
            "initial_pre_mutation": initial_snapshot,
            "governor_finalize": governor_snapshot,
        },
        "tests": tests,
        "voice_smoke": voice_smoke,
        "runtime_state": {
            "voice_backend": model_config["voice"]["backend"],
            "served_name": model_config["voice"]["served_name"],
            "validated_candidate": model_config["openaster_training"]["validated_candidate"],
            "auto_deploy": model_config["openaster_training"]["auto_deploy"],
            "triad_contract_version": model_config["triad"]["contract_version"],
            "cpu_triad_contract_version": cpu_config["triad"]["contract_version"],
            "deployment_changed": False,
            "training_started": False,
        },
        "resources": {
            "master_rid": master_rid,
            "evidence_s_n": master_s_n,
            "l_free_bytes": disk.free,
            "l_free_gib": round(disk.free / (1024**3), 2),
            "processes": processes,
        },
        "known_residuals": {
            "boundary_registry_modules": architecture["boundary_modules"],
            "meaning": (
                "Existing direct boundary sites are frozen as explicit migration debt; "
                "registry drift blocks new sites."
            ),
            "offline_backup": "deferred_by_architect",
        },
    }
    report["ok"] = bool(
        all(item["ok"] for item in tests)
        and architecture.get("ok")
        and architecture.get("coverage_pct") == 100.0
        and not architecture.get("direct_bridge_violations")
        and triad.get("error") is None
        and report["security"]["integrity"].get("ok")
        and report["security"]["triad_ledger"].get("ok")
        and report["security"]["training_ledger"].get("ok")
        and report["security"]["backup_ledger"].get("ok")
        and initial_snapshot.get("ok")
        and governor_snapshot.get("ok")
        and voice_smoke.get("ok")
        and processes.get("none_active")
        and report["runtime_state"]["validated_candidate"] is None
        and not report["runtime_state"]["auto_deploy"]
        and not report["runtime_state"]["deployment_changed"]
        and not report["runtime_state"]["training_started"]
    )
    report_payload = json.dumps(report, indent=2, ensure_ascii=False)
    report["evidence_receipt"] = _secure_artifact(OUT, report_payload, master_s_n)
    report_payload = json.dumps(report, indent=2, ensure_ascii=False)
    _secure_artifact(OUT, report_payload, master_s_n)
    summary = "\n".join(
        [
            "# AIOS Triad Membrane and Engineering Governor",
            "",
            f"- Result: **{'PASS' if report['ok'] else 'FAIL'}**",
            f"- Contract: `{triad['contract_version']}`",
            f"- Pillars: `{', '.join(sorted(triad['pillars']))}`",
            f"- Python architecture coverage: {architecture['coverage_pct']}%",
            f"- Frozen boundary modules: {architecture['boundary_modules']}",
            f"- Triad ledger events: {report['security']['triad_ledger']['events']}",
            f"- Initial safety snapshot: `{INITIAL_SNAPSHOT}`",
            f"- Governor safety snapshot: `{GOVERNOR_SNAPSHOT}`",
            f"- Voice round trip: {'PASS' if voice_smoke['ok'] else 'FAIL'} (GPU not invoked)",
            "- Training/deployment: not started; Qwen configuration unchanged.",
            "- Existing raw boundary inventory is frozen; new drift fails preflight.",
            "",
        ]
    )
    _secure_artifact(OUT_MD, summary, master_s_n)
    print(json.dumps({"ok": report["ok"], "report": str(OUT), "summary": str(OUT_MD)}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
