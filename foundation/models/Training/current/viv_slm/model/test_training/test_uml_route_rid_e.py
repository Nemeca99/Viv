#!/usr/bin/env python3
"""E: RID/PID residual from invalid / high-cost UML routes."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent
MODEL = SANDBOX.parent
FOUNDATION = MODEL.parents[4]
for p in (FOUNDATION, MODEL, SANDBOX):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.uml_equation_registry import SANDBOX96_ARTIFACT, UMLEquationRegistry  # noqa: E402
from lib.uml_route_governor import route_efficiency_error  # noqa: E402
from rid_pid import RIDMonitor  # noqa: E402
from plant_checkpoint import load_plant_state_dict  # noqa: E402
from plant_runtime import configure_plant_runtime  # noqa: E402
from sandbox_codex_identity import IDENTITY_MODEL_CFG, resolve_codex_dataset  # noqa: E402
from sandbox_paths import DEEP_CKPT, EFFICIENT_CKPT  # noqa: E402
from speak_lanes import speak_viv_sandwich  # noqa: E402
from tokenizer import CharacterTokenizer  # noqa: E402
from transformer import TransformerLanguageModel  # noqa: E402

PILOT = SANDBOX / "runs" / "uml_equation_ab_v2" / "pilot_uml_mix_masked.pt"
RECEIPT = SANDBOX / "runs" / "uml_route_rid_e_latest.json"


def _load(path: Path, tok, device):
    payload = __import__("torch").load(path, map_location="cpu", weights_only=False)
    import torch
    from transformer import TransformerLanguageModel as TLM

    model = TLM(tok.vocab_size, **IDENTITY_MODEL_CFG).to(device)
    load_plant_state_dict(
        model,
        payload["model_state_dict"],
        strict=False,
        config=dict(payload.get("config") or IDENTITY_MODEL_CFG),
    )
    model.eval()
    return model


def main() -> int:
    import torch

    failures: list[str] = []
    reg = UMLEquationRegistry.load(SANDBOX96_ARTIFACT)

    cheap = route_efficiency_error(reg, proposed="41", target_char="H")
    costly = route_efficiency_error(reg, proposed="40+1", target_char="H")
    bad = route_efficiency_error(reg, proposed="999", target_char="H")
    if cheap["error"] > 0.05:
        failures.append(f"cheap_error:{cheap}")
    if not (costly["error"] > cheap["error"]):
        failures.append(f"costly_not_higher:{costly['error']} vs {cheap['error']}")
    if bad["error"] < 0.99 or bad["kind"] != "invalid":
        failures.append(f"bad_route:{bad}")

    mon = RIDMonitor()
    s_cheap = mon.score_from_route(proposed_expr="41", target_char="H", registry=reg)
    r_cheap = mon.receipt()
    s_bad = mon.score_from_route(proposed_expr="999", target_char="H", registry=reg)
    r_bad = mon.receipt()
    if r_cheap.get("route_error", {}).get("error", 1) > 0.05:
        failures.append("rid_cheap_error")
    if r_bad.get("route_error", {}).get("error", 0) < 0.99:
        failures.append("rid_bad_error")
    if abs(s_bad - r_bad["S_RID"]) > 1e-9:
        failures.append("rid_s_mismatch")

    # Sandwich stamps rid_route
    _, vocab_path, _ = resolve_codex_dataset("v61")
    tok = CharacterTokenizer.from_manifest(vocab_path)
    configure_plant_runtime(device="cpu")
    deep_ckpt = PILOT if PILOT.is_file() else DEEP_CKPT
    model_e = _load(EFFICIENT_CKPT, tok, torch.device("cpu"))
    model_d = _load(deep_ckpt, tok, torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    prompt = "User: Prefer efficient UML for H\nViv: "
    ids = torch.tensor([tok.encode(prompt)], dtype=torch.long)
    sandwich = speak_viv_sandwich(
        model_e,
        model_d,
        ids,
        deep_max=24,
        decode_fn=tok.decode,
        uml_pressure={"stoi": tok.stoi, "itos": tok.itos, "hard_mask": True},
        stamp_master_rid=False,
    )
    rid_route = sandwich["receipt"].get("rid_route") or {}
    if "route_error" not in rid_route and rid_route.get("status") == "FAIL":
        failures.append(f"sandwich_rid:{rid_route}")
    elif "S_RID" not in rid_route:
        failures.append(f"sandwich_missing_s:{rid_route}")

    status = "PASS" if not failures else "FAIL"
    receipt = {
        "schema_version": "uml_route_rid_e_v1",
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "errors": {"cheap": cheap, "costly": costly, "bad": bad},
        "rid": {"cheap_S": s_cheap, "bad_S": s_bad, "bad_u": r_bad.get("u_actuation")},
        "sandwich_equation": sandwich.get("equation_text"),
        "sandwich_rid": rid_route,
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"UML_ROUTE_RID_E_{status} cheap_err={cheap['error']:.3f} "
        f"costly_err={costly['error']:.3f} bad_err={bad['error']:.3f} "
        f"eq={sandwich.get('equation_text')!r}"
    )
    if failures:
        for item in failures[:20]:
            print("FAIL", item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
