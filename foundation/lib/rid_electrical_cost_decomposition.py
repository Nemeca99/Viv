#!/usr/bin/env python3
"""Cost decomposition campaign definitions (no V2 fit).

Independent cell families for load/residency, prompt-eval, token-eval (V1 ref),
and post-action tail. Measurements only; no combined multivariate model.

Cell design (locked for evidence campaign):
- load/residency: same prompt + same num_predict=360 across cold/warm/unload-reload
- prompt_eval: fixed np=360; short/medium/long prompt text wired into generate
- token_eval_v1_reference: 2.5/3.5/4.5 s targets (np≈258/360/464)
- post_action_tail: horizons 5/10/20 s
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DecompositionCell:
    family: str
    cell_id: str
    description: str
    num_predict: int
    residency: str
    prompt_variant: str
    tail_tau_s: float
    repeats: int = 5
    notes: str = ""
    unload_before: bool = False
    target_eval_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Fixed eval duration ~3.5s (~360 tokens @ ~103 tok/s).
_PROMPT_FIXED_NP = 360
# Token-eval reference targets at ~103 tok/s.
_NP_2P5S = 258
_NP_3P5S = 360
_NP_4P5S = 464

CLOSURE_EPS_MAX = 0.15
CLOSURE_N_HOLDOUT_MIN = 5
FAMILY_ORDER: tuple[str, ...] = (
    "load_residency",
    "prompt_eval",
    "token_eval_v1_reference",
    "post_action_tail",
)

DECOMPOSITION_CELLS: tuple[DecompositionCell, ...] = (
    # 1) Model load / residency — same duration across cells
    DecompositionCell(
        family="load_residency",
        cell_id="decomp_cold_load__np360",
        description="Cold first load with same-duration generate (np=360)",
        num_predict=_PROMPT_FIXED_NP,
        residency="cold_first",
        prompt_variant="standard",
        tail_tau_s=5.0,
        notes="E_load ≈ cold−warm ΔE at matched eval duration",
    ),
    DecompositionCell(
        family="load_residency",
        cell_id="decomp_warm_resident__np360",
        description="Already-warm resident same-duration generate (np=360)",
        num_predict=_PROMPT_FIXED_NP,
        residency="warm_repeat",
        prompt_variant="standard",
        tail_tau_s=5.0,
    ),
    DecompositionCell(
        family="load_residency",
        cell_id="decomp_unload_reload__np360",
        description="Explicit unload then reload before same-duration generate",
        num_predict=_PROMPT_FIXED_NP,
        residency="cold_first",
        prompt_variant="standard",
        tail_tau_s=5.0,
        unload_before=True,
        notes="Requires explicit unload before cell",
    ),
    # 2) Prompt evaluation (fixed generation length, varied prompt)
    DecompositionCell(
        family="prompt_eval",
        cell_id="decomp_prompt_short__np360",
        description="Short prompt, fixed num_predict~3.5s",
        num_predict=_PROMPT_FIXED_NP,
        residency="warm_repeat",
        prompt_variant="short",
        tail_tau_s=5.0,
    ),
    DecompositionCell(
        family="prompt_eval",
        cell_id="decomp_prompt_medium__np360",
        description="Medium prompt, fixed num_predict~3.5s",
        num_predict=_PROMPT_FIXED_NP,
        residency="warm_repeat",
        prompt_variant="medium",
        tail_tau_s=5.0,
    ),
    DecompositionCell(
        family="prompt_eval",
        cell_id="decomp_prompt_long__np360",
        description="Long prompt, fixed num_predict~3.5s",
        num_predict=_PROMPT_FIXED_NP,
        residency="warm_repeat",
        prompt_variant="long",
        tail_tau_s=5.0,
    ),
    # 3) Token evaluation — V1 reference only (do not refit)
    DecompositionCell(
        family="token_eval_v1_reference",
        cell_id="decomp_token_eval_ref__2p5s",
        description="V1 reference ~2.5s target; compare to frozen V1 only",
        num_predict=_NP_2P5S,
        residency="warm_repeat",
        prompt_variant="standard",
        tail_tau_s=5.0,
        target_eval_s=2.5,
        notes="No V2 fit; config-drift check vs frozen V1",
    ),
    DecompositionCell(
        family="token_eval_v1_reference",
        cell_id="decomp_token_eval_ref__3p5s",
        description="V1 reference ~3.5s target; compare to frozen V1 only",
        num_predict=_NP_3P5S,
        residency="warm_repeat",
        prompt_variant="standard",
        tail_tau_s=5.0,
        target_eval_s=3.5,
        notes="No V2 fit; config-drift check vs frozen V1",
    ),
    DecompositionCell(
        family="token_eval_v1_reference",
        cell_id="decomp_token_eval_ref__4p5s",
        description="V1 reference ~4.5s target; compare to frozen V1 only",
        num_predict=_NP_4P5S,
        residency="warm_repeat",
        prompt_variant="standard",
        tail_tau_s=5.0,
        target_eval_s=4.5,
        notes="No V2 fit; config-drift check vs frozen V1",
    ),
    # 4) Post-action tail horizons 5/10/20 s
    DecompositionCell(
        family="post_action_tail",
        cell_id="decomp_tail_5s__np360",
        description="Tail horizon 5s after generate",
        num_predict=_PROMPT_FIXED_NP,
        residency="warm_repeat",
        prompt_variant="standard",
        tail_tau_s=5.0,
    ),
    DecompositionCell(
        family="post_action_tail",
        cell_id="decomp_tail_10s__np360",
        description="Tail horizon 10s after generate",
        num_predict=_PROMPT_FIXED_NP,
        residency="warm_repeat",
        prompt_variant="standard",
        tail_tau_s=10.0,
    ),
    DecompositionCell(
        family="post_action_tail",
        cell_id="decomp_tail_20s__np360",
        description="Tail horizon 20s after generate",
        num_predict=_PROMPT_FIXED_NP,
        residency="warm_repeat",
        prompt_variant="standard",
        tail_tau_s=20.0,
    ),
)


PROMPT_TEXT: dict[str, str] = {
    "standard": (
        "Explain liquid-cooled CPU and GPU power draw for a local agent in clear prose. "
        "Include thermal and electrical considerations."
    ),
    "short": "Explain GPU power draw briefly.",
    "medium": (
        "Explain liquid-cooled CPU and GPU power draw for a local agent. "
        "Cover idle baseline, active inference, and thermal coupling in several paragraphs."
    ),
    "long": (
        "Write a detailed technical briefing on liquid-cooled CPU and GPU power draw for a "
        "local autonomous agent. Cover idle baseline settling, PCIe and EPS rails, NVML vs "
        "board power, prompt-eval versus token-eval phases, thermal return-to-idle, and "
        "measurement pitfalls with slow telemetry cadence. Use clear prose and concrete examples."
    ),
}


def cells_by_family() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for c in DECOMPOSITION_CELLS:
        out.setdefault(c.family, []).append(c.to_dict())
    return out


def cells_for_family(family: str) -> list[DecompositionCell]:
    return [c for c in DECOMPOSITION_CELLS if c.family == family]


def prompt_for_variant(variant: str) -> str:
    return PROMPT_TEXT.get(str(variant), PROMPT_TEXT["standard"])


def campaign_manifest() -> dict[str, Any]:
    return {
        "ok": True,
        "protocol": "rid_electrical_cost_decomposition_evidence_v1",
        "lifecycle_from": "auditable_action_energy_ledger",
        "lifecycle_target": "decomposition_evidence_complete",
        "v2_fit_authorized": False,
        "refit_v1_forbidden": True,
        "closure_eps_max": CLOSURE_EPS_MAX,
        "closure_n_holdout_min": CLOSURE_N_HOLDOUT_MIN,
        "family_order": list(FAMILY_ORDER),
        "families": list(cells_by_family().keys()),
        "cells": [c.to_dict() for c in DECOMPOSITION_CELLS],
        "prompt_variants": list(PROMPT_TEXT.keys()),
        "gates": {
            "snr_net_min": 3.0,
            "cv_e_max": 0.20,
            "cv_p_mean_max": 0.15,
            "repeats_min": 5,
        },
        "note": (
            "Independent family campaigns with matched-duration load cells, wired prompt "
            "variants, V1 reference targets, and separate E_tail. No V2 coefficient fit."
        ),
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
    }
