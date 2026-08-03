#!/usr/bin/env python3
"""
Viv security_core — operator CLI.

Thin Python surface over the Rust security_core PyO3 module.
Enforcement logic lives in Rust only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_VIV = _ROOT.parent
_FOUNDATION = _VIV / "foundation"
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

VERSION = "0.2.6"


def _load_rust():
    try:
        from lib import security_bridge  # noqa: PLC0415
        return security_bridge.rust_module()
    except (ImportError, RuntimeError) as exc:
        print(
            "verified Viv-local security_core Rust module unavailable. Build:\n"
            "  cd L:\\Continue\\Viv\\security_core\n"
            "  cargo build --release\n"
            "  use security_core\\runtime\\security_core.pyd with its SHA-256 sidecar",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc


def _live_s_n(fallback: float | None) -> float:
    if fallback is not None:
        return float(fallback)
    try:
        from lib.master_rid import load_master_rid  # noqa: PLC0415
        return float(load_master_rid().master_s_n)
    except Exception:
        return 1.0


def cmd_check_in(args: argparse.Namespace) -> int:
    sc = _load_rust()
    text = " ".join(args.text)
    s_n = _live_s_n(args.s_n)
    verdict = sc.check_ingress(text, s_n)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict.get("allowed") else 1


def cmd_check_out(args: argparse.Namespace) -> int:
    sc = _load_rust()
    text = " ".join(args.text)
    s_n = _live_s_n(args.s_n)
    verdict = sc.check_egress(text, s_n)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict.get("allowed") else 1


def cmd_enforce(args: argparse.Namespace) -> int:
    sc = _load_rust()
    s_n = _live_s_n(args.s_n)
    result = sc.enforce_morality(args.tool, args.params, s_n, args.forensic or "")
    print(json.dumps(result, indent=2))
    return 0 if result.get("allowed") else 1


def cmd_status(_: argparse.Namespace) -> int:
    sc = _load_rust()
    from lib import security_bridge  # noqa: PLC0415
    print(json.dumps({
        "layer": "security_core",
        "language": "rust",
        "version": getattr(sc, "__version__", VERSION),
        "dormancy_threshold": sc.dormancy_threshold(),
        "runtime_path": security_bridge.runtime_path(),
        "integrity": security_bridge.integrity_status(),
        "api": [
            "check_ingress", "check_egress", "enforce_morality", "get_constitution",
            "authorize_training", "begin_training_lease", "commit_training_lease",
            "freeze_training_registry",
            "quarantine_training_payload", "read_training_quarantine",
            "verify_training_ledger",
        ],
    }, indent=2))
    return 0


def cmd_constitution(_: argparse.Namespace) -> int:
    sc = _load_rust()
    fn = getattr(sc, "get_constitution", None) or getattr(sc, "constitution")
    print(json.dumps(fn(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="security_main", description="Viv Rust security layer CLI")
    p.add_argument("--version", action="version", version=f"security_main {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    cin = sub.add_parser("check-in", help="Security IN — first line of defense")
    cin.add_argument("text", nargs="+")
    cin.add_argument("--s-n", type=float, default=None)
    cin.set_defaults(func=cmd_check_in)

    cout = sub.add_parser("check-out", help="Security OUT — last line of defense")
    cout.add_argument("text", nargs="+")
    cout.add_argument("--s-n", type=float, default=None)
    cout.set_defaults(func=cmd_check_out)

    en = sub.add_parser("enforce", help="Rust law enforcement for tool actions")
    en.add_argument("tool")
    en.add_argument("--params", default="{}")
    en.add_argument("--s-n", type=float, default=None)
    en.add_argument("--forensic", default="")
    en.set_defaults(func=cmd_enforce)

    sub.add_parser("status", help="Show security_core module status").set_defaults(func=cmd_status)
    sub.add_parser("constitution", help="Print 3 Primes + 8 Laws").set_defaults(func=cmd_constitution)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
