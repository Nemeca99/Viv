#!/usr/bin/env python3
"""Read-only static review of local-coder draft artifacts."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RISK_PATTERNS = {
    "process_execution": r"\b(?:subprocess|os\.system|shell\s*=|Popen|run\s*\()",
    "filesystem_mutation": r"\b(?:write_text|write_bytes|unlink|rmtree|remove|replace)\s*\(|open\s*\([^\n]+['\"](?:w|a|x|wb|ab)",
    "dynamic_execution": r"\b(?:eval|exec|compile)\s*\(",
    "network_access": r"\b(?:urllib|requests|socket|httpx|aiohttp)\b",
    "privileged_training": r"\b(?:begin_run_lease|optimizer\.step|authorize_training|deploy|promotion)\b",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def extract_python(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.I | re.S)
    return "\n\n".join(blocks) if blocks else text


def review_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    source = extract_python(raw)
    risks = sorted(name for name, pattern in RISK_PATTERNS.items() if re.search(pattern, source, flags=re.I))
    syntax_error = None
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        syntax_error = f"line={exc.lineno};offset={exc.offset};msg={exc.msg}"
    return {"path": str(path).replace("\\", "/"), "sha256": digest(path), "bytes": len(raw.encode("utf-8")), "python_source_bytes": len(source.encode("utf-8")), "syntax_pass": syntax_error is None, "syntax_error": syntax_error, "risk_findings": risks, "semantic_review_required": True, "integration_decision": "HOLD_FOR_FOREMAN_REVIEW" if syntax_error or risks else "STATIC_REVIEW_PASS_NOT_INTEGRATED"}


def review_root(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"draft_root_missing:{root}")
    drafts = sorted(root.glob("*.txt"))
    cases = [review_file(path) for path in drafts]
    return {"schema_version": "local_coder_draft_review_v1", "status": "DRAFT_REVIEW_COMPLETE", "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "root": str(root).replace("\\", "/"), "drafts": cases, "draft_count": len(cases), "syntax_failures": sum(not case["syntax_pass"] for case in cases), "risk_cases": sum(bool(case["risk_findings"]) for case in cases), "semantic_review_required": True, "integration_allowed": False, "execution_performed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Review local coder drafts without executing them")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = review_root(args.root)
    report_path = args.report or (args.root / "DRAFT_REVIEW.json")
    if report_path.exists():
        raise FileExistsError(f"refuse_to_overwrite:{report_path}")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "status": report["status"], "drafts": report["draft_count"], "syntax_failures": report["syntax_failures"], "risk_cases": report["risk_cases"], "integration_allowed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
