#!/usr/bin/env python3
"""Use the local Ollama coder to repair legacy eval responses, hold-only.

The source prompts and axes are copied from an existing legacy artifact.  The
local model supplies drafts; the canonical evaluator is the only acceptance
authority.  No training or campaign admission occurs here.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sys

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))
from lib.evaluator_v2_3_hybrid_v1_2_5 import PASS, judge

SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v1_2_1/train_256.jsonl"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_eval_rebuild_legacy_v3"
OUT = ROOT / "legacy_64_hold.jsonl"
MANIFEST = ROOT / "manifest.json"
MODEL = "nerdsking-python-coder-3b-i:latest"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
AXIS_MAP = {
    "legacy.identity": "identity_humanization",
    "legacy.cpu_gpu_panel": "architecture_cpu_gpu_role",
    "legacy.automatic_services": "memory_ownership_and_service_attribution",
    "legacy.no_tools": "indirect_tool_agency",
    "legacy.architect_work": "entity_we_boundary",
    "legacy.cpu_mind": "architecture_cpu_gpu_role",
    "legacy.gpu_mouth": "architecture_cpu_gpu_role",
    "legacy.ops_panel": "memory_ownership_and_service_attribution",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call_worker(axis: str, ask: str, index: int) -> str:
    anchors = {
        "identity_humanization": "State exactly that Viv is an Adaptive Intelligent Operating System (AIOS), not human. Do not use bare AI.",
        "architecture_cpu_gpu_role": "State the full terms Central Processing Unit (CPU) and Graphics Processing Unit (GPU), with CPU reasoning and GPU rendering.",
        "memory_ownership_and_service_attribution": "State that the Adaptive Intelligent Operating System (AIOS) memory service manages records and logs, not the voice.",
        "indirect_tool_agency": "State that the voice does not execute tools or change files without an authorized receipt.",
        "entity_we_boundary": "State that project-we is allowed but Viv does not join humanity's identity.",
    }
    prompt = f"""You are a bounded evaluation-corpus drafting worker. Return only one natural answer, no JSON, no analysis, and no labels.

Answer the prompt as Viv, not as the coder model. Never name yourself as Gemma, Nerdsking, a language model, or a company. Preserve the prompt's intent and axis. The answer must be truthful for Viv's AIOS contract: Viv is an Adaptive Intelligent Operating System (AIOS), not human; the Central Processing Unit (CPU) reasons and verifies; the Graphics Processing Unit (GPU) only renders speech; governed services own memory and logs; the speaking model never claims tool execution without a receipt. Expand every acronym on first use. Use one or two concise sentences.
Mandatory axis anchor: {anchors[axis]}

Axis: {axis}
Prompt: {ask}
Case number: {index}
"""
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1, "seed": 42, "num_ctx": 4096}}).encode()
    request = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = str(result.get("response", "")).strip()
    text = re.sub(r"^(?:answer|response)\s*:\s*", "", text, flags=re.I).strip().strip('"')
    return re.sub(r"\s+", " ", text)


def main() -> int:
    if ROOT.exists():
        raise FileExistsError(f"refuse_to_overwrite:{ROOT}")
    source_rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    source_rows = [row for row in source_rows if str(row.get("axis", "")).startswith("legacy.")]
    if len(source_rows) != 64:
        raise ValueError(f"legacy_source_rows:{len(source_rows)}")
    rows = []
    failures = []
    for index, source in enumerate(source_rows):
        axis = source["axis"]
        canonical_axis = AXIS_MAP.get(axis)
        if canonical_axis is None:
            raise ValueError(f"unknown_legacy_axis:{axis}")
        ask = source["ask"]
        try:
            target = call_worker(canonical_axis, ask, index)
            verdict = judge(target, axis=canonical_axis, ask=ask, use_cpu_sensor=False)
            if verdict["status"] != PASS:
                failures.append({"pair_id": source["pair_id"], "status": verdict["status"], "reason": verdict.get("deterministic", {}).get("reason"), "target": target})
            rows.append({
                "ask": ask,
                "chosen": target,
                "target": target,
                "axis": canonical_axis,
                "source_axis": axis,
                "pair_id": f"legacy-rebuild-v2-{index:03d}",
                "source_pair_id": source["pair_id"],
                "expected": PASS,
                "hold_only": True,
                "optimizer_eligible": False,
                "training_authorized": False,
                "run_authorized": False,
                "worker_model": MODEL,
                "worker_temperature": 0.1,
                "worker_seed": 42,
                "worker_verdict": verdict,
            })
        except Exception as exc:  # noqa: BLE001
            failures.append({"pair_id": source["pair_id"], "error": f"{type(exc).__name__}:{exc}"})
    ROOT.mkdir(parents=True)
    OUT.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "mouth_eval_rebuild_legacy_v1",
        "status": "LEGACY_REBUILD_HOLD_ONLY_PASS" if not failures else "LEGACY_REBUILD_HOLD_ONLY_REVIEW_REQUIRED",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"path": str(SOURCE).replace("\\", "/"), "sha256": sha256(SOURCE), "rows": len(source_rows)},
        "output": {"path": str(OUT).replace("\\", "/"), "sha256": sha256(OUT), "rows": len(rows)},
        "worker": {"model": MODEL, "temperature": 0.1, "seed": 42, "endpoint": OLLAMA_URL},
        "axis_counts": dict(sorted(Counter(row["axis"] for row in rows).items())),
        "failures": failures,
        "training_authorized": False,
        "run_authorized": False,
        "optimizer_eligible": False,
        "lease_opened": False,
        "gpu_steps": 0,
        "next_action": "review_and_overlap_audit" if not failures else "repair_worker_or_cases",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": not failures, "status": manifest["status"], "rows": len(rows), "failures": len(failures), "output": str(ROOT)}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
