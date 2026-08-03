"""Callable input_core adapter — Viv inbox + ingress_gate (REAL).

Registry id: input_core
V2 source (read-only survey): L:/Continue/FSAA/Luna/AIOS_V2/input_core

API: status(), normalize(text_or_event), run_smoke()

Prefer Viv organism inbox + security_membrane.ingress_gate over porting V2
multimodal InputProcessor (pdf/vision/audio stubs). Text/event normalize only.
Does not mutate security_core. Does not write to D:.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.aios_inbox import INBOX_PATH, ORGANISM_ROOT, OUTBOX_PATH  # noqa: E402
from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.security_membrane import membrane_status  # noqa: E402
from lib.triad_kernel import (  # noqa: E402
    TriadDenied,
    TriadEnvelope,
    open_context,
)

ADAPTER_ID = "input_core"
REGISTRY_ID = "input_core"

V2_INPUT = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/input_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "input"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"

_MAX_TEXT = 8000
_TEXT_KEYS = ("text", "content", "message", "ask", "prompt", "body", "input")


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def _v2_presence() -> dict[str, Any]:
    proc = V2_INPUT / "input_processor.py"
    return {
        "v2_input_readable": V2_INPUT.is_dir(),
        "v2_input_processor": proc.is_file(),
        "v2_init": (V2_INPUT / "__init__.py").is_file(),
        "viv_ports_v2_multimodal": False,
        "viv_mode": "inbox_plus_ingress_gate",
        "note": (
            "V2 InputProcessor surveyed read-only (pdf/vision/audio stubs not absorbed). "
            "Viv normalizes text/events via ingress_gate + organism inbox paths."
        ),
    }


def _inbox_stats() -> dict[str, Any]:
    queued = 0
    bytes_n = 0
    if INBOX_PATH.is_file():
        try:
            bytes_n = INBOX_PATH.stat().st_size
            for line in INBOX_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("status") in (None, "queued"):
                    queued += 1
        except OSError:
            pass
    return {
        "inbox_path": _as_posix(INBOX_PATH),
        "inbox_exists": INBOX_PATH.is_file(),
        "inbox_bytes": bytes_n,
        "queued_approx": queued,
        "outbox_exists": OUTBOX_PATH.is_file(),
        "organism_root": _as_posix(ORGANISM_ROOT),
    }


def _extract_text(text_or_event: Any) -> tuple[str, str, dict[str, Any]]:
    """Return (text, source_kind, meta)."""
    meta: dict[str, Any] = {}
    if text_or_event is None:
        return "", "empty", meta
    if isinstance(text_or_event, str):
        return text_or_event, "text", meta
    if isinstance(text_or_event, (bytes, bytearray)):
        try:
            return bytes(text_or_event).decode("utf-8", errors="replace"), "bytes", meta
        except Exception:  # noqa: BLE001
            return "", "bytes_decode_fail", meta
    if isinstance(text_or_event, dict):
        meta = {k: text_or_event.get(k) for k in ("id", "action", "priority", "status") if k in text_or_event}
        for key in _TEXT_KEYS:
            val = text_or_event.get(key)
            if isinstance(val, str) and val.strip():
                return val, f"event:{key}", meta
        # Nested payload
        payload = text_or_event.get("payload")
        if isinstance(payload, dict):
            for key in _TEXT_KEYS:
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val, f"event:payload.{key}", meta
        return json.dumps(text_or_event, ensure_ascii=False, default=str)[:_MAX_TEXT], "event:json", meta
    return str(text_or_event), "str_coerce", meta


def status() -> dict[str, Any]:
    """Inbox + membrane + V2 survey. Returns {ok, evidence}."""
    try:
        mem = membrane_status()
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "membrane": mem,
                "inbox": _inbox_stats(),
                "v2": _v2_presence(),
                "viv_modules": {
                    "ingress_gate": "lib.security_membrane.ingress_gate",
                    "inbox": "lib.aios_inbox",
                },
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "error": str(exc),
            },
        }


def normalize(text_or_event: Any, s_n: float | None = None) -> dict[str, Any]:
    """Gate + normalize text or inbox-like event into a structured dict."""
    sn = float(s_n) if s_n is not None else _s_n()
    raw, kind, meta = _extract_text(text_or_event)
    text = (raw or "").strip()
    truncated = False
    if len(text) > _MAX_TEXT:
        text = text[:_MAX_TEXT]
        truncated = True
    if not text:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "normalize",
                "at": _utc(),
                "s_n": sn,
                "source_kind": kind,
                "error": "empty_input",
                "meta": meta,
            },
        }
    try:
        context = open_context(
            TriadEnvelope.build(
                actor="external_input",
                source=kind,
                target="aios",
                action="INGRESS",
                payload={"text": text, "meta": meta},
                s_n=sn,
            )
        )
        gate = context.security_ingress
    except TriadDenied as exc:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "normalize",
                "at": _utc(),
                "s_n": sn,
                "source_kind": kind,
                "error": f"triad_ingress:{exc.reason}",
                "triad": exc.evidence,
                "meta": meta,
            },
        }
    allowed = bool(gate.get("allowed", True))
    return {
        "ok": allowed,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "normalize",
            "at": _utc(),
            "s_n": sn,
            "source_kind": kind,
            "source_type": "text",
            "plain_text": text if allowed else None,
            "chars": len(text),
            "truncated": truncated,
            "ingress": {
                "allowed": allowed,
                "stage": gate.get("stage"),
                "reason": gate.get("reason"),
            },
            "triad": {
                "context_id": context.context_id,
                "contract_version": context.envelope.contract_version,
                "pillar_versions": context.pillar_versions,
            },
            "meta": meta,
            "viv_ports_v2_multimodal": False,
            "via": "triad_kernel.open_context",
            "error": None if allowed else str(gate.get("reason") or "ingress_blocked"),
        },
    }


def _smoke_s_n(live: float) -> float:
    """Use gate-safe S_n for allow-path proof when plant is Law-5 dormant."""
    try:
        from lib.security_membrane import dormancy_threshold

        floor = float(dormancy_threshold()) + 0.02
    except Exception:  # noqa: BLE001
        floor = 0.39
    return max(float(live), floor)


def run_smoke() -> dict[str, Any]:
    """Prove status + normalize via ingress_gate (no V2 multimodal port).

    Allow-path uses max(live_s_n, dormancy+0.02) so Law-5 plant dormancy does not
    false-fail wiring. When live S_n is below dormancy, also prove deny path.
    """
    live_sn = _s_n()
    sn = _smoke_s_n(live_sn)
    marker = f"INPUT_ADAPTER_SMOKE_{_utc().replace(':', '').replace('-', '')}"
    st = status()
    sev = st.get("evidence") or {}
    norm_text = normalize(marker, sn)
    nev = norm_text.get("evidence") or {}
    event = {"id": "smoke-in", "text": marker, "status": "queued", "priority": 99}
    norm_ev = normalize(event, sn)
    eev = norm_ev.get("evidence") or {}
    empty = normalize("   ", sn)
    dormancy_deny: dict[str, Any] | None = None
    dormancy_deny_ok = True
    if live_sn + 1e-9 < sn:
        dormancy_deny = normalize(marker, live_sn)
        dormancy_deny_ok = not bool(dormancy_deny.get("ok"))
    ok = (
        bool(st.get("ok"))
        and bool(norm_text.get("ok"))
        and nev.get("plain_text") == marker
        and bool(norm_ev.get("ok"))
        and eev.get("plain_text") == marker
        and not bool(empty.get("ok"))
        and dormancy_deny_ok
        and (sev.get("v2") or {}).get("viv_ports_v2_multimodal") is False
        and bool((sev.get("inbox") or {}).get("organism_root"))
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "s_n": sn,
        "live_s_n": live_sn,
        "marker": marker,
        "status_ok": bool(st.get("ok")),
        "normalize_text_ok": bool(norm_text.get("ok")),
        "normalize_event_ok": bool(norm_ev.get("ok")),
        "empty_denied": not bool(empty.get("ok")),
        "dormancy_deny_ok": dormancy_deny_ok,
        "viv_ports_v2_multimodal": (sev.get("v2") or {}).get("viv_ports_v2_multimodal"),
        "inbox_exists": (sev.get("inbox") or {}).get("inbox_exists"),
        "status": st,
        "normalize_text": norm_text,
        "normalize_event": norm_ev,
        "normalize_empty": empty,
        "normalize_dormancy_live": dormancy_deny,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "marker": marker,
            "live_s_n": live_sn,
            "s_n": sn,
            "normalize_text_ok": evidence["normalize_text_ok"],
            "normalize_event_ok": evidence["normalize_event_ok"],
            "empty_denied": evidence["empty_denied"],
            "dormancy_deny_ok": evidence["dormancy_deny_ok"],
            "viv_ports_v2_multimodal": evidence["viv_ports_v2_multimodal"],
        }
        ADAPTER_EVIDENCE.write_text(json.dumps(slim, indent=2), encoding="utf-8")
        evidence["evidence_path"] = _as_posix(ADAPTER_EVIDENCE)
    except OSError as exc:
        evidence["evidence_write_error"] = str(exc)
    return {"ok": ok, "evidence": evidence}


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
