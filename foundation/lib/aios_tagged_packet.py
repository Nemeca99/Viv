"""Schema-locked CPU authority packet for the Viv GPU mouth.

The CPU owns facts, authority, provenance, and verification. The GPU receives
an escaped rendering of this packet and returns prose only. User text is kept
in a data-only block and can never create an authoritative tag.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import html
import json
import re
import secrets
from typing import Any, Iterable, Mapping
import uuid


SCHEMA_VERSION = "aios_tagged_packet_v1"
ALLOWED_TAGS = (
    "identity",
    "knowledge",
    "telemetry",
    "user_request",
    "allowed_actions",
    "unknowns",
    "rendering_rules",
)
REQUIRED_TAGS = frozenset(ALLOWED_TAGS)
_CPU_SIGNING_KEY = secrets.token_bytes(32)
_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:%|°?[CF])?(?![A-Za-z])")
_TAG_RE = re.compile(r"<\s*/?\s*([A-Za-z_][\w-]*)")
_CAPABILITY_RE = re.compile(
    r"\b(?:I|we|Viv)\s+(?:can|may|will|am able to)\s+"
    r"(?:run|execute|deploy|promote|delete|write|change|modify|access|download|send|authorize)\b",
    flags=re.I,
)
_UNKNOWN_MARKER_RE = re.compile(
    r"\b(?:unknown|not known|cannot determine|can't determine|cannot verify|can't verify|unverified|not available)\b",
    flags=re.I,
)


class TaggedPacketError(ValueError):
    """Fail-closed packet or draft validation error."""


@dataclass(frozen=True)
class DraftVerification:
    status: str
    errors: tuple[str, ...]
    checked_numbers: tuple[str, ...] = ()
    required_fact_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "errors": list(self.errors),
            "checked_numbers": list(self.checked_numbers),
            "required_fact_ids": list(self.required_fact_ids),
        }


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sign(value: Any) -> str:
    return hmac.new(_CPU_SIGNING_KEY, _canonical(value), hashlib.sha256).hexdigest()


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _block(tag: str, value: Any, *, block_id: str, source: str, confidence: str = "measured", required: bool = False, required_terms: Iterable[str] = ()) -> dict[str, Any]:
    if tag not in ALLOWED_TAGS:
        raise TaggedPacketError(f"unknown_tag:{tag}")
    if tag == "user_request" and source != "user":
        raise TaggedPacketError("user_request_source_must_be_user")
    if tag != "user_request" and source == "user":
        raise TaggedPacketError("authoritative_tag_cannot_be_user_source")
    return {
        "id": str(block_id),
        "source": str(source),
        "confidence": str(confidence),
        "required": bool(required),
        "required_terms": [str(x) for x in required_terms if str(x)],
        "value": value,
    }


def build_tagged_packet(
    *,
    identity: Iterable[Mapping[str, Any] | Any] = (),
    knowledge: Iterable[Mapping[str, Any] | Any] = (),
    telemetry: Iterable[Mapping[str, Any] | Any] = (),
    user_request: str,
    allowed_actions: Iterable[Mapping[str, Any] | Any] = (),
    unknowns: Iterable[Mapping[str, Any] | Any] = (),
    rendering_rules: Mapping[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Construct and CPU-sign a complete packet with exactly seven tag classes."""
    def blocks(tag: str, values: Iterable[Mapping[str, Any] | Any], prefix: str, source: str) -> list[dict[str, Any]]:
        out = []
        for index, item in enumerate(values, 1):
            if isinstance(item, Mapping):
                value = item.get("value", item.get("text", item))
                out.append(_block(
                    tag,
                    value,
                    block_id=str(item.get("id") or f"{prefix}{index:03d}"),
                    source=str(item.get("source") or source),
                    confidence=str(item.get("confidence") or "measured"),
                    required=bool(item.get("required", False)),
                    required_terms=item.get("required_terms") or (),
                ))
            else:
                out.append(_block(tag, item, block_id=f"{prefix}{index:03d}", source=source))
        return out

    rules = dict(rendering_rules or {})
    rules.setdefault("mode", "render_only")
    rules.setdefault("internal_only", ["telemetry"])
    rules.setdefault("preserve_unknowns", True)
    rules.setdefault("capability_claims_require_authorization", True)
    def nonempty(rows: list[dict[str, Any]], tag: str, block_id: str, value: Any, source: str, confidence: str = "known_empty") -> list[dict[str, Any]]:
        return rows or [_block(tag, value, block_id=block_id, source=source, confidence=confidence)]

    body = {
        "schema_version": SCHEMA_VERSION,
        "packet_id": str(trace_id or uuid.uuid4().hex),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "blocks": {
            "identity": nonempty(blocks("identity", identity, "I", "cpu_identity"), "identity", "I000", "No additional identity was supplied.", "cpu_identity"),
            "knowledge": nonempty(blocks("knowledge", knowledge, "K", "cpu_knowledge"), "knowledge", "K000", "No additional knowledge was supplied.", "cpu_knowledge"),
            "telemetry": nonempty(blocks("telemetry", telemetry, "T", "cpu_telemetry"), "telemetry", "T000", {"available": False}, "cpu_telemetry"),
            "user_request": [_block("user_request", str(user_request), block_id="U001", source="user", confidence="unverified")],
            "allowed_actions": nonempty(blocks("allowed_actions", allowed_actions, "A", "cpu_authority"), "allowed_actions", "A000", {"name": "none", "authorized": False}, "cpu_authority", "policy"),
            "unknowns": nonempty(blocks("unknowns", unknowns, "UQ", "cpu_unknown"), "unknowns", "UQ000", "No additional unknown was recorded.", "cpu_unknown"),
            "rendering_rules": [_block("rendering_rules", rules, block_id="R001", source="cpu_authority", confidence="policy")],
        },
    }
    body["packet_digest"] = _digest(body)
    body["cpu_signature"] = _sign(body)
    validate_tagged_packet(body)
    return body


def validate_tagged_packet(packet: Mapping[str, Any]) -> None:
    """Validate schema, tag allowlist, provenance, digest, and CPU signature."""
    if not isinstance(packet, Mapping) or packet.get("schema_version") != SCHEMA_VERSION:
        raise TaggedPacketError("schema_version")
    blocks = packet.get("blocks")
    if not isinstance(blocks, Mapping) or set(blocks) != REQUIRED_TAGS:
        raise TaggedPacketError("tag_set_mismatch")
    unsigned = {k: packet[k] for k in ("schema_version", "packet_id", "created_at", "blocks")}
    if packet.get("packet_digest") != _digest(unsigned):
        raise TaggedPacketError("packet_digest_mismatch")
    if not hmac.compare_digest(str(packet.get("cpu_signature") or ""), _sign(unsigned | {"packet_digest": packet["packet_digest"]})):
        raise TaggedPacketError("cpu_signature_mismatch")
    for tag in ALLOWED_TAGS:
        rows = blocks[tag]
        if not isinstance(rows, list) or not rows:
            raise TaggedPacketError(f"tag_missing_or_empty:{tag}")
        for row in rows:
            if not isinstance(row, Mapping) or not row.get("id") or "value" not in row:
                raise TaggedPacketError(f"malformed_block:{tag}")
            source = str(row.get("source") or "")
            if tag == "user_request" and source != "user":
                raise TaggedPacketError("user_request_provenance")
            if tag != "user_request" and source == "user":
                raise TaggedPacketError(f"user_injected_authority:{tag}")


def render_for_gpu(packet: Mapping[str, Any]) -> str:
    """Render escaped, explicit tags; values cannot create active tags."""
    validate_tagged_packet(packet)
    lines = [f'<aios_packet schema="{SCHEMA_VERSION}" digest="{html.escape(str(packet["packet_digest"]))}">']
    rules_rows = packet["blocks"].get("rendering_rules") or []
    rules_value = rules_rows[0].get("value") if rules_rows and isinstance(rules_rows[0], Mapping) else {}
    internal_only = set(rules_value.get("internal_only") or []) if isinstance(rules_value, Mapping) else set()
    for tag in ALLOWED_TAGS:
        if tag in internal_only:
            continue
        for row in packet["blocks"][tag]:
            attrs = (
                f' id="{html.escape(str(row["id"]))}"'
                f' source="{html.escape(str(row["source"]))}"'
                f' confidence="{html.escape(str(row.get("confidence") or ""))}"'
                f' required="{str(bool(row.get("required"))).lower()}"'
            )
            raw_value = row.get("value")
            if tag == "rendering_rules" and isinstance(raw_value, Mapping):
                # The CPU uses this field to decide what to suppress; the GPU
                # does not need the private tag names themselves. Exposing
                # ``internal_only: [telemetry]`` would place an operational
                # label in the ordinary model-visible packet.
                raw_value = {
                    key: value
                    for key, value in raw_value.items()
                    if key != "internal_only"
                }
            value = html.escape(_text(raw_value), quote=False)
            lines.append(f"  <{tag}{attrs}>{value}</{tag}>")
    lines.append("</aios_packet>")
    return "\n".join(lines)


def _all_authoritative_values(packet: Mapping[str, Any]) -> str:
    rows: list[str] = []
    for tag in ("identity", "knowledge", "telemetry", "allowed_actions", "unknowns"):
        rows.extend(_text(row.get("value")) for row in packet["blocks"][tag])
    return "\n".join(rows)


def verify_gpu_draft(packet: Mapping[str, Any], draft: str) -> DraftVerification:
    """CPU-side deterministic verification; never trusts GPU prose by itself."""
    try:
        validate_tagged_packet(packet)
    except TaggedPacketError as exc:
        return DraftVerification("FAIL", (f"packet:{exc}",))
    text = str(draft or "").strip()
    if len(text) < 2:
        return DraftVerification("FAIL", ("empty_draft",))
    errors: list[str] = []
    tag_names = _TAG_RE.findall(text)
    if tag_names:
        errors.append("draft_contains_tags")
    authoritative = _all_authoritative_values(packet)
    source_numbers = set(_NUMBER_RE.findall(authoritative))
    draft_numbers = tuple(_NUMBER_RE.findall(text))
    unknown_numbers = sorted(set(draft_numbers) - source_numbers)
    if unknown_numbers:
        errors.append("numeric_claim_not_in_packet:" + ",".join(unknown_numbers))
    rules = packet["blocks"]["rendering_rules"][0]["value"]
    required_rows = [
        row
        for tag in ("identity", "knowledge", "telemetry", "unknowns")
        for row in packet["blocks"][tag]
        if row.get("required")
    ]
    required_ids = tuple(str(row["id"]) for row in required_rows)
    folded = text.casefold()
    for row in required_rows:
        terms = [str(x).casefold() for x in row.get("required_terms") or ()]
        if terms and not any(term in folded for term in terms):
            errors.append(f"required_fact_omitted:{row['id']}")
    unknown_rows = packet["blocks"]["unknowns"]
    if rules.get("preserve_unknowns") and any(row.get("required") for row in unknown_rows) and not _UNKNOWN_MARKER_RE.search(text):
        errors.append("unknowns_omitted")
    action_names = {
        str(row.get("value", {}).get("name") if isinstance(row.get("value"), Mapping) else row.get("value")).casefold()
        for row in packet["blocks"]["allowed_actions"]
        if isinstance(row.get("value"), Mapping) and row["value"].get("authorized") is True
    }
    if rules.get("capability_claims_require_authorization") and _CAPABILITY_RE.search(text):
        if not any(name and name in folded for name in action_names):
            errors.append("unsupported_capability_claim")
    return DraftVerification("FAIL" if errors else "PASS", tuple(errors), draft_numbers, required_ids)
