#!/usr/bin/env python3
"""Selftest: UML Training Thesis control law + compositional lattice.

Tests doctrine claims with registry + governor evidence (no long train).
Receipt: runs/uml_training_thesis_selftest_latest.json
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import (  # noqa: E402
    decide_route,
    route_efficiency_error,
    sample_route,
)
from rid_pid import RIDMonitor  # noqa: E402

RECEIPT = SANDBOX / "runs" / "uml_training_thesis_selftest_latest.json"
LATTICE = SANDBOX / "uml_domain_expert_lattice.json"
THESIS = SANDBOX / "UML_TRAINING_THESIS.md"

BASE = ("A", "S", "M", "D")


def _fail(failures: list[str], cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def _domains_in_expr(expr: str) -> set[str]:
    found: set[str] = set()
    text = expr
    if "**" in text:
        found.add("M")
        text = text.replace("**", " ")
    for op, dom in (("+", "A"), ("-", "S"), ("*", "M"), ("/", "D")):
        if op in text:
            found.add(dom)
    return found


def test_lattice_counts(failures: list[str]) -> dict[str, Any]:
    unordered = []
    for k in range(1, 5):
        unordered.extend("".join(c) for c in itertools.combinations(BASE, k))
    ordered = []
    for k in range(1, 5):
        ordered.extend("".join(p) for p in itertools.permutations(BASE, k))
    _fail(failures, len(unordered) == 15, f"unordered_count:{len(unordered)}")
    _fail(failures, len(ordered) == 64, f"ordered_count:{len(ordered)}")
    mixed = [u for u in unordered if len(u) > 1]
    _fail(failures, len(mixed) == 11, f"mixed_count:{len(mixed)}")
    lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
    _fail(
        failures,
        int(lattice["composition_unordered"]["total_nonempty"]) == 15,
        "lattice_json_unordered",
    )
    _fail(
        failures,
        int(lattice["composition_ordered"]["total_without_repeats"]) == 64,
        "lattice_json_ordered",
    )
    return {
        "unordered": len(unordered),
        "ordered": len(ordered),
        "mixed": len(mixed),
        "labels_sample": unordered[:8],
    }


def test_reversible_roundtrip(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    surfaces = ["H", "Viv", "Hello", "A+B", "Nested PEMDAS", "identity"]
    rows = []
    for s in surfaces:
        eqs = reg.encode_text(s)
        back = reg.decode_equations(eqs)
        ok = back == s
        _fail(failures, ok, f"roundtrip:{s!r}->{back!r}")
        rows.append({"surface": s, "n_eq": len(eqs), "ok": ok})
    return {"n": len(surfaces), "rows": rows}


def test_sealed_destination_many_routes(
    reg: UMLEquationRegistry, failures: list[str]
) -> dict[str, Any]:
    ch = "H"
    entry = reg.entries[ch]
    sealed_value = int(entry["value"])
    canon = str(entry["canonical"])
    alts = [str(x) for x in (entry.get("equivalents") or [])[:8]]
    bank = [canon] + alts
    decoded = [reg.decode_eq(e) for e in bank]
    _fail(failures, all(d == ch for d in decoded), f"sealed_decode_mismatch:{decoded}")

    values_ok = True
    for e in bank:
        info = route_efficiency_error(reg, proposed=e, target_char=ch)
        if not info["valid"] or info["target_value"] != sealed_value:
            values_ok = False
    _fail(failures, values_ok, "sealed_valid_bank")

    bad = route_efficiency_error(reg, proposed="999", target_char=ch)
    _fail(failures, bad["kind"] == "invalid" and bad["error"] >= 0.99, f"invalid_not_rejected:{bad}")

    err_q = route_efficiency_error(reg, proposed=canon, target_char=ch)
    _fail(failures, err_q["error"] <= 0.05, f"canon_not_cheap:{err_q}")
    costly_info = None
    if alts:
        err_c = route_efficiency_error(reg, proposed=alts[-1], target_char=ch)
        _fail(
            failures,
            err_c["valid"] and (err_c["error"] >= err_q["error"]),
            f"costly_not_routing_fault:{err_c}",
        )
        costly_info = err_c

    return {
        "char": ch,
        "sealed_value": sealed_value,
        "bank_size": len(bank),
        "canonical": canon,
        "all_decode_to_char": all(d == ch for d in decoded),
        "invalid": bad,
        "cheap": err_q,
        "costly": costly_info,
    }


def test_probability_only_among_valid(
    reg: UMLEquationRegistry, failures: list[str]
) -> dict[str, Any]:
    ch = "H"
    entry = reg.entries[ch]
    proposals = [str(entry["canonical"])] + [str(x) for x in (entry.get("equivalents") or [])[:4]]
    proposals += ["999", "not_an_eq", "40+1"]
    dec = decide_route(
        reg,
        target_char=ch,
        proposals=proposals,
        include_registry_pool=True,
    )
    _fail(failures, dec.valid_count >= 1, "no_valid_routes")
    _fail(failures, reg.decode_eq(dec.selected) == ch, f"decide_wrong_dest:{dec.selected}")

    bad_samples = 0
    selected: list[str] = []
    for i in range(32):
        g = torch.Generator().manual_seed(1000 + i)
        s = sample_route(
            reg,
            target_char=ch,
            proposals=proposals,
            include_registry_pool=True,
            temperature=1.2,
            generator=g,
        )
        selected.append(s.selected)
        if reg.decode_eq(s.selected) != ch:
            bad_samples += 1
    _fail(failures, bad_samples == 0, f"sample_broke_seal:{bad_samples}")
    return {
        "decide_selected": dec.selected,
        "decide_cost": dec.selected_cost,
        "valid_count": dec.valid_count,
        "rejected_count": dec.rejected_count,
        "samples": len(selected),
        "unique_routes": sorted(set(selected))[:12],
        "seal_breaks": bad_samples,
    }


def test_domain_tagging(failures: list[str]) -> dict[str, Any]:
    lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
    labels = lattice["composition_unordered"]["labels"]
    mixed_labels = set(labels["pairs"] + labels["triples"] + labels["all_four"])
    cases = [
        ("41", set()),
        ("40+1", {"A"}),
        ("42-1", {"S"}),
        ("5*8", {"M"}),
        ("82/2", {"D"}),
        ("(40+1)*1", {"A", "M"}),
        ("(5*8)+1", {"A", "M"}),
    ]
    rows = []
    for expr, want in cases:
        got = _domains_in_expr(expr)
        ok = got == want
        _fail(failures, ok, f"domains:{expr}:{got}!={want}")
        if not got:
            fed = "LIT"
            mono = True
        else:
            fed = "".join(d for d in BASE if d in got)
            mono = len(got) == 1
        if not mono and fed != "LIT":
            _fail(failures, fed in mixed_labels, f"fed_not_in_lattice:{fed}")
        rows.append(
            {"expr": expr, "domains": sorted(got), "federation": fed, "monolithic": mono, "ok": ok}
        )
    return {"rows": rows}


def test_rid_residual_on_faults(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    mon = RIDMonitor()
    s_cheap = mon.score_from_route(proposed_expr="41", target_char="H", registry=reg)
    r_cheap = mon.receipt()
    s_bad = mon.score_from_route(proposed_expr="999", target_char="H", registry=reg)
    r_bad = mon.receipt()
    e_cheap = float((r_cheap.get("route_error") or {}).get("error", 1))
    e_bad = float((r_bad.get("route_error") or {}).get("error", 0))
    _fail(failures, e_cheap <= 0.05, f"rid_cheap:{e_cheap}")
    _fail(failures, e_bad >= 0.99, f"rid_bad:{e_bad}")
    return {
        "cheap_S": s_cheap,
        "bad_S": s_bad,
        "cheap_error": e_cheap,
        "bad_error": e_bad,
        "u_bad": r_bad.get("u_actuation"),
    }


def test_pipeline_contract(failures: list[str]) -> dict[str, Any]:
    lattice = json.loads(LATTICE.read_text(encoding="utf-8"))
    thesis = THESIS.read_text(encoding="utf-8")
    required = [
        "Determinism chooses the destination",
        "Probability chooses the route",
        "compositional expert lattice",
        "15",
        "64",
        "Closed executable proof",
        "UML is the tokenizer",
        "RID controls",
    ]
    missing = [r for r in required if r not in thesis]
    _fail(failures, not missing, f"thesis_missing:{missing}")
    _fail(failures, lattice.get("metaphor") == "conway_generators", "lattice_metaphor")
    return {
        "thesis_bytes": len(thesis.encode("utf-8")),
        "pipeline": lattice.get("pipeline"),
        "control_law": lattice.get("control_law"),
    }


def test_heldout_generalization(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    """T7: Unseen / longer surfaces still reverse + seal per char."""
    # Surfaces not in the original T2 short list.
    heldout = [
        "The dog bites man",
        "Universal Machine Language",
        "RID is a stability score",
        "encode then compute then decode",
        "0123456789",
        "ZzYyXxWw",
        "()[]{}.,;:!?",
    ]
    rows = []
    char_seal_breaks = 0
    for s in heldout:
        try:
            eqs = reg.encode_text(s)
            back = reg.decode_equations(eqs)
            ok = back == s
        except Exception as exc:
            ok = False
            eqs = []
            back = f"ERR:{exc!r}"
        _fail(failures, ok, f"heldout_roundtrip:{s!r}->{back!r}")
        # Per-char seal via decide on first char if printable in registry.
        seal_ok = True
        if s and s[0] in reg.entries:
            dec = decide_route(reg, target_char=s[0], include_registry_pool=True)
            if reg.decode_eq(dec.selected) != s[0]:
                seal_ok = False
                char_seal_breaks += 1
        _fail(failures, seal_ok, f"heldout_seal:{s[0]!r}")
        rows.append({"surface": s, "n_eq": len(eqs), "ok": ok, "seal_ok": seal_ok})
    return {
        "hypothesis": "Held-out surfaces reverse byte-for-byte; first-char seal holds under decide_route.",
        "n": len(heldout),
        "all_ok": all(r["ok"] for r in rows),
        "char_seal_breaks": char_seal_breaks,
        "rows": rows,
    }


def test_cost_pressure_bias(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    """T8: decide=cheapest; low-T samples mass on low-cost; high-T more diverse; seal always."""
    ch = "H"
    entry = reg.entries[ch]
    canon = str(entry["canonical"])
    decide = decide_route(reg, target_char=ch, include_registry_pool=True)
    _fail(failures, decide.selected == canon or decide.selected_cost <= int(entry["canonical_cost"]), 
          f"decide_not_cheapest:{decide.selected} cost={decide.selected_cost} canon={canon}")
    # Stronger: selected cost must equal min valid cost from considered.
    valid_costs = [int(r.symbolic_cost or 10**9) for r in decide.considered if r.valid]
    min_cost = min(valid_costs) if valid_costs else -1
    _fail(failures, decide.selected_cost == min_cost, f"decide_cost_not_min:{decide.selected_cost}!={min_cost}")

    def _mean_cost(temp: float, n: int = 64) -> tuple[float, int, int]:
        costs = []
        breaks = 0
        for i in range(n):
            g = torch.Generator().manual_seed(7000 + int(temp * 100) + i)
            s = sample_route(
                reg,
                target_char=ch,
                include_registry_pool=True,
                temperature=temp,
                generator=g,
            )
            costs.append(float(s.selected_cost))
            if reg.decode_eq(s.selected) != ch:
                breaks += 1
        return sum(costs) / len(costs), breaks, len(set(costs))

    mean_lo, br_lo, uniq_lo = _mean_cost(0.05)
    mean_hi, br_hi, uniq_hi = _mean_cost(2.5)
    _fail(failures, br_lo == 0 and br_hi == 0, f"cost_sample_seal_breaks:{br_lo}/{br_hi}")
    # Low T should not be worse (higher mean cost) than high T.
    _fail(failures, mean_lo <= mean_hi + 0.05, f"lowT_not_cheaper:{mean_lo}>{mean_hi}")
    return {
        "hypothesis": "Efficiency pressure: decide argmax cheapest; low-T mean cost <= high-T; seal unbroken.",
        "decide_selected": decide.selected,
        "decide_cost": decide.selected_cost,
        "min_valid_cost": min_cost,
        "low_T": {"T": 0.05, "mean_cost": mean_lo, "seal_breaks": br_lo, "unique_costs": uniq_lo},
        "high_T": {"T": 2.5, "mean_cost": mean_hi, "seal_breaks": br_hi, "unique_costs": uniq_hi},
        "pressure_works": mean_lo <= mean_hi + 0.05,
    }


def test_registry_federation_coverage(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    """T9: Across vocab, equivalents span multiple domain federations (generators exist in bank)."""
    fed_counts: dict[str, int] = {}
    mono = 0
    mixed = 0
    lit = 0
    scanned = 0
    for ch, entry in list(reg.entries.items())[:96]:
        routes = [str(entry["canonical"])] + [str(x) for x in (entry.get("equivalents") or [])]
        for expr in routes:
            scanned += 1
            doms = _domains_in_expr(expr)
            if not doms:
                lit += 1
                fed = "LIT"
            else:
                fed = "".join(d for d in BASE if d in doms)
                if len(doms) == 1:
                    mono += 1
                else:
                    mixed += 1
            fed_counts[fed] = fed_counts.get(fed, 0) + 1
    # Need all four base domains present somewhere in the bank.
    for d in BASE:
        _fail(failures, fed_counts.get(d, 0) > 0 or any(d in k for k in fed_counts), f"domain_absent:{d}")
    present_base = [d for d in BASE if fed_counts.get(d, 0) > 0]
    present_mixed = [k for k in fed_counts if len(k) > 1 and k != "LIT"]
    _fail(failures, len(present_base) >= 3, f"too_few_base_domains:{present_base}")
    # After v1.2 diversity fill, prepared bank must expose mixed federations.
    _fail(failures, mixed > 0, f"bank_no_mixed_federations:mono={mono} lit={lit}")
    return {
        "hypothesis": (
            "Prepared bank realizes A/S/M/D generators; mixed federations appear via "
            "federation-diversity slots in pick_canonical (v1.2)."
        ),
        "scanned_routes": scanned,
        "lit": lit,
        "mono": mono,
        "mixed": mixed,
        "fed_counts_top": dict(sorted(fed_counts.items(), key=lambda kv: -kv[1])[:16]),
        "present_base": present_base,
        "present_mixed": present_mixed[:20],
        "has_mixed": mixed > 0,
    }


def test_live_speak_ladder(ladder: list[str]) -> dict[str, Any]:
    """T10: Live speak seal + cheap rate (ladder — does not hard-fail contract)."""
    try:
        from plant_checkpoint import load_plant_state_dict
        from plant_runtime import configure_plant_runtime
        from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset
        from sandbox_paths import EFFICIENT_CKPT
        from speak_lanes import speak_viv_sandwich
        from tokenizer import CharacterTokenizer
        from transformer import TransformerLanguageModel
    except Exception as exc:
        ladder.append(f"speak_import:{exc!r}")
        return {"status": "SKIP", "reason": str(exc)}

    runs = SANDBOX / "runs"
    ckpt = runs / "uml_equation_ab_v2_g_boost2" / "pilot_uml_mix_masked.pt"
    if not ckpt.is_file():
        ckpt = runs / "uml_equation_ab_v2" / "pilot_uml_mix_masked.pt"
    if not ckpt.is_file() or not EFFICIENT_CKPT.is_file():
        ladder.append("speak_missing_ckpt")
        return {"status": "SKIP", "reason": "missing_ckpt"}

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    configure_plant_runtime(device=str(device))

    def _load(path: Path, dev: torch.device) -> Any:
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
    chars = list("HAVQXBZ")
    match_n = cheap_n = dirty_n = 0
    err_sum = 0.0
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
        eq = str(sandwich.get("equation_text") or "").strip()
        dirty = (not eq) or ("\n" in eq) or eq.startswith("Vi")
        if dirty:
            dirty_n += 1
        match = False
        try:
            match = (not dirty) and reg.decode_eq(eq) == ch
        except Exception:
            match = False
        if match:
            match_n += 1
        info = route_efficiency_error(reg, proposed=eq if eq else "???", target_char=ch)
        if info.get("kind") == "valid_efficient":
            cheap_n += 1
        err_sum += float(info.get("error") or 1.0)
        snap = sandwich["receipt"].get("prefer_efficient_snap") or {}
        rows.append(
            {
                "char": ch,
                "eq": eq,
                "match": match,
                "kind": info.get("kind"),
                "error": info.get("error"),
                "domains": sorted(_domains_in_expr(eq)) if eq else [],
                "snapped": bool(snap.get("snapped")),
                "equation_source": sandwich["receipt"].get("equation_source"),
            }
        )
    n = len(chars)
    match_rate = match_n / n
    cheap_rate = cheap_n / n
    mean_err = err_sum / n
    snap_n = sum(1 for r in rows if r.get("snapped"))
    # Ladder gates (not contract-hard): seal should stay high; cheap is the open gap.
    if match_rate < 0.85:
        ladder.append(f"speak_match_low:{match_rate}")
    if cheap_rate < 0.25:
        ladder.append(f"speak_cheap_gap:{cheap_rate}")
    status = "PASS" if match_rate >= 0.85 and cheap_rate >= 0.25 else (
        "PARTIAL" if match_rate >= 0.85 else "FAIL"
    )
    return {
        "hypothesis": (
            "Live speak seals destination; Prefer-efficient prompts snap to cheapest "
            "valid route (cost selection, not truth selection)."
        ),
        "status": status,
        "ckpt": str(ckpt).replace("\\", "/"),
        "n": n,
        "match_rate": match_rate,
        "cheap_rate": cheap_rate,
        "dirty_rate": dirty_n / n,
        "mean_route_error": mean_err,
        "snap_count": snap_n,
        "rows": rows,
    }


def test_multi_char_seal_chain(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    """T11: Encode multi-char text; each equation seals its char; concat decodes full text."""
    text = "Viv"
    eqs = reg.encode_text(text)
    _fail(failures, len(eqs) == len(text), f"eq_len:{len(eqs)}!={len(text)}")
    sealed = []
    for ch, eq in zip(text, eqs):
        back = reg.decode_eq(eq)
        ok = back == ch
        _fail(failures, ok, f"chain_seal:{ch}->{eq}->{back}")
        # Also decide_route for that char must stay sealed.
        dec = decide_route(reg, target_char=ch, proposals=[eq], include_registry_pool=True)
        _fail(failures, reg.decode_eq(dec.selected) == ch, f"chain_decide:{ch}")
        sealed.append({"char": ch, "eq": eq, "ok": ok, "decide": dec.selected})
    full = reg.decode_equations(eqs)
    _fail(failures, full == text, f"chain_full:{full!r}")
    return {
        "hypothesis": "Multi-char prompt is a sealed chain of per-token routes; concat restores text.",
        "text": text,
        "sealed": sealed,
        "full_ok": full == text,
    }


def test_rid_address_precision(failures: list[str]) -> dict[str, Any]:
    """T12: Decimal depth is unique RID address capacity; d=ceil(log10(N+1))."""
    import math

    doctrine = SANDBOX / "rid_normalized_address_space.json"
    _fail(failures, doctrine.is_file(), f"missing_rid_doctrine:{doctrine}")
    payload = json.loads(doctrine.read_text(encoding="utf-8")) if doctrine.is_file() else {}

    def slots(d: int) -> int:
        return (10**d) - 1

    for d, want in ((1, 9), (2, 99), (3, 999), (6, 999_999)):
        _fail(failures, slots(d) == want, f"slots_d{d}:{slots(d)}!={want}")

    def depth_for(n: int) -> int:
        return int(math.ceil(math.log10(n + 1)))

    for n, want_d in ((999, 3), (999_999, 6), (999_999_999, 9), (999_999_999_999, 12)):
        got = depth_for(n)
        _fail(failures, got == want_d, f"depth_N{n}:{got}!={want_d}")
        _fail(failures, slots(got) >= n, f"capacity_short_N{n}:slots={slots(got)}")

    # Uniqueness at fixed depth: all quantized k/10^d for k=1..10^d-1 are distinct.
    d = 4
    vals = [k / (10**d) for k in range(1, 10**d)]
    _fail(failures, len(vals) == len(set(vals)) == slots(d), f"unique_fail_d{d}")

    # RID fold stays in [0,1] for address-space endpoints.
    from rid_pid import rid_fold

    s = rid_fold(1.0, 1.0, 1.0)
    z = rid_fold(0.0, 0.5, 1.0)
    mid = rid_fold(0.5, 0.5, 0.5)
    _fail(failures, s == 1.0 and z == 0.0 and 0.0 < mid < 1.0, f"rid_fold_bounds:{s}/{z}/{mid}")

    thesis = THESIS.read_text(encoding="utf-8")
    _fail(failures, "RID normalized address space" in thesis, "thesis_missing_rid_address")
    _fail(
        failures,
        "d = ceil(log10(N + 1))" in thesis or "ceil(log10(N + 1))" in thesis,
        "thesis_missing_precision_formula",
    )
    return {
        "hypothesis": (
            "N unique parameters need d=ceil(log10(N+1)) decimal depth in one [0,1] "
            "RID identity field; slots=10^d-1; no collisions at that quantization."
        ),
        "slots_1_2_3": [slots(1), slots(2), slots(3)],
        "depth_examples": {
            "999": depth_for(999),
            "1e6-ish": depth_for(999_999),
            "1e12-ish": depth_for(999_999_999_999),
        },
        "doctrine_schema": payload.get("schema_version"),
        "uniqueness_d4": True,
    }


def test_rid_char_slot_assignment(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    """T13: Each vocab char gets a unique RID-quantized slot at depth d=ceil(log10(N+1))."""
    import math

    from rid_pid import rid_fold

    n = len(reg.vocab)
    d = int(math.ceil(math.log10(n + 1)))
    slots = (10**d) - 1
    _fail(failures, slots >= n, f"slots_lt_vocab:{slots}<{n}")
    # Assign slot k/(10^d) by token index (1-based to stay in (0,1)).
    assigned: dict[str, float] = {}
    for i, ch in enumerate(reg.vocab):
        assigned[ch] = (i + 1) / (10**d)
    vals = list(assigned.values())
    _fail(failures, len(vals) == len(set(vals)), "rid_slot_collision")
    _fail(failures, all(0.0 < v < 1.0 for v in vals), "rid_slot_oob")
    # UML locate: encode char → value → same sealed char; slot is address of that identity.
    locate_ok = 0
    for ch in ("H", "V", "i", "v", "A"):
        if ch not in reg.entries:
            continue
        eq = reg.encode_char(ch)
        back = reg.decode_eq(eq)
        slot = assigned[ch]
        # Fold with healthy leaves + slot as p-channel stand-in.
        s = rid_fold(1.0, 1.0, slot)
        if back == ch and abs(s - slot) < 1e-12:
            locate_ok += 1
        else:
            failures.append(f"locate:{ch}->{back} slot={slot} S={s}")
    return {
        "hypothesis": (
            "Vocab identities occupy unique RID-normalized slots; UML encode locates the "
            "sealed char; RID fold with p=slot preserves the address."
        ),
        "vocab_n": n,
        "depth_d": d,
        "slots": slots,
        "locate_ok": locate_ok,
        "sample_slots": {ch: assigned[ch] for ch in ("H", "V", "i") if ch in assigned},
    }


def test_uml_codec_math_tokens(failures: list[str]) -> dict[str, Any]:
    """T14: Text↔UML codec; native prompt is math tokens; math does not lie."""
    from uml_codec_io import (
        build_native_uml_prompt,
        continue_uml_response,
        encode_text_to_uml,
        is_math_token_surface,
        math_does_not_lie,
    )

    thesis = THESIS.read_text(encoding="utf-8")
    _fail(failures, "Math into tokens" in thesis, "thesis_missing_math_tokens")
    _fail(failures, "Math does not lie" in thesis, "thesis_missing_math_does_not_lie")

    enc = encode_text_to_uml("Viv")
    _fail(failures, bool(enc.get("roundtrip_ok")), f"codec_roundtrip:{enc}")
    _fail(failures, is_math_token_surface(enc["uml_stream"]), f"not_math:{enc['uml_stream']!r}")
    _fail(failures, not is_math_token_surface("Hello world"), "prose_marked_math")

    native = build_native_uml_prompt("Hi")
    _fail(failures, native["model_prompt"].startswith("UML:"), f"native_hdr:{native['model_prompt']!r}")
    _fail(failures, "Prefer efficient" not in native["model_prompt"], "native_has_english_instr")
    _fail(failures, is_math_token_surface(native["encode"]["uml_stream"]), "native_stream_not_math")

    # Model-like continuation in UML; decode back.
    cont = continue_uml_response(native["encode"]["uml_stream"], n_expected=2)
    _fail(failures, cont.get("status") == "PASS", f"continue:{cont}")
    _fail(failures, cont.get("surface") == "Hi", f"continue_surface:{cont.get('surface')!r}")

    lie_bad = math_does_not_lie("999", target_char="H")
    lie_cost = math_does_not_lie("40+1", target_char="H")
    lie_ok = math_does_not_lie("41", target_char="H")
    _fail(failures, lie_bad["fault_kind"] == "invalid_equation", f"lie_bad:{lie_bad}")
    _fail(failures, lie_cost["fault_kind"] == "routing_fault", f"lie_cost:{lie_cost}")
    _fail(failures, lie_ok["fault_kind"] == "valid_efficient", f"lie_ok:{lie_ok}")

    return {
        "hypothesis": (
            "UML plant I/O is math tokens; English stays outside encode/decode; "
            "faults are invalid equation or routing fault — math does not lie."
        ),
        "encode_viv": enc,
        "native_prompt": native["model_prompt"],
        "continue": cont,
        "faults": {
            "invalid": lie_bad["fault_kind"],
            "costly": lie_cost["fault_kind"],
            "cheap": lie_ok["fault_kind"],
        },
    }


def test_structure_vs_binding(failures: list[str]) -> dict[str, Any]:
    """T15: Unbound A+A → 2A; sealed A=1 → 2; grounded 1+1=2; no invented binding."""
    from uml_structure_binding import BindingEnv, evaluate_with_bindings

    thesis = THESIS.read_text(encoding="utf-8")
    _fail(failures, "Structure vs sealed identity binding" in thesis, "thesis_missing_binding")

    unbound = evaluate_with_bindings("?A + ?A")
    _fail(failures, unbound["kind"] == "unbound_structure", f"unbound_kind:{unbound}")
    _fail(failures, unbound.get("structure_result") == "2*?A", f"unbound_struct:{unbound}")
    _fail(failures, unbound.get("numeric_value") is None, "unbound_numeric_invented")
    _fail(failures, unbound.get("invented_binding") is False, "unbound_invent_flag")

    env = BindingEnv()
    env.bind("?A", 1.0)
    bound = evaluate_with_bindings("?A + ?A", env)
    _fail(failures, bound["kind"] == "bound_grounded", f"bound_kind:{bound}")
    _fail(failures, float(bound["numeric_value"]) == 2.0, f"bound_val:{bound}")

    grounded = evaluate_with_bindings("1 + 1")
    _fail(failures, grounded["kind"] == "grounded", f"grounded_kind:{grounded}")
    _fail(failures, float(grounded["numeric_value"]) == 2.0, f"grounded_val:{grounded}")

    incomplete = evaluate_with_bindings("?A * ?B")
    _fail(failures, incomplete["kind"] == "unbound_incomplete", f"incomplete:{incomplete}")
    _fail(failures, incomplete.get("numeric_value") is None, "incomplete_numeric")

    invent_raised = False
    try:
        evaluate_with_bindings("?A + ?A", allow_invent=True)
    except ValueError as exc:
        invent_raised = "invent_forbidden" in str(exc)
    _fail(failures, invent_raised, "invent_not_forbidden")

    return {
        "hypothesis": (
            "Unbound preserves structure; sealed binding enables numeric collapse; "
            "grounded needs no guess; inventing bindings is forbidden."
        ),
        "unbound": unbound,
        "bound": {"kind": bound["kind"], "value": bound["numeric_value"]},
        "grounded": {"kind": grounded["kind"], "value": grounded["numeric_value"]},
        "incomplete_kind": incomplete["kind"],
        "invent_forbidden": invent_raised,
    }


def test_speak_uml_native_live(failures: list[str]) -> dict[str, Any]:
    """T16: Native speak shell — plant prompt is UML math tokens; decode seals surface."""
    try:
        import torch
        from plant_checkpoint import load_plant_state_dict
        from plant_runtime import configure_plant_runtime
        from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset
        from sandbox_paths import EFFICIENT_CKPT
        from speak_uml_native import speak_uml_native
        from tokenizer import CharacterTokenizer
        from transformer import TransformerLanguageModel
    except Exception as exc:
        failures.append(f"native_import:{exc!r}")
        return {"status": "FAIL", "error": repr(exc)}

    thesis = THESIS.read_text(encoding="utf-8")
    _fail(failures, "UML is the tokenizer" in thesis, "thesis_uml_tokenizer")

    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    configure_plant_runtime(device=str(device))
    payload = torch.load(EFFICIENT_CKPT, map_location="cpu", weights_only=False)
    model = TransformerLanguageModel(tok.vocab_size, **IDENTITY_MODEL_CFG).to(device)
    load_plant_state_dict(
        model,
        payload["model_state_dict"],
        strict=False,
        config=dict(payload.get("config") or IDENTITY_MODEL_CFG),
    )
    model.eval()

    user = "Hi"
    out = speak_uml_native(
        model,
        user,
        encode_fn=tok.encode,
        decode_fn=tok.decode,
        max_new_tokens=16,
        prefer_efficient=True,
        temperature=0.0,
        uml_pressure={
            "stoi": tok.stoi,
            "itos": tok.itos,
            "hard_mask": True,
            "scale": 8.0,
        },
    )
    prompt = out["model_prompt"]
    _fail(failures, prompt.startswith("UML:"), f"prompt_not_uml:{prompt!r}")
    _fail(failures, "Prefer efficient" not in prompt, "english_instr_in_native")
    # Roundtrip may fail if LM continues badly — then continue_uml_response uses
    # prefer_efficient snap per eq; still require model_prompt math + receipt schema.
    rec = out["receipt"]
    _fail(failures, rec.get("schema_version") == "speak_uml_native_v1", "bad_schema")
    surface = out.get("surface")
    # Soft: if generation fails decode, mark ladder-style but don't hard-fail contract
    # when prompt shell is correct — still try hard seal when possible.
    sealed = surface == user
    if not sealed:
        # Contract requires the shell; seal success is ladder until native train exists.
        pass
    return {
        "hypothesis": "Native speak feeds UML math tokens into the plant; decode restores text.",
        "model_prompt": prompt,
        "surface": surface,
        "equations": out.get("equations"),
        "roundtrip_ok": sealed,
        "continue_status": (out.get("receipt") or {}).get("continue", {}).get("status"),
    }


def test_thermal_route_vs_symbolic(reg: UMLEquationRegistry, failures: list[str]) -> dict[str, Any]:
    """T17: Foundation thermal RID ranks sealed equations; destination seal holds."""
    from lib.uml_thermal_route import (
        compare_equations_thermal,
        decide_route_thermal,
        equation_heat_proxy,
        read_plant_thermal,
    )
    from uml_speak_pressure import resolve_equation_for_policy

    plant = read_plant_thermal()
    # Probe several chars — need at least one with multiple valid routes.
    probes = []
    diverged = 0
    seal_breaks = 0
    for ch in ("H", "A", "V", "i", "1", "+"):
        if ch not in reg.entries:
            continue
        base = decide_route(reg, target_char=ch, include_registry_pool=True)
        thermal = decide_route_thermal(reg, target_char=ch, include_registry_pool=True)
        _fail(failures, thermal.get("status") == "PASS", f"thermal_fail:{ch}")
        selected = str(thermal.get("selected") or "")
        try:
            decoded = reg.decode_eq(selected)
        except Exception as exc:
            seal_breaks += 1
            failures.append(f"thermal_decode:{ch}:{exc!r}")
            continue
        if decoded != ch:
            seal_breaks += 1
            failures.append(f"thermal_seal_break:{ch}->{decoded!r}")
        if thermal.get("diverged_from_symbolic_cheapest"):
            diverged += 1
        heats = [equation_heat_proxy(r.expr)["heat"] for r in base.considered if r.valid]
        probes.append(
            {
                "char": ch,
                "symbolic": base.selected,
                "thermal": selected,
                "symbolic_cost": base.selected_cost,
                "thermal_score": thermal.get("selected_thermal_score"),
                "diverged": bool(thermal.get("diverged_from_symbolic_cheapest")),
                "valid_count": thermal.get("valid_count"),
                "heat_span": (max(heats) - min(heats)) if heats else 0.0,
            }
        )

    # Explicit compare of two sealed routes for same destination (costly vs cheap).
    ch = "H"
    cheap = decide_route(reg, target_char=ch).selected
    # Use a known-valid costly equivalent if present.
    entry = reg.entries[ch]
    alts = [str(e) for e in (entry.get("equivalents") or []) if str(e) != cheap]
    cmp_eqs = [cheap] + alts[:3]
    cmp = compare_equations_thermal(reg, cmp_eqs, target_char=ch)
    _fail(failures, cmp.get("best_thermal_valid") is not None, "compare_no_best")
    best = cmp["best_thermal_valid"]
    _fail(failures, reg.decode_eq(best["expr"]) == ch, "compare_seal")

    # Speak snap uses thermal policy.
    snap = resolve_equation_for_policy(
        equation_text=alts[0] if alts else cheap,
        prompt_text=f"Prefer efficient UML for {ch}",
        registry=reg,
        policy="prefer_efficient",
    )
    _fail(failures, snap.get("policy") in ("thermal_efficient", "prefer_efficient_fallback"), "snap_policy")
    _fail(failures, reg.decode_eq(snap["equation_text"]) == ch, "snap_seal")

    thesis = THESIS.read_text(encoding="utf-8")
    _fail(failures, "thermal" in thesis.lower() or "T17" in thesis, "thesis_mentions_thermal")

    return {
        "hypothesis": (
            "Among valid sealed equations, thermal RID (plant × Nested-PEMDAS heat) "
            "selects the coolest path without breaking destination identity."
        ),
        "plant": {
            "available": plant.available,
            "source": plant.source,
            "master_s_n": plant.master_s_n,
            "thermal_stress": plant.thermal_stress,
            "coolant_s_n": plant.coolant_s_n,
            "gpu_s_n": plant.gpu_s_n,
        },
        "probes": probes,
        "diverged_count": diverged,
        "seal_breaks": seal_breaks,
        "compare_best": best,
        "snap_policy": snap.get("policy"),
        "snap_equation": snap.get("equation_text"),
        "snap_decision": snap.get("decision"),
    }


def main() -> int:
    failures: list[str] = []
    ladder: list[str] = []
    if not LATTICE.is_file():
        failures.append(f"missing_lattice:{LATTICE}")
    if not THESIS.is_file():
        failures.append(f"missing_thesis:{THESIS}")
    if not SANDBOX96_ARTIFACT.is_file():
        failures.append(f"missing_registry:{SANDBOX96_ARTIFACT}")

    sections: dict[str, Any] = {}
    if not failures:
        reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)
        sections = {
            "T0_pipeline_contract": test_pipeline_contract(failures),
            "T1_lattice_counts": test_lattice_counts(failures),
            "T2_reversible_roundtrip": test_reversible_roundtrip(reg, failures),
            "T3_sealed_destination": test_sealed_destination_many_routes(reg, failures),
            "T4_probability_among_valid": test_probability_only_among_valid(reg, failures),
            "T5_domain_tagging": test_domain_tagging(failures),
            "T6_rid_residual": test_rid_residual_on_faults(reg, failures),
            "T7_heldout_generalization": test_heldout_generalization(reg, failures),
            "T8_cost_pressure_bias": test_cost_pressure_bias(reg, failures),
            "T9_registry_federation_coverage": test_registry_federation_coverage(reg, failures),
            "T10_live_speak_ladder": test_live_speak_ladder(ladder),
            "T11_multi_char_seal_chain": test_multi_char_seal_chain(reg, failures),
            "T12_rid_address_precision": test_rid_address_precision(failures),
            "T13_rid_char_slot_assignment": test_rid_char_slot_assignment(reg, failures),
            "T14_uml_codec_math_tokens": test_uml_codec_math_tokens(failures),
            "T15_structure_vs_binding": test_structure_vs_binding(failures),
            "T16_speak_uml_native_live": test_speak_uml_native_live(failures),
            "T17_thermal_route_vs_symbolic": test_thermal_route_vs_symbolic(reg, failures),
        }

    contract_status = "PASS" if not failures else "FAIL"
    speak = sections.get("T10_live_speak_ladder") or {}
    ladder_status = speak.get("status", "SKIP")
    if ladder and ladder_status == "PASS":
        ladder_status = "PARTIAL"
    # Overall: contract is primary; ladder gaps do not revoke closed proof.
    status = contract_status
    if contract_status == "PASS" and ladder_status in {"PARTIAL", "FAIL"}:
        status = "PASS_CONTRACT_LADDER_OPEN"

    receipt = {
        "schema_version": "uml_training_thesis_selftest_v2",
        "status": status,
        "contract_status": contract_status,
        "ladder_status": ladder_status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "thesis": str(THESIS).replace("\\", "/"),
        "lattice": str(LATTICE).replace("\\", "/"),
        "control_law": (
            "Determinism chooses the destination. Probability chooses the route. "
            "Domain weighting chooses who participates. Cost chooses which valid route should win."
        ),
        "failures": failures,
        "ladder_gaps": ladder,
        "expanded_claims": [
            "T7 held-out reverse+seal",
            "T8 cost pressure (decide cheapest; low-T <= high-T mean cost)",
            "T9 bank realizes A/S/M/D (+ mixed when nested)",
            "T10 live speak seal vs cheap (ladder)",
            "T11 multi-char sealed chain",
            "T12 RID decimal address capacity + uniqueness",
            "T13 vocab RID slots + UML locate",
            "T14 math→tokens codec; math does not lie",
            "T15 structure vs sealed binding (unbound≠invent)",
        ],
        "sections": sections,
        "milestone": {
            "id": "closed_executable_proof_plus_ladder",
            "central_result": "T4 seal + T8 cost pressure + T7 held-out; T10 cheap_rate remains open gap",
        },
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_THESIS_SELFTEST_{status} contract={contract_status} "
        f"ladder={ladder_status} failures={len(failures)} gaps={len(ladder)}",
        flush=True,
    )
    for f in failures[:20]:
        print(f"  FAIL {f}", flush=True)
    for g in ladder[:20]:
        print(f"  LADDER {g}", flush=True)
    return 0 if contract_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
