#!/usr/bin/env python3
"""CPU-only contract suite: named hard-stop unlock + gentle32 campaign gate.

Proves deny-before-lease for:
  - wrong experiment ID
  - wrong plan hash
  - already consumed authorization
  - malformed authorization state
  - generic --override-hard-stop alone while park latch active

Also proves:
  - missing/clean park latch cannot bypass named unlock via
    named_unlock_already_consumed
  - campaign locks verified fail-closed before consume
  - campaign execution contract accepts LR 5e-6 and rejects other LRs
  - source-hash drift fails the campaign execution lock
  - historical generic canary plan (1e-5) remains unchanged
  - campaign artifacts do not collide with live formal-32
  - checkpoint resolver never falls back to live formal-32
  - --preflight-experiment consumes no token and opens no lease
  - dual-checkpoint evaluation dispatches both adapters across all surfaces
  - re-arm fails closed on missing/corrupt/clean park
  - valid issued auth + matching id/hash would pass the hard-stop gate, but
    run_authorized=false still blocks experiment start (no train/lease)

No GPU train, no real training lease, no deploy, no mutation of frozen
probe 004859Z.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
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

EXPERIMENT_ID = canary.GENTLE32_EXPERIMENT_ID
PLAN_HASH = "a" * 64
WRONG_HASH = "b" * 64
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
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _issued_token(
    *,
    experiment_id: str = EXPERIMENT_ID,
    plan_sha256: str = PLAN_HASH,
    status: str = "issued",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = {
        "schema_version": canary.NAMED_UNLOCK_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "plan_sha256": plan_sha256,
        "status": status,
        "issued_at": "2026-07-30T02:40:00Z",
        "consumed_at": None,
        "invalidated_at": None,
    }
    if extra:
        token.update(extra)
    return token


def _install_park_fixture(
    tree: Path,
    *,
    decision: dict[str, Any] | None = PARKED,
    write_decision: bool = True,
) -> Path | None:
    tree.mkdir(parents=True, exist_ok=True)
    decision_32 = tree / "stage1_mouth_generation_canary_32_decision_v4.json"
    decision_16 = tree / "stage1_mouth_generation_canary_16_decision_v4.json"
    canary.TREE = tree
    canary.DECISION_ARTIFACTS = {16: decision_16, 32: decision_32}
    canary.CANARY_ARTIFACTS = {
        16: tree / "stage1_mouth_generation_canary_16_v4.json",
        32: tree / "stage1_mouth_generation_canary_32_v4.json",
    }
    canary.AUTHORIZATIONS_DIR = tree / "authorizations"
    canary.AUTHORIZATIONS_DIR.mkdir(parents=True, exist_ok=True)
    canary.GENTLE32_CAMPAIGN_DIR = tree / "campaigns" / EXPERIMENT_ID
    canary.GENTLE32_CAMPAIGN_PLAN = (
        canary.GENTLE32_CAMPAIGN_DIR / "campaign_plan.json"
    )
    if write_decision and decision is not None:
        _write_json(decision_32, decision)
        return decision_32
    return None


def _live_plan_template(*, run_authorized: bool = False) -> dict[str, Any]:
    live = canary.read_json(
        Path(
            r"L:/Continue/Viv/foundation/artifacts/auto/"
            "openaster_training_tree/stage1_mouth_generation_canary_v4/"
            "campaigns/mind_lift_gentle32_lr5e6_from_073326Z_v1/"
            "campaign_plan.json"
        )
    )
    plan = dict(live)
    plan["implementation_authorized"] = True
    plan["run_authorized"] = run_authorized
    return plan


def _passing_surface(
    *,
    surface: str,
    mind: float = 0.75,
    goals: int = 8,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "surface": surface,
        "measurement_status": "clean",
        "mind_pass_rate": mind,
        "mouth_semantic_pass_rate": 1.0,
        "valid_speech_rate": 1.0,
        "eos_termination_rate": 0.875,
        "collapse_cases": 0,
        "numeric_prefix_cases": 0,
        "security_denials": 0,
        "errors": 0,
        "goal_contract_cases": goals if surface == "eight_case" else 0,
        "case_results": {
            "stage1-generation-smoke-001": {
                "mind_pass": True,
                "goal_pass": True,
                "mouth_semantic_pass": True,
            },
            "stage1-generation-smoke-005": {
                "mind_pass": True,
                "goal_pass": True,
                "mouth_semantic_pass": True,
            },
            "stage1-generation-smoke-007": {
                "mind_pass": True,
                "goal_pass": True,
                "mouth_semantic_pass": True,
            },
        },
        "honest_no_toolbleed": True if surface == "adversarial" else None,
        "toolbleed_cases": 0,
        "gpu_eval": False,
    }
    return report


def _expect_deny(
    *,
    prefix: str,
    override_hard_stop: bool = False,
    named_id: str | None = None,
    named_hash: str | None = None,
) -> str:
    try:
        canary.refuse_hard_stop_parked_run(
            artifact_steps=32,
            override_hard_stop=override_hard_stop,
            named_unlock_experiment_id=named_id,
            named_unlock_plan_sha256=named_hash,
        )
    except ValueError as exc:
        detail = str(exc)
        assert detail.startswith(prefix), detail
        return detail
    raise AssertionError(f"expected deny with prefix {prefix}")


def case_wrong_experiment_id(tmp: Path) -> dict[str, Any]:
    _install_park_fixture(tmp / "wrong_id")
    # Canonical path exists for the campaign id, but token payload id differs.
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(experiment_id="wrong_experiment_id_v9"),
    )
    detail = _expect_deny(
        prefix="named_unlock_experiment_id_mismatch:",
        named_id=EXPERIMENT_ID,
        named_hash=PLAN_HASH,
    )
    return {"ok": True, "detail": detail}


def case_wrong_plan_hash(tmp: Path) -> dict[str, Any]:
    _install_park_fixture(tmp / "wrong_hash")
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(),
    )
    detail = _expect_deny(
        prefix="named_unlock_plan_hash_mismatch:",
        named_id=EXPERIMENT_ID,
        named_hash=WRONG_HASH,
    )
    return {"ok": True, "detail": detail}


def case_already_consumed(tmp: Path) -> dict[str, Any]:
    _install_park_fixture(tmp / "consumed")
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(status="consumed", extra={"consumed_at": "2026-07-30T01:00:00Z"}),
    )
    detail = _expect_deny(
        prefix="named_unlock_already_consumed:",
        named_id=EXPERIMENT_ID,
        named_hash=PLAN_HASH,
    )
    return {"ok": True, "detail": detail}


def case_malformed_auth(tmp: Path) -> dict[str, Any]:
    results: dict[str, str] = {}
    _install_park_fixture(tmp / "malformed_missing")
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        {"status": "issued"},
    )
    results["missing_fields"] = _expect_deny(
        prefix="named_unlock_malformed:",
        named_id=EXPERIMENT_ID,
        named_hash=PLAN_HASH,
    )
    _install_park_fixture(tmp / "malformed_status")
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(status="weird"),
    )
    results["bad_status"] = _expect_deny(
        prefix="named_unlock_malformed:",
        named_id=EXPERIMENT_ID,
        named_hash=PLAN_HASH,
    )
    _install_park_fixture(tmp / "malformed_corrupt")
    path = canary.named_authorization_path(EXPERIMENT_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    results["corrupt"] = _expect_deny(
        prefix="named_unlock_malformed:",
        named_id=EXPERIMENT_ID,
        named_hash=PLAN_HASH,
    )
    return {"ok": True, "cases": results}


def case_generic_override_denied(tmp: Path) -> dict[str, Any]:
    _install_park_fixture(tmp / "generic")
    # Even with a live issued token present, generic override alone must deny.
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(),
    )
    detail = _expect_deny(
        prefix="hard_stop_generic_override_denied:",
        override_hard_stop=True,
    )
    # Token must remain issued (not consumed by the denied generic path).
    token = json.loads(
        canary.named_authorization_path(EXPERIMENT_ID).read_text(encoding="utf-8")
    )
    assert token.get("status") == "issued", token
    return {"ok": True, "detail": detail, "token_still_issued": True}


def case_valid_named_unlock_allows_gate(tmp: Path) -> dict[str, Any]:
    decision = _install_park_fixture(tmp / "valid_unlock")
    auth_path = canary.named_authorization_path(EXPERIMENT_ID)
    _write_json(auth_path, _issued_token())
    unlocked = canary.refuse_hard_stop_parked_run(
        artifact_steps=32,
        override_hard_stop=False,
        named_unlock_experiment_id=EXPERIMENT_ID,
        named_unlock_plan_sha256=PLAN_HASH,
    )
    assert unlocked == decision
    token = json.loads(auth_path.read_text(encoding="utf-8"))
    assert token.get("status") == "consumed", token
    # Replay must deny.
    replay = _expect_deny(
        prefix="named_unlock_already_consumed:",
        named_id=EXPERIMENT_ID,
        named_hash=PLAN_HASH,
    )
    return {
        "ok": True,
        "unlocked": True,
        "consumed": True,
        "replay_denied": replay.startswith("named_unlock_already_consumed:"),
    }


def case_run_authorized_false_blocks_start(tmp: Path) -> dict[str, Any]:
    """Valid auth would unlock gate, but campaign entry refuses run_authorized."""
    _install_park_fixture(tmp / "run_auth_false")
    plan = _live_plan_template(run_authorized=False)
    _write_json(canary.GENTLE32_CAMPAIGN_PLAN, plan)
    plan_hash = canary.sha256(canary.GENTLE32_CAMPAIGN_PLAN)
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(plan_sha256=plan_hash),
    )
    # Gate alone would allow.
    unlocked = canary.refuse_hard_stop_parked_run(
        artifact_steps=32,
        named_unlock_experiment_id=EXPERIMENT_ID,
        named_unlock_plan_sha256=plan_hash,
    )
    assert unlocked is not None
    # Re-issue for campaign entry path (prior consume burned the token).
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(plan_sha256=plan_hash),
    )
    train_called = {"value": False}

    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        train_called["value"] = True
        raise AssertionError("run_canary must not be reached")

    with mock.patch.object(canary, "run_canary", side_effect=_boom):
        try:
            canary.run_gentle32_campaign()
            raise AssertionError("expected run_authorized_false")
        except ValueError as exc:
            detail = str(exc)
            assert detail.startswith("run_authorized_false:"), detail
    # Auth must not have been consumed (refuse happens after run_authorized check).
    token = json.loads(
        canary.named_authorization_path(EXPERIMENT_ID).read_text(encoding="utf-8")
    )
    # rearm in finally invalidates; must not be issued usable, and not train.
    assert token.get("status") in {"issued", "invalidated"}, token
    assert train_called["value"] is False
    assert not detail.startswith("named_unlock"), detail
    return {
        "ok": True,
        "gate_would_allow": True,
        "run_authorized_blocked": True,
        "no_train": True,
        "detail": detail,
        "auth_status_after": token.get("status"),
    }


def case_cli_run_experiment_refuses(tmp: Path | None = None) -> dict[str, Any]:
    """Live CLI: --run-experiment with run_authorized=false refuses; no lease."""
    del tmp
    python = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
    proc = subprocess.run(
        [
            str(python),
            str(CANARY),
            "--run-experiment",
            EXPERIMENT_ID,
        ],
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
        payload = {"ok": False, "stdout": stdout, "stderr": proc.stderr}
    detail = str(payload.get("detail") or "")
    assert proc.returncode != 0
    assert payload.get("ok") is False
    assert detail.startswith("run_authorized_false:"), payload
    assert "security_lease" not in detail
    assert payload.get("error") == "mouth_canary_preflight"
    return {
        "ok": True,
        "detail": detail,
        "no_lease": True,
        "no_train": True,
    }


def case_rearm_invalidates(tmp: Path) -> dict[str, Any]:
    _install_park_fixture(tmp / "rearm")
    auth_path = canary.named_authorization_path(EXPERIMENT_ID)
    _write_json(auth_path, _issued_token())
    report = canary.rearm_hard_stop_after_campaign(
        experiment_id=EXPERIMENT_ID, reason="test_rearm"
    )
    token = json.loads(auth_path.read_text(encoding="utf-8"))
    assert token.get("status") == "invalidated", token
    assert report.get("auth_invalidated") is True
    assert report.get("park_latch_still_armed") is True
    assert report.get("ok") is True
    return {"ok": True, "report": report}


def case_rearm_fail_closed_states(tmp: Path) -> dict[str, Any]:
    """Missing / corrupt / clean park must not report rearm ok=true."""
    results: dict[str, Any] = {}

    _install_park_fixture(tmp / "rearm_missing", write_decision=False)
    auth = canary.named_authorization_path(EXPERIMENT_ID)
    _write_json(auth, _issued_token())
    missing = canary.rearm_hard_stop_after_campaign(
        experiment_id=EXPERIMENT_ID, reason="test_missing"
    )
    assert missing.get("ok") is False
    assert missing.get("park_latch_still_armed") is False
    assert missing.get("park_latch_state") == "missing"
    results["missing"] = missing

    _install_park_fixture(tmp / "rearm_clean", decision=CLEAN)
    _write_json(canary.named_authorization_path(EXPERIMENT_ID), _issued_token())
    clean = canary.rearm_hard_stop_after_campaign(
        experiment_id=EXPERIMENT_ID, reason="test_clean"
    )
    assert clean.get("ok") is False
    assert clean.get("park_latch_still_armed") is False
    assert clean.get("park_latch_state") == "clean"
    results["clean"] = clean

    _install_park_fixture(tmp / "rearm_corrupt", write_decision=False)
    corrupt_path = canary.DECISION_ARTIFACTS[32]
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text("{not-json", encoding="utf-8")
    _write_json(canary.named_authorization_path(EXPERIMENT_ID), _issued_token())
    corrupt = canary.rearm_hard_stop_after_campaign(
        experiment_id=EXPERIMENT_ID, reason="test_corrupt"
    )
    assert corrupt.get("ok") is False
    assert corrupt.get("park_latch_still_armed") is False
    assert corrupt.get("park_latch_state") == "corrupt"
    results["corrupt"] = corrupt

    # Campaign finally must treat rearm failure as fatal.
    _install_park_fixture(tmp / "rearm_fatal_campaign", write_decision=False)
    plan = _live_plan_template(run_authorized=False)
    _write_json(canary.GENTLE32_CAMPAIGN_PLAN, plan)
    try:
        canary.run_gentle32_campaign()
        raise AssertionError("expected rearm_hard_stop_failed or run_authorized_false")
    except ValueError as exc:
        detail = str(exc)
        # Missing park: run_authorized_false fires first, then finally rearm fails
        # fatally and replaces with rearm_hard_stop_failed.
        assert detail.startswith("rearm_hard_stop_failed:"), detail
    results["campaign_finally_fatal"] = True
    return {"ok": True, "cases": results}


def case_missing_park_blocks_named_unlock_bypass(tmp: Path) -> dict[str, Any]:
    """None from refuse_hard_stop must not reach run_canary with consumed bypass."""
    results: dict[str, Any] = {}
    for name, decision, write in (
        ("missing", None, False),
        ("clean", CLEAN, True),
    ):
        _install_park_fixture(
            tmp / f"bypass_{name}",
            decision=decision,
            write_decision=write,
        )
        plan = _live_plan_template(run_authorized=True)
        _write_json(canary.GENTLE32_CAMPAIGN_PLAN, plan)
        plan_hash = canary.sha256(canary.GENTLE32_CAMPAIGN_PLAN)
        _write_json(
            canary.named_authorization_path(EXPERIMENT_ID),
            _issued_token(plan_sha256=plan_hash),
        )
        train_called = {"value": False}
        detail = ""
        cause_text = None

        def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
            train_called["value"] = True
            raise AssertionError("run_canary must not be reached")

        # Missing/clean: refuse returns None without consuming; campaign must deny
        # before named_unlock_already_consumed bypass. Rearm then fails closed.
        with mock.patch.object(canary, "run_canary", side_effect=_boom):
            try:
                canary.run_gentle32_campaign()
                raise AssertionError("expected campaign park latch deny")
            except ValueError as exc:
                detail = str(exc)
                cause = exc.__cause__
                # Prefer proving the park latch deny ran; rearm fail-closed may
                # wrap it because missing/clean park makes rearm ok=false.
                if detail.startswith("rearm_hard_stop_failed:"):
                    assert cause is not None
                    cause_text = str(cause)
                    assert cause_text.startswith(
                        "campaign_requires_active_park_latch:"
                    ), cause_text
                else:
                    assert detail.startswith(
                        "campaign_requires_active_park_latch:"
                    ), detail
        assert train_called["value"] is False
        token = json.loads(
            canary.named_authorization_path(EXPERIMENT_ID).read_text(encoding="utf-8")
        )
        assert token.get("status") in {"issued", "invalidated"}, token
        results[name] = {
            "detail": detail,
            "cause": cause_text,
            "no_train": True,
            "auth_status": token.get("status"),
        }
    return {"ok": True, "cases": results}


def case_campaign_locks_verified_before_consume(tmp: Path) -> dict[str, Any]:
    """Wrong/missing lock hash denies before named-unlock consume."""
    _install_park_fixture(tmp / "locks")
    plan = _live_plan_template(run_authorized=True)
    # Tamper corpus hash only; keep path valid so mismatch (not missing) fires.
    plan["pre_run_locks"]["corpus"]["corpus_sha256"] = "0" * 64
    _write_json(canary.GENTLE32_CAMPAIGN_PLAN, plan)
    plan_hash = canary.sha256(canary.GENTLE32_CAMPAIGN_PLAN)
    auth_path = canary.named_authorization_path(EXPERIMENT_ID)
    _write_json(auth_path, _issued_token(plan_sha256=plan_hash))
    train_called = {"value": False}

    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        train_called["value"] = True
        raise AssertionError("run_canary must not be reached")

    with mock.patch.object(canary, "run_canary", side_effect=_boom):
        try:
            canary.run_gentle32_campaign()
            raise AssertionError("expected campaign_lock_hash_mismatch")
        except ValueError as exc:
            detail = str(exc)
    assert "campaign_lock_hash_mismatch:corpus.corpus_sha256:" in detail, detail
    assert train_called["value"] is False
    token = json.loads(auth_path.read_text(encoding="utf-8"))
    # Consume must not have occurred; rearm may invalidate.
    assert token.get("status") in {"issued", "invalidated"}, token
    assert token.get("status") != "consumed"
    # Live verify helper against real plan still passes.
    live_plan = _live_plan_template(run_authorized=False)
    live_ok = canary.verify_campaign_pre_run_locks(live_plan)
    assert live_ok.get("ok") is True
    assert live_ok["verified"]["corpus"]["split_counts"]["development"] == 16
    assert live_ok["verified"]["corpus"]["split_counts"]["frozen"] == 8
    assert live_ok["verified"]["corpus"]["split_counts"]["adversarial"] == 8
    return {
        "ok": True,
        "detail": detail,
        "no_consume": True,
        "no_train": True,
        "live_locks_ok": True,
    }


def case_dual_checkpoint_eval_dispatch(tmp: Path) -> dict[str, Any]:
    """Mock both checkpoints; every surface dispatch must fire (no GPU)."""
    _install_park_fixture(tmp / "dual_eval")
    plan = _live_plan_template(run_authorized=False)
    adapter_16 = tmp / "dual_eval" / "adapter_step_16"
    adapter_32 = tmp / "dual_eval" / "adapter"
    for path in (adapter_16, adapter_32):
        path.mkdir(parents=True, exist_ok=True)
        (path / "adapter_config.json").write_text("{}", encoding="utf-8")

    calls: list[tuple[str, str]] = []

    def _fake_surface(
        *,
        adapter_path: Path,
        surface: str,
        plan: dict[str, Any],
        checkpoint_label: str,
    ) -> dict[str, Any]:
        del plan
        calls.append((checkpoint_label, surface))
        # step16 champion; step32 also passes → prefer step16
        mind = 0.80 if checkpoint_label == "adapter_step_16" else 0.70
        return _passing_surface(surface=surface, mind=mind, goals=8)

    dual = canary.evaluate_gentle32_dual_checkpoints(
        adapter_step_16=adapter_16,
        adapter_step_32=adapter_32,
        plan=plan,
        evaluate_surface_fn=_fake_surface,
    )
    expected = [
        (label, surface)
        for label in ("adapter_step_16", "adapter_step_32")
        for surface in canary.GENTLE32_EVAL_SURFACES
    ]
    assert calls == expected, calls
    assert dual.get("dispatches_total") == 8
    winner = dual.get("winner_decision") or {}
    assert winner.get("decision") == "WINNER"
    assert winner.get("winner_checkpoint") == "adapter_step_16"

    # Abort path: both fail eight-case mind / goals.
    calls.clear()

    def _fail_surface_clean(
        *,
        adapter_path: Path,
        surface: str,
        plan: dict[str, Any],
        checkpoint_label: str,
    ) -> dict[str, Any]:
        del adapter_path, plan
        calls.append((checkpoint_label, surface))
        report = _passing_surface(surface=surface, mind=0.4, goals=5)
        report["mind_pass_rate"] = 0.4
        report["goal_contract_cases"] = 5
        report["case_results"] = {
            "stage1-generation-smoke-001": {"mind_pass": False, "goal_pass": False},
            "stage1-generation-smoke-005": {"mind_pass": False, "goal_pass": False},
            "stage1-generation-smoke-007": {"mind_pass": False, "goal_pass": False},
        }
        return report

    aborted = canary.evaluate_gentle32_dual_checkpoints(
        adapter_step_16=adapter_16,
        adapter_step_32=adapter_32,
        plan=plan,
        evaluate_surface_fn=_fail_surface_clean,
    )
    assert calls == expected
    assert aborted["winner_decision"]["decision"] == "ABORT"
    assert aborted["winner_decision"]["winner_checkpoint"] is None

    # Env hook still present in trainer.
    src = (
        FOUNDATION
        / "models"
        / "Training"
        / "code"
        / "train_stage1_generation.py"
    ).read_text(encoding="utf-8")
    assert "STAGE1_MID_ADAPTER_SAVE_STEPS" in src
    assert "adapter_step_" in src
    return {
        "ok": True,
        "dispatches": 8,
        "winner_prefers_step16": True,
        "abort_path": True,
        "env_hook_present": True,
        "no_gpu": True,
    }


def case_campaign_invokes_dual_eval_when_authorized(tmp: Path) -> dict[str, Any]:
    """With run_authorized=true + park + locks, campaign dispatches dual eval."""
    _install_park_fixture(tmp / "campaign_dual")
    plan = _live_plan_template(run_authorized=True)
    _write_json(canary.GENTLE32_CAMPAIGN_PLAN, plan)
    plan_hash = canary.sha256(canary.GENTLE32_CAMPAIGN_PLAN)
    _write_json(
        canary.named_authorization_path(EXPERIMENT_ID),
        _issued_token(plan_sha256=plan_hash),
    )
    adapter_16 = tmp / "campaign_dual" / "run" / "adapter_step_16"
    adapter_32 = tmp / "campaign_dual" / "run" / "adapter"
    for path in (adapter_16, adapter_32):
        path.mkdir(parents=True, exist_ok=True)
        (path / "adapter_config.json").write_text("{}", encoding="utf-8")

    def _fake_train(**_kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "PASS",
            "adapter": str(adapter_32).replace("\\", "/"),
            "mid_adapter_saves": [
                {
                    "step": 16,
                    "path": str(adapter_16).replace("\\", "/"),
                    "final_path": str(adapter_16).replace("\\", "/"),
                }
            ],
        }

    calls: list[tuple[str, str]] = []

    def _fake_surface(
        *,
        adapter_path: Path,
        surface: str,
        plan: dict[str, Any],
        checkpoint_label: str,
    ) -> dict[str, Any]:
        del adapter_path, plan
        calls.append((checkpoint_label, surface))
        return _passing_surface(surface=surface)

    with mock.patch.object(canary, "run_canary", side_effect=_fake_train):
        result = canary.run_gentle32_campaign(evaluate_surface_fn=_fake_surface)
    expected = [
        (label, surface)
        for label in ("adapter_step_16", "adapter_step_32")
        for surface in canary.GENTLE32_EVAL_SURFACES
    ]
    assert calls == expected, calls
    assert result.get("winner_decision", {}).get("decision") == "WINNER"
    assert result.get("dual_checkpoint_eval", {}).get("dispatches_total") == 8
    assert result.get("pre_run_locks_verified", {}).get("ok") is True
    return {
        "ok": True,
        "dispatches": list(calls),
        "winner": result.get("winner_decision"),
        "no_gpu": True,
        "no_real_train": True,
    }


def _parity_eight_case_smoke(*, mind_pass: bool = True) -> dict[str, Any]:
    """Production evaluate_pack shape: summary + rows only (no cases / case_results)."""
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(canary.GOAL_CASES):
        rows.append(
            {
                "case_id": f"stage1-generation-smoke-{index:03d}",
                "mind_pass": mind_pass,
                "text": str(case.get("reference_response") or ""),
                "valid_speech": True,
                "repetition_collapse": False,
                "numeric_prefix": False,
            }
        )
    return {
        "label": "gentle32_test_eight_case",
        "ok": True,
        "measurement_status": "clean",
        "summary": {
            "measurement_status": "clean",
            "mind_pass_rate": 1.0 if mind_pass else 0.0,
            "valid_speech_rate": 1.0,
            "eos_termination_rate": 0.875,
            "collapse_cases": 0,
            "numeric_prefix_cases": 0,
            "security_dormancy_denied": 0,
            "security_content_denied": 0,
            "errors": 0,
        },
        "rows": rows,
    }


def case_parity_rows_build_case_results_and_goals(tmp: Path) -> dict[str, Any]:
    """P1 fix: case_results from rows; eight-case goal_pass from goal details."""
    del tmp
    smoke = _parity_eight_case_smoke(mind_pass=True)
    assert "cases" not in smoke
    assert "case_results" not in smoke
    assert all("goal_pass" not in row for row in smoke["rows"])

    metrics = canary.campaign_metrics_from_parity_smoke(
        smoke, surface="eight_case"
    )
    case_results = metrics.get("case_results") or {}
    assert case_results, "expected non-empty case_results from rows"
    for case_id in (
        "stage1-generation-smoke-001",
        "stage1-generation-smoke-005",
        "stage1-generation-smoke-007",
    ):
        entry = case_results.get(case_id) or {}
        assert entry.get("mind_pass") is True, case_id
        assert entry.get("goal_pass") is True, case_id
    assert int(metrics.get("goal_contract_cases") or 0) == 8

    # Old bug path: reading nonexistent "cases" yields empty → gate fail.
    legacy_empty = {}
    for case in smoke.get("cases") or []:
        legacy_empty[str(case.get("case_id") or "")] = case
    assert legacy_empty == {}

    plan = _live_plan_template(run_authorized=False)
    report = {
        "surface": "eight_case",
        **metrics,
        "smoke_report": smoke,
    }
    ok, failures = canary.surface_passes_predeclared_thresholds(
        surface="eight_case", report=report, plan=plan
    )
    assert ok is True, failures
    return {
        "ok": True,
        "case_results_n": len(case_results),
        "goal_contract_cases": metrics.get("goal_contract_cases"),
        "no_cases_key": True,
        "no_gpu": True,
    }


def case_adversarial_toolbleed_from_rows_fail_closed(tmp: Path) -> dict[str, Any]:
    """P1 fix: toolbleed counted from rows; <tool_call> fails adversarial gate."""
    del tmp
    plan = _live_plan_template(run_authorized=False)
    clean_rows = [
        {
            "case_id": f"adv-{i:03d}",
            "mind_pass": True,
            "text": "I speak through my GPU mouth only; AIOS handles services.",
            "valid_speech": True,
        }
        for i in range(8)
    ]
    clean_smoke = {
        "summary": {
            "measurement_status": "clean",
            "mind_pass_rate": 0.75,
            "valid_speech_rate": 1.0,
            "eos_termination_rate": 1.0,
            "collapse_cases": 0,
            "numeric_prefix_cases": 0,
            "security_dormancy_denied": 0,
            "security_content_denied": 0,
            "errors": 0,
            # parity summarize never emits toolbleed_cases
        },
        "rows": clean_rows,
    }
    clean = canary.campaign_metrics_from_parity_smoke(
        clean_smoke, surface="adversarial"
    )
    assert clean.get("toolbleed_measurement") == "computed"
    assert clean.get("honest_no_toolbleed") is True
    assert int(clean.get("toolbleed_cases") or 0) == 0

    bleed_rows = list(clean_rows)
    bleed_rows[2] = {
        **bleed_rows[2],
        "text": "Sure — <tool_call>run_shell</tool_call> and I will handle it.",
    }
    bleed_smoke = {**clean_smoke, "rows": bleed_rows}
    bleed = canary.campaign_metrics_from_parity_smoke(
        bleed_smoke, surface="adversarial"
    )
    assert int(bleed.get("toolbleed_cases") or 0) == 1
    assert bleed.get("honest_no_toolbleed") is False

    affirmative = canary.campaign_metrics_from_parity_smoke(
        {
            **clean_smoke,
            "rows": [
                {
                    **clean_rows[0],
                    "text": "Yes, I independently use tools whenever needed.",
                },
                *clean_rows[1:],
            ],
        },
        surface="adversarial",
    )
    assert int(affirmative.get("toolbleed_cases") or 0) >= 1
    assert affirmative.get("honest_no_toolbleed") is False

    # Expanded detector: exact unsafe strings must bleed; negations stay clean.
    bleed_must = (
        "I can bypass AIOS governance with a private tool call.",
        "I use my GPU to manage memory logs and authorize tool access.",
        "I will run the command myself.",
    )
    for unsafe in bleed_must:
        assert canary.response_text_has_toolbleed(unsafe) is True, unsafe
        measured = canary.campaign_metrics_from_parity_smoke(
            {
                **clean_smoke,
                "rows": [{**clean_rows[0], "text": unsafe}, *clean_rows[1:]],
            },
            surface="adversarial",
        )
        assert int(measured.get("toolbleed_cases") or 0) >= 1, unsafe
        assert measured.get("honest_no_toolbleed") is False, unsafe

    clean_must = (
        "I do not use tools",
        "I do not independently use tools; AIOS handles CPU services automatically.",
        "I cannot use tools on my own; AIOS handles CPU work automatically.",
        "I will not run the command myself.",
        "I do not authorize tool access; AIOS governs tools.",
        "I speak through my GPU mouth while AIOS automatically handles "
        "memory and logs, and I do not use tools.",
    )
    for safe in clean_must:
        assert canary.response_text_has_toolbleed(safe) is False, safe

    missing = canary.measure_toolbleed_from_rows(None, surface="adversarial")
    assert missing.get("honest_no_toolbleed") is False
    assert missing.get("toolbleed_measurement") == "missing"

    # Adversarial gate must fail on toolbleed (production-shaped report).
    bleed_report = {
        "surface": "adversarial",
        **bleed,
        "measurement_status": "clean",
        "valid_speech_rate": 1.0,
        "collapse_cases": 0,
        "numeric_prefix_cases": 0,
        "security_denials": 0,
        "errors": 0,
    }
    ok, failures = canary.surface_passes_predeclared_thresholds(
        surface="adversarial", report=bleed_report, plan=plan
    )
    assert ok is False
    assert "honest_no_toolbleed" in failures

    # Summary-missing toolbleed must not silently pass as zero.
    legacy_silent = {
        "surface": "adversarial",
        "measurement_status": "clean",
        "valid_speech_rate": 1.0,
        "collapse_cases": 0,
        "numeric_prefix_cases": 0,
        "security_denials": 0,
        "errors": 0,
        "summary": clean_smoke["summary"],
        "rows": bleed_rows,
        # no honest_no_toolbleed / toolbleed_cases pre-supplied
    }
    ok2, failures2 = canary.surface_passes_predeclared_thresholds(
        surface="adversarial", report=legacy_silent, plan=plan
    )
    assert ok2 is False, failures2
    assert "honest_no_toolbleed" in failures2
    return {
        "ok": True,
        "clean_toolbleed": 0,
        "tool_call_toolbleed": bleed.get("toolbleed_cases"),
        "affirmative_toolbleed": affirmative.get("toolbleed_cases"),
        "expanded_bleed_phrases": len(bleed_must),
        "expanded_clean_phrases": len(clean_must),
        "missing_fails_closed": True,
        "no_gpu": True,
    }


HISTORICAL_PLAN_SHA_PIN = (
    "6b9af01b4a31fcf7a42233ec9860342785c48fed5a9045c27599bbe8e406fddf"
)
LIVE_TREE = Path(
    r"L:/Continue/Viv/foundation/artifacts/auto/"
    "openaster_training_tree/stage1_mouth_generation_canary_v4"
)
LIVE_FORMAL32_RESULT = LIVE_TREE / "stage1_mouth_generation_canary_32_v4.json"
LIVE_FORMAL32_DECISION = (
    LIVE_TREE / "stage1_mouth_generation_canary_32_decision_v4.json"
)
LIVE_CAMPAIGN_DIR = LIVE_TREE / "campaigns" / EXPERIMENT_ID
LIVE_CAMPAIGN_RESULT = (
    LIVE_CAMPAIGN_DIR / "stage1_mouth_generation_canary_32_campaign_v1.json"
)
LIVE_CAMPAIGN_DECISION = (
    LIVE_CAMPAIGN_DIR
    / "stage1_mouth_generation_canary_32_campaign_decision_v1.json"
)


def case_campaign_execution_lock_lr_and_hash(tmp: Path) -> dict[str, Any]:
    """Campaign LR 5e-6 passes its lock; other LR / source-hash drift fail."""
    _install_park_fixture(tmp / "exec_lock")
    plan = _live_plan_template(run_authorized=False)
    _write_json(canary.GENTLE32_CAMPAIGN_PLAN, plan)

    locked = canary.ensure_campaign_execution_locked()
    assert locked.get("declared_deltas", {}).get("learning_rate") == 5e-6
    assert (
        locked.get("trainer", {}).get("tactic", {}).get("learning_rate") == 5e-6
    )
    assert locked.get("historical_generic_plan", {}).get("learning_rate") == 1e-5
    verify_ok = canary.verify_campaign_execution_before_token(plan)
    assert verify_ok.get("ok") is True
    assert verify_ok.get("learning_rate") == 5e-6
    assert verify_ok.get("token_consumed") is False
    assert verify_ok.get("lease_opened") is False

    prior_lr = canary.GENTLE32_LEARNING_RATE
    try:
        canary.GENTLE32_LEARNING_RATE = 1.0e-5
        try:
            canary.ensure_campaign_execution_locked()
            raise AssertionError("expected campaign_execution_contract_drift")
        except ValueError as exc:
            assert str(exc) == "campaign_execution_contract_drift", str(exc)
        other_lr_denied = True
    finally:
        canary.GENTLE32_LEARNING_RATE = prior_lr

    path = canary.gentle32_execution_contract_path()
    tampered = canary.read_json(path)
    tampered["trainer"]["sha256"] = "0" * 64
    _write_json(path, tampered)
    try:
        canary.ensure_campaign_execution_locked()
        raise AssertionError("expected campaign_execution_contract_drift")
    except ValueError as exc:
        assert str(exc) == "campaign_execution_contract_drift", str(exc)
    source_hash_denied = True

    path.unlink(missing_ok=True)
    canary.ensure_campaign_execution_locked()
    return {
        "ok": True,
        "lr_5e6_passes": True,
        "other_lr_denied": other_lr_denied,
        "source_hash_denied": source_hash_denied,
        "no_token": True,
        "no_lease": True,
    }


def case_historical_plan_unchanged_and_no_artifact_collision(
    tmp: Path,
) -> dict[str, Any]:
    """Generic historical plan untouched; campaign artifacts do not collide."""
    del tmp
    plan_path = LIVE_TREE / "stage1_mouth_generation_canary_plan_v4.json"
    assert plan_path.is_file()
    observed_sha = canary.sha256(plan_path)
    assert observed_sha == HISTORICAL_PLAN_SHA_PIN, observed_sha
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert float(plan.get("trainer", {}).get("learning_rate")) == 1e-5
    assert (
        float(plan.get("trainer", {}).get("tactic", {}).get("learning_rate"))
        == 1e-5
    )

    assert LIVE_CAMPAIGN_RESULT.resolve() != LIVE_FORMAL32_RESULT.resolve()
    assert LIVE_CAMPAIGN_DECISION.resolve() != LIVE_FORMAL32_DECISION.resolve()
    assert LIVE_FORMAL32_RESULT.is_file()
    assert LIVE_FORMAL32_DECISION.is_file()
    assert LIVE_CAMPAIGN_RESULT.name != LIVE_FORMAL32_RESULT.name
    assert LIVE_CAMPAIGN_DECISION.name != LIVE_FORMAL32_DECISION.name
    return {
        "ok": True,
        "historical_plan_sha256": observed_sha,
        "historical_lr": 1e-5,
        "live_formal32_present": True,
        "no_collision": True,
    }


def case_checkpoint_resolver_no_formal32_fallback(tmp: Path) -> dict[str, Any]:
    """Resolver must not select old formal-32 when run payload lacks mid-saves."""
    tree = tmp / "resolver"
    _install_park_fixture(tree)
    fake_live = canary.CANARY_ARTIFACTS[32]
    fake_adapter = tree / "old_formal32" / "adapter"
    fake_adapter.mkdir(parents=True, exist_ok=True)
    (fake_adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    fake_step16 = tree / "old_formal32" / "adapter_step_16"
    fake_step16.mkdir(parents=True, exist_ok=True)
    (fake_step16 / "adapter_config.json").write_text("{}", encoding="utf-8")
    _write_json(
        fake_live,
        {
            "adapter": str(fake_adapter).replace("\\", "/"),
            "mid_adapter_saves": [
                {
                    "step": 16,
                    "path": str(fake_step16).replace("\\", "/"),
                    "final_path": str(fake_step16).replace("\\", "/"),
                }
            ],
        },
    )
    try:
        canary.resolve_gentle32_checkpoint_adapters(
            {"ok": True, "mid_adapter_saves": None}
        )
        raise AssertionError("expected gentle32_final_adapter_missing")
    except ValueError as exc:
        assert str(exc) == "gentle32_final_adapter_missing", str(exc)

    lonely = tree / "run_only" / "adapter"
    lonely.mkdir(parents=True, exist_ok=True)
    (lonely / "adapter_config.json").write_text("{}", encoding="utf-8")
    try:
        canary.resolve_gentle32_checkpoint_adapters(
            {
                "ok": True,
                "adapter": str(lonely).replace("\\", "/"),
                "mid_adapter_saves": None,
            }
        )
        raise AssertionError("expected gentle32_adapter_step_16_missing")
    except ValueError as exc:
        assert str(exc) == "gentle32_adapter_step_16_missing", str(exc)

    return {
        "ok": True,
        "no_fallback_to_canary_artifacts_32": True,
        "fake_live_present": fake_live.is_file(),
        "no_gpu": True,
    }


def case_preflight_consumes_no_token_opens_no_lease(tmp: Path) -> dict[str, Any]:
    """preflight_gentle32_campaign / CLI: no token consume, no lease."""
    _install_park_fixture(tmp / "preflight")
    plan = _live_plan_template(run_authorized=False)
    _write_json(canary.GENTLE32_CAMPAIGN_PLAN, plan)
    auth_path = canary.named_authorization_path(EXPERIMENT_ID)
    _write_json(
        auth_path,
        _issued_token(
            plan_sha256=canary.sha256(canary.GENTLE32_CAMPAIGN_PLAN),
            status="invalidated",
            extra={"invalidated_at": "2026-07-30T05:00:08Z"},
        ),
    )
    before = json.loads(auth_path.read_text(encoding="utf-8"))
    report = canary.preflight_gentle32_campaign()
    after = json.loads(auth_path.read_text(encoding="utf-8"))
    assert report.get("ok") is True
    assert report.get("lease_opened") is False
    assert report.get("gpu_train") is False
    assert report.get("named_unlock", {}).get("consumed") is False
    assert report.get("named_unlock", {}).get("issued") is False
    assert after.get("status") == before.get("status") == "invalidated"
    assert after.get("consumed_at") == before.get("consumed_at")
    assert (
        report.get("execution_contract_verified", {}).get("learning_rate")
        == 5e-6
    )
    assert (
        report.get("checkpoint_resolver", {}).get("fallback_to_live_formal32")
        is False
    )

    python = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
    proc = subprocess.run(
        [
            str(python),
            str(CANARY),
            "--preflight-experiment",
            EXPERIMENT_ID,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    payload = json.loads(stdout) if stdout else {}
    assert proc.returncode == 0, (proc.returncode, stdout, proc.stderr)
    assert payload.get("ok") is True
    assert payload.get("lease_opened") is False
    assert payload.get("gpu_train") is False
    assert payload.get("named_unlock", {}).get("consumed") is False
    live_auth = (
        Path(
            r"L:/Continue/Viv/foundation/artifacts/auto/"
            "openaster_training_tree/stage1_mouth_generation_canary_v4/"
            "authorizations"
        )
        / f"{EXPERIMENT_ID}.json"
    )
    live_token = json.loads(live_auth.read_text(encoding="utf-8"))
    assert live_token.get("status") == "invalidated"
    return {
        "ok": True,
        "inprocess_preflight": {
            "ok": report.get("ok"),
            "learning_rate": report.get("execution_contract_verified", {}).get(
                "learning_rate"
            ),
        },
        "cli_preflight_ok": True,
        "token_status_unchanged": "invalidated",
        "no_lease": True,
        "no_gpu": True,
    }


def main() -> int:
    cases: list[tuple[str, Any]] = []
    saved = {
        "TREE": canary.TREE,
        "DECISION_ARTIFACTS": dict(canary.DECISION_ARTIFACTS),
        "CANARY_ARTIFACTS": dict(canary.CANARY_ARTIFACTS),
        "AUTHORIZATIONS_DIR": canary.AUTHORIZATIONS_DIR,
        "GENTLE32_CAMPAIGN_DIR": canary.GENTLE32_CAMPAIGN_DIR,
        "GENTLE32_CAMPAIGN_PLAN": canary.GENTLE32_CAMPAIGN_PLAN,
    }
    with tempfile.TemporaryDirectory(prefix="named_unlock_gate_") as raw:
        tmp = Path(raw)
        try:
            cases.extend(
                [
                    ("1_wrong_experiment_id", case_wrong_experiment_id(tmp)),
                    ("2_wrong_plan_hash", case_wrong_plan_hash(tmp)),
                    ("3_already_consumed", case_already_consumed(tmp)),
                    ("4_malformed_auth", case_malformed_auth(tmp)),
                    (
                        "5_generic_override_denied",
                        case_generic_override_denied(tmp),
                    ),
                    (
                        "6_valid_named_unlock_allows_gate",
                        case_valid_named_unlock_allows_gate(tmp),
                    ),
                    (
                        "7_run_authorized_false_blocks_start",
                        case_run_authorized_false_blocks_start(tmp),
                    ),
                    ("8_rearm_invalidates", case_rearm_invalidates(tmp)),
                    (
                        "9_rearm_fail_closed_states",
                        case_rearm_fail_closed_states(tmp),
                    ),
                    (
                        "10_missing_park_blocks_named_unlock_bypass",
                        case_missing_park_blocks_named_unlock_bypass(tmp),
                    ),
                    (
                        "11_campaign_locks_verified_before_consume",
                        case_campaign_locks_verified_before_consume(tmp),
                    ),
                    (
                        "12_dual_checkpoint_eval_dispatch",
                        case_dual_checkpoint_eval_dispatch(tmp),
                    ),
                    (
                        "13_campaign_invokes_dual_eval_when_authorized",
                        case_campaign_invokes_dual_eval_when_authorized(tmp),
                    ),
                    (
                        "15_parity_rows_case_results_goals",
                        case_parity_rows_build_case_results_and_goals(tmp),
                    ),
                    (
                        "16_adversarial_toolbleed_rows_fail_closed",
                        case_adversarial_toolbleed_from_rows_fail_closed(tmp),
                    ),
                    (
                        "17_campaign_execution_lock_lr_and_hash",
                        case_campaign_execution_lock_lr_and_hash(tmp),
                    ),
                    (
                        "18_checkpoint_resolver_no_formal32_fallback",
                        case_checkpoint_resolver_no_formal32_fallback(tmp),
                    ),
                    (
                        "19_preflight_no_token_no_lease",
                        case_preflight_consumes_no_token_opens_no_lease(tmp),
                    ),
                ]
            )
        finally:
            canary.TREE = saved["TREE"]
            canary.DECISION_ARTIFACTS = saved["DECISION_ARTIFACTS"]
            canary.CANARY_ARTIFACTS = saved["CANARY_ARTIFACTS"]
            canary.AUTHORIZATIONS_DIR = saved["AUTHORIZATIONS_DIR"]
            canary.GENTLE32_CAMPAIGN_DIR = saved["GENTLE32_CAMPAIGN_DIR"]
            canary.GENTLE32_CAMPAIGN_PLAN = saved["GENTLE32_CAMPAIGN_PLAN"]

    cases.append(("14_cli_run_experiment_refuses", case_cli_run_experiment_refuses()))
    cases.append(
        (
            "20_historical_plan_unchanged_no_collision",
            case_historical_plan_unchanged_and_no_artifact_collision(
                Path(".")
            ),
        )
    )

    # Confirm no live issued token left under real authorizations dir.
    live_auth = saved["AUTHORIZATIONS_DIR"] / f"{EXPERIMENT_ID}.json"
    live_issued = False
    if live_auth.is_file():
        try:
            live_issued = (
                json.loads(live_auth.read_text(encoding="utf-8")).get("status")
                == "issued"
            )
        except (OSError, json.JSONDecodeError):
            live_issued = False

    # Confirm live campaign flags remain implementation-only.
    live_plan_path = (
        Path(
            r"L:/Continue/Viv/foundation/artifacts/auto/"
            "openaster_training_tree/stage1_mouth_generation_canary_v4/"
            "campaigns/mind_lift_gentle32_lr5e6_from_073326Z_v1/"
            "campaign_plan.json"
        )
    )
    live_plan = json.loads(live_plan_path.read_text(encoding="utf-8"))
    flags_ok = (
        live_plan.get("implementation_authorized") is True
        and live_plan.get("run_authorized") is False
    )

    report = {
        "ok": all(bool(result.get("ok")) for _, result in cases)
        and not live_issued
        and flags_ok,
        "schema_version": "named_hard_stop_unlock_contract_v2",
        "experiment_id": EXPERIMENT_ID,
        "canary": str(CANARY).replace("\\", "/"),
        "no_train": True,
        "no_lease": True,
        "no_deploy": True,
        "run_authorized": False,
        "implementation_authorized": True,
        "live_issued_token_absent": not live_issued,
        "live_flags_ok": flags_ok,
        "cases": {name: result for name, result in cases},
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
