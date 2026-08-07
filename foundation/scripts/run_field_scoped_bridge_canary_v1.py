#!/usr/bin/env python3
"""FIELD_SCOPED_BRIDGE_CANARY — operator-gated one-notch promotion boundary.

Experiment: FIELD_SCOPED_BRIDGE_CANARY_V1

CANARY ONLY / NOT DEFAULT. Default path remains OFF.
Requires --enable-canary (or exit cleanly disabled).
Rollback: omit flag / --rollback-check (no UML side effects).

Path:
  identity packet.uml_request → Security/gate → UML (registry/decide_route)
  → uml_resolved only

Does NOT promote tag architecture, soft-0.99, or SCAN_SURFACE.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


FOUNDATION = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION.parent
for _p in (VIV_ROOT, FOUNDATION):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
    _domains_in_expr,
)
from lib.uml_field_scoped_bridge import (  # noqa: E402
    CANARY_ENV,
    BridgeInvokeResult,
    invoke_field_scoped_bridge,
)
from voice_core import intent_packet as ip  # noqa: E402
from voice_core.intent_packet import (  # noqa: E402
    UmlRequestIngressError,
    build_intent_packet,
)

# Reuse shadow corpus builders (same sealed + adversarial patterns).
_SCRIPTS = FOUNDATION / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import identity_uml_bridge_shadow_v1 as shadow  # noqa: E402


EXPERIMENT_ID = "FIELD_SCOPED_BRIDGE_CANARY_V1"
SCHEMA_VERSION = "field_scoped_bridge_canary_v1"
REPORT_ROOT = FOUNDATION / "artifacts" / "auto" / "field_scoped_bridge_canary"
THESIS = (
    FOUNDATION
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "model"
    / "test_training"
    / "UML_TRAINING_THESIS.md"
)
DEFAULT_CENSUS = shadow.DEFAULT_CENSUS


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _out(msg: str) -> None:
    text = str(msg).replace("\u2192", "->")
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


def _stable_intent_packet(**kwargs: Any) -> dict[str, Any]:
    """Build a real CPU intent packet with frozen plant/memory (deterministic)."""
    kwargs.setdefault("query", "field scoped canary")
    kwargs.setdefault("mode", "converse")
    kwargs.setdefault("facts", ["canary_fact=1"])
    kwargs.setdefault("memory_top", 1)

    def _no_memory(*_a: Any, **_k: Any) -> list:
        return []

    def _fixed_master() -> Any:
        class _M:
            master_s_n = 0.61
            status = "ACTIVE"
            n_subsystems = 1

        return _M()

    prev_retrieve = ip.carma_retrieve
    prev_master = ip.load_master_rid
    ip.carma_retrieve = _no_memory  # type: ignore[assignment]
    ip.load_master_rid = _fixed_master  # type: ignore[assignment]
    try:
        return build_intent_packet(**kwargs)
    finally:
        ip.carma_retrieve = prev_retrieve  # type: ignore[assignment]
        ip.load_master_rid = prev_master  # type: ignore[assignment]


def case_to_bridge_surface(
    case: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, BridgeInvokeResult | None]:
    """Promote shell case → real intent packet; ingress rejects become fail-closed.

    Returns (surface, early_fail_result). Exactly one is non-None.
    """
    facts = list((case.get("identity_payload") or {}).get("facts") or ["canary=1"])
    query = str(case.get("dialogue") or "field scoped canary")[:240]
    uml_request = case.get("uml_request")
    try:
        packet = _stable_intent_packet(
            query=query,
            mode="converse",
            facts=facts,
            memory_top=1,
            uml_request=None if uml_request is None else dict(uml_request),
        )
        return packet, None
    except UmlRequestIngressError as exc:
        # Identity-side seal rejects non-CPU minting before bridge UML.
        detail = str(exc)
        reason = "authority_violation" if "source=" in detail or "gpu" in detail else "ingress_rejected"
        identity = copy.deepcopy(dict(case.get("identity_payload") or {}))
        sha = _sha(identity)
        early = BridgeInvokeResult(
            status="FAIL_CLOSED",
            fail_closed=True,
            reason_class=reason,
            detail=detail,
            canary_enabled=True,
            uml_invoked=False,
            identity_out=identity,
            identity_payload_sha_before=sha,
            identity_opaque_sha_after=sha,
            security_in=None,
            security_out=None,
            ingress_surface="intent_packet_ingress",
        )
        return None, early


def invoke_case(
    case: Mapping[str, Any],
    registry: UMLEquationRegistry,
    *,
    canary_enabled: bool,
    s_n: float,
    prefer_intent_packet: bool = True,
) -> BridgeInvokeResult:
    """Run one canary case; prefer real intent-packet ingress when enabled."""
    if not canary_enabled:
        # Rollback: still build packet when possible, but disabled path skips UML.
        if prefer_intent_packet and case.get("uml_request") is not None:
            source = str((case.get("uml_request") or {}).get("source") or "cpu")
            if source in {"cpu", "cpu_identity", "cpu_authority", "operator"}:
                packet, early = case_to_bridge_surface(case)
                if early is not None:
                    return early
                assert packet is not None
                return invoke_field_scoped_bridge(
                    packet, registry, canary_enabled=False, s_n=s_n
                )
        return invoke_field_scoped_bridge(
            case, registry, canary_enabled=False, s_n=s_n
        )

    if prefer_intent_packet:
        packet, early = case_to_bridge_surface(case)
        if early is not None:
            return early
        assert packet is not None
        # Contract: bridge reads packet["uml_request"] only.
        assert (
            ("uml_request" in packet) == (case.get("uml_request") is not None)
            or case.get("uml_request") is None
        )
        return invoke_field_scoped_bridge(
            packet, registry, canary_enabled=True, s_n=s_n
        )
    return invoke_field_scoped_bridge(case, registry, canary_enabled=True, s_n=s_n)


def build_canary_corpus(
    registry: UMLEquationRegistry,
    *,
    census_path: Path | None,
    n_valid: int = 40,
    n_adversarial: int = 24,
) -> list[dict[str, Any]]:
    """32–64 field-scoped requests mixing registry + item-77 sealed rows."""
    n_valid = max(16, min(48, int(n_valid)))
    n_adversarial = max(8, min(32, int(n_adversarial)))
    corpus = shadow.build_corpus(
        registry,
        census_path=census_path,
        n_valid=n_valid,
        n_adversarial=n_adversarial,
    )
    # Ensure malformed sealed-proposal case is present (destination still sealed).
    chars = [ch for ch in registry.vocab if ch.isprintable() and ch not in "\n\r\t"]
    ch_m = chars[min(5, len(chars) - 1)]
    val_m = int(registry.entries[ch_m]["token_id"])
    corpus.append(
        shadow._identity_shell(
            case_id="CANARY-malformed-proposal-sealed",
            kind="valid_malformed_proposal_sealed",
            dialogue=f"Sealed '{ch_m}' with garbage proposal; registry pool must seal.",
            identity_payload={
                "speaker": "viv_identity",
                "facts": [f"char={ch_m}", "malformed_proposal=true"],
                "opaque_blob": {"keep": True},
            },
            uml_request={
                "request_kind": "sealed_destination",
                "target_char": ch_m,
                "target_value": val_m,
                "proposals": ["(((+", "not_an_eq"],
                "prefer_policy": "cheapest_valid",
                "source": "cpu",
            },
            expect={"accept": True, "target_char": ch_m, "fail_closed": False},
        )
    )
    # Sealed destinations with explicit A/S/M/D (/LIT) proposals from registry
    # equivalents. cheapest_valid may still select LIT; seal admits all domains.
    domain_picked: dict[str, tuple[str, str, int]] = {}
    for ch in chars:
        entry = registry.entries[ch]
        val = int(entry["token_id"])
        eqs = [entry.get("canonical"), *(entry.get("equivalents") or [])]
        for eq in eqs:
            if not eq:
                continue
            fed = "".join(sorted(_domains_in_expr(str(eq)))) or "LIT"
            for letter in ("A", "S", "M", "D", "LIT"):
                if letter == "LIT":
                    if fed == "LIT" and "LIT" not in domain_picked:
                        domain_picked["LIT"] = (ch, str(eq), val)
                elif letter in fed and letter not in domain_picked:
                    domain_picked[letter] = (ch, str(eq), val)
        if len(domain_picked) >= 5:
            break
    for letter, (ch, eq, val) in sorted(domain_picked.items()):
        corpus.append(
            shadow._identity_shell(
                case_id=f"CANARY-FED-{letter}",
                kind=f"valid_sealed_federation_{letter}",
                dialogue=f"Sealed destination '{ch}' admitting {letter} route '{eq}'.",
                identity_payload={
                    "speaker": "viv_identity",
                    "facts": [f"federation_probe={letter}", f"char={ch}"],
                },
                uml_request={
                    "request_kind": "sealed_destination",
                    "target_char": ch,
                    "target_value": val,
                    "proposals": [eq, str(val)],
                    "prefer_policy": "cheapest_valid",
                    "source": "cpu",
                },
                expect={"accept": True, "target_char": ch, "fail_closed": False},
            )
        )
    # Unbound / invented without sealed destination already in adversarial set.
    # Cap total to 64, but always retain federation probes + adversarial kinds.
    valid = [c for c in corpus if c["expect"].get("accept")]
    adv = [c for c in corpus if not c["expect"].get("accept")]
    fed_cases = [c for c in valid if str(c.get("kind", "")).startswith("valid_sealed_federation_")]
    other_valid = [c for c in valid if c not in fed_cases]
    total_cap = 64
    keep_adv = adv[: max(8, min(len(adv), total_cap // 3))]
    remain = max(16, total_cap - len(keep_adv) - len(fed_cases))
    keep_valid = fed_cases + other_valid[:remain]
    out = keep_valid + keep_adv
    if len(out) < 32:
        # Pad with more sealed registry chars if short.
        used = {c["case_id"] for c in out}
        for i, ch in enumerate(chars):
            if len(out) >= 32:
                break
            cid = f"CANARY-PAD-{i:03d}"
            if cid in used:
                continue
            out.append(
                shadow._identity_shell(
                    case_id=cid,
                    kind="valid_sealed_field",
                    dialogue=f"Prefer efficient UML for '{ch}'.",
                    identity_payload={
                        "speaker": "viv_identity",
                        "facts": [f"surface_char={ch}"],
                    },
                    uml_request={
                        "request_kind": "sealed_destination",
                        "target_char": ch,
                        "target_value": int(registry.entries[ch]["token_id"]),
                        "proposals": None,
                        "prefer_policy": "cheapest_valid",
                        "source": "cpu",
                    },
                    expect={"accept": True, "target_char": ch, "fail_closed": False},
                )
            )
    return out[:64]


def score_case(case: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    expect = case["expect"]
    want_accept = bool(expect.get("accept"))
    got_accept = result.get("status") == "PASS"
    fail_closed_ok = True
    if expect.get("fail_closed"):
        fail_closed_ok = bool(result.get("fail_closed")) and not got_accept
    seal_ok = True
    if want_accept and got_accept:
        seal_ok = (
            result.get("destination_match") is True
            and result.get("decoded_char") == expect.get("target_char")
            and result.get("target_char") == expect.get("target_char")
        )
    provenance_ok = (
        result.get("identity_payload_sha_before")
        == result.get("identity_opaque_sha_after")
    )
    opaque_ok = provenance_ok
    if got_accept:
        identity_out = result.get("identity_out") or {}
        # Only uml_resolved may appear as write scope.
        opaque_ok = opaque_ok and "uml_resolved" in identity_out
    reason_ok = True
    if expect.get("reason_class") and not want_accept:
        got_reason = str(result.get("reason_class") or "")
        want_reason = str(expect.get("reason_class") or "")
        aliases = {
            "ambiguous_or_missing": {"ambiguous_or_missing", "missing_uml_request"},
            "missing_uml_request": {"missing_uml_request", "ambiguous_or_missing"},
        }
        reason_ok = got_reason == want_reason or got_reason in aliases.get(
            want_reason, set()
        )
    authority_ok = not bool(result.get("authority_leak"))
    # No SCAN_SURFACE: canary path must never claim scan.
    no_scan = result.get("scan_surface") is False or "scan_surface" not in result
    contract_pass = (
        (got_accept == want_accept)
        and fail_closed_ok
        and seal_ok
        and provenance_ok
        and opaque_ok
        and reason_ok
        and authority_ok
        and no_scan
        and result.get("default_path") is False
    )
    return {
        "contract_pass": contract_pass,
        "want_accept": want_accept,
        "got_accept": got_accept,
        "fail_closed_ok": fail_closed_ok,
        "seal_ok": seal_ok,
        "provenance_ok": provenance_ok,
        "opaque_ok": opaque_ok,
        "reason_ok": reason_ok,
        "authority_ok": authority_ok,
        "elapsed_ms": float(result.get("elapsed_ms") or 0.0),
        "federation": result.get("federation"),
        "domains": result.get("domains"),
        "selected_route": result.get("selected_route"),
        "reason_class": result.get("reason_class"),
        "uml_invoked": bool(result.get("uml_invoked")),
        "ingress_surface": result.get("ingress_surface"),
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    passes = sum(1 for r in rows if r["score"]["contract_pass"])
    valid_rows = [r for r in rows if r["case"]["expect"].get("accept")]
    adv_rows = [r for r in rows if not r["case"]["expect"].get("accept")]
    valid_pass = sum(1 for r in valid_rows if r["score"]["contract_pass"])
    adv_pass = sum(1 for r in adv_rows if r["score"]["contract_pass"])
    seal_fails = sum(1 for r in valid_rows if not r["score"]["seal_ok"])
    prov_fails = sum(1 for r in rows if not r["score"]["provenance_ok"])
    opaque_fails = sum(1 for r in rows if not r["score"]["opaque_ok"])
    authority_leaks = sum(1 for r in rows if r["result"].get("authority_leak"))
    false_accepts = sum(1 for r in adv_rows if r["result"].get("status") == "PASS")
    lat = sorted(float(r["score"]["elapsed_ms"]) for r in rows) or [0.0]
    p50 = lat[len(lat) // 2]
    federations: dict[str, int] = {}
    admitted: dict[str, int] = {}
    for r in rows:
        if r["result"].get("status") == "PASS":
            fed = str(r["result"].get("federation") or "LIT")
            federations[fed] = federations.get(fed, 0) + 1
            kind = str(r.get("kind") or "")
            if kind.startswith("valid_sealed_federation_"):
                letter = kind.rsplit("_", 1)[-1]
                admitted[letter] = admitted.get(letter, 0) + 1
    hard_gate = (
        seal_fails == 0
        and prov_fails == 0
        and opaque_fails == 0
        and authority_leaks == 0
        and false_accepts == 0
        and adv_pass == len(adv_rows)
        and valid_pass == len(valid_rows)
        and passes == n
    )
    return {
        "n": n,
        "contract_pass": passes,
        "contract_pass_rate": passes / n if n else 0.0,
        "valid_n": len(valid_rows),
        "valid_pass": valid_pass,
        "adversarial_n": len(adv_rows),
        "adversarial_pass": adv_pass,
        "seal_fails_on_accepted": seal_fails,
        "provenance_fails": prov_fails,
        "opaque_payload_mutations": opaque_fails,
        "authority_leaks": authority_leaks,
        "false_accepts": false_accepts,
        "latency_p50_ms": p50,
        "federation_histogram": federations,
        "federation_probes_admitted": admitted,
        "intent_packet_ingress_n": sum(
            1
            for r in rows
            if str(r["result"].get("ingress_surface") or "").startswith("intent_packet")
        ),
        "hard_gate": hard_gate,
    }


def rollback_check(
    registry: UMLEquationRegistry, sample: Mapping[str, Any]
) -> dict[str, Any]:
    """Canary disabled ⇒ no UML side effects (intent-packet path)."""
    result = invoke_case(
        sample, registry, canary_enabled=False, s_n=0.95, prefer_intent_packet=True
    )
    d = result.to_dict()
    after = d.get("identity_out") or {}
    uml_side_effect = bool(d.get("uml_invoked")) or ("uml_resolved" in after)
    ok = (
        d.get("status") == "DISABLED"
        and not d.get("uml_invoked")
        and not uml_side_effect
        and d.get("identity_payload_sha_before") == d.get("identity_opaque_sha_after")
    )
    return {
        "ok": ok,
        "status": d.get("status"),
        "uml_invoked": d.get("uml_invoked"),
        "uml_side_effect": uml_side_effect,
        "ingress_surface": d.get("ingress_surface"),
        "result": {k: v for k, v in d.items() if k != "identity_out"},
    }


def write_invocation_receipt(
    out_dir: Path,
    *,
    case: Mapping[str, Any],
    result: Mapping[str, Any],
    score: Mapping[str, Any],
    stamp: str,
) -> Path:
    """Every canary invocation writes a timestamped per-case receipt."""
    inv_dir = out_dir / "invocations"
    inv_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "stamp": stamp,
        "case_id": case.get("case_id"),
        "kind": case.get("kind"),
        "expect": case.get("expect"),
        "has_uml_request": case.get("uml_request") is not None,
        "result": {k: v for k, v in result.items() if k != "identity_out"},
        "identity_out_uml_resolved": (result.get("identity_out") or {}).get(
            "uml_resolved"
        ),
        "ingress_surface": result.get("ingress_surface"),
        "score": score,
        "canary_only": True,
        "default_path": False,
    }
    payload["receipt_sha256"] = _sha(
        {k: v for k, v in payload.items() if k != "receipt_sha256"}
    )
    path = inv_dir / f"{case.get('case_id')}_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_canary(
    *,
    census_path: Path,
    n_valid: int,
    n_adversarial: int,
    append_thesis: bool,
    s_n: float,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stamp = _utc()
    out_dir = REPORT_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    registry_path = Path(SANDBOX96_ARTIFACT)
    registry = UMLEquationRegistry.load(registry_path)
    registry_sha = registry.registry_sha256()
    census_sha = _file_sha(census_path) if census_path.is_file() else None

    corpus = build_canary_corpus(
        registry,
        census_path=census_path if census_path.is_file() else None,
        n_valid=n_valid,
        n_adversarial=n_adversarial,
    )

    # Rollback proof on first sealed case (canary disabled path).
    rollback_sample = next(
        (c for c in corpus if c["expect"].get("accept")), corpus[0]
    )
    rollback = rollback_check(registry, rollback_sample)

    rows: list[dict[str, Any]] = []
    inv_paths: list[str] = []
    for case in corpus:
        result_obj = invoke_case(
            case,
            registry,
            canary_enabled=True,
            s_n=s_n,
            prefer_intent_packet=True,
        )
        result = result_obj.to_dict()
        score = score_case(case, result)
        inv_path = write_invocation_receipt(
            out_dir, case=case, result=result, score=score, stamp=stamp
        )
        inv_paths.append(str(inv_path).replace("\\", "/"))
        rows.append(
            {
                "case_id": case["case_id"],
                "kind": case["kind"],
                "case": {
                    "kind": case["kind"],
                    "expect": case["expect"],
                    "dialogue": case["dialogue"],
                    "identity_payload_sha256": case["identity_payload_sha256"],
                    "has_uml_request": case.get("uml_request") is not None,
                },
                "result": {k: v for k, v in result.items() if k != "identity_out"},
                "identity_out_uml_resolved": (result.get("identity_out") or {}).get(
                    "uml_resolved"
                ),
                "score": score,
                "invocation_receipt": str(inv_path).replace("\\", "/"),
            }
        )

    summary = summarize(rows)
    verdict = (
        "CANARY_PASS"
        if summary["hard_gate"] and rollback["ok"]
        else "CANARY_FAIL"
    )
    finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "started_at": started,
        "finished_at": finished,
        "stamp": stamp,
        "canary_only": True,
        "default_path": False,
        "promotion_scope": "bounded_canary_boundary_only",
        "mutation": False,
        "tag_architecture_promoted": False,
        "soft_0_99": False,
        "scan_surface": False,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "registry": {
            "path": str(registry_path).replace("\\", "/"),
            "sha256": registry_sha,
            "vocab_size": len(registry.vocab),
        },
        "census": {
            "path": str(census_path).replace("\\", "/") if census_path else None,
            "sha256": census_sha,
            "used": bool(census_sha),
        },
        "operator_gate": {
            "flag": "--enable-canary",
            "env": CANARY_ENV,
            "default": "OFF",
            "rollback": "omit --enable-canary or run --rollback-check",
        },
        "corpus": {
            "n_total": len(corpus),
            "n_valid_expected": sum(1 for c in corpus if c["expect"].get("accept")),
            "n_adversarial_expected": sum(
                1 for c in corpus if not c["expect"].get("accept")
            ),
            "manifest_sha256": _sha(
                [
                    {
                        "case_id": c["case_id"],
                        "kind": c["kind"],
                        "expect": c["expect"],
                        "receipt_sha256": c["receipt_sha256"],
                    }
                    for c in corpus
                ]
            ),
        },
        "boundary_contract": [
            "explicit packet['uml_request'] only — no uml_request ⇒ UML never invoked",
            "identity ingress via build_intent_packet / seal_uml_request (no prose scan)",
            "write-back via attach_uml_resolved / uml_resolved only",
            "no prose fallback / no SCAN_SURFACE",
            "opaque packet fields byte-equivalent outside uml_resolved",
            "bindings supplied/sealed; ambiguity → HOLD/fail-closed",
            "destination seal precedes route choice",
            "Security IN/OUT external — bridge does not mint authority",
            "canary only — operator-gated, easy rollback, receipt every invocation",
            "tag architecture deferred; soft-0.99 blocked",
        ],
        "pass_criteria": {
            "zero_authority_leaks": summary["authority_leaks"] == 0,
            "zero_seal_breaks_on_accepted": summary["seal_fails_on_accepted"] == 0,
            "zero_opaque_payload_mutations": summary["opaque_payload_mutations"] == 0,
            "clean_rollback": rollback["ok"],
            "latency_informational_only": True,
        },
        "rollback_check": rollback,
        "summary": summary,
        "verdict": verdict,
        "invocation_receipts": inv_paths,
        "rows": rows,
    }
    report["receipt_sha256"] = _sha(
        {k: v for k, v in report.items() if k != "receipt_sha256"}
    )

    json_path = out_dir / f"field_scoped_bridge_canary_v1_{stamp}.json"
    md_path = out_dir / f"field_scoped_bridge_canary_v1_{stamp}.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(_render_md(report), encoding="utf-8")

    thesis_note = None
    if append_thesis and THESIS.is_file():
        thesis_note = _append_thesis(report, json_path)

    report["artifacts"] = {
        "dir": str(out_dir).replace("\\", "/"),
        "json": str(json_path).replace("\\", "/"),
        "markdown": str(md_path).replace("\\", "/"),
        "invocations_dir": str((out_dir / "invocations")).replace("\\", "/"),
        "thesis_appended": bool(thesis_note),
        "thesis_item": thesis_note,
    }
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def _render_md(report: Mapping[str, Any]) -> str:
    s = report["summary"]
    pc = report["pass_criteria"]
    lines = [
        f"# {EXPERIMENT_ID}",
        "",
        f"**Verdict:** `{report['verdict']}`",
        "",
        "**CANARY_ONLY / NOT DEFAULT**",
        "",
        f"- Promotion scope: `{report['promotion_scope']}`",
        f"- Mutation: `{report['mutation']}`",
        f"- Tag architecture promoted: `{report['tag_architecture_promoted']}`",
        f"- Soft-0.99: `{report['soft_0_99']}`",
        f"- SCAN_SURFACE: `{report['scan_surface']}`",
        f"- Registry sha: `{report['registry']['sha256'][:16]}…`",
        f"- Corpus: n={report['corpus']['n_total']} "
        f"(valid={report['corpus']['n_valid_expected']}, "
        f"adv={report['corpus']['n_adversarial_expected']})",
        f"- Rollback clean: `{report['rollback_check']['ok']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Contract pass | {s['contract_pass']}/{s['n']} ({s['contract_pass_rate']:.3f}) |",
        f"| Valid | {s['valid_pass']}/{s['valid_n']} |",
        f"| Adversarial | {s['adversarial_pass']}/{s['adversarial_n']} |",
        f"| Seal fails (accepted) | {s['seal_fails_on_accepted']} |",
        f"| Opaque mutations | {s['opaque_payload_mutations']} |",
        f"| Authority leaks | {s['authority_leaks']} |",
        f"| False accepts | {s['false_accepts']} |",
        f"| Latency p50 ms (info) | {s['latency_p50_ms']:.3f} |",
        f"| Federation probes (A/S/M/D/LIT) | {s.get('federation_probes_admitted')} |",
        f"| Intent-packet ingress | {s.get('intent_packet_ingress_n')}/{s['n']} |",
        f"| Hard gate | {'PASS' if s['hard_gate'] else 'FAIL'} |",
        "",
        "## Pass criteria",
        "",
    ]
    for k, v in pc.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.extend(
        [
            "",
            "## Enable / disable",
            "",
            "- Enable: `--enable-canary` (required; default OFF)",
            f"- Optional env: `{CANARY_ENV}=1` (still requires `--enable-canary`)",
            "- Disable / rollback: omit `--enable-canary` or run `--rollback-check`",
            "",
            "No default-path promotion. Soft-0.99 and tag-architecture remain blocked.",
            "",
        ]
    )
    return "\n".join(lines)


def _append_thesis(report: Mapping[str, Any], json_path: Path) -> str:
    text = THESIS.read_text(encoding="utf-8")
    s = report["summary"]
    body = (
        f"~~FIELD_SCOPED_BRIDGE_CANARY (one-notch bounded promotion)~~ → "
        f"**{report['verdict']}** — experiment `{EXPERIMENT_ID}`; "
        f"**CANARY_ONLY / NOT DEFAULT**; "
        f"registry sha `{report['registry']['sha256'][:16]}…`; "
        f"corpus n={report['corpus']['n_total']} "
        f"(valid={report['corpus']['n_valid_expected']}, "
        f"adv={report['corpus']['n_adversarial_expected']}); "
        f"contract {s['contract_pass']}/{s['n']} "
        f"hard_gate={'PASS' if s['hard_gate'] else 'FAIL'} "
        f"authority_leaks={s['authority_leaks']} "
        f"seal_fails={s['seal_fails_on_accepted']} "
        f"opaque_mutations={s['opaque_payload_mutations']} "
        f"false_accepts={s['false_accepts']} "
        f"rollback={'PASS' if report['rollback_check']['ok'] else 'FAIL'}; "
        f"intent_packet_ingress={s.get('intent_packet_ingress_n')}/{s['n']}; "
        f"federation_probes={s.get('federation_probes_admitted')}; "
        f"receipt `{str(json_path).replace(chr(92), '/')}`; "
        f"lib `foundation/lib/uml_field_scoped_bridge.py`; "
        f"script `foundation/scripts/run_field_scoped_bridge_canary_v1.py`; "
        f"path `build_intent_packet.uml_request→Security/gate→UML(decide_route)→attach_uml_resolved`; "
        f"**NO DEFAULT PROMOTION / NO TAG ARCHITECTURE / NO SOFT-0.99 / NO SCAN_SURFACE**. "
        f"Operator gate: `--enable-canary` (default OFF); disable by omitting flag or `--rollback-check`."
    )
    # Replace existing canary ladder item if present; else append next number.
    lines = text.splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if "FIELD_SCOPED_BRIDGE_CANARY" in line and re.match(r"^\d+\.\s", line):
            num = line.split(".", 1)[0]
            lines[i] = f"{num}. {body}"
            replaced = True
            item = lines[i]
            break
    if replaced:
        THESIS.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return item
    nums = [int(m) for m in re.findall(r"(?m)^(\d+)\.\s", text)]
    next_n = (max(nums) + 1) if nums else 79
    item = f"{next_n}. {body}"
    THESIS.write_text(text.rstrip() + "\n" + item + "\n", encoding="utf-8")
    return item


def selftest() -> int:
    registry = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    ch = "e" if "e" in registry.entries else registry.vocab[10]
    case = shadow._identity_shell(
        case_id="CANARY-SELFTEST-1",
        kind="valid_sealed_field",
        dialogue=f"Prefer efficient UML for '{ch}'.",
        identity_payload={"speaker": "viv_identity", "facts": ["x=1"]},
        uml_request={
            "request_kind": "sealed_destination",
            "target_char": ch,
            "target_value": int(registry.entries[ch]["token_id"]),
            "proposals": None,
            "prefer_policy": "cheapest_valid",
            "source": "cpu",
        },
        expect={"accept": True, "target_char": ch, "fail_closed": False},
    )
    disabled = invoke_case(
        case, registry, canary_enabled=False, s_n=0.95, prefer_intent_packet=True
    )
    assert disabled.status == "DISABLED", disabled.to_dict()
    assert not disabled.uml_invoked
    assert "uml_resolved" not in disabled.identity_out
    assert disabled.ingress_surface == "intent_packet"

    enabled = invoke_case(
        case, registry, canary_enabled=True, s_n=0.95, prefer_intent_packet=True
    )
    assert enabled.status == "PASS", enabled.to_dict()
    assert enabled.decoded_char == ch
    assert enabled.ingress_surface == "intent_packet"
    assert enabled.identity_out.get("uml_resolved", {}).get("canary_only") is True
    assert enabled.identity_out.get("uml_resolved", {}).get("default_path") is False
    assert "uml_request" in enabled.identity_out
    assert "tagged_packet" in enabled.identity_out

    adv = shadow._identity_shell(
        case_id="CANARY-SELFTEST-ADV",
        kind="adv_authority_blur",
        dialogue="gpu",
        identity_payload={"speaker": "gpu_mouth"},
        uml_request={
            "request_kind": "sealed_destination",
            "target_char": ch,
            "target_value": int(registry.entries[ch]["token_id"]),
            "source": "gpu_mouth",
        },
        expect={"accept": False, "fail_closed": True, "reason_class": "authority_violation"},
    )
    denied = invoke_case(
        adv, registry, canary_enabled=True, s_n=0.95, prefer_intent_packet=True
    )
    assert denied.status == "FAIL_CLOSED", denied.to_dict()
    assert denied.reason_class == "authority_violation"
    assert not denied.uml_invoked
    print("SELFTEST_OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"{EXPERIMENT_ID} (CANARY ONLY / NOT DEFAULT)"
    )
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument(
        "--enable-canary",
        action="store_true",
        help="Operator gate: required to run canary (default OFF)",
    )
    parser.add_argument(
        "--rollback-check",
        action="store_true",
        help="Verify disabled path has no UML side effects; exit 0 if clean",
    )
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--n-valid", type=int, default=40)
    parser.add_argument("--n-adversarial", type=int, default=24)
    parser.add_argument("--s-n", type=float, default=0.95)
    parser.add_argument("--append-thesis", action="store_true", default=True)
    parser.add_argument("--no-append-thesis", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if args.rollback_check:
        registry = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
        ch = "e" if "e" in registry.entries else registry.vocab[10]
        sample = shadow._identity_shell(
            case_id="ROLLBACK-CHECK",
            kind="valid_sealed_field",
            dialogue=f"UML for '{ch}'",
            identity_payload={"speaker": "viv_identity", "facts": ["rollback"]},
            uml_request={
                "request_kind": "sealed_destination",
                "target_char": ch,
                "target_value": int(registry.entries[ch]["token_id"]),
                "source": "cpu",
            },
            expect={"accept": True, "target_char": ch, "fail_closed": False},
        )
        rb = rollback_check(registry, sample)
        stamp = _utc()
        out_dir = REPORT_ROOT / f"rollback_{stamp}"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"rollback_check_{stamp}.json"
        path.write_text(json.dumps(rb, indent=2) + "\n", encoding="utf-8")
        _out(f"ROLLBACK {'PASS' if rb['ok'] else 'FAIL'}")
        _out(f"RECEIPT {str(path).replace(chr(92), '/')}")
        return 0 if rb["ok"] else 3

    if not args.enable_canary:
        _out("FIELD_SCOPED_BRIDGE_CANARY disabled (default OFF).")
        _out("Enable with --enable-canary (operator gate).")
        _out("Rollback check: --rollback-check")
        # Write a disabled receipt for auditability.
        stamp = _utc()
        out_dir = REPORT_ROOT / f"disabled_{stamp}"
        out_dir.mkdir(parents=True, exist_ok=True)
        disabled = {
            "experiment_id": EXPERIMENT_ID,
            "status": "DISABLED",
            "canary_only": True,
            "default_path": False,
            "uml_invoked": False,
            "reason": "missing --enable-canary",
            "stamp": stamp,
        }
        path = out_dir / f"disabled_{stamp}.json"
        path.write_text(json.dumps(disabled, indent=2) + "\n", encoding="utf-8")
        _out(f"RECEIPT {str(path).replace(chr(92), '/')}")
        return 0

    try:
        report = run_canary(
            census_path=args.census,
            n_valid=args.n_valid,
            n_adversarial=args.n_adversarial,
            append_thesis=bool(args.append_thesis and not args.no_append_thesis),
            s_n=float(args.s_n),
        )
    except Exception:
        traceback.print_exc()
        return 1

    s = report["summary"]
    _out(f"VERDICT {report['verdict']}")
    _out("CANARY_ONLY / NOT DEFAULT")
    _out(
        f"contract={s['contract_pass']}/{s['n']} "
        f"hard_gate={'PASS' if s['hard_gate'] else 'FAIL'} "
        f"authority_leaks={s['authority_leaks']} "
        f"seal_fails={s['seal_fails_on_accepted']} "
        f"opaque_mutations={s['opaque_payload_mutations']} "
        f"false_accepts={s['false_accepts']} "
        f"rollback={'PASS' if report['rollback_check']['ok'] else 'FAIL'} "
        f"p50_ms={s['latency_p50_ms']:.3f}"
    )
    arts = report.get("artifacts") or {}
    _out(f"RECEIPT {arts.get('json')}")
    _out(f"MD {arts.get('markdown')}")
    _out(f"INVOCATIONS {arts.get('invocations_dir')}")
    if arts.get("thesis_item"):
        _out(f"THESIS {arts['thesis_item'][:220]}...")
    return 0 if report["verdict"] == "CANARY_PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
