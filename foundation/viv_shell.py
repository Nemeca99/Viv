#!/usr/bin/env python3
"""Viv standalone shell — no VS Code, no Cursor, no Continue UI required.

  L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/viv_shell.py
  viv_shell.py status | talk <msg> | chat | aifl | gate | expand | bridges | adapters | rebuild | manifest | inbox | watch

  Chatbox UI:
  L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/viv_chat.py

  AIFL (she talks to herself / ingests L: files; judge aligns):
  viv_shell.py aifl --mode ingest --files 3 --turns 5
  viv_shell.py aifl --mode mixed
  viv_shell.py aifl --mode identity

  LoRA admission gate (hold-out pre-flight + train_ready signal):
  viv_shell.py gate
  viv_shell.py gate status
  viv_shell.py gate unfreeze
"""
from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

BRIDGES = Path(r"L:/Continue/Viv/sandbox/work/aios_build/system_bridges")
MANIFEST = Path(r"L:/Continue/Viv/sandbox/work/aios_build/MANIFEST.md")

_ADAPTER_MODS = (
    ("carma", "lib.aios_adapter_carma"),
    ("knowledge", "lib.aios_adapter_knowledge"),
    ("steel", "lib.aios_adapter_steel"),
    ("tool", "lib.aios_adapter_tool"),
    ("dataset", "lib.aios_adapter_dataset"),
    ("dream", "lib.aios_adapter_dream"),
    ("audit", "lib.aios_adapter_audit"),
    ("consciousness", "lib.aios_adapter_consciousness"),
    ("luna", "lib.aios_adapter_luna"),
    ("mirror", "lib.aios_adapter_mirror"),
    ("rid", "lib.aios_adapter_rid"),
    ("input", "lib.aios_adapter_input"),
    ("support", "lib.aios_adapter_support"),
    ("nox", "lib.aios_adapter_nox"),
    ("utils", "lib.aios_adapter_utils"),
    ("vision", "lib.aios_adapter_vision"),
    ("backup", "lib.aios_adapter_backup"),
)


def _print(obj: object) -> None:
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


def _adapter_inventory() -> list[dict]:
    rows: list[dict] = []
    for name, modpath in _ADAPTER_MODS:
        path = _ROOT / "lib" / f"aios_adapter_{name}.py"
        row: dict = {"id": name, "module": modpath, "path": str(path).replace("\\", "/"), "import_ok": False}
        try:
            mod = importlib.import_module(modpath)
            row["import_ok"] = True
            row["has_status"] = callable(getattr(mod, "status", None))
            row["has_smoke"] = callable(getattr(mod, "run_smoke", None))
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)[:160]
        rows.append(row)
    return rows


def cmd_status() -> int:
    from lib.prt_cycle import observe_state
    from lib.viv_ide import status as ide_status
    from lib.prt_overnight import overnight_halted, read_state

    plant = observe_state()
    st = read_state()
    bridges = sorted(p.name for p in BRIDGES.glob("*_bridge.json")) if BRIDGES.is_dir() else []
    adapters = _adapter_inventory()
    out = {
        "plant": {
            "master_s_n": plant.get("master_s_n"),
            "status": plant.get("status"),
            "rsr": plant.get("master_rsr") or plant.get("rsr"),
            "ltp": plant.get("master_ltp") or plant.get("ltp"),
            "rle": plant.get("master_rle") or plant.get("rle"),
        },
        "halted": overnight_halted(),
        "overnight": {
            k: st.get(k)
            for k in ("status", "mode", "rounds_done", "started_at", "pid", "capability_expansion")
        },
        "bridges_n": len(bridges),
        "bridges": bridges,
        "adapters_n": len(adapters),
        "adapters_ok": sum(1 for a in adapters if a.get("import_ok")),
        "adapters": [a["id"] for a in adapters if a.get("import_ok")],
        "ide": ide_status(),
    }
    _print(out)
    return 0


def cmd_adapters(*, smoke: bool = False) -> int:
    rows = _adapter_inventory()
    if smoke:
        for row in rows:
            if not row.get("import_ok"):
                row["smoke"] = {"ok": False, "error": "import_failed"}
                continue
            try:
                mod = importlib.import_module(str(row["module"]))
                fn = getattr(mod, "run_smoke", None)
                if not callable(fn):
                    row["smoke"] = {"ok": False, "error": "no_run_smoke"}
                    continue
                out = fn()
                ok = bool(out.get("ok")) if isinstance(out, dict) else bool(out)
                row["smoke"] = {"ok": ok, "compact": {k: out.get(k) for k in list(out)[:8]} if isinstance(out, dict) else out}
            except Exception as exc:  # noqa: BLE001
                row["smoke"] = {"ok": False, "error": str(exc)[:200]}
    _print({"n": len(rows), "adapters": rows})
    return 0 if all(r.get("import_ok") for r in rows) else 1


def cmd_rebuild() -> int:
    from lib.viv_ide import tool_rebuild_ticket

    ticket = tool_rebuild_ticket()
    _print(ticket)
    return 0 if ticket.get("ok") else 1


def cmd_talk(text: str, *, speak: bool = False) -> int:
    from lib.viv_ide import ide_turn

    turn = ide_turn(text, speak=speak)
    _print(turn)
    print("\n--- Viv ---")
    print(turn.get("reply") or turn.get("error") or "")
    return 0 if turn.get("ok") else 1


def cmd_expand() -> int:
    from lib.prt_capability_expand import run_capability_expansion
    from lib.prt_cycle import observe_state

    sn = float(observe_state().get("master_s_n") or 0.0)
    out = run_capability_expansion(s_n=sn, min_speak_reward_rate=0.0, speak_reward_rate=1.0)
    _print(out)
    return 0 if out.get("ok") or out.get("skipped") else 1


def cmd_inbox() -> int:
    from lib.viv_ide import drain_inbox

    out = drain_inbox(max_turns=3, speak=False)
    _print(out)
    return 0 if out.get("ok") else 1


def cmd_bridges() -> int:
    rows = []
    if BRIDGES.is_dir():
        for p in sorted(BRIDGES.glob("*_bridge.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            rows.append(
                {
                    "file": p.name,
                    "system_id": data.get("system_id"),
                    "status": data.get("status"),
                    "on_disk": data.get("on_disk"),
                    "files": len(data.get("file_sample") or []),
                    "role": (data.get("role") or "")[:80],
                }
            )
    _print({"n": len(rows), "bridges": rows})
    return 0


def cmd_manifest() -> int:
    text = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else ""
    rewards = [ln for ln in text.splitlines() if "REWARD" in ln and "PRT-EXPAND" in ln]
    _print({"path": str(MANIFEST).replace("\\", "/"), "chars": len(text), "expand_rewards": len(rewards), "tail": rewards[-12:]})
    return 0


def cmd_watch(seconds: float = 60.0) -> int:
    """Poll plant + overnight while PRT runs."""
    from lib.prt_cycle import observe_state
    from lib.prt_overnight import read_state

    end = time.time() + max(5.0, seconds)
    while time.time() < end:
        o = observe_state()
        st = read_state()
        print(
            f"{time.strftime('%H:%M:%S')} sn={float(o.get('master_s_n') or 0):.4f} "
            f"{o.get('status')} rounds={st.get('rounds_done')} status={st.get('status')}"
        )
        time.sleep(5.0)
    return 0


def cmd_chat(*, speak: bool = False) -> int:
    from viv_chat import run_chat

    return run_chat(speak=speak)


def cmd_gate(*, action: str = "check") -> int:
    """LoRA admission gate: evaluate policy, hold-out drift, train_ready signal."""
    from lib.viv_judge_train_gate import (
        evaluate_lora_admission,
        load_gate_state,
        save_gate_state,
        status,
    )

    if action == "status":
        _print(status())
        return 0
    if action == "unfreeze":
        st = load_gate_state()
        st["frozen"] = False
        save_gate_state(st)
        _print({"ok": True, "frozen": False, "note": "operator_unfreeze"})
        return 0
    out = evaluate_lora_admission(write_signal=True)
    _print(out)
    return 0 if out.get("ok") else 1


def cmd_aifl(*, turns: int = 5, mode: str = "mixed", n_files: int = 2) -> int:
    """AIFL — she talks to herself / ingests L: files; shadow judge aligns; we watch logs."""
    from lib.viv_aifl import run_aifl

    out = run_aifl(turns=turns, speak=False, mode=mode, n_files=n_files)
    _print(
        {
            "ok": out.get("ok"),
            "mode": out.get("mode"),
            "turns": out.get("turns"),
            "elapsed_ms": out.get("elapsed_ms"),
            "labels": out.get("labels"),
            "ingest": out.get("ingest"),
            "memories": out.get("memories"),
            "train_gate": out.get("train_gate"),
            "conversation_path": out.get("conversation_path"),
            "posture": out.get("posture"),
            "tail": out.get("tail"),
        }
    )
    return 0 if out.get("ok") else 1


def repl() -> int:
    print(
        "Viv shell (standalone). Commands: status | chat | aifl | gate | talk <msg> | expand | bridges | "
        "adapters [smoke] | rebuild | manifest | inbox | watch [s] | quit"
    )
    print("Plant-gated. Prefer `chat` for the terminal chatbox. `aifl` = self-talk + judge. `gate` = LoRA admit.\n")
    while True:
        try:
            line = input("viv> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        low = line.lower()
        if low in {"q", "quit", "exit"}:
            return 0
        if low in {"chat", "c"}:
            return cmd_chat(speak=False)
        if low.startswith("aifl"):
            parts = low.split()
            turns = 5
            mode = "mixed"
            n_files = 2
            for i, part in enumerate(parts[1:], start=1):
                if part.isdigit():
                    turns = int(part)
                elif part in {"identity", "ingest", "mixed"}:
                    mode = part
                elif part.startswith("files=") and part.split("=", 1)[1].isdigit():
                    n_files = int(part.split("=", 1)[1])
            cmd_aifl(turns=turns, mode=mode, n_files=n_files)
            continue
        if low.startswith("gate"):
            parts = low.split()
            action = parts[1] if len(parts) > 1 else "check"
            cmd_gate(action=action)
            continue
        if low == "status":
            cmd_status()
            continue
        if low == "expand":
            cmd_expand()
            continue
        if low == "inbox":
            cmd_inbox()
            continue
        if low == "bridges":
            cmd_bridges()
            continue
        if low.startswith("adapters"):
            parts = low.split()
            cmd_adapters(smoke=("smoke" in parts))
            continue
        if low == "rebuild":
            cmd_rebuild()
            continue
        if low == "manifest":
            cmd_manifest()
            continue
        if low.startswith("watch"):
            parts = low.split()
            secs = float(parts[1]) if len(parts) > 1 else 60.0
            cmd_watch(secs)
            continue
        if low.startswith("talk "):
            cmd_talk(line[5:].strip())
            continue
        if low == "talk":
            print("usage: talk <message>  (or: chat)")
            continue
        cmd_talk(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return repl()
    cmd = argv[0].lower()
    if cmd == "status":
        return cmd_status()
    if cmd == "expand":
        return cmd_expand()
    if cmd == "inbox":
        return cmd_inbox()
    if cmd == "bridges":
        return cmd_bridges()
    if cmd == "adapters":
        return cmd_adapters(smoke=("smoke" in [a.lower() for a in argv[1:]]))
    if cmd == "rebuild":
        return cmd_rebuild()
    if cmd == "manifest":
        return cmd_manifest()
    if cmd == "watch":
        return cmd_watch(float(argv[1]) if len(argv) > 1 else 60.0)
    if cmd in {"chat", "c"}:
        return cmd_chat(speak=("--speak" in argv))
    if cmd == "aifl":
        turns = 5
        mode = "mixed"
        n_files = 2
        i = 1
        while i < len(argv):
            a = argv[i]
            if a in {"--turns", "-n"} and i + 1 < len(argv):
                try:
                    turns = int(argv[i + 1])
                except ValueError:
                    turns = 5
                i += 2
                continue
            if a in {"--mode", "-m"} and i + 1 < len(argv):
                mode = argv[i + 1]
                i += 2
                continue
            if a in {"--files", "-f"} and i + 1 < len(argv):
                try:
                    n_files = int(argv[i + 1])
                except ValueError:
                    n_files = 2
                i += 2
                continue
            if a.isdigit():
                turns = int(a)
            elif a in {"identity", "ingest", "mixed"}:
                mode = a
            i += 1
        return cmd_aifl(turns=turns, mode=mode, n_files=n_files)
    if cmd == "gate":
        action = argv[1].lower() if len(argv) > 1 else "check"
        return cmd_gate(action=action)
    if cmd == "talk":
        rest = [a for a in argv[1:] if a != "--speak"]
        return cmd_talk(" ".join(rest), speak=("--speak" in argv))
    if cmd in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    return cmd_talk(" ".join(argv))


if __name__ == "__main__":
    raise SystemExit(main())
