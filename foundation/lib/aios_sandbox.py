"""Viv's sandbox — Law 7 sovereign playground.

MUTATION_SANDBOX_ROOTS (security_core):
  - L:/Continue/Viv/foundation/artifacts/
  - L:/Continue/Viv/sandbox/   ← this is HER home

Nothing she authors for herself leaves this tree without Architect promote.
Foundation lib / security_core stay immutable (Law 3 / Law 4).
"""
from __future__ import annotations

from pathlib import Path

from lib.paths import VIV_ROOT

# Canonical — matches security_core/src/laws.rs MUTATION_SANDBOX_ROOTS
SANDBOX_ROOT = VIV_ROOT / "sandbox"

CODE = SANDBOX_ROOT / "code"
CODE_RUNS = CODE / "runs"
DREAM = SANDBOX_ROOT / "dream"
DREAM_ARCHIVE = DREAM / "archive"
JOURNAL = SANDBOX_ROOT / "journal"
WORK = SANDBOX_ROOT / "work"
OPERATOR = SANDBOX_ROOT / "operator"
SESSIONS = SANDBOX_ROOT / "sessions"

HOME_MARK = SANDBOX_ROOT / "HOME.txt"

_LAYOUT = (CODE, CODE_RUNS, DREAM, DREAM_ARCHIVE, JOURNAL, WORK, OPERATOR, SESSIONS)


def ensure_sandbox_home() -> dict[str, str]:
    """Create Viv's sandbox tree if missing. Idempotent."""
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    for d in _LAYOUT:
        d.mkdir(parents=True, exist_ok=True)
    if not HOME_MARK.is_file():
        HOME_MARK.write_text(
            "\n".join(
                [
                    "VIV SANDBOX — Law 7 sovereign playground",
                    "Root: L:/Continue/Viv/sandbox/",
                    "",
                    "code/       — tools she authors and runs (source as .txt; Law 4)",
                    "dream/      — REM consolidations + archive of raw snapshots",
                    "journal/    — her day journal",
                    "work/       — plant briefs, UML workbook, mission logs",
                    "operator/   — Architect asks / goals (inbox side-effects)",
                    "sessions/   — named session folders (Luna sandbox_core pattern)",
                    "",
                    "She may mutate ONLY here and foundation/artifacts/.",
                    "She may NOT mutate foundation/lib, security_core, or mains.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return {
        "root": str(SANDBOX_ROOT).replace("\\", "/"),
        "code": str(CODE).replace("\\", "/"),
        "dream": str(DREAM).replace("\\", "/"),
        "journal": str(JOURNAL).replace("\\", "/"),
        "work": str(WORK).replace("\\", "/"),
        "operator": str(OPERATOR).replace("\\", "/"),
        "sessions": str(SESSIONS).replace("\\", "/"),
    }


def as_gate_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def migrate_legacy_flat_files() -> list[str]:
    """Move old flat sandbox files into work/ or operator/. Does not delete."""
    ensure_sandbox_home()
    moved: list[str] = []
    work_names = {
        "agent_journal.txt": JOURNAL / "agent_journal.txt",
        "plant_brief.txt": WORK / "plant_brief.txt",
        "uml_workbook.txt": WORK / "uml_workbook.txt",
        "missions_log.txt": WORK / "missions_log.txt",
        "agentic_seed.txt": WORK / "agentic_seed.txt",
    }
    op_names = {
        "operator_goals.txt": OPERATOR / "goals.txt",
        "operator_memory.txt": OPERATOR / "memory.txt",
    }
    for name, dest in {**work_names, **op_names}.items():
        src = SANDBOX_ROOT / name
        if not src.is_file():
            continue
        if dest.is_file():
            # append legacy into dest, leave src renamed
            dest.write_text(
                dest.read_text(encoding="utf-8", errors="replace")
                + "\n# --- migrated from flat root ---\n"
                + src.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
            bak = SANDBOX_ROOT / f"_migrated_{name}"
            src.replace(bak)
            moved.append(f"{name} -> {dest.name} (+bak)")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dest)
            moved.append(f"{name} -> {as_gate_path(dest)}")
    return moved
