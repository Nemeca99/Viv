"""UML / Viv-SLM training control-plane catalog, plan, and safe status helpers.

Does not start AIOS, does not promote checkpoints, and does not launch GPU-long
train loops unless the caller explicitly passes ``i_understand_gpu_long=True``.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
PYTHON = FOUNDATION.parent.parent / ".venv" / "Scripts" / "python.exe"
TEST_TRAINING = (
    FOUNDATION
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "model"
    / "test_training"
)
TRAINING_CURRENT = FOUNDATION / "models" / "Training" / "current"
EVIDENCE_ROOT = FOUNDATION / "models" / "Training" / "evidence"
SNAPSHOTS_ROOT = EVIDENCE_ROOT / "snapshots"
BACKUP_RECEIPTS = FOUNDATION / "artifacts" / "auto" / "backup_core" / "receipts"
RECEIPTS_ROOT = FOUNDATION / "artifacts" / "auto" / "training_automation"
THESIS = TEST_TRAINING / "UML_TRAINING_THESIS.md"
SURVIVOR = TEST_TRAINING / "runs" / "uml_mix_layers" / "layer_survivor.pt"
MASTER_PROGRAM = TRAINING_CURRENT / "MASTER_TRAINING_PROGRAM.json"
TRAINING_KNOBS = TRAINING_CURRENT / "TRAINING_KNOBS.json"

RISK_GPU_LONG = "GPU_LONG"
RISK_CPU_SAFE = "CPU_SAFE"
RISK_MEASUREMENT = "MEASUREMENT_ONLY"

SMOKE_WALL_SECONDS = 120

SCHEMA_RECEIPT = "viv_training_automation_receipt_v1"
SCHEMA_CATALOG = "viv_training_automation_catalog_v1"


def _posix(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_stamp() -> str:
    # Milliseconds avoid same-second receipt folder collisions under Windows.
    now = _utc_now()
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"


def _sha256_file(path: Path, *, max_bytes: int | None = None) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        remaining = max_bytes
        while True:
            chunk = fh.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining))
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0:
                    break
    return h.hexdigest()


def _file_identity(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": _posix(path), "exists": False}
    st = path.stat()
    return {
        "path": _posix(path),
        "exists": True,
        "bytes": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
        "sha256": _sha256_file(path),
    }


def _tt_cmd(script_name: str, *args: str) -> list[str]:
    script = TEST_TRAINING / script_name
    return [_posix(PYTHON), "-B", _posix(script), *args]


def catalog_jobs() -> list[dict[str, Any]]:
    """Declare runnable training/eval jobs with risk tags (no execute)."""
    jobs: list[dict[str, Any]] = [
        {
            "id": "uml_status",
            "title": "UML measurement-only status (survivor/thesis/evidence/backup)",
            "risk": RISK_MEASUREMENT,
            "auto_execute": True,
            "profile": "uml_status",
            "requires_gpu_long_gate": False,
            "expected_receipts": [
                "foundation/artifacts/auto/training_automation/<stamp>/RECEIPT.json"
            ],
            "notes": "Reads only; never trains or promotes.",
        },
        {
            "id": "uml_speak_cheap_census_selftest",
            "title": "Speak-cheap census --selftest (no model, no train)",
            "risk": RISK_CPU_SAFE,
            "auto_execute": True,
            "profile": "uml_smoke",
            "requires_gpu_long_gate": False,
            "command": _tt_cmd("run_uml_speak_cheap_census.py", "--selftest"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_wall_seconds_max": SMOKE_WALL_SECONDS,
            "expected_receipts": [
                "stdout UML_SPEAK_CHEAP_CENSUS_SELFTEST_PASS",
                "foundation/artifacts/auto/training_automation/<stamp>/RECEIPT.json",
            ],
            "notes": "Pre-existing smoke; gated for uml_smoke if <2 minutes.",
        },
        {
            "id": "uml_merge_extra_surfaces",
            "title": "Merge heldout/OOD surfaces into extras catalog (no tensor rebuild)",
            "risk": RISK_CPU_SAFE,
            "auto_execute": False,
            "requires_gpu_long_gate": False,
            "command": _tt_cmd("merge_uml_mix_extra_surfaces.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/data/uml_mix_extra_surfaces/surfaces.json",
            ],
            "notes": "CPU catalog merge; does not rebuild bank or train.",
        },
        {
            "id": "uml_speak_cheap_census_full",
            "title": "Matched speak-cheap census n=256 (inference, no train)",
            "risk": RISK_MEASUREMENT,
            "auto_execute": False,
            "requires_gpu_long_gate": False,
            "command": _tt_cmd("run_uml_speak_cheap_census.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/runs/uml_speak_cheap_census/census_*/census.json",
            ],
            "notes": "May use GPU for inference; does not write checkpoints. Not auto-run.",
        },
        {
            "id": "uml_ood_probe",
            "title": "OOD never-seen probe (eval only)",
            "risk": RISK_MEASUREMENT,
            "auto_execute": False,
            "requires_gpu_long_gate": False,
            "command": _tt_cmd("run_uml_ood_probe.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/runs/uml_ood_probe_latest.json",
            ],
            "notes": "Eval/probe; may load CUDA. Not auto-run by default profiles.",
        },
        {
            "id": "sandbox_smoke",
            "title": "Sandbox load+fingerprint+speak smoke",
            "risk": RISK_MEASUREMENT,
            "auto_execute": False,
            "requires_gpu_long_gate": False,
            "command": _tt_cmd("run_sandbox_smoke.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "model/artifacts_local/experiments/H_sandbox_test_training.json",
            ],
            "notes": "Loads specialists; wall time not guaranteed <2m - excluded from uml_smoke auto.",
        },
        {
            "id": "uml_blend_recover",
            "title": "Default OOD blend recover (heldout+0.25 OOD, 3000 steps)",
            "risk": RISK_GPU_LONG,
            "auto_execute": False,
            "requires_gpu_long_gate": True,
            "command": _tt_cmd("run_uml_ood_blend_recover.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/runs/uml_ood_blend_recover/blend_recover_latest.json",
                "test_training/runs/uml_mix_layers/layer_survivor.pt (may commit)",
            ],
            "notes": "GPU train; may commit survivor. Requires --i-understand-gpu-long.",
        },
        {
            "id": "uml_real_heldout_loop",
            "title": "Real held-out English train/eval loop (default 4000-6000 steps)",
            "risk": RISK_GPU_LONG,
            "auto_execute": False,
            "requires_gpu_long_gate": True,
            "command": _tt_cmd(
                "run_uml_real_heldout_loop.py",
                "--seed",
                "42",
                "--n",
                "256",
                "--steps",
                "4000",
            ),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/runs/uml_real_heldout/real_heldout_latest.json",
            ],
            "notes": "GPU train; may commit survivor. Requires --i-understand-gpu-long.",
        },
        {
            "id": "uml_ood_train_loop",
            "title": "OOD train loop A->train->A+B",
            "risk": RISK_GPU_LONG,
            "auto_execute": False,
            "requires_gpu_long_gate": True,
            "command": _tt_cmd("run_uml_ood_train_loop.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/runs/uml_ood_train_loop_latest.json",
            ],
            "notes": "GPU train. Requires --i-understand-gpu-long.",
        },
        {
            "id": "uml_speak_cheap_pressure",
            "title": "Speak cheap-pressure train (+3k steps)",
            "risk": RISK_GPU_LONG,
            "auto_execute": False,
            "requires_gpu_long_gate": True,
            "command": _tt_cmd("run_uml_speak_cheap_pressure.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/runs/uml_speak_cheap_pressure_latest.json",
            ],
            "notes": "GPU train. Requires --i-understand-gpu-long.",
        },
        {
            "id": "uml_mix_continue_train",
            "title": "UML mix continue_train layer (recipe default steps, often 10k)",
            "risk": RISK_GPU_LONG,
            "auto_execute": False,
            "requires_gpu_long_gate": True,
            "command": _tt_cmd("run_uml_mix_layer.py", "--layer", "continue_train"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/runs/uml_mix_layers/layer_continue_train_latest.json",
            ],
            "notes": "GPU train. Requires --i-understand-gpu-long. No promotion without separate authority.",
        },
        {
            "id": "sandbox_campaign",
            "title": "Sandbox specialist campaign (build+train both lanes)",
            "risk": RISK_GPU_LONG,
            "auto_execute": False,
            "requires_gpu_long_gate": True,
            "command": _tt_cmd("run_campaign.py"),
            "cwd": _posix(TEST_TRAINING.parent),
            "expected_receipts": [
                "test_training/checkpoints/efficient/specialist.pt",
                "test_training/checkpoints/deep/specialist.pt",
            ],
            "notes": "GPU train. Requires --i-understand-gpu-long.",
        },
        {
            "id": "master_supervisor_dry_run",
            "title": "MASTER_TRAINING_PROGRAM supervisor dry-run template (authority closed)",
            "risk": RISK_CPU_SAFE,
            "auto_execute": False,
            "requires_gpu_long_gate": False,
            "command": [
                _posix(PYTHON),
                "-B",
                _posix(
                    TRAINING_CURRENT
                    / "viv_slm"
                    / "run_viv_slm_layered_training_supervisor.py"
                ),
                "--campaign-id",
                "<campaign_id>",
                "--campaign-contract",
                "<contract>",
                "--output-dir",
                "foundation/models/Training/runs/viv_slm/<run_dir>",
                "--steps",
                "250",
                "--dry-run",
            ],
            "expected_receipts": [
                "run dir dry-run receipt (when placeholders replaced)",
            ],
            "notes": (
                "Declarative template from MASTER_TRAINING_PROGRAM.json; "
                "placeholders must be filled. training_authorized=false by default."
            ),
            "control_plane": {
                "master_program": _posix(MASTER_PROGRAM),
                "knobs": _posix(TRAINING_KNOBS),
            },
        },
        {
            "id": "master_supervisor_canary_250",
            "title": "MASTER bounded 250-step canary (operator authorize required)",
            "risk": RISK_GPU_LONG,
            "auto_execute": False,
            "requires_gpu_long_gate": True,
            "command": [
                _posix(PYTHON),
                "-B",
                _posix(
                    TRAINING_CURRENT
                    / "viv_slm"
                    / "run_viv_slm_layered_training_supervisor.py"
                ),
                "--campaign-id",
                "<campaign_id>",
                "--campaign-contract",
                "<contract>",
                "--output-dir",
                "foundation/models/Training/runs/viv_slm/<run_dir>",
                "--steps",
                "250",
                "--execute",
                "--operator-authorize",
            ],
            "expected_receipts": [
                "foundation/models/Training/runs/viv_slm/<run_dir>/...",
            ],
            "notes": (
                "GPU canary. Requires --i-understand-gpu-long AND separate MASTER "
                "authority flags. This orchestrator never opens training_authorized."
            ),
            "control_plane": {
                "master_program": _posix(MASTER_PROGRAM),
                "knobs": _posix(TRAINING_KNOBS),
            },
        },
    ]
    return jobs


def get_job(job_id: str) -> dict[str, Any]:
    for job in catalog_jobs():
        if job["id"] == job_id:
            return job
    raise KeyError(f"unknown_job:{job_id}")


def plan_job(job_id: str) -> dict[str, Any]:
    """Expand a job to exact commands + paths + expected receipts (no execute)."""
    job = dict(get_job(job_id))
    return {
        "ok": True,
        "mode": "plan_only",
        "job_id": job_id,
        "risk": job.get("risk"),
        "requires_gpu_long_gate": bool(job.get("requires_gpu_long_gate")),
        "auto_execute": bool(job.get("auto_execute")),
        "command": job.get("command"),
        "cwd": job.get("cwd"),
        "expected_receipts": list(job.get("expected_receipts") or []),
        "paths": {
            "python": _posix(PYTHON),
            "foundation": _posix(FOUNDATION),
            "test_training": _posix(TEST_TRAINING),
            "survivor": _posix(SURVIVOR),
            "thesis": _posix(THESIS),
            "master_program": _posix(MASTER_PROGRAM),
            "training_knobs": _posix(TRAINING_KNOBS),
            "receipts_root": _posix(RECEIPTS_ROOT),
        },
        "notes": job.get("notes"),
        "control_plane": job.get("control_plane"),
        "aios_runtime_started": False,
        "checkpoint_promotion": False,
        "execution_approved": False,
    }


def parse_thesis_ladder_tip(thesis_path: Path | None = None) -> dict[str, Any]:
    path = thesis_path or THESIS
    if not path.is_file():
        return {"ok": False, "path": _posix(path), "error": "thesis_missing"}
    text = path.read_text(encoding="utf-8")
    # Prefer "Next evidence ladder" section; fall back to whole file.
    section = text
    marker = "### Next evidence ladder"
    if marker in text:
        section = text.split(marker, 1)[1]
        # stop at next ### heading if present
        nxt = re.search(r"\n###\s+", section)
        if nxt:
            section = section[: nxt.start()]
    pattern = re.compile(
        r"^(\d+)\.\s+(~~)?(.+?)(?:~~)?\s*→\s+\*\*([^*]+)\*\*(.*)$",
        re.MULTILINE,
    )
    tips: list[dict[str, Any]] = []
    for match in pattern.finditer(section):
        tips.append(
            {
                "item": int(match.group(1)),
                "struck": bool(match.group(2)),
                "title": match.group(3).strip(),
                "verdict": match.group(4).strip(),
                "tail": (match.group(5) or "").strip()[:240],
            }
        )
    if not tips:
        return {
            "ok": False,
            "path": _posix(path),
            "error": "ladder_tip_not_found",
            "sha256": _sha256_file(path),
        }
    tip = max(tips, key=lambda row: row["item"])
    return {
        "ok": True,
        "path": _posix(path),
        "sha256": _sha256_file(path),
        "item": tip["item"],
        "struck": tip["struck"],
        "title": tip["title"],
        "verdict": tip["verdict"],
        "tail": tip["tail"],
        "tip_line": f"{tip['item']}. {tip['title']} -> **{tip['verdict']}**",
    }


def latest_evidence_snapshot() -> dict[str, Any]:
    if not SNAPSHOTS_ROOT.is_dir():
        return {"ok": False, "path": _posix(SNAPSHOTS_ROOT), "error": "snapshots_missing"}
    dirs = sorted(
        [p for p in SNAPSHOTS_ROOT.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    if not dirs:
        return {"ok": False, "path": _posix(SNAPSHOTS_ROOT), "error": "no_snapshots"}
    latest = dirs[0]
    manifest = latest / "MANIFEST.json"
    payload: dict[str, Any] = {
        "ok": True,
        "snapshot_id": latest.name,
        "path": _posix(latest),
        "manifest_path": _posix(manifest) if manifest.is_file() else None,
    }
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            payload["purpose"] = data.get("purpose")
            payload["verdicts"] = data.get("verdicts")
            payload["created_at_utc"] = data.get("created_at_utc")
            payload["manifest_sha256"] = _sha256_file(manifest)
        except (OSError, json.JSONDecodeError) as exc:
            payload["manifest_error"] = str(exc)
            payload["ok"] = False
    return payload


def latest_backup_receipt_pointer() -> dict[str, Any]:
    if not BACKUP_RECEIPTS.is_dir():
        return {
            "ok": False,
            "path": _posix(BACKUP_RECEIPTS),
            "error": "backup_receipts_missing",
            "present": False,
        }
    dirs = sorted(
        [p for p in BACKUP_RECEIPTS.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    if not dirs:
        return {
            "ok": False,
            "path": _posix(BACKUP_RECEIPTS),
            "error": "no_backup_receipts",
            "present": False,
        }
    latest = dirs[0]
    receipt = latest / "RECEIPT.json"
    out: dict[str, Any] = {
        "ok": receipt.is_file(),
        "present": True,
        "stamp": latest.name,
        "receipt_path": _posix(receipt) if receipt.is_file() else None,
        "folder": _posix(latest),
    }
    if receipt.is_file():
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
            out["profile"] = data.get("profile")
            out["snapshot_id"] = data.get("snapshot_id")
            out["mode"] = data.get("mode")
            out["receipt_ok"] = data.get("ok")
        except (OSError, json.JSONDecodeError) as exc:
            out["ok"] = False
            out["error"] = str(exc)
    return out


def collect_uml_status() -> dict[str, Any]:
    """Measurement-only UML training control-plane status."""
    survivor = _file_identity(SURVIVOR)
    tip = parse_thesis_ladder_tip()
    snapshot = latest_evidence_snapshot()
    backup = latest_backup_receipt_pointer()
    master: dict[str, Any] = {"path": _posix(MASTER_PROGRAM), "exists": MASTER_PROGRAM.is_file()}
    if MASTER_PROGRAM.is_file():
        try:
            data = json.loads(MASTER_PROGRAM.read_text(encoding="utf-8"))
            master["status"] = data.get("status")
            master["authority"] = data.get("authority")
            master["sha256"] = _sha256_file(MASTER_PROGRAM)
        except (OSError, json.JSONDecodeError) as exc:
            master["error"] = str(exc)
    knobs: dict[str, Any] = {"path": _posix(TRAINING_KNOBS), "exists": TRAINING_KNOBS.is_file()}
    if TRAINING_KNOBS.is_file():
        knobs["sha256"] = _sha256_file(TRAINING_KNOBS)
    ok = bool(survivor.get("exists")) and bool(tip.get("ok"))
    return {
        "ok": ok,
        "mode": "uml_status",
        "risk": RISK_MEASUREMENT,
        "survivor": survivor,
        "thesis_ladder_tip": tip,
        "last_evidence_snapshot": snapshot,
        "last_backup_receipt": backup,
        "master_training_program": master,
        "training_knobs": knobs,
        "aios_runtime_started": False,
        "checkpoint_promotion": False,
        "gpu_train_launched": False,
    }


def smoke_candidate() -> dict[str, Any]:
    """Return the only auto-smoke candidate if it is pre-existing and short."""
    job = get_job("uml_speak_cheap_census_selftest")
    return {
        "job_id": job["id"],
        "risk": job["risk"],
        "command": job["command"],
        "cwd": job.get("cwd"),
        "expected_wall_seconds_max": int(job.get("expected_wall_seconds_max") or SMOKE_WALL_SECONDS),
        "pre_existing": True,
        "reason": (
            "run_uml_speak_cheap_census.py --selftest is a no-model determinism "
            "check; expected wall < 120s. Full sandbox/GPU smokes are not auto-run."
        ),
    }


def run_uml_smoke(*, dry_check_only: bool = False) -> dict[str, Any]:
    """Run uml_smoke only if the pre-existing short selftest is available."""
    candidate = smoke_candidate()
    script = TEST_TRAINING / "run_uml_speak_cheap_census.py"
    if not script.is_file():
        return {
            "ok": True,
            "skipped": True,
            "reason": "smoke_script_missing",
            "candidate": candidate,
            "smoke_ran": False,
        }
    if dry_check_only:
        return {
            "ok": True,
            "skipped": False,
            "planned": True,
            "candidate": candidate,
            "smoke_ran": False,
            "execution_approved": False,
        }
    cmd = list(candidate["command"] or [])
    wall_max = int(candidate["expected_wall_seconds_max"])
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(TEST_TRAINING.parent),
            capture_output=True,
            text=True,
            timeout=wall_max,
            check=False,
        )
        elapsed = time.perf_counter() - started
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        passed = proc.returncode == 0 and "UML_SPEAK_CHEAP_CENSUS_SELFTEST_PASS" in stdout
        return {
            "ok": passed and elapsed < wall_max,
            "skipped": False,
            "smoke_ran": True,
            "candidate": candidate,
            "returncode": proc.returncode,
            "elapsed_seconds": round(elapsed, 3),
            "wall_max_seconds": wall_max,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-1000:],
            "passed_marker": "UML_SPEAK_CHEAP_CENSUS_SELFTEST_PASS" in stdout,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        return {
            "ok": False,
            "skipped": True,
            "smoke_ran": False,
            "reason": "smoke_exceeded_2_minutes",
            "candidate": candidate,
            "elapsed_seconds": round(elapsed, 3),
            "wall_max_seconds": wall_max,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-1000:] if isinstance(exc.stderr, str) else "",
        }


def gate_gpu_long(job_id: str, *, i_understand_gpu_long: bool) -> dict[str, Any]:
    job = get_job(job_id)
    if not job.get("requires_gpu_long_gate"):
        return {"ok": True, "gated": False, "job_id": job_id}
    if i_understand_gpu_long:
        return {
            "ok": True,
            "gated": True,
            "allowed": True,
            "job_id": job_id,
            "warning": "operator_gpu_long_gate_acknowledged",
        }
    return {
        "ok": False,
        "gated": True,
        "allowed": False,
        "job_id": job_id,
        "risk": job.get("risk"),
        "error": "gpu_long_blocked_without_--i-understand-gpu-long",
        "command": job.get("command"),
        "notes": job.get("notes"),
    }


def write_receipt(stamp: str | None, payload: dict[str, Any]) -> Path:
    stamp = stamp or _utc_stamp()
    folder = RECEIPTS_ROOT / stamp
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "RECEIPT.json"
    body = dict(payload)
    body.setdefault("schema_version", SCHEMA_RECEIPT)
    body.setdefault("created_at", _utc_now().isoformat())
    body.setdefault("stamp", stamp)
    body.setdefault("aios_runtime_started", False)
    body.setdefault("checkpoint_promotion", False)
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    md = folder / "RECEIPT.md"
    md.write_text(
        "\n".join(
            [
                f"# training automation receipt `{stamp}`",
                "",
                f"- ok: `{body.get('ok')}`",
                f"- mode: `{body.get('mode')}`",
                f"- profile: `{body.get('profile')}`",
                f"- smoke_ran: `{body.get('smoke_ran')}`",
                f"- gpu_train_launched: `{body.get('gpu_train_launched')}`",
                f"- aios_runtime_started: `{body.get('aios_runtime_started')}`",
                f"- checkpoint_promotion: `{body.get('checkpoint_promotion')}`",
                "",
                "## Summary JSON",
                "",
                "```json",
                json.dumps(
                    {
                        k: body.get(k)
                        for k in (
                            "ok",
                            "mode",
                            "profile",
                            "job_id",
                            "smoke_ran",
                            "gpu_train_launched",
                            "survivor_sha256",
                            "thesis_ladder_tip",
                        )
                        if k in body or body.get(k) is not None
                    },
                    indent=2,
                ),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


# Integration hook for a future AIOS core orchestrator.
AIOS_CORE_INTEGRATION_HOOK = """
Future run_aios_core_automation_v1.py should invoke this control plane as a
bounded child profile, never as an unbounded train launcher:

  from lib.training_automation_v1 import collect_uml_status, catalog_jobs, plan_job

  # Safe default in AIOS core loops:
  status = collect_uml_status()          # MEASUREMENT_ONLY
  # Optional short smoke (CPU):
  #   subprocess / run_training_automation_v1.py --profile uml_smoke
  # Never call GPU_LONG jobs from AIOS core without explicit operator gate
  #   --i-understand-gpu-long AND separate MASTER_TRAINING_PROGRAM authority.

CLI equivalent:
  L:/Continue/.venv/Scripts/python.exe -B foundation/scripts/run_training_automation_v1.py --profile uml_status
  L:/Continue/.venv/Scripts/python.exe -B foundation/scripts/run_training_automation_v1.py --catalog
  L:/Continue/.venv/Scripts/python.exe -B foundation/scripts/run_training_automation_v1.py --plan-only --job uml_blend_recover

Receipts land under foundation/artifacts/auto/training_automation/<stamp>/.
Do not start/stop AIOS from this module. Do not promote checkpoints here.
""".strip()
