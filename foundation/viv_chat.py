#!/usr/bin/env python3
"""Viv terminal chatbox — standalone converse UI (no VS Code / Cursor).

  L:/Continue/.venv/Scripts/python.exe L:/Continue/Viv/foundation/viv_chat.py
  viv_shell.py chat

Slash commands: /quit /status /clear /speak on|off /help
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
_VIV = _ROOT.parent
for _p in (_ROOT, _VIV):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

THEME = Theme(
    {
        "you": "bold cyan",
        "viv": "bold magenta",
        "meta": "dim",
        "ok": "green",
        "warn": "yellow",
        "bad": "red",
        "sys": "bright_black",
    }
)

console = Console(theme=THEME, highlight=False)


def _utc_short() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _plant_line() -> str:
    try:
        from lib.prt_cycle import observe_state
        from voice_core.intent_packet import felt_state

        o = observe_state()
        sn = float(o.get("master_s_n") or 0.0)
        st = str(o.get("status") or "?")
        felt = felt_state(sn, st)
        return f"plant {st} · felt {felt} · S_n {sn:.3f} (bg)"
    except Exception as exc:  # noqa: BLE001
        return f"plant unavailable ({exc})"


def _session_line() -> str:
    try:
        from lib.viv_ide import load_session_state

        st = load_session_state()
        name = st.get("architect_name") or "Architect"
        turns = int(st.get("turn_count") or 0)
        return f"session · {name} · turns {turns}"
    except Exception:  # noqa: BLE001
        return "session · —"


def _header(*, speak: bool) -> Panel:
    title = Text("Viv", style="viv") + Text(" chat", style="meta")
    body = Text.from_markup(
        f"[meta]{_plant_line()}[/meta]\n"
        f"[meta]{_session_line()} · speak={'on' if speak else 'off'} · {_utc_short()}Z[/meta]\n"
        f"[sys]/quit  /status  /clear  /speak on|off  /help[/sys]"
    )
    return Panel(body, title=title, border_style="magenta", padding=(0, 1))


def _bubble(role: str, text: str, *, meta: str = "") -> Panel:
    if role.lower() == "you":
        style = "cyan"
        label = "You"
        rstyle = "you"
    else:
        style = "magenta"
        label = "Viv"
        rstyle = "viv"
    head = Text(label, style=rstyle)
    if meta:
        head.append(f"  {meta}", style="meta")
    content = Text(text.strip() or "…")
    return Panel(
        Group(head, Rule(style="bright_black"), content),
        border_style=style,
        padding=(0, 1),
    )


def _help() -> None:
    console.print(
        Panel(
            "[you]/quit[/you] leave\n"
            "[you]/status[/you] plant + session\n"
            "[you]/clear[/you] clear screen (chat file kept)\n"
            "[you]/speak on|off[/you] speak flag\n"
            "[you]/teach <text>[/you] live knowledge inject\n"
            "[you]/help[/you] this panel\n\n"
            "Or type [you]teach: <fact>[/you] as a normal message.\n"
            "Ask [you]what do you know about …[/you] to query live knowledge.\n"
            "Telemetry stays background — she answers as herself.",
            title="help",
            border_style="bright_black",
        )
    )


def _turn(message: str, *, speak: bool) -> dict[str, Any]:
    from lib.viv_ide import ide_turn

    # Fast path: no plant wait — Soft Oblivion still soft-converses immediately
    return ide_turn(message, speak=speak, wait_plant_s=0.0)


def run_chat(*, speak: bool = False) -> int:
    speak_flag = bool(speak)
    console.clear()
    console.print(_header(speak=speak_flag))
    console.print(
        Text("Travis — talk when ready. She holds the thread.", style="meta")
    )
    console.print()

    while True:
        try:
            line = console.input("[you]you>[/you] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print(Text("bye.", style="meta"))
            return 0

        if not line:
            continue

        low = line.lower()
        if low in {"/q", "/quit", "/exit", ":q"}:
            console.print(Text("bye.", style="meta"))
            return 0
        if low in {"/h", "/help", "?"}:
            _help()
            continue
        if low == "/clear":
            console.clear()
            console.print(_header(speak=speak_flag))
            continue
        if low == "/status":
            console.print(
                Panel(
                    f"{_plant_line()}\n{_session_line()}",
                    title="status",
                    border_style="bright_black",
                )
            )
            continue
        if low.startswith("/speak"):
            parts = low.split()
            if len(parts) >= 2 and parts[1] in {"on", "1", "true"}:
                speak_flag = True
            elif len(parts) >= 2 and parts[1] in {"off", "0", "false"}:
                speak_flag = False
            else:
                speak_flag = not speak_flag
            console.print(Text(f"speak={'on' if speak_flag else 'off'}", style="meta"))
            continue
        if low.startswith("/teach"):
            body = line[6:].strip()
            if not body:
                console.print(Text("usage: /teach <fact>", style="warn"))
                continue
            line = f"teach: {body}"
            # fall through as a normal turn
        elif line.startswith("/"):
            console.print(Text(f"unknown command: {line}", style="warn"))
            continue

        console.print(_bubble("you", line, meta=_utc_short()))
        with console.status("[meta]…[/meta]", spinner="dots"):
            t0 = time.time()
            try:
                turn = _turn(line, speak=speak_flag)
            except Exception as exc:  # noqa: BLE001
                console.print(_bubble("viv", f"(error) {exc}", meta="fail"))
                continue
        dt = time.time() - t0
        reply = str(turn.get("reply") or turn.get("error") or "…")
        soft = bool(turn.get("soft_dormant"))
        voice = (turn.get("voice") or {}) if isinstance(turn.get("voice"), dict) else {}
        meta_bits = [f"{dt*1000:.0f}ms"]
        if soft:
            meta_bits.append("soft")
        src = voice.get("voice_source")
        if src and src != "cpu_personality":
            meta_bits.append(str(src))
        sj = voice.get("shadow_judge") if isinstance(voice.get("shadow_judge"), dict) else {}
        if sj.get("label"):
            meta_bits.append(str(sj.get("label")))
        sn = turn.get("s_n")
        if sn is not None:
            meta_bits.append(f"S_n={float(sn):.2f}")
        console.print(_bubble("viv", reply, meta=" · ".join(meta_bits)))
        # Don't redraw full header every turn — keeps feel snappy
        console.print()

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    speak = "--speak" in argv
    if any(a in {"-h", "--help", "help"} for a in argv):
        print(__doc__)
        return 0
    return run_chat(speak=speak)


if __name__ == "__main__":
    raise SystemExit(main())
