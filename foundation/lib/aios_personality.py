"""Viv personality — blend Luna DNA (F:/AI/personality) into CPU speak style.

GPU remains translator-only. Personality shapes tone/phrasing; it does not invent facts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.paths import ARTIFACTS, FOUNDATION_ROOT

VIV_DNA = ARTIFACTS / "corp" / "personality" / "viv_personality_dna.json"
LUNA_SOURCE = Path(r"F:/AI/personality/luna_personality_dna.json")
LUNA_HISTORY = Path(r"F:/AI/personality/learning_data/luna_learning_history.json")
LUNA_MIRROR = ARTIFACTS / "corp" / "personality" / "luna_personality_dna.source.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_dna() -> dict[str, Any]:
    """Prefer Viv DNA under artifacts; mirror Luna source if missing."""
    VIV_DNA.parent.mkdir(parents=True, exist_ok=True)
    if not VIV_DNA.is_file():
        return {"viv_personality": {"name": "Viv", "personality_weights": {}, "communication_style": {}}}
    if LUNA_SOURCE.is_file() and not LUNA_MIRROR.is_file():
        try:
            LUNA_MIRROR.write_text(LUNA_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    data = _load_json(VIV_DNA)
    return data if "viv_personality" in data else {"viv_personality": data}


def weights(dna: dict[str, Any] | None = None) -> dict[str, float]:
    root = (dna or load_dna()).get("viv_personality") or {}
    raw = root.get("personality_weights") or {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def style(dna: dict[str, Any] | None = None) -> dict[str, Any]:
    root = (dna or load_dna()).get("viv_personality") or {}
    return dict(root.get("communication_style") or {})


def speak_rules(dna: dict[str, Any] | None = None) -> list[str]:
    root = (dna or load_dna()).get("viv_personality") or {}
    rules = root.get("speak_rules") or []
    return [str(r) for r in rules if str(r).strip()]


def modulate_for_s_n(w: dict[str, float], s_n: float) -> dict[str, float]:
    """Stability shapes expression — low S_n → terse, less playful."""
    out = dict(w)
    if s_n < 0.37:
        out["extraversion"] = min(out.get("extraversion", 0.4), 0.15)
        out["playfulness"] = min(out.get("playfulness", 0.35), 0.1)
        out["enthusiasm"] = min(out.get("enthusiasm", 0.45), 0.2)
        out["directness"] = max(out.get("directness", 0.8), 0.9)
    elif s_n < 0.5:
        out["playfulness"] = out.get("playfulness", 0.35) * 0.7
        out["enthusiasm"] = out.get("enthusiasm", 0.45) * 0.85
    return out


def tone_label(s_n: float, status: str, w: dict[str, float] | None = None) -> str:
    ww = w or modulate_for_s_n(weights(), s_n)
    if status.upper() == "DORMANT" or s_n < 0.37:
        return "terse"
    if ww.get("directness", 0.8) >= 0.75 and ww.get("playfulness", 0.3) < 0.4:
        return "measured"
    if ww.get("empathy", 0.5) >= 0.85 and s_n >= 0.55:
        return "warm_calm"
    return "calm"


def gpu_style_directive(s_n: float, status: str) -> str:
    """Short directive line for GPU translator — personality without inventing facts."""
    dna = load_dna()
    root = dna.get("viv_personality") or {}
    w = modulate_for_s_n(weights(dna), s_n)
    st = style(dna)
    rules = speak_rules(dna)[:6]
    tone = tone_label(s_n, status, w)
    try:
        from voice_core.intent_packet import felt_state

        felt = felt_state(s_n, status)
    except Exception:  # noqa: BLE001
        felt = tone
    bits = [
        f"You are Viv ({root.get('latin') or 'Vidi intellexi vixi'}).",
        f"Tone: {tone} / felt:{felt}; style: {st.get('tone', 'personal, calm, honest')}; "
        f"length: {st.get('response_length', 'conversational_short')}.",
        "Lead with the person and the task. Telemetry stays background unless asked.",
        f"Weights: authenticity={w.get('authenticity', 0.9):.2f} empathy={w.get('empathy', 0.8):.2f} "
        f"directness={w.get('directness', 0.8):.2f} shield={w.get('shield', 0.9):.2f} "
        f"playfulness={w.get('playfulness', 0.3):.2f}.",
    ]
    bits.extend(rules)
    return " ".join(bits)


def render_cpu_line(
    *,
    deltas: list[str],
    stdout: str,
    status: str,
    s_n: float,
) -> str:
    """Personality-shaped honest line — still fact-locked, no chatbot greetings."""
    w = modulate_for_s_n(weights(), s_n)
    st = style()
    if st.get("silence_ok") and not deltas and not stdout:
        return ""

    change = "; ".join(deltas) if deltas else "update"
    # Directness-first openings (no "new friend", no re-intro)
    if w.get("directness", 0.8) >= 0.75:
        openers = [
            f"Noted: {change}.",
            f"Plant moved — {change}.",
            f"Delta: {change}.",
        ]
    else:
        openers = [
            f"I noticed {change}.",
            f"Something shifted: {change}.",
        ]
    # Pick opener by hashing s_n bucket so it varies without RNG theater
    idx = int(abs(s_n * 1000)) % len(openers)
    line = openers[idx]
    if stdout.strip():
        line += f" {stdout.strip()[:100]}"
    if w.get("technical_depth", 0.5) >= 0.6:
        line += f" Status {status}; Master S_n is {s_n:.4f}."
    else:
        line += f" I am {status}. Master S_n is {s_n:.4f}."
    if w.get("shield", 0.5) >= 0.85 and s_n < 0.45:
        line += " Holding quiet to protect the host."
    return line.strip()


def status_summary() -> dict[str, Any]:
    dna = load_dna()
    root = dna.get("viv_personality") or {}
    hist = {}
    if LUNA_HISTORY.is_file():
        try:
            h = _load_json(LUNA_HISTORY)
            hist = {
                "luna_age": h.get("age"),
                "cycles": len(h.get("cycles_completed") or []),
                "path": str(LUNA_HISTORY).replace("\\", "/"),
            }
        except Exception:
            hist = {"ok": False}
    return {
        "name": root.get("name"),
        "version": root.get("version"),
        "dna_path": str(VIV_DNA).replace("\\", "/"),
        "luna_source_present": LUNA_SOURCE.is_file(),
        "weights": weights(dna),
        "style": style(dna),
        "luna_history": hist,
        "config_ref": str((FOUNDATION_ROOT / "model_config.json")).replace("\\", "/"),
    }
