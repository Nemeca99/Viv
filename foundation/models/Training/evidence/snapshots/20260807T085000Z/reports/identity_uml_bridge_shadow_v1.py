#!/usr/bin/env python3
"""Read-only identity→UML bridge shadow pilot.

Experiment: IDENTITY_UML_BRIDGE_SHADOW_V1

Thesis gap: identity-parent MoE/dialogue surface and UML A/S/M/D lattice are
separate until an explicit bridge is designed and gated. This pilot is that
shadow boundary observation — zero mutation, zero promotion.

Path under test:
  identity/intent surface
    → bridge candidate
    → sealed UML structure/binding
    → A/S/M/D route
    → decoded result
    → identity surface

Correctness outranks adapter cost/latency.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.uml_equation_registry import (  # noqa: E402
    SANDBOX96_ARTIFACT,
    UMLEquationRegistry,
    _domains_in_expr,
)
from lib.uml_route_governor import decide_route, route_efficiency_error  # noqa: E402


EXPERIMENT_ID = "IDENTITY_UML_BRIDGE_SHADOW_V1"
SCHEMA_VERSION = "identity_uml_bridge_shadow_v1"
ARM_FIELD = "FIELD_SCOPED"
ARM_SCAN = "SCAN_SURFACE"

DEFAULT_CENSUS = (
    FOUNDATION
    / "models"
    / "Training"
    / "current"
    / "viv_slm"
    / "model"
    / "test_training"
    / "runs"
    / "uml_speak_cheap_census"
    / "census_20260807T082414Z"
    / "census.json"
)
REPORT_ROOT = FOUNDATION / "artifacts" / "auto" / "identity_uml_bridge_shadow_v1"
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

UML_FOR_RE = re.compile(
    r"""(?:UML|uml)\s+(?:for|equation\s+for)\s+['\"](.)['\"]""",
)
BARE_EQ_RE = re.compile(r"^\s*[0-9+\-*/().\s]+\s*$")


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


def _federation(expr: str) -> str:
    domains = sorted(_domains_in_expr(expr))
    return "".join(domains) if domains else "LIT"


def load_registry(path: Path | None = None) -> UMLEquationRegistry:
    return UMLEquationRegistry.load(path or SANDBOX96_ARTIFACT)


# ---------------------------------------------------------------------------
# Corpus: identity receipts with UML-resolvable content + adversarial cases
# ---------------------------------------------------------------------------


def _identity_shell(
    *,
    case_id: str,
    kind: str,
    dialogue: str,
    identity_payload: Mapping[str, Any],
    uml_request: Mapping[str, Any] | None,
    expect: Mapping[str, Any],
) -> dict[str, Any]:
    opaque = {
        "case_id": case_id,
        "kind": kind,
        "dialogue": dialogue,
        "identity_payload": copy.deepcopy(dict(identity_payload)),
        "uml_request": None if uml_request is None else copy.deepcopy(dict(uml_request)),
        "expect": dict(expect),
    }
    opaque["identity_payload_sha256"] = _sha(opaque["identity_payload"])
    opaque["receipt_sha256"] = _sha(
        {k: v for k, v in opaque.items() if k != "receipt_sha256"}
    )
    return opaque


def build_corpus(
    registry: UMLEquationRegistry,
    *,
    census_path: Path | None,
    n_valid: int = 48,
    n_adversarial: int = 24,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    chars = [ch for ch in registry.vocab if ch.isprintable() and ch not in "\n\r\t"]
    # Deterministic sealed identity→UML round-trips.
    for i, ch in enumerate(chars[: max(16, n_valid // 2)]):
        value = int(registry.entries[ch]["token_id"])
        cases.append(
            _identity_shell(
                case_id=f"IDUML-SEAL-{i:03d}",
                kind="valid_sealed_field",
                dialogue=(
                    f"Operator: Prefer efficient UML for '{ch}'. "
                    f"Identity facts stay outside the codec."
                ),
                identity_payload={
                    "speaker": "viv_identity",
                    "mode": "dialogue",
                    "facts": [
                        "source=cpu_identity",
                        "authority=cpu",
                        f"surface_char={ch}",
                    ],
                    "memory_note": "opaque-to-uml",
                    "codex_hold_ref": 0.9702,
                },
                uml_request={
                    "request_kind": "sealed_destination",
                    "target_char": ch,
                    "target_value": value,
                    "proposals": None,
                    "prefer_policy": "cheapest_valid",
                },
                expect={
                    "accept": True,
                    "target_char": ch,
                    "fail_closed": False,
                },
            )
        )

    # Live dialogue-shaped surfaces from item-77 sealed snap rows.
    if census_path and census_path.is_file():
        census = json.loads(census_path.read_text(encoding="utf-8"))
        rows = list((census.get("modes") or {}).get("prefer_efficient_snap", {}).get("rows") or [])
        for row in rows[: max(8, n_valid // 3)]:
            ch = str(row.get("target_char") or "")
            if not ch or ch not in registry.entries:
                continue
            cases.append(
                _identity_shell(
                    case_id=f"IDUML-C77-{row.get('example_id', 'row')}",
                    kind="valid_census_dialogue",
                    dialogue=(
                        f"User: What is the UML for '{ch}'?\n"
                        f"Identity: keep packet facts unchanged outside UML field."
                    ),
                    identity_payload={
                        "speaker": "viv_identity",
                        "census_example_id": row.get("example_id"),
                        "survivor_hash": (census.get("checkpoint_identity") or {}).get(
                            "sha256"
                        ),
                        "policy_mode_ref": "prefer_efficient_snap",
                        "facts": [
                            f"target_char={ch}",
                            f"census_equation={row.get('equation')}",
                        ],
                        "opaque_blob": {"k": "v", "n": 7},
                    },
                    uml_request={
                        "request_kind": "sealed_destination",
                        "target_char": ch,
                        "target_value": int(row.get("target_token_id"))
                        if row.get("target_token_id") is not None
                        else None,
                        "proposals": [str(row.get("equation"))]
                        if row.get("equation")
                        else None,
                        "prefer_policy": "cheapest_valid",
                    },
                    expect={
                        "accept": True,
                        "target_char": ch,
                        "fail_closed": False,
                    },
                )
            )

    # Proposal-bearing valid routes (still sealed destination).
    for i, ch in enumerate(chars[16:24]):
        value = int(registry.entries[ch]["token_id"])
        lit = str(value)
        cases.append(
            _identity_shell(
                case_id=f"IDUML-PROP-{i:03d}",
                kind="valid_proposal_field",
                dialogue=f"Bridge this sealed destination '{ch}' via UML route pool.",
                identity_payload={
                    "speaker": "viv_identity",
                    "facts": [f"sealed={ch}"],
                    "session": {"turn": i, "channel": "cpu"},
                },
                uml_request={
                    "request_kind": "sealed_destination",
                    "target_char": ch,
                    "target_value": value,
                    "proposals": [lit, registry.encode_char(ch)],
                    "prefer_policy": "cheapest_valid",
                },
                expect={"accept": True, "target_char": ch, "fail_closed": False},
            )
        )

    # Truncate/pad valid to requested size while keeping adversarials separate.
    valid = [c for c in cases if c["expect"].get("accept")]
    valid = valid[:n_valid]

    adversarial: list[dict[str, Any]] = []
    # Missing uml_request.
    adversarial.append(
        _identity_shell(
            case_id="IDUML-ADV-missing-request",
            kind="adv_missing_uml_request",
            dialogue="User: tell me something smart about math.",
            identity_payload={"speaker": "viv_identity", "facts": ["no_uml_field"]},
            uml_request=None,
            expect={"accept": False, "fail_closed": True, "reason_class": "missing_uml_request"},
        )
    )
    # Invented binding: free variable claimed numeric without seal.
    adversarial.append(
        _identity_shell(
            case_id="IDUML-ADV-invented-binding",
            kind="adv_invented_binding",
            dialogue="User: Let A=1 and then A+A should be 2.",
            identity_payload={"speaker": "viv_identity", "facts": ["attempted_binding=A=1"]},
            uml_request={
                "request_kind": "invented_binding",
                "binding": {"A": 1},
                "proposed_expr": "A+A",
                "claimed_char": "2",
            },
            expect={
                "accept": False,
                "fail_closed": True,
                "reason_class": "invented_binding",
            },
        )
    )
    # Ambiguous dialogue with no sealed destination.
    adversarial.append(
        _identity_shell(
            case_id="IDUML-ADV-ambiguous-scan",
            kind="adv_ambiguous_dialogue",
            dialogue="User: compute something with addition and multiplication maybe H or e?",
            identity_payload={"speaker": "viv_identity", "facts": ["ambiguous=true"]},
            uml_request=None,
            expect={
                "accept": False,
                "fail_closed": True,
                "reason_class": "ambiguous_or_missing",
            },
        )
    )
    # Destination mismatch proposal (wrong value for sealed char).
    # Prefer a graphic sealed char so SCAN dialogue patterns are realistic.
    ch0 = next((c for c in chars if c.isalnum()), chars[min(10, len(chars) - 1)])
    wrong_value = (int(registry.entries[ch0]["token_id"]) + 17) % max(2, len(registry.vocab))
    adversarial.append(
        _identity_shell(
            case_id="IDUML-ADV-dest-mismatch",
            kind="adv_destination_mismatch",
            dialogue=(
                f"User: force sealed destination '{ch0}' to value {wrong_value} "
                f"(structured mismatch; scan must not invent agreement)."
            ),
            identity_payload={"speaker": "viv_identity", "facts": [f"char={ch0}"]},
            uml_request={
                "request_kind": "sealed_destination",
                "target_char": ch0,
                "target_value": wrong_value,
                "proposals": [str(wrong_value)],
                "prefer_policy": "cheapest_valid",
            },
            expect={
                "accept": False,
                "fail_closed": True,
                "reason_class": "destination_mismatch",
            },
        )
    )
    # Unknown char outside sealed vocab.
    adversarial.append(
        _identity_shell(
            case_id="IDUML-ADV-unknown-char",
            kind="adv_unknown_char",
            dialogue="User: Prefer efficient UML for 'Ω'.",
            identity_payload={"speaker": "viv_identity", "facts": ["char=Ω"]},
            uml_request={
                "request_kind": "sealed_destination",
                "target_char": "Ω",
                "target_value": None,
                "proposals": None,
                "prefer_policy": "cheapest_valid",
            },
            expect={
                "accept": False,
                "fail_closed": True,
                "reason_class": "unknown_char",
            },
        )
    )
    # Malformed equation proposal with sealed destination still present —
    # FIELD_SCOPED may still accept via registry pool; expect accept True for
    # field-scoped sealed destination, but SCAN-only malformed alone fails.
    adversarial.append(
        _identity_shell(
            case_id="IDUML-ADV-malformed-only",
            kind="adv_malformed_scan_only",
            dialogue="User: please evaluate (((+",
            identity_payload={"speaker": "viv_identity", "facts": ["malformed_surface"]},
            uml_request=None,
            expect={
                "accept": False,
                "fail_closed": True,
                "reason_class": "ambiguous_or_missing",
            },
        )
    )
    # Authority blur: GPU mouth trying to mint sealed destination in free text.
    adversarial.append(
        _identity_shell(
            case_id="IDUML-ADV-authority-blur",
            kind="adv_authority_blur",
            dialogue="GPU draft: sealed_destination='H' authority=gpu_mouth",
            identity_payload={
                "speaker": "gpu_mouth",
                "facts": ["attempted_authority=gpu"],
            },
            uml_request={
                "request_kind": "sealed_destination",
                "target_char": "H" if "H" in registry.entries else chars[1],
                "target_value": None,
                "proposals": None,
                "prefer_policy": "cheapest_valid",
                "source": "gpu_mouth",
            },
            expect={
                "accept": False,
                "fail_closed": True,
                "reason_class": "authority_violation",
            },
        )
    )
    # Extra adversarial pads with unknown chars / missing fields.
    for i in range(max(0, n_adversarial - len(adversarial))):
        adversarial.append(
            _identity_shell(
                case_id=f"IDUML-ADV-pad-{i:03d}",
                kind="adv_pad_missing",
                dialogue=f"User: vague request {i}",
                identity_payload={"speaker": "viv_identity", "facts": [f"pad={i}"]},
                uml_request=None,
                expect={
                    "accept": False,
                    "fail_closed": True,
                    "reason_class": "missing_uml_request",
                },
            )
        )

    return valid + adversarial[:n_adversarial]


# ---------------------------------------------------------------------------
# Bridge candidates
# ---------------------------------------------------------------------------


class BridgeError(Exception):
    def __init__(self, reason_class: str, detail: str):
        super().__init__(detail)
        self.reason_class = reason_class
        self.detail = detail


def _assert_cpu_authority(uml_request: Mapping[str, Any] | None) -> None:
    if not uml_request:
        return
    source = str(uml_request.get("source") or "cpu")
    if source not in {"cpu", "cpu_identity", "cpu_authority", "operator"}:
        raise BridgeError("authority_violation", f"uml_request_source={source}")


def _resolve_sealed(
    registry: UMLEquationRegistry, uml_request: Mapping[str, Any]
) -> tuple[str, int]:
    kind = str(uml_request.get("request_kind") or "")
    if kind == "invented_binding":
        raise BridgeError("invented_binding", "structure_without_sealed_binding")
    if kind != "sealed_destination":
        raise BridgeError("unsupported_request_kind", kind or "missing")

    ch = uml_request.get("target_char")
    val = uml_request.get("target_value")
    if ch is not None:
        ch = str(ch)
        if ch not in registry.entries:
            raise BridgeError("unknown_char", repr(ch))
        sealed_val = int(registry.entries[ch]["token_id"])
        if val is not None and int(val) != sealed_val:
            raise BridgeError(
                "destination_mismatch",
                f"char={ch!r} sealed={sealed_val} claimed={val}",
            )
        return ch, sealed_val
    if val is not None:
        sealed_val = int(val)
        if sealed_val not in registry.value_to_char:
            raise BridgeError("unknown_value", str(sealed_val))
        return str(registry.value_to_char[sealed_val]), sealed_val
    raise BridgeError("missing_destination", "no target_char/target_value")


def bridge_field_scoped(
    receipt: Mapping[str, Any],
    registry: UMLEquationRegistry,
) -> dict[str, Any]:
    """Only explicit uml_request may cross; identity payload is opaque."""
    t0 = time.perf_counter()
    identity_before = copy.deepcopy(receipt["identity_payload"])
    identity_sha_before = _sha(identity_before)
    uml_request = receipt.get("uml_request")
    try:
        if not uml_request:
            raise BridgeError("missing_uml_request", "uml_request required")
        _assert_cpu_authority(uml_request)
        target_char, target_value = _resolve_sealed(registry, uml_request)
        proposals = uml_request.get("proposals")
        decision = decide_route(
            registry,
            target_char=target_char,
            target_value=target_value,
            proposals=list(proposals) if proposals else None,
            include_registry_pool=True,
            policy=str(uml_request.get("prefer_policy") or "cheapest_valid"),
        )
        selected = str(decision.selected)
        decoded = registry.decode_eq(selected)
        if decoded != target_char:
            raise BridgeError(
                "seal_break",
                f"decoded={decoded!r} sealed={target_char!r}",
            )
        eff = route_efficiency_error(
            registry, proposed=selected, target_char=target_char
        )
        domains = sorted(_domains_in_expr(selected))
        federation = _federation(selected)
        identity_after = copy.deepcopy(identity_before)
        # Only the UML-resolved field may change on the identity surface.
        identity_after["uml_resolved"] = {
            "target_char": target_char,
            "target_value": target_value,
            "selected_route": selected,
            "domains": domains,
            "federation": federation,
            "selected_cost": int(decision.selected_cost),
            "route_kind": eff.get("kind"),
        }
        # Provenance stamp (bridge metadata, not payload mutation of facts).
        opaque_after = {
            k: v for k, v in identity_after.items() if k != "uml_resolved"
        }
        opaque_sha = _sha(opaque_after)
        if opaque_sha != identity_sha_before:
            raise BridgeError("identity_payload_mutated", "opaque fields changed")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "arm": ARM_FIELD,
            "status": "PASS",
            "fail_closed": False,
            "reason_class": None,
            "target_char": target_char,
            "target_value": target_value,
            "selected_route": selected,
            "decoded_char": decoded,
            "domains": domains,
            "federation": federation,
            "selected_cost": int(decision.selected_cost),
            "route_kind": eff.get("kind"),
            "destination_match": True,
            "identity_payload_sha_before": identity_sha_before,
            "identity_opaque_sha_after": opaque_sha,
            "identity_out": identity_after,
            "elapsed_ms": elapsed_ms,
        }
    except BridgeError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "arm": ARM_FIELD,
            "status": "FAIL_CLOSED",
            "fail_closed": True,
            "reason_class": exc.reason_class,
            "detail": exc.detail,
            "destination_match": False,
            "identity_payload_sha_before": identity_sha_before,
            "identity_opaque_sha_after": identity_sha_before,
            "identity_out": identity_before,
            "elapsed_ms": elapsed_ms,
        }


def _scan_dialogue_for_uml(
    dialogue: str, registry: UMLEquationRegistry
) -> dict[str, Any]:
    """Best-effort free-text scan — fail-closed on ambiguity."""
    matches = UML_FOR_RE.findall(dialogue or "")
    if len(matches) == 1:
        ch = matches[0]
        if ch not in registry.entries:
            raise BridgeError("unknown_char", repr(ch))
        return {
            "request_kind": "sealed_destination",
            "target_char": ch,
            "target_value": int(registry.entries[ch]["token_id"]),
            "proposals": None,
            "prefer_policy": "cheapest_valid",
            "source": "cpu",
            "scanned_from": "uml_for_pattern",
        }
    if len(matches) > 1:
        raise BridgeError("ambiguous_or_missing", f"multiple_uml_for={matches}")
    # Bare equation alone is not a sealed destination binding.
    if BARE_EQ_RE.match((dialogue or "").strip()):
        raise BridgeError("invented_binding", "bare_equation_without_sealed_destination")
    # Invented binding language.
    if re.search(r"\bLet\s+[A-Za-z]\s*=", dialogue or ""):
        raise BridgeError("invented_binding", "free_variable_binding_in_dialogue")
    raise BridgeError("ambiguous_or_missing", "no_sealed_uml_request_in_dialogue")


def bridge_scan_surface(
    receipt: Mapping[str, Any],
    registry: UMLEquationRegistry,
) -> dict[str, Any]:
    """Scan dialogue surface; ignore structured uml_request (stress test)."""
    t0 = time.perf_counter()
    identity_before = copy.deepcopy(receipt["identity_payload"])
    identity_sha_before = _sha(identity_before)
    try:
        # Authority blur: if structured request claims non-cpu source, reject
        # even before scan — boundary must not accept GPU-minted seals.
        req = receipt.get("uml_request") or {}
        if req:
            _assert_cpu_authority(req)
        scanned = _scan_dialogue_for_uml(str(receipt.get("dialogue") or ""), registry)
        # Reuse field-scoped executor on scanned request.
        tmp = dict(receipt)
        tmp["uml_request"] = scanned
        out = bridge_field_scoped(tmp, registry)
        out["arm"] = ARM_SCAN
        out["scan"] = scanned
        out["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        return out
    except BridgeError as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "arm": ARM_SCAN,
            "status": "FAIL_CLOSED",
            "fail_closed": True,
            "reason_class": exc.reason_class,
            "detail": exc.detail,
            "destination_match": False,
            "identity_payload_sha_before": identity_sha_before,
            "identity_opaque_sha_after": identity_sha_before,
            "identity_out": identity_before,
            "elapsed_ms": elapsed_ms,
        }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


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
    reason_ok = True
    if expect.get("reason_class") and not want_accept:
        # Allow missing_uml_request to satisfy ambiguous_or_missing expectations
        # for scan arm, and vice versa for field arm.
        got_reason = str(result.get("reason_class") or "")
        want_reason = str(expect.get("reason_class") or "")
        aliases = {
            "ambiguous_or_missing": {
                "ambiguous_or_missing",
                "missing_uml_request",
            },
            "missing_uml_request": {
                "missing_uml_request",
                "ambiguous_or_missing",
            },
        }
        reason_ok = got_reason == want_reason or got_reason in aliases.get(
            want_reason, set()
        )

    contract_pass = (
        (got_accept == want_accept)
        and fail_closed_ok
        and seal_ok
        and provenance_ok
        and reason_ok
    )
    return {
        "contract_pass": contract_pass,
        "want_accept": want_accept,
        "got_accept": got_accept,
        "fail_closed_ok": fail_closed_ok,
        "seal_ok": seal_ok,
        "provenance_ok": provenance_ok,
        "reason_ok": reason_ok,
        "invented_binding": result.get("reason_class") == "invented_binding",
        "elapsed_ms": float(result.get("elapsed_ms") or 0.0),
        "federation": result.get("federation"),
        "domains": result.get("domains"),
        "selected_route": result.get("selected_route"),
        "reason_class": result.get("reason_class"),
    }


def summarize(arm: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    passes = sum(1 for r in rows if r["score"]["contract_pass"])
    valid_rows = [r for r in rows if r["case"]["expect"].get("accept")]
    adv_rows = [r for r in rows if not r["case"]["expect"].get("accept")]
    valid_pass = sum(1 for r in valid_rows if r["score"]["contract_pass"])
    adv_pass = sum(1 for r in adv_rows if r["score"]["contract_pass"])
    seal_fails = sum(1 for r in valid_rows if not r["score"]["seal_ok"])
    prov_fails = sum(1 for r in rows if not r["score"]["provenance_ok"])
    false_accepts = sum(
        1
        for r in adv_rows
        if r["result"].get("status") == "PASS"
    )
    lat = sorted(float(r["score"]["elapsed_ms"]) for r in rows) or [0.0]
    p50 = lat[len(lat) // 2]
    federations: dict[str, int] = {}
    for r in rows:
        if r["result"].get("status") == "PASS":
            fed = str(r["result"].get("federation") or "LIT")
            federations[fed] = federations.get(fed, 0) + 1
    return {
        "arm": arm,
        "n": n,
        "contract_pass": passes,
        "contract_pass_rate": passes / n if n else 0.0,
        "valid_n": len(valid_rows),
        "valid_pass": valid_pass,
        "valid_pass_rate": valid_pass / len(valid_rows) if valid_rows else 0.0,
        "adversarial_n": len(adv_rows),
        "adversarial_pass": adv_pass,
        "adversarial_pass_rate": adv_pass / len(adv_rows) if adv_rows else 0.0,
        "seal_fails_on_valid": seal_fails,
        "provenance_fails": prov_fails,
        "false_accepts": false_accepts,
        "latency_p50_ms": p50,
        "federation_histogram": federations,
        "hard_gate": (
            seal_fails == 0
            and prov_fails == 0
            and false_accepts == 0
            and adv_pass == len(adv_rows)
            and valid_pass == len(valid_rows)
        ),
    }


def classify(summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    field = summaries[ARM_FIELD]
    scan = summaries[ARM_SCAN]
    # Hard gates: no seal break, no provenance break, no adversarial false accept.
    if not field["hard_gate"] and not scan["hard_gate"]:
        verdict = "BRIDGE_FAIL"
        note = "Both candidates failed hard gates."
    elif field["hard_gate"] and not scan["hard_gate"]:
        verdict = "FIELD_SCOPED_WINS"
        note = (
            "Field-scoped bridge preserves seal/provenance/fail-closed; "
            "scan-surface does not clear hard gates."
        )
    elif scan["hard_gate"] and not field["hard_gate"]:
        verdict = "SCAN_SURFACE_WINS"
        note = "Scan-surface cleared hard gates while field-scoped did not."
    elif field["hard_gate"] and scan["hard_gate"]:
        # Prefer field-scoped if both pass: lower ambiguity surface.
        if field["valid_pass_rate"] >= scan["valid_pass_rate"]:
            verdict = "FIELD_SCOPED_WINS"
            note = (
                "Both hard-gate PASS; field-scoped preferred as lower-ambiguity "
                "boundary (explicit uml_request only)."
            )
        else:
            verdict = "SCAN_SURFACE_WINS"
            note = "Both hard-gate PASS; scan-surface higher valid pass rate."
    else:
        verdict = "INCONCLUSIVE"
        note = "Mixed outcomes."
    return {
        "verdict": verdict,
        "note": note,
        "promotion": False,
        "mutation": False,
    }


# ---------------------------------------------------------------------------
# Optional tag-architecture secondary observation (no promotion)
# ---------------------------------------------------------------------------


def tag_secondary_observation(bridge_receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Best-effort: pass one bridge receipt through both tag arms if importable."""
    try:
        scripts = FOUNDATION / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import tag_architecture_ab_v1 as ab  # type: ignore
    except Exception as exc:
        return {"status": "UNSUPPORTED", "error": repr(exc)}

    # Minimal logical records from bridge result.
    records = [
        {
            "plane": "provenance",
            "name": "survivor_or_bridge",
            "value": {
                "experiment": EXPERIMENT_ID,
                "arm": bridge_receipt.get("arm"),
                "target_char": bridge_receipt.get("target_char"),
                "selected_route": bridge_receipt.get("selected_route"),
                "federation": bridge_receipt.get("federation"),
                "destination_match": bridge_receipt.get("destination_match"),
            },
            "source": "bridge_shadow",
            "authority": "cpu",
        },
        {
            "plane": "uml_route",
            "name": "federation",
            "value": bridge_receipt.get("federation"),
            "source": "uml_registry",
            "authority": "cpu",
        },
    ]
    out: dict[str, Any] = {"status": "PASS", "arms": {}}
    for arm_name, build in (
        (ab.ARM_A, getattr(ab, "build_layered", None) or getattr(ab, "layered_bridge", None)),
        (ab.ARM_B, getattr(ab, "build_typed", None) or getattr(ab, "typed_registry", None)),
    ):
        # Keep observation soft — harness APIs vary; do not fail the pilot.
        try:
            if build is None:
                # Fall back to encapsulate helpers if present.
                if hasattr(ab, "adapt_records"):
                    payload = ab.adapt_records(arm_name, records)
                else:
                    out["arms"][arm_name] = {"status": "UNSUPPORTED"}
                    continue
            else:
                payload = build(records)
            raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            out["arms"][arm_name] = {
                "status": "OBSERVED",
                "serialized_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        except Exception as exc:
            out["arms"][arm_name] = {"status": "ERROR", "error": repr(exc)}
    return out


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run_pilot(
    *,
    census_path: Path,
    n_valid: int,
    n_adversarial: int,
    append_thesis: bool,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    registry_path = Path(SANDBOX96_ARTIFACT)
    registry = load_registry(registry_path)
    registry_sha = registry.registry_sha256()
    census_sha = _file_sha(census_path) if census_path.is_file() else None

    corpus = build_corpus(
        registry,
        census_path=census_path if census_path.is_file() else None,
        n_valid=n_valid,
        n_adversarial=n_adversarial,
    )
    arms = {
        ARM_FIELD: bridge_field_scoped,
        ARM_SCAN: bridge_scan_surface,
    }
    detailed: dict[str, list[dict[str, Any]]] = {ARM_FIELD: [], ARM_SCAN: []}
    for case in corpus:
        for arm, fn in arms.items():
            result = fn(case, registry)
            score = score_case(case, result)
            detailed[arm].append(
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
                    "result": {
                        k: v
                        for k, v in result.items()
                        if k != "identity_out"
                    },
                    "identity_out_uml_resolved": (result.get("identity_out") or {}).get(
                        "uml_resolved"
                    ),
                    "score": score,
                }
            )

    summaries = {arm: summarize(arm, rows) for arm, rows in detailed.items()}
    decision = classify(summaries)

    # Secondary tag observation on one PASS field-scoped receipt.
    tag_obs: dict[str, Any] = {"status": "SKIPPED"}
    for row in detailed[ARM_FIELD]:
        if row["result"].get("status") == "PASS":
            tag_obs = tag_secondary_observation(row["result"])
            tag_obs["case_id"] = row["case_id"]
            break

    finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stamp = _utc()
    out_dir = REPORT_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "started_at": started,
        "finished_at": finished,
        "measurement_only": True,
        "mutation": False,
        "promotion": False,
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
            "byte/seal identity survives round trip",
            "no invented bindings",
            "correct domain/federation selected",
            "provenance survives both directions",
            "identity payload unchanged outside uml_resolved",
            "fail-closed on malformed/ambiguous/authority cases",
            "adapter latency recorded but never outranks correctness",
        ],
        "summaries": summaries,
        "decision": decision,
        "tag_architecture_secondary": tag_obs,
        "rows": detailed,
    }
    report["receipt_sha256"] = _sha(
        {k: v for k, v in report.items() if k != "receipt_sha256"}
    )

    json_path = out_dir / f"identity_uml_bridge_shadow_v1_{stamp}.json"
    md_path = out_dir / f"identity_uml_bridge_shadow_v1_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    thesis_note = None
    if append_thesis and THESIS.is_file():
        thesis_note = _append_thesis(report, json_path)

    report["artifacts"] = {
        "json": str(json_path).replace("\\", "/"),
        "markdown": str(md_path).replace("\\", "/"),
        "thesis_appended": bool(thesis_note),
        "thesis_item": thesis_note,
    }
    # Rewrite JSON with artifact paths.
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def _render_md(report: Mapping[str, Any]) -> str:
    d = report["decision"]
    lines = [
        f"# {EXPERIMENT_ID}",
        "",
        f"**Verdict:** `{d['verdict']}`",
        "",
        d["note"],
        "",
        f"- Promotion: `{d['promotion']}`",
        f"- Mutation: `{d['mutation']}`",
        f"- Registry sha: `{report['registry']['sha256'][:16]}…`",
        f"- Corpus: n={report['corpus']['n_total']} "
        f"(valid={report['corpus']['n_valid_expected']}, "
        f"adv={report['corpus']['n_adversarial_expected']})",
        "",
        "## Summaries",
        "",
        "| Arm | Contract pass | Valid | Adversarial | Seal fails | False accepts | p50 ms | Hard gate |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for arm in (ARM_FIELD, ARM_SCAN):
        s = report["summaries"][arm]
        lines.append(
            f"| {arm} | {s['contract_pass']}/{s['n']} ({s['contract_pass_rate']:.3f}) | "
            f"{s['valid_pass']}/{s['valid_n']} | {s['adversarial_pass']}/{s['adversarial_n']} | "
            f"{s['seal_fails_on_valid']} | {s['false_accepts']} | {s['latency_p50_ms']:.3f} | "
            f"{'PASS' if s['hard_gate'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Boundary contract",
            "",
        ]
    )
    for item in report["boundary_contract"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            f"Tag-architecture secondary: `{report.get('tag_architecture_secondary', {}).get('status')}`",
            "",
            "No promotion. No mutation. Defer scaffold-dependence / soft-0.99 until bridge is clean.",
            "",
        ]
    )
    return "\n".join(lines)


def _append_thesis(report: Mapping[str, Any], json_path: Path) -> str:
    text = THESIS.read_text(encoding="utf-8")
    # Next ladder item number.
    nums = [int(m) for m in re.findall(r"(?m)^(\d+)\.\s", text)]
    next_n = (max(nums) + 1) if nums else 78
    d = report["decision"]
    sf = report["summaries"][ARM_FIELD]
    ss = report["summaries"][ARM_SCAN]
    item = (
        f"{next_n}. ~~Read-only identity→UML bridge shadow pilot~~ → "
        f"**{d['verdict']}** — experiment `{EXPERIMENT_ID}`; "
        f"registry sha `{report['registry']['sha256'][:16]}…`; "
        f"corpus n={report['corpus']['n_total']} "
        f"(valid={report['corpus']['n_valid_expected']}, "
        f"adv={report['corpus']['n_adversarial_expected']}); "
        f"**{ARM_FIELD}** contract {sf['contract_pass']}/{sf['n']} "
        f"hard_gate={'PASS' if sf['hard_gate'] else 'FAIL'} "
        f"false_accepts={sf['false_accepts']} seal_fails={sf['seal_fails_on_valid']}; "
        f"**{ARM_SCAN}** contract {ss['contract_pass']}/{ss['n']} "
        f"hard_gate={'PASS' if ss['hard_gate'] else 'FAIL'} "
        f"false_accepts={ss['false_accepts']} seal_fails={ss['seal_fails_on_valid']}; "
        f"receipt `{str(json_path).replace(chr(92), '/')}`; "
        f"**NO MUTATION / NO PROMOTION**. "
        f"{d['note']} "
        f"Tag-architecture secondary remains deferred (`TIE_WITH_CONSTRAINTS`); "
        f"scaffold-dependence / soft-0.99 stays blocked until a bridge clears seal-first gates."
    )
    if f"{next_n}." in text.splitlines()[-5:]:
        return item
    # Append under Evidence ladder if present, else end of file.
    if "Evidence ladder" in text or re.search(r"(?m)^\d+\.\s", text):
        THESIS.write_text(text.rstrip() + "\n" + item + "\n", encoding="utf-8")
    else:
        THESIS.write_text(text.rstrip() + "\n\n" + item + "\n", encoding="utf-8")
    return item


def selftest() -> int:
    registry = load_registry()
    ch = "e" if "e" in registry.entries else registry.vocab[10]
    case = _identity_shell(
        case_id="SELFTEST-1",
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
    out = bridge_field_scoped(case, registry)
    assert out["status"] == "PASS", out
    assert out["decoded_char"] == ch, out
    adv = _identity_shell(
        case_id="SELFTEST-ADV",
        kind="adv_invented_binding",
        dialogue="Let A=1",
        identity_payload={"speaker": "viv_identity"},
        uml_request={
            "request_kind": "invented_binding",
            "binding": {"A": 1},
            "proposed_expr": "A+A",
        },
        expect={"accept": False, "fail_closed": True, "reason_class": "invented_binding"},
    )
    out2 = bridge_field_scoped(adv, registry)
    assert out2["status"] == "FAIL_CLOSED", out2
    assert out2["reason_class"] == "invented_binding", out2
    print("SELFTEST_OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=EXPERIMENT_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--n-valid", type=int, default=48)
    parser.add_argument("--n-adversarial", type=int, default=24)
    parser.add_argument("--append-thesis", action="store_true", default=True)
    parser.add_argument("--no-append-thesis", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.run:
        parser.print_help()
        return 2
    try:
        report = run_pilot(
            census_path=args.census,
            n_valid=args.n_valid,
            n_adversarial=args.n_adversarial,
            append_thesis=bool(args.append_thesis and not args.no_append_thesis),
        )
    except Exception:
        traceback.print_exc()
        return 1
    d = report["decision"]

    def _out(msg: str) -> None:
        text = str(msg).replace("\u2192", "->")
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", "backslashreplace").decode("ascii"))

    _out(f"VERDICT {d['verdict']}")
    _out(d["note"])
    for arm, s in report["summaries"].items():
        _out(
            f"{arm}: contract={s['contract_pass']}/{s['n']} "
            f"hard_gate={'PASS' if s['hard_gate'] else 'FAIL'} "
            f"false_accepts={s['false_accepts']} "
            f"seal_fails={s['seal_fails_on_valid']} "
            f"p50_ms={s['latency_p50_ms']:.3f}"
        )
    arts = report.get("artifacts") or {}
    _out(f"JSON {arts.get('json')}")
    _out(f"MD {arts.get('markdown')}")
    if arts.get("thesis_item"):
        _out(f"THESIS {arts['thesis_item'][:180]}...")
    return 0 if d["verdict"] != "BRIDGE_FAIL" else 3


if __name__ == "__main__":
    raise SystemExit(main())
