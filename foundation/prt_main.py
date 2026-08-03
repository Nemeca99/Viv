#!/usr/bin/env python3
"""Viv PRT entry — voice-channel predictive reasoning collect + train (physics teacher).

Does NOT enable autonomous voice_speak. Explicit collect / apply only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.prt_cycle import (  # noqa: E402
    PRT_CYCLES_PATH,
    PRT_SUMMARY_PATH,
    collect,
    ensure_pre_prt_backup,
    halted,
    observe_state,
    run_cycle,
)
from lib.prt_train import build_prt_train_jsonl, train_prt_lora  # noqa: E402
from lib.prt_presets import get_preset  # noqa: E402
from lib.prt_overnight import (  # noqa: E402
    clear_overnight_halt,
    force_halt,
    request_halt,
    run_autonomous,
    run_overnight,
    status_snapshot,
)


def cmd_status(_: argparse.Namespace) -> int:
    st = {
        "ok": True,
        "halted": halted(),
        "cycles_path": str(PRT_CYCLES_PATH).replace("\\", "/"),
        "summary_path": str(PRT_SUMMARY_PATH).replace("\\", "/"),
        "observe": observe_state(),
        "voice_speak": False,
        "note": "Auto-speak remains halted; use collect/apply for PRT.",
    }
    print(json.dumps(st, indent=2, default=str))
    return 0


def cmd_observe(_: argparse.Namespace) -> int:
    print(json.dumps(observe_state(), indent=2, default=str))
    return 0


def cmd_cycle(args: argparse.Namespace) -> int:
    ensure_pre_prt_backup()
    row = run_cycle(
        act=args.act,
        settle_s=args.settle,
        skip_model_predict=args.baseline_predict,
        cpu_hold=bool(getattr(args, "cpu_hold", False)),
    )
    print(json.dumps(row, indent=2, default=str))
    return 0 if row.get("ok") or row.get("excluded") else 1


def cmd_collect(args: argparse.Namespace) -> int:
    ensure_pre_prt_backup()
    summary = collect(
        cycles=args.cycles,
        act=args.act,
        settle_s=args.settle,
        skip_model_predict=args.baseline_predict,
        cpu_hold=bool(getattr(args, "cpu_hold", False)),
    )
    print(json.dumps(summary, indent=2))
    return 0


def cmd_build(_: argparse.Namespace) -> int:
    summary = build_prt_train_jsonl()
    print(json.dumps(summary, indent=2))
    return 0 if int(summary.get("train_rows") or 0) > 0 else 1


def cmd_stage_status(_: argparse.Namespace) -> int:
    from lib.prt_stage import current_run_params, load_state, rolling_stage_metrics

    state = load_state()
    params = current_run_params()
    print(json.dumps({
        "ok": True,
        "state": state,
        "run_params": params,
        "metrics": rolling_stage_metrics(stage=int(state["stage"])),
    }, indent=2, default=str))
    return 0


def cmd_stage_check(_: argparse.Namespace) -> int:
    from lib.prt_stage import check_promotion

    decision = check_promotion()
    print(json.dumps(decision, indent=2, default=str))
    return 0


def cmd_stage_promote(args: argparse.Namespace) -> int:
    from lib.prt_stage import promote

    result = promote(operator=bool(args.force))
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("promoted") else 1


def cmd_stage_epoch_begin(args: argparse.Namespace) -> int:
    from lib.prt_stage import begin_live_telemetry_epoch

    state = begin_live_telemetry_epoch(
        note=args.note or "operator epoch begin",
        ghost_baseline_path=args.ghost_baseline,
    )
    print(json.dumps({"ok": True, "state": state}, indent=2, default=str))
    return 0


def cmd_stage_ab_piston(_: argparse.Namespace) -> int:
    import subprocess

    script = _ROOT / "scripts" / "ab_piston_ghost_vs_live.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=str(_ROOT), check=False)
    return int(proc.returncode)


def cmd_train(args: argparse.Namespace) -> int:
    meta = train_prt_lora(
        steps=args.steps,
        lr=args.lr,
        continue_adapter=not args.fresh,
    )
    print(json.dumps(meta, indent=2, default=str))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Collect physics cycles → build JSONL → continue LoRA train."""
    ensure_pre_prt_backup()
    observe_n = args.observe_cycles
    speak_n = args.speak_cycles
    life_n = int(getattr(args, "life_cycles", 0) or 0)
    pulse_n = int(getattr(args, "pulse_cycles", 0) or 0)
    settle = args.settle
    steps = args.steps
    lr = args.lr
    preset_name = getattr(args, "preset", None)
    if preset_name:
        pre = get_preset(preset_name)
        observe_n = int(pre.get("observe_cycles", observe_n))
        speak_n = int(pre.get("speak_cycles", speak_n))
        life_n = int(pre.get("life_cycles", life_n))
        pulse_n = int(pre.get("pulse_cycles", pulse_n))
        settle = float(pre.get("settle_s", settle))
        steps = int(pre.get("steps", steps))
        lr = float(pre.get("lr", lr))

    report: dict = {"preset": preset_name or "custom", "phases": []}

    if observe_n > 0:
        obs = collect(
            cycles=observe_n,
            act="observe",
            settle_s=settle,
            skip_model_predict=False,
        )
        report["phases"].append({"observe_collect": obs})

    if life_n > 0:
        lf = collect(
            cycles=life_n,
            act="life",
            settle_s=settle,
            skip_model_predict=False,
        )
        report["phases"].append({"life_collect": lf})

    if speak_n > 0:
        sp = collect(
            cycles=speak_n,
            act="speak",
            settle_s=settle,
            skip_model_predict=False,
        )
        report["phases"].append({"speak_collect": sp})

    if pulse_n > 0:
        pu = collect(
            cycles=pulse_n,
            act="pulse",
            settle_s=settle,
            skip_model_predict=False,
        )
        report["phases"].append({"pulse_collect": pu})

    built = build_prt_train_jsonl()
    report["build"] = built
    if int(built.get("train_rows") or 0) < 4:
        print(json.dumps(report, indent=2))
        print("abort train: not enough PRT rows", file=sys.stderr)
        return 2

    if not args.build_only:
        meta = train_prt_lora(
            steps=steps,
            lr=lr,
            continue_adapter=not args.fresh,
        )
        report["train"] = meta

    # Supercooling link: crystallize → strain tick (pending grow; auto-widen off by default)
    try:
        from lib.growth_strain import load_growth_config, strain_tick

        gcfg = load_growth_config()
        ticks = int(gcfg.get("overnight_strain_ticks") or 0)
        apply_g = bool(gcfg.get("apply_on_overnight"))
        last: dict = {}
        for _ in range(max(0, ticks)):
            last = strain_tick(apply_growth=apply_g)
            if last.get("near_dead") or last.get("fired"):
                break
        report["growth"] = last
    except Exception as exc:  # noqa: BLE001
        report["growth"] = {"ok": False, "error": str(exc)}

    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_quick(args: argparse.Namespace) -> int:
    """Daytime quick PRT — small collect + short continue while building."""
    args.preset = "quick"
    args.observe_cycles = 3
    args.speak_cycles = 1
    args.life_cycles = 2
    args.settle = 3.0
    args.steps = 40
    args.lr = 1e-4
    args.fresh = False
    args.build_only = False
    return cmd_apply(args)


def cmd_night_status(_: argparse.Namespace) -> int:
    print(json.dumps(status_snapshot(), indent=2, default=str))
    return 0


def cmd_night_halt(args: argparse.Namespace) -> int:
    reason = args.reason or "operator"
    # Default: force-kill apply/overnight tree in seconds. --soft = wait for round end.
    if getattr(args, "soft", False):
        path = request_halt(reason)
        print(
            json.dumps(
                {
                    "ok": True,
                    "halt": str(path).replace("\\", "/"),
                    "reason": reason,
                    "force": False,
                    "note": "soft halt — stops between rounds / mid-collect within ~1 cycle",
                }
            )
        )
        return 0
    out = force_halt(reason)
    print(json.dumps(out, indent=2))
    return 0


def cmd_night_resume(_: argparse.Namespace) -> int:
    cleared = clear_overnight_halt()
    st = status_snapshot()
    print(
        json.dumps(
            {
                "ok": True,
                "overnight_halt_cleared": cleared,
                "still_global_halt": st.get("global_halt"),
                "hint": "If global halt.flag exists, remove it separately to resume piston/auto.",
            },
            indent=2,
        )
    )
    return 0


def cmd_night_start(args: argparse.Namespace) -> int:
    """Sleep-safe PRT overnight loop. Does NOT enable voice_speak."""
    config_path = Path(args.config) if getattr(args, "config", None) else None
    report = run_overnight(
        max_rounds=args.max_rounds,
        max_hours=args.max_hours,
        cooldown_s=args.cooldown,
        dry_run=bool(args.dry_run),
        config_path=config_path,
    )
    print(json.dumps(report, indent=2, default=str))
    if report.get("status") == "HALTED":
        return 3
    if report.get("status") == "BUSY":
        return 4
    return 0 if report.get("ok") else 1


def cmd_autonomous(args: argparse.Namespace) -> int:
    """Fully autonomous PRT loop: wait S_n → collect/apply → integrity → expand? → cooldown forever.

    Same deep overnight config as `night start`. voice_speak forced False.
    Optional --with-capability-expansion runs PRT-scored sandbox module invent.
    """
    report = run_autonomous(
        cooldown_s=None,
        dry_run=False,
        config_path=None,  # deep overnight config (same as night start)
        capability_expansion=bool(args.with_capability_expansion),
        force_voice_speak_off=True,
        autonomous_audit=True,
        ide_inbox=True,
    )
    print(json.dumps(report, indent=2, default=str))
    if report.get("status") == "HALTED":
        return 3
    if report.get("status") == "BUSY":
        return 4
    if report.get("status") == "REFUSED":
        return 5
    return 0 if report.get("ok") else 1


def cmd_talk(args: argparse.Namespace) -> int:
    """Talk to Viv IDE — she uses the same .cursor skills + local tools as Cursor."""
    from lib.viv_ide import drain_inbox, ide_turn, status as ide_status

    if getattr(args, "status", False):
        print(json.dumps(ide_status(), indent=2, default=str))
        return 0
    if getattr(args, "inbox", False):
        out = drain_inbox(max_turns=int(args.max_turns or 1), speak=bool(args.speak))
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("ok") else 1
    msg = " ".join(args.message or []).strip()
    if not msg:
        print("usage: prt_main.py talk \"your message\"  |  talk --inbox  |  talk --status", file=sys.stderr)
        return 2
    turn = ide_turn(msg, speak=bool(args.speak))
    print(json.dumps(turn, indent=2, default=str))
    return 0 if turn.get("ok") else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Viv PRT — physics-graded predict/act/measure/train")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="Halt + live Master S_n")
    s.set_defaults(func=cmd_status)

    o = sub.add_parser("observe", help="One sensor/Master sample")
    o.set_defaults(func=cmd_observe)

    c = sub.add_parser("cycle", help="One PRT cycle")
    c.add_argument("--act", choices=["observe", "speak", "life"], default="observe")
    c.add_argument("--settle", type=float, default=None)
    c.add_argument("--baseline-predict", action="store_true")
    c.add_argument(
        "--cpu-hold",
        action="store_true",
        help="Pure CPU RID hold prediction (no GPU). Plant still grades.",
    )
    c.set_defaults(func=cmd_cycle)

    g = sub.add_parser("collect", help="N PRT cycles + summary")
    g.add_argument("--cycles", type=int, default=3)
    g.add_argument("--act", choices=["observe", "speak", "life"], default="observe")
    g.add_argument("--settle", type=float, default=None)
    g.add_argument("--baseline-predict", action="store_true")
    g.add_argument(
        "--cpu-hold",
        action="store_true",
        help="Pure CPU RID hold prediction (no GPU). Plant still grades.",
    )
    g.set_defaults(func=cmd_collect)

    b = sub.add_parser("build", help="Build train JSONL from scored cycles")
    b.set_defaults(func=cmd_build)

    t = sub.add_parser("train", help="LoRA train/continue on PRT JSONL only")
    t.add_argument("--steps", type=int, default=120)
    t.add_argument("--lr", type=float, default=1e-4)
    t.add_argument("--fresh", action="store_true", help="New LoRA (ignore existing adapter)")
    t.set_defaults(func=cmd_train)

    a = sub.add_parser("apply", help="Collect + build + train (main PRT apply path)")
    a.add_argument("--preset", choices=["quick", "deep"], default=None, help="Use named preset")
    a.add_argument("--observe-cycles", type=int, default=8)
    a.add_argument("--speak-cycles", type=int, default=3)
    a.add_argument("--life-cycles", type=int, default=0, help="Conway pressure task cycles")
    a.add_argument("--pulse-cycles", type=int, default=0, help="CPU pulse game cycles")
    a.add_argument("--settle", type=float, default=3.0)
    a.add_argument("--steps", type=int, default=120)
    a.add_argument("--lr", type=float, default=1e-4)
    a.add_argument("--fresh", action="store_true")
    a.add_argument("--build-only", action="store_true")
    a.set_defaults(func=cmd_apply)

    q = sub.add_parser("quick", help="Daytime quick PRT (4obs+2speak, 40 steps) while building")
    q.set_defaults(func=cmd_quick)

    st = sub.add_parser("stage", help="Growth-stage ladder (train to apex, tighten, release)")
    stsub = st.add_subparsers(dest="stage_cmd", required=True)
    sts = stsub.add_parser("status", help="Current stage + rolling metrics")
    sts.set_defaults(func=cmd_stage_status)
    stc = stsub.add_parser("check", help="Apex/promotion eligibility check")
    stc.set_defaults(func=cmd_stage_check)
    stp = stsub.add_parser("promote", help="Promote if apex reached (snapshots adapter release)")
    stp.add_argument("--force", action="store_true", help="Operator override")
    stp.set_defaults(func=cmd_stage_promote)
    ste = stsub.add_parser("epoch-begin", help="Begin live telemetry epoch (excludes ghost cycles from promotion)")
    ste.add_argument("--note", default="", help="Epoch note stored in stage state")
    ste.add_argument(
        "--ghost-baseline",
        default="L:/Continue/Viv/foundation/artifacts/audit/prt_overnight_ghost_baseline_summary.json",
        help="Path to archived ghost baseline summary",
    )
    ste.set_defaults(func=cmd_stage_epoch_begin)
    stab = stsub.add_parser("ab-piston", help="Build ghost-vs-live A/B report (ab_piston_ghost_vs_live_v1)")
    stab.set_defaults(func=cmd_stage_ab_piston)

    n = sub.add_parser("night", help="Overnight DEEP autonomous PRT loop (bounded + halt-gated)")
    nsub = n.add_subparsers(dest="night_cmd", required=True)

    ns = nsub.add_parser("status", help="Overnight state + plant snapshot")
    ns.set_defaults(func=cmd_night_status)

    nh = nsub.add_parser(
        "halt",
        help="Stop overnight NOW (force-kills apply tree). Use --soft to wait for round end.",
    )
    nh.add_argument("--reason", default="operator")
    nh.add_argument(
        "--soft",
        action="store_true",
        help="Do not kill — stop at next collect cycle / between rounds only",
    )
    nh.set_defaults(func=cmd_night_halt)

    nr = nsub.add_parser("resume", help="Clear overnight halt flag (not global halt.flag)")
    nr.set_defaults(func=cmd_night_resume)

    ngo = nsub.add_parser("start", help="Run overnight PRT until budget/halt")
    ngo.add_argument("--max-rounds", type=int, default=None)
    ngo.add_argument("--max-hours", type=float, default=None)
    ngo.add_argument("--cooldown", type=float, default=None, help="Seconds between applies")
    ngo.add_argument("--dry-run", action="store_true", help="Gate + wait path only; no GPU train")
    ngo.add_argument(
        "--config",
        default=None,
        help="Overnight config JSON (default artifacts/models/prt_overnight_config.json)",
    )
    ngo.set_defaults(func=cmd_night_start)

    au = sub.add_parser(
        "autonomous",
        help="Fully autonomous PRT: perpetual deep collect/apply + optional capability expansion",
    )
    au.add_argument(
        "--with-capability-expansion",
        action="store_true",
        default=False,
        help="After integrity pass, invent/score/commit sandbox AIOS modules (PRT-gated)",
    )
    au.set_defaults(func=cmd_autonomous)

    tk = sub.add_parser(
        "talk",
        help="Talk to Viv IDE (Cursor-replacement: skills + read/write/search/shell)",
    )
    tk.add_argument("message", nargs="*", help="Architect message")
    tk.add_argument("--inbox", action="store_true", help="Drain organism inbox as IDE turns")
    tk.add_argument("--status", action="store_true", help="IDE skill/tool status")
    tk.add_argument("--speak", action="store_true", help="Also speak reply via voice (if server up)")
    tk.add_argument("--max-turns", type=int, default=1)
    tk.set_defaults(func=cmd_talk)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())