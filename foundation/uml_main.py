#!/usr/bin/env python3
"""
Viv foundation — UML main (Intellexi).

Symbolic language and calculator pillar — part of the CPU core.
Does NOT own voice rendering, emotion selection, .gguf loading, or GPU inference.
Those belong to GPU/Voice and Training layers above the three mains.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.paths import FOUNDATION_ROOT  # noqa: E402
from lib.train_corpus import build_corpus  # noqa: E402
from lib.uml_engine import (  # noqa: E402
    SYMBOLS,
    dual_eval,
    evaluate,
    fmt,
    from_b52,
    repl,
    run_demo,
    run_demo2,
    run_examples,
    to_b52,
    to_std,
    to_uml,
    trace_steps,
    verify,
    decode_word,
    encode_word,
    word_encoding_options,
)
from lib.triad_kernel import TRIAD_CONTRACT_VERSION
from lib.uml_character_tokenizer import (  # noqa: E402
    TOKEN_ID_BASE as UML_CHARACTER_TOKEN_ID_BASE,
    TOKEN_UNIT as UML_CHARACTER_TOKEN_UNIT,
    VOCAB_MODE as UML_CHARACTER_VOCAB_MODE,
    VOCAB_SHA256 as UML_CHARACTER_VOCAB_SHA256,
    VOCAB_SIZE as UML_CHARACTER_VOCAB_SIZE,
    decode as decode_uml_characters,
    encode as encode_uml_characters,
    structure as uml_character_structure,
)

VERSION = "1.1.0"
DEFAULT_CORPUS = FOUNDATION_ROOT / "artifacts" / "uml" / "corpus.jsonl"


def _stable_json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def triad_descriptor() -> dict:
    """Stable Intellexi structural contract consumed by the Triad kernel."""
    return {
        "pillar": "uml",
        "name": "Intellexi",
        "version": VERSION,
        "triad_contract_version": TRIAD_CONTRACT_VERSION,
        "capabilities": ["validate_envelope", "validate_operation", "validate_result"],
        "authority": "structure_not_security",
    }


def triad_validate_envelope(envelope: dict) -> dict:
    required = {
        "trace_id",
        "actor",
        "source",
        "target",
        "action",
        "payload",
        "payload_sha256",
        "s_n",
        "contract_version",
        "created_at",
    }
    missing = sorted(required - set(envelope))
    actual_hash = hashlib.sha256(
        _stable_json(envelope.get("payload")).encode("utf-8")
    ).hexdigest()
    allowed = (
        not missing
        and envelope.get("contract_version") == TRIAD_CONTRACT_VERSION
        and envelope.get("payload_sha256") == actual_hash
    )
    return {
        "allowed": allowed,
        "reason": "envelope_structurally_valid" if allowed else "malformed_envelope",
        "missing": missing,
        "payload_hash_match": envelope.get("payload_sha256") == actual_hash,
    }


def triad_validate_operation(*, operation: str, params: dict, context: dict) -> dict:
    serializable = True
    try:
        _stable_json(params)
    except (TypeError, ValueError):
        serializable = False
    allowed = (
        bool(str(operation).strip())
        and isinstance(params, dict)
        and serializable
        and bool((context.get("security_ingress") or {}).get("allowed"))
    )
    return {
        "allowed": allowed,
        "reason": "operation_structurally_valid" if allowed else "malformed_operation",
        "operation": str(operation),
    }


def triad_validate_result(*, result, context: dict) -> dict:
    del context
    try:
        encoded = _stable_json(result)
        allowed = bool(encoded) and len(encoded.encode("utf-8")) <= 8 * 1024 * 1024
    except (TypeError, ValueError):
        allowed = False
    return {
        "allowed": allowed,
        "reason": "result_structurally_valid" if allowed else "malformed_result",
    }


def _expr(args: argparse.Namespace) -> str:
    return " ".join(args.expr)


def cmd_eval(args: argparse.Namespace) -> int:
    expr = _expr(args)
    try:
        result, node, nota, _ = evaluate(expr)
        alt = to_std(node) if nota == "uml" else to_uml(node)
        print(fmt(result))
        if args.verbose:
            print(f"[{nota.upper()}] alt: {alt}")
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    ok, report = verify(_expr(args))
    if args.json:
        print(json.dumps({"ok": ok, "report": report}, indent=2))
    else:
        print(f"{'PASS' if ok else 'FAIL'}: {report}")
    return 0 if ok else 1


def cmd_trace(args: argparse.Namespace) -> int:
    expr = _expr(args)
    try:
        result, node, nota, trace = evaluate(expr)
        render = to_uml if nota == "uml" else to_std
        rows = trace if trace else trace_steps(node, render)
        print(f"result: {fmt(result)}")
        for depth, sub, val in rows:
            print(f"  d={depth}  {sub}  =>  {fmt(val)}")
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    expr = _expr(args)
    try:
        _, node, nota, _ = evaluate(expr)
        uml = to_uml(node)
        std = to_std(node)
        if args.json:
            print(json.dumps({"detected": nota, "uml": uml, "standard": std}, indent=2))
        else:
            print(f"detected: {nota}")
            print(f"UML:      {uml}")
            print(f"standard: {std}")
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


def cmd_b52(args: argparse.Namespace) -> int:
    text = _expr(args)
    try:
        if args.decode:
            val = from_b52(text)
            print(val)
        else:
            val = int(text)
            print(to_b52(val))
            if args.verbose:
                print(f"decimal: {val}")
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


def cmd_word(args: argparse.Namespace) -> int:
    text = str(args.word)
    try:
        if args.decode:
            out = {"word": decode_word(text), "packed": text}
        elif args.json:
            out = {"word": text, "options": word_encoding_options(text)}
        else:
            out = {"word": text, "uml": encode_word(text, mode=args.mode)}
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json or args.decode else out["uml"])
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


def cmd_tokenize(args: argparse.Namespace) -> int:
    """Encode text with the CPU UML single-character vocabulary."""
    try:
        encoded = uml_character_structure(args.text)
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(encoded, ensure_ascii=False, indent=2))
    else:
        print(" ".join(str(token_id) for token_id in encoded["token_ids"]))
    return 0


def cmd_detokenize(args: argparse.Namespace) -> int:
    """Decode CPU UML single-character token IDs back into text."""
    try:
        text = decode_uml_characters(args.token_ids)
    except Exception as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps(
                {
                    "token_ids": args.token_ids,
                    "text": text,
                    "vocab_mode": UML_CHARACTER_VOCAB_MODE,
                    "vocab_size": UML_CHARACTER_VOCAB_SIZE,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(text)
    return 0


def cmd_tokenizer_vocab(args: argparse.Namespace) -> int:
    """Print the complete CPU Universal UML vocabulary metadata."""
    del args
    print(
        json.dumps(
            {
                "vocab_mode": UML_CHARACTER_VOCAB_MODE,
                "token_unit": UML_CHARACTER_TOKEN_UNIT,
                "vocab_size": UML_CHARACTER_VOCAB_SIZE,
                "token_id_base": UML_CHARACTER_TOKEN_ID_BASE,
                "unicode_scalar_range": "U+0000..U+10FFFF",
                "surrogate_range_excluded": "U+D800..U+DFFF",
                "vocab_sha256": UML_CHARACTER_VOCAB_SHA256,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_dual_eval(args: argparse.Namespace) -> int:
    if len(args.expr) < 2:
        print("usage: uml_main dual-eval <uml-expr> -- <std-expr>", file=sys.stderr)
        return 2
    if "--" in args.expr:
        idx = args.expr.index("--")
        uml_s = " ".join(args.expr[:idx])
        std_s = " ".join(args.expr[idx + 1 :])
    else:
        uml_s = args.expr[0]
        std_s = " ".join(args.expr[1:])
    out = dual_eval(uml_s, std_s)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(out.get("report", ""))
        if out.get("agree"):
            print(f"UML: {fmt(out.get('uml_val'))}")
        else:
            if "uml_val" in out:
                print(f"UML: {fmt(out['uml_val'])}")
            if "std_val" in out:
                print(f"STD: {fmt(out['std_val'])}")
    return 0 if out.get("agree") else 1


def cmd_corpus(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else DEFAULT_CORPUS
    counts = build_corpus(out, include_wiki=args.include_wiki, max_slm_logs=args.max_slm_logs)
    if args.json:
        print(json.dumps({"out": str(out), "counts": counts}, indent=2))
    else:
        print(f"wrote {out}")
        for k, v in counts.items():
            print(f"  {k}: {v}")
    return 0


def cmd_repl(_: argparse.Namespace) -> int:
    repl()
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    if args.mode == "hardware":
        run_demo2()
    else:
        run_demo()
    return 0


def cmd_symbols(_: argparse.Namespace) -> int:
    print(SYMBOLS)
    return 0


def cmd_examples(_: argparse.Namespace) -> int:
    run_examples()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="uml_main",
        description="Viv UML foundation — Universal Mathematical/Machine Language (Intellexi).",
    )
    p.add_argument("--version", action="version", version=f"uml_main {VERSION}")
    sub = p.add_subparsers(dest="command")

    ev = sub.add_parser("eval", help="Evaluate one expression")
    ev.add_argument("expr", nargs="+", help="UML or standard math expression")
    ev.add_argument("-v", "--verbose", action="store_true")
    ev.set_defaults(func=cmd_eval)

    vf = sub.add_parser("verify", help="Triple-leg verify (eval + UML render + STD render)")
    vf.add_argument("expr", nargs="+")
    vf.add_argument("--json", action="store_true")
    vf.set_defaults(func=cmd_verify)

    tr = sub.add_parser("trace", help="Step-by-step depth trace")
    tr.add_argument("expr", nargs="+")
    tr.set_defaults(func=cmd_trace)

    cv = sub.add_parser("convert", help="Show UML and standard forms side by side")
    cv.add_argument("expr", nargs="+")
    cv.add_argument("--json", action="store_true")
    cv.set_defaults(func=cmd_convert)

    b5 = sub.add_parser("b52", help="Decimal to base-52 (or --decode)")
    b5.add_argument("expr", nargs="+", help="Integer or base-52 string with --decode")
    b5.add_argument("--decode", action="store_true")
    b5.add_argument("-v", "--verbose", action="store_true")
    b5.set_defaults(func=cmd_b52)

    wd = sub.add_parser("word", help="Encode/decode a base-52 word token")
    wd.add_argument("word")
    wd.add_argument("--mode", choices=("packed", "sum"), default="packed")
    wd.add_argument("--decode", action="store_true")
    wd.add_argument("--json", action="store_true")
    wd.set_defaults(func=cmd_word)

    tk = sub.add_parser("tokenize", help="Encode text with the CPU UML character vocabulary")
    tk.add_argument("text")
    tk.add_argument("--json", action="store_true")
    tk.set_defaults(func=cmd_tokenize)

    dt = sub.add_parser("detokenize", help="Decode CPU UML character token IDs")
    dt.add_argument("token_ids", nargs="+", type=int)
    dt.add_argument("--json", action="store_true")
    dt.set_defaults(func=cmd_detokenize)

    sub.add_parser("tokenizer-vocab", help="Print the CPU UML character vocabulary").set_defaults(
        func=cmd_tokenizer_vocab
    )

    de = sub.add_parser("dual-eval", help="Parallel UML vs standard engine comparison")
    de.add_argument("expr", nargs="+", help='UML expr -- STD expr (use "--" separator)')
    de.add_argument("--json", action="store_true")
    de.set_defaults(func=cmd_dual_eval)

    cp = sub.add_parser("corpus", help="Build JSONL corpus for Training layer (not runtime voice)")
    cp.add_argument("--out", default="", help=f"Default: {DEFAULT_CORPUS}")
    cp.add_argument("--include-wiki", action="store_true")
    cp.add_argument("--max-slm-logs", type=int, default=500)
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=cmd_corpus)

    sub.add_parser("repl", help="Interactive calculator menu").set_defaults(func=cmd_repl)

    dm = sub.add_parser("demo", help="Guided or hardware-random demo")
    dm.add_argument(
        "--mode",
        choices=("guided", "hardware"),
        default="guided",
        help="guided = operator tour; hardware = live device samples",
    )
    dm.set_defaults(func=cmd_demo)

    sub.add_parser("symbols", help="Print symbol table").set_defaults(func=cmd_symbols)
    sub.add_parser("examples", help="Run built-in examples").set_defaults(func=cmd_examples)

    p.add_argument("expr_default", nargs="*", help=argparse.SUPPRESS)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    known = (
        "eval", "verify", "trace", "convert", "b52", "dual-eval", "corpus",
        "repl", "demo", "symbols", "examples", "word", "tokenize", "detokenize",
        "tokenizer-vocab", "-h", "--help", "--version",
    )
    if argv and argv[0] not in known:
        argv = ["eval", *argv]
    args = parser.parse_args(argv)
    if args.command is None:
        if args.expr_default:
            args.expr = args.expr_default
            args.verbose = False
            return cmd_eval(args)
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
