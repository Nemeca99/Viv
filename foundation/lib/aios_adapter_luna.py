"""Callable luna_core adapter — Viv personality DNA + voice status (REAL).

Registry id: luna_core
V2 source (read-only): L:/Continue/FSAA/Luna/AIOS_V2/luna_core

API: status(), render_line(...), voice_probe(), run_smoke()

Wraps lib/aios_personality + voice_core.speak_status. Personality shapes tone;
does not invent chatbot converse or execute V2 LunaCore LLM loops.
Does not mutate security_core.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
_VIV = _FOUNDATION.parent
for _p in (_FOUNDATION, _VIV):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.aios_personality import (  # noqa: E402
    LUNA_MIRROR,
    LUNA_SOURCE,
    VIV_DNA,
    render_cpu_line,
    status_summary,
    tone_label,
    weights,
)
from lib.paths import AUTO_ARTIFACTS  # noqa: E402

ADAPTER_ID = "luna_core"
REGISTRY_ID = "luna_core"

V2_LUNA = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/luna_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "luna"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"


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


def _plant_status() -> str:
    try:
        from lib.master_rid import load_master_rid

        return str(load_master_rid().status)
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _v2_presence() -> dict[str, Any]:
    frag = V2_LUNA / "personality" / "fragment_profiles.json"
    return {
        "v2_luna_readable": V2_LUNA.is_dir(),
        "v2_luna_py": (V2_LUNA / "luna.py").is_file(),
        "v2_memory_voice_py": (V2_LUNA / "memory_voice.py").is_file(),
        "v2_fragment_profiles": frag.is_file(),
        "viv_executes_v2": False,
        "viv_mode": "personality_dna_plus_voice_status",
        "note": (
            "V2 LunaCore surveyed read-only; Viv uses aios_personality DNA + "
            "voice_core status (no fake converse)."
        ),
    }


def status() -> dict[str, Any]:
    """Personality DNA + voice peripheral presence. Returns {ok, evidence}."""
    try:
        summary = status_summary()
        sn = _s_n()
        pst = _plant_status()
        tone = tone_label(sn, pst, weights())
        voice: dict[str, Any] = {}
        try:
            from voice_core.speak import speak_status

            voice = speak_status()
        except Exception as exc:  # noqa: BLE001
            voice = {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": sn,
                "plant_status": pst,
                "tone": tone,
                "personality": summary,
                "dna_exists": VIV_DNA.is_file(),
                "luna_source_present": LUNA_SOURCE.is_file(),
                "luna_mirror_exists": LUNA_MIRROR.is_file(),
                "voice": {
                    "ok": bool(voice.get("ok")),
                    "backend": voice.get("backend"),
                    "served_name": voice.get("served_name"),
                    "reachable": voice.get("reachable"),
                    "gpu_optional": voice.get("gpu_optional"),
                },
                "viv_module": "lib.aios_personality",
                "viv_fake_converse": False,
                "v2": _v2_presence(),
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


def render_line(
    *,
    deltas: list[str] | None = None,
    stdout: str = "",
    status_name: str | None = None,
    master_s_n: float | None = None,
) -> dict[str, Any]:
    """Fact-locked personality-shaped CPU line (no LLM converse)."""
    try:
        sn = float(master_s_n) if master_s_n is not None else _s_n()
        pst = status_name or _plant_status()
        line = render_cpu_line(
            deltas=list(deltas or []),
            stdout=stdout or "",
            status=pst,
            s_n=sn,
        )
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "render_line",
                "at": _utc(),
                "s_n": sn,
                "status": pst,
                "tone": tone_label(sn, pst, weights()),
                "line": line,
                "chars": len(line),
                "source": "lib.aios_personality.render_cpu_line",
                "viv_fake_converse": False,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "render_line",
                "at": _utc(),
                "error": str(exc),
            },
        }


def voice_probe() -> dict[str, Any]:
    """Voice peripheral status only — does not speak or call GPU generate."""
    try:
        from voice_core.speak import speak_status

        vs = speak_status()
        return {
            "ok": bool(vs.get("ok", True)),
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "voice_probe",
                "at": _utc(),
                "backend": vs.get("backend"),
                "served_name": vs.get("served_name"),
                "reachable": vs.get("reachable"),
                "gpu_optional": vs.get("gpu_optional"),
                "prefer_over_lora": vs.get("prefer_over_lora"),
                "viv_spoke": False,
                "source": "voice_core.speak.speak_status",
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "voice_probe",
                "at": _utc(),
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """Prove DNA load + render_line + voice probe; assert no fake converse."""
    st = status()
    line = render_line(
        deltas=["adapter_smoke"],
        stdout="luna_core wrap",
        master_s_n=_s_n(),
    )
    voice = voice_probe()
    sev = st.get("evidence") or {}
    lev = line.get("evidence") or {}
    vev = voice.get("evidence") or {}
    v2 = sev.get("v2") or {}
    pers = sev.get("personality") or {}
    ok = (
        bool(st.get("ok"))
        and bool(line.get("ok"))
        and bool(sev.get("dna_exists"))
        and bool(pers.get("name"))
        and isinstance(pers.get("weights"), dict)
        and len(pers.get("weights") or {}) > 0
        and sev.get("viv_fake_converse") is False
        and lev.get("viv_fake_converse") is False
        and v2.get("viv_executes_v2") is False
        and vev.get("viv_spoke") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "status_ok": bool(st.get("ok")),
        "render_ok": bool(line.get("ok")),
        "voice_ok": bool(voice.get("ok")),
        "dna_exists": sev.get("dna_exists"),
        "name": pers.get("name"),
        "tone": sev.get("tone"),
        "line_chars": lev.get("chars"),
        "line_preview": (lev.get("line") or "")[:160],
        "voice_backend": vev.get("backend"),
        "voice_reachable": vev.get("reachable"),
        "viv_fake_converse": False,
        "v2_luna_readable": v2.get("v2_luna_readable"),
        "viv_executes_v2": v2.get("viv_executes_v2"),
        "status": st,
        "render_line": line,
        "voice_probe": voice,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "name": pers.get("name"),
            "tone": sev.get("tone"),
            "line_chars": lev.get("chars"),
            "voice_backend": vev.get("backend"),
            "viv_executes_v2": v2.get("viv_executes_v2"),
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
