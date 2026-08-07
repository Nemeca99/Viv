#!/usr/bin/env python3
"""Emergence audit: run probes, let gaps rank what the system needs next.

Does not invent priorities from narrative alone — each need is tied to a
failing/incomplete probe with evidence.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

RECEIPT = SANDBOX / "runs" / "uml_emergence_audit_latest.json"
SELFTEST = SANDBOX / "test_uml_training_thesis.py"
SELFTEST_RECEIPT = SANDBOX / "runs" / "uml_training_thesis_selftest_latest.json"


def _probe_selftest() -> dict[str, Any]:
    proc = subprocess.run(
        [str(PY), "-B", str(SELFTEST)],
        cwd=str(SANDBOX),
        capture_output=True,
        text=True,
    )
    payload = {}
    if SELFTEST_RECEIPT.is_file():
        payload = json.loads(SELFTEST_RECEIPT.read_text(encoding="utf-8"))
    return {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-500:],
        "contract": payload.get("contract_status"),
        "ladder": payload.get("ladder_status"),
        "failures": payload.get("failures") or [],
        "ladder_gaps": payload.get("ladder_gaps") or [],
    }


def _probe_native_speak_wired() -> dict[str, Any]:
    """Does a native UML speak path exist that builds math-token prompts?"""
    from uml_codec_io import build_native_uml_prompt, is_math_token_surface

    native = build_native_uml_prompt("Hi")
    native_mod = MODEL / "speak_uml_native.py"
    present = native_mod.is_file()
    uses_builder = False
    if present:
        text = native_mod.read_text(encoding="utf-8")
        uses_builder = "build_native_uml_prompt" in text and "speak_uml_native" in text
    # Live roundtrip smoke (no LM): encode/decode only proves shell; LM probe separate.
    return {
        "status": "PASS" if present and uses_builder and native["is_math_surface"] else "GAP",
        "speak_uml_native_present": present,
        "uses_build_native_uml_prompt": uses_builder,
        "native_prompt_sample": native["model_prompt"],
        "native_is_math": is_math_token_surface(native["encode"]["uml_stream"]),
        "need": None
        if present and uses_builder
        else "Wire speak path to build_native_uml_prompt so the plant sees UML tokens, not English.",
    }


def _probe_snap_free_cheap() -> dict[str, Any]:
    """Without prefer_efficient_snap, does LM already emit cheapest?"""
    try:
        import torch
        from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry
        from lib.uml_route_governor import route_efficiency_error
        from plant_checkpoint import load_plant_state_dict
        from plant_runtime import configure_plant_runtime
        from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset
        from sandbox_paths import EFFICIENT_CKPT
        from speak_lanes import speak_viv_sandwich
        from tokenizer import CharacterTokenizer
        from transformer import TransformerLanguageModel
        from uml_speak_pressure import clip_uml_equation_text
    except Exception as exc:
        return {"status": "SKIP", "error": repr(exc)}

    runs = SANDBOX / "runs"
    ckpt = runs / "uml_equation_ab_v2_g_boost2" / "pilot_uml_mix_masked.pt"
    if not ckpt.is_file():
        ckpt = runs / "uml_equation_ab_v2" / "pilot_uml_mix_masked.pt"
    if not ckpt.is_file():
        return {"status": "SKIP", "reason": "missing_ckpt"}

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    configure_plant_runtime(device=str(device))

    def _load(path: Path, dev: torch.device):
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model = TransformerLanguageModel(tok.vocab_size, **IDENTITY_MODEL_CFG).to(dev)
        load_plant_state_dict(
            model,
            payload["model_state_dict"],
            strict=False,
            config=dict(payload.get("config") or IDENTITY_MODEL_CFG),
        )
        model.eval()
        return model

    model_e = _load(EFFICIENT_CKPT, torch.device("cpu"))
    model_d = _load(ckpt, device)
    # Measure raw deep equation before snap by reading deep text + clip.
    chars = list("HAV")
    cheap_raw = 0
    match_raw = 0
    rows = []
    for ch in chars:
        prompt = f"User: Prefer efficient UML for {ch}\nViv: "
        ids = torch.tensor([tok.encode(prompt)], dtype=torch.long)
        sandwich = speak_viv_sandwich(
            model_e,
            model_d,
            ids,
            deep_max=24,
            verify_max=16,
            decode_fn=tok.decode,
            uml_pressure={
                "stoi": tok.stoi,
                "itos": tok.itos,
                "prompt_len": int(ids.shape[1]),
                "hard_mask": True,
                "scale": 6.0,
            },
            uml_pressure_on="deep",
            stamp_master_rid=False,
        )
        # Proposed before snap (if recorded).
        snap = sandwich["receipt"].get("prefer_efficient_snap") or {}
        proposed = str(snap.get("proposed") or sandwich.get("equation_text") or "")
        final = str(sandwich.get("equation_text") or "")
        deep_text = sandwich.get("deep", {}).get("text") or ""
        raw_clip = clip_uml_equation_text(str(deep_text), prompt)
        use = proposed or raw_clip
        try:
            match = reg.decode_eq(use) == ch
        except Exception:
            match = False
        info = route_efficiency_error(reg, proposed=use if use else "???", target_char=ch)
        if match:
            match_raw += 1
        if info.get("kind") == "valid_efficient":
            cheap_raw += 1
        rows.append(
            {
                "char": ch,
                "raw": use,
                "final": final,
                "raw_kind": info.get("kind"),
                "snapped": bool(snap.get("snapped")),
                "match_raw": match,
            }
        )
    n = len(chars)
    cheap_rate = cheap_raw / n
    status = "PASS" if cheap_rate >= 0.5 else "GAP"
    return {
        "status": status,
        "n": n,
        "match_raw_rate": match_raw / n,
        "cheap_raw_rate": cheap_rate,
        "rows": rows,
        "need": None
        if status == "PASS"
        else (
            "LM does not internally prefer cheapest under Prefer-efficient; "
            "needs UML-native math-token training and/or stronger route pressure "
            "(snap currently compensates)."
        ),
    }


def _probe_domain_experts_exist() -> dict[str, Any]:
    root = SANDBOX / "checkpoints"
    expected = ["addition", "subtraction", "multiplication", "division"]
    found = {}
    for name in expected:
        paths = list(root.rglob(f"*{name}*")) if root.is_dir() else []
        found[name] = [str(p).replace("\\", "/") for p in paths[:3]]
    any_found = any(found[k] for k in expected)
    return {
        "status": "PASS" if any_found else "GAP",
        "found": found,
        "need": None
        if any_found
        else "Four monolithic domain experts (A/S/M/D) are not present as checkpoints — lattice generators need training surfaces + specialist stubs.",
    }


def _probe_v6_bank() -> dict[str, Any]:
    build = SANDBOX / "data" / "uml_equation_mix_v1" / "BUILD.json"
    if not build.is_file():
        return {"status": "GAP", "need": "Missing UML mix BUILD.json"}
    meta = json.loads(build.read_text(encoding="utf-8"))
    ver = str(meta.get("bank_version") or "")
    ok = ver == "v6_federation"
    # Check if any A/B receipt used v6
    ab = SANDBOX / "runs" / "uml_equation_ab_v2_latest.json"
    ab_ver = None
    if ab.is_file():
        ab_ver = json.loads(ab.read_text(encoding="utf-8")).get("bank_version")
    trained_on_v6 = ab_ver == "v6_federation"
    status = "PASS" if ok and trained_on_v6 else ("PARTIAL" if ok else "GAP")
    need = None
    if not ok:
        need = "Rebuild mix bank to v6_federation"
    elif not trained_on_v6:
        need = "Run matched UML A/B on v6_federation bank (current pilots still on older bank)."
    return {
        "status": status,
        "bank_version": ver,
        "last_ab_bank": ab_ver,
        "need": need,
    }


def _probe_structure_binding_coverage() -> dict[str, Any]:
    from uml_structure_binding import BindingEnv, evaluate_with_bindings

    cases = [
        ("?A + ?A", "unbound_structure"),
        ("1+1", "grounded"),
        ("?A * ?B", "unbound_incomplete"),
    ]
    env = BindingEnv()
    env.bind("?A", 1)
    rows = []
    for expr, want in cases:
        got = evaluate_with_bindings(expr)
        rows.append({"expr": expr, "want": want, "got": got["kind"], "ok": got["kind"] == want})
    bound = evaluate_with_bindings("?A + ?A", env)
    rows.append(
        {
            "expr": "?A+?A bound",
            "want": "bound_grounded",
            "got": bound["kind"],
            "ok": bound["kind"] == "bound_grounded" and float(bound["numeric_value"]) == 2.0,
        }
    )
    ok = all(r["ok"] for r in rows)
    return {
        "status": "PASS" if ok else "FAIL",
        "rows": rows,
        "need": None if ok else "Expand structure-binding rules beyond identical addends.",
    }


def main() -> int:
    probes = {
        "P0_selftest": _probe_selftest(),
        "P1_native_speak_wired": _probe_native_speak_wired(),
        "P2_snap_free_cheap": _probe_snap_free_cheap(),
        "P3_domain_experts": _probe_domain_experts_exist(),
        "P4_v6_bank_training": _probe_v6_bank(),
        "P5_structure_binding": _probe_structure_binding_coverage(),
    }

    needs: list[dict[str, Any]] = []
    for name, probe in probes.items():
        need = probe.get("need")
        st = probe.get("status")
        if need and st in {"GAP", "PARTIAL", "FAIL"}:
            severity = {"FAIL": 0, "GAP": 1, "PARTIAL": 2}.get(str(st), 3)
            needs.append({"probe": name, "severity": severity, "status": st, "need": need})
    needs.sort(key=lambda r: (r["severity"], r["probe"]))

    # Emergent statement: what the system is asking for.
    top = needs[0] if needs else None
    receipt = {
        "schema_version": "uml_emergence_audit_v1",
        "status": "PASS" if probes["P0_selftest"]["status"] == "PASS" else "FAIL",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "method": "hypothesis_probe_rank_needs",
        "probes": probes,
        "emergent_needs_ranked": needs,
        "system_says": (
            top["need"]
            if top
            else "No blocking gaps in this probe set — expand lattice/expert training next by operator choice."
        ),
        "recommended_next": top,
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"UML_EMERGENCE_{receipt['status']}", flush=True)
    print(f"SYSTEM_SAYS: {receipt['system_says']}", flush=True)
    for i, n in enumerate(needs[:5], 1):
        print(f"  NEED[{i}] ({n['status']}) {n['probe']}: {n['need']}", flush=True)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
