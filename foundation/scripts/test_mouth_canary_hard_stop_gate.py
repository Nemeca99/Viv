#!/usr/bin/env python3
"""Contract suite for mouth-canary hard-stop entry gate.

Standalone (venv python). Uses temp fixture trees so the live park latch is
not mutated. CLI override cases invoke the real canary entrypoint and abort
on a later safe preflight — no train, no lease, no deploy.

Expected malformed behavior: raise ValueError with prefix
hard_stop_decision_malformed: (fail closed; never silent allow).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any
from unittest import mock

FOUNDATION = Path(__file__).resolve().parents[1]
REPO = FOUNDATION.parent
CANARY = (
    FOUNDATION
    / "models"
    / "Training"
    / "code"
    / "train_stage1_mouth_generation_canary.py"
)
VENV_PYTHON = REPO.parent / ".venv" / "Scripts" / "python.exe"
for candidate in (FOUNDATION, REPO):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from models.Training.code import (  # noqa: E402
    train_stage1_mouth_generation_canary as canary,
)

PARKED: dict[str, Any] = {
    "status": "FAIL",
    "hard_stop_no_retry": True,
    "park_on_frozen_probe_004859Z": True,
    "next_action": "park_on_frozen_probe_004859Z_no_retry",
    "authorize_next_stage": {"next_stage": "PARK_004859Z"},
}
CLEAN: dict[str, Any] = {
    "status": "PASS",
    "hard_stop_no_retry": False,
    "park_on_frozen_probe_004859Z": False,
    "next_action": "separate_mouth_full_training_review_required",
    "authorize_next_stage": {"next_stage": "REVIEW"},
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    else:
        path.write_text(str(payload), encoding="utf-8")


def _install_fixture_tree(
    tree: Path,
    *,
    live: dict[str, Any] | None = None,
    live_raw: str | None = None,
    priors: list[tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Path]:
    """Point canary module globals at an isolated temp TREE."""
    tree.mkdir(parents=True, exist_ok=True)
    decision_32 = tree / "stage1_mouth_generation_canary_32_decision_v4.json"
    decision_16 = tree / "stage1_mouth_generation_canary_16_decision_v4.json"
    canary.TREE = tree
    canary.DECISION_ARTIFACTS = {16: decision_16, 32: decision_32}
    canary.CANARY_ARTIFACTS = {
        16: tree / "stage1_mouth_generation_canary_16_v4.json",
        32: tree / "stage1_mouth_generation_canary_32_v4.json",
    }
    if live_raw is not None:
        decision_32.write_text(live_raw, encoding="utf-8")
    elif live is not None:
        _write_json(decision_32, live)
    prior_paths: list[Path] = []
    for index, (label, payload) in enumerate(priors or []):
        prior = (
            tree
            / f"prior_{label}"
            / "stage1_mouth_generation_canary_32_decision_v4.json"
        )
        _write_json(prior, payload)
        # Ensure stable newest-by-mtime ordering on fast filesystems.
        stamp = time.time() + float(index)
        os.utime(prior, (stamp, stamp))
        prior_paths.append(prior)
    return {
        "tree": tree,
        "live": decision_32,
        "prior_newest": prior_paths[-1] if prior_paths else Path(),
    }


def _expect_hard_stop_deny(*, artifact_steps: int = 32) -> str:
    try:
        canary.refuse_hard_stop_parked_run(
            artifact_steps=artifact_steps, override_hard_stop=False
        )
    except ValueError as exc:
        detail = str(exc)
        assert detail.startswith("hard_stop_no_retry_active:"), detail
        return detail
    raise AssertionError("expected hard_stop_no_retry_active deny")


def _expect_malformed() -> str:
    try:
        canary.refuse_hard_stop_parked_run(
            artifact_steps=32, override_hard_stop=False
        )
    except ValueError as exc:
        detail = str(exc)
        assert detail.startswith("hard_stop_decision_malformed:"), detail
        return detail
    raise AssertionError("expected hard_stop_decision_malformed fail-closed")


def case_parked_live_denies_32(tmp: Path) -> dict[str, Any]:
    paths = _install_fixture_tree(tmp / "live_park", live=PARKED)
    detail = _expect_hard_stop_deny()
    assert str(paths["live"]).replace("\\", "/") in detail.replace("\\", "/")
    # Gate fires before lease / archive / train.
    assert "named unlock required" in detail
    return {"ok": True, "detail": detail}


def case_archived_prior_still_denies(tmp: Path) -> dict[str, Any]:
    # No live decision; newest prior_* still arms the latch.
    paths = _install_fixture_tree(
        tmp / "archived_park",
        live=None,
        priors=[
            ("older_clean", CLEAN),
            ("newer_parked", PARKED),
        ],
    )
    # Ensure mtime order: newer_parked is newest (written last).
    assert paths["prior_newest"] is not None
    detail = _expect_hard_stop_deny()
    assert "prior_newer_parked" in detail.replace("\\", "/")
    assert canary.latest_32_decision_path() == paths["prior_newest"]
    return {"ok": True, "detail": detail}


def case_override_only_unlock(tmp: Path) -> dict[str, Any]:
    paths = _install_fixture_tree(tmp / "override_only", live=PARKED)
    _expect_hard_stop_deny()
    try:
        canary.refuse_hard_stop_parked_run(
            artifact_steps=32, override_hard_stop=True
        )
        raise AssertionError("generic override must deny under park latch")
    except ValueError as exc:
        detail = str(exc)
        assert detail.startswith("hard_stop_generic_override_denied:"), detail
    # --operator-override is a different flag and must not unlock this gate.
    still = _expect_hard_stop_deny()
    return {
        "ok": True,
        "park_path": str(paths["live"]).replace("\\", "/"),
        "generic_override_denied": True,
        "operator_override_does_not_unlock": still.startswith(
            "hard_stop_no_retry_active:"
        ),
        "detail": detail,
    }


def case_steps16_allowed_under_park(tmp: Path) -> dict[str, Any]:
    _install_fixture_tree(tmp / "steps16", live=PARKED)
    assert (
        canary.refuse_hard_stop_parked_run(
            artifact_steps=16, override_hard_stop=False
        )
        is None
    )
    return {"ok": True}


def case_eval_only_allowed_under_park(tmp: Path) -> dict[str, Any]:
    """Eval-only CLI branch never hits the hard-stop refuse (park may remain)."""
    _install_fixture_tree(tmp / "eval_only", live=PARKED)
    _expect_hard_stop_deny()  # latch still armed for 32 chase
    sentinel = {
        "ok": True,
        "schema_version": "eval_only_hard_stop_contract_probe",
        "authority": canary.AUTHORITY,
    }
    with mock.patch.object(
        canary, "run_eval_only_adapter_32_gates", return_value=sentinel
    ) as mocked:
        with mock.patch.object(
            sys,
            "argv",
            ["train_stage1_mouth_generation_canary.py", "--eval-only-adapter"],
        ):
            with mock.patch("builtins.print"):
                rc = canary.main()
    assert rc == 0
    mocked.assert_called_once()
    return {"ok": True, "cli_rc": rc, "eval_invoked": True}


def case_clean_does_not_deny(tmp: Path) -> dict[str, Any]:
    _install_fixture_tree(tmp / "clean", live=CLEAN)
    assert (
        canary.refuse_hard_stop_parked_run(
            artifact_steps=32, override_hard_stop=False
        )
        is None
    )
    return {"ok": True}


def case_malformed_fails_closed(tmp: Path) -> dict[str, Any]:
    results: dict[str, str] = {}
    # Empty object / missing hard-stop schema keys.
    _install_fixture_tree(tmp / "malformed_empty", live={})
    results["empty_object"] = _expect_malformed()
    # Non-dict root.
    _install_fixture_tree(tmp / "malformed_list", live=["not", "a", "dict"])
    results["non_dict"] = _expect_malformed()
    # Corrupt file.
    _install_fixture_tree(
        tmp / "malformed_corrupt", live_raw="{not-json"
    )
    results["corrupt"] = _expect_malformed()
    # Missing keys (status alone is insufficient).
    _install_fixture_tree(
        tmp / "malformed_missing", live={"status": "FAIL"}
    )
    results["missing_keys"] = _expect_malformed()
    # Generic override must not convert malformed into allow.
    try:
        canary.refuse_hard_stop_parked_run(
            artifact_steps=32, override_hard_stop=True
        )
        raise AssertionError("override must not unlock malformed decision")
    except ValueError as exc:
        assert str(exc).startswith("hard_stop_decision_malformed:"), str(exc)
        results["override_still_fails_closed"] = str(exc)
    return {"ok": True, "cases": results}


def _run_canary_cli(args: list[str]) -> tuple[int, dict[str, Any]]:
    python = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
    proc = subprocess.run(
        [str(python), str(CANARY), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "parse_error": True,
            "stdout": stdout,
            "stderr": proc.stderr,
        }
    return proc.returncode, payload


def case_cli_hard_stop_and_override() -> dict[str, Any]:
    """Real CLI: deny without flag; generic --override-hard-stop still denies.

    Uses the live parked decision. Generic override must NOT clear hard-stop.
    No lease / train / deploy.
    """
    deny_rc, deny_payload = _run_canary_cli(["--run", "--steps", "32"])
    deny_detail = str(deny_payload.get("detail") or "")
    assert deny_rc != 0
    assert deny_payload.get("ok") is False
    assert deny_detail.startswith("hard_stop_no_retry_active:"), deny_payload

    unlock_rc, unlock_payload = _run_canary_cli(
        ["--run", "--steps", "32", "--override-hard-stop"]
    )
    unlock_detail = str(unlock_payload.get("detail") or "")
    assert unlock_rc != 0  # must not train
    assert unlock_payload.get("ok") is False
    assert unlock_detail.startswith("hard_stop_generic_override_denied:"), (
        unlock_payload
    )
    assert unlock_payload.get("error") == "mouth_canary_preflight"
    return {
        "ok": True,
        "deny_detail": deny_detail,
        "override_detail": unlock_detail,
        "generic_override_still_denied": True,
        "no_train_evidence": True,
    }


def main() -> int:
    cases: list[tuple[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="hard_stop_gate_") as raw:
        tmp = Path(raw)
        # Preserve live module paths; restore after fixtures.
        saved = {
            "TREE": canary.TREE,
            "DECISION_ARTIFACTS": dict(canary.DECISION_ARTIFACTS),
            "CANARY_ARTIFACTS": dict(canary.CANARY_ARTIFACTS),
        }
        try:
            cases.extend(
                [
                    (
                        "1_parked_live_denies_32",
                        case_parked_live_denies_32(tmp),
                    ),
                    (
                        "2_archived_prior_still_denies",
                        case_archived_prior_still_denies(tmp),
                    ),
                    (
                        "3_override_only_unlock",
                        case_override_only_unlock(tmp),
                    ),
                    (
                        "4_steps16_allowed_under_park",
                        case_steps16_allowed_under_park(tmp),
                    ),
                    (
                        "5_eval_only_allowed_under_park",
                        case_eval_only_allowed_under_park(tmp),
                    ),
                    (
                        "6_clean_does_not_deny",
                        case_clean_does_not_deny(tmp),
                    ),
                    (
                        "7_malformed_fails_closed",
                        case_malformed_fails_closed(tmp),
                    ),
                ]
            )
        finally:
            canary.TREE = saved["TREE"]
            canary.DECISION_ARTIFACTS = saved["DECISION_ARTIFACTS"]
            canary.CANARY_ARTIFACTS = saved["CANARY_ARTIFACTS"]

    cases.append(
        ("8_cli_hard_stop_and_override", case_cli_hard_stop_and_override())
    )

    report = {
        "ok": all(bool(result.get("ok")) for _, result in cases),
        "schema_version": "mouth_canary_hard_stop_gate_contract_v1",
        "canary": str(CANARY).replace("\\", "/"),
        "cases": {name: result for name, result in cases},
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
