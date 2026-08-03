#!/usr/bin/env python3
"""Immutable decomposition corpus freeze for V2 fitting.

Fit code must load rows only through this freeze. Source family JSONs are
hashed and never mutated by the fitter.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_cost_decomposition import (
    FAMILY_ORDER,
    campaign_manifest,
)
from lib.rid_electrical_policy import policy_stamp
from lib.rid_electrical_predictor import PLANT_CONFIG_ID

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
FREEZE_NAME = "DECOMPOSITION_CORPUS_FROZEN_V1"
FAMILY_FILES = {
    fam: f"decomp_{fam}_latest.json" for fam in FAMILY_ORDER
}
EVIDENCE_FILE = "decomposition_evidence_latest.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_freeze_manifest(*, out_dir: Path | None = None) -> dict[str, Any]:
    out = Path(out_dir) if out_dir else OUT
    sources: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    missing: list[str] = []

    for fam, fname in FAMILY_FILES.items():
        path = out / fname
        if not path.exists():
            missing.append(str(path).replace("\\", "/"))
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = list(payload.get("rows") or [])
        for r in rows:
            r = dict(r)
            r.setdefault("decomp_family", fam)
            all_rows.append(r)
        sources[fam] = {
            "path": str(path.resolve()).replace("\\", "/"),
            "sha256": _sha256_file(path),
            "n_rows": len(rows),
            "session_orders": payload.get("session_orders"),
            "at": payload.get("at"),
        }

    epath = out / EVIDENCE_FILE
    evidence_meta: dict[str, Any] = {}
    if epath.exists():
        evidence = json.loads(epath.read_text(encoding="utf-8"))
        evidence_meta = {
            "path": str(epath.resolve()).replace("\\", "/"),
            "sha256": _sha256_file(epath),
            "status": evidence.get("status"),
            "component_summary": evidence.get("component_summary"),
            "heldout_closure": {
                k: (evidence.get("heldout_closure") or {}).get(k)
                for k in (
                    "closure_pass",
                    "median_eps_closure",
                    "mean_eps_closure",
                    "n_holdout",
                    "eps_max",
                )
            },
            "component_results": evidence.get("component_results"),
            "phase_attributions": evidence.get("phase_attributions"),
        }

    sessions = sorted(
        {int(r["session_i"]) for r in all_rows if r.get("session_i") is not None}
    )
    manifest = {
        "ok": len(missing) == 0 and len(all_rows) >= 60,
        "at": _utc(),
        "freeze_id": FREEZE_NAME,
        "immutable": True,
        "fit_must_not_modify": True,
        "n_actions": len(all_rows),
        "expected_n_actions": 60,
        "sessions": sessions,
        "family_order": list(FAMILY_ORDER),
        "sources": sources,
        "missing_sources": missing,
        "evidence": evidence_meta,
        "cell_definitions": campaign_manifest(),
        "plant_config_id": PLANT_CONFIG_ID,
        "sensor_provenance": {
            "plant_config_id": PLANT_CONFIG_ID,
            "telemetry": "hwinfo_csv+nvml_board_power_generate_locked",
            "protocol": "rid_electrical_ledger_controls_v2",
        },
        "policy": policy_stamp(),
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "v2_fit_authorized": False,
            "accounting_predictor_v2_approved": False,
        },
        "note": (
            "Frozen decomposition evidence corpus. V2 fitting must load via "
            "load_frozen_corpus() and must not rewrite source family artifacts."
        ),
    }
    return manifest


def write_freeze(*, out_dir: Path | None = None) -> dict[str, Any]:
    out = Path(out_dir) if out_dir else OUT
    out.mkdir(parents=True, exist_ok=True)
    manifest = build_freeze_manifest(out_dir=out)
    jpath = out / f"{FREEZE_NAME}.json"
    mpath = out / f"{FREEZE_NAME}.md"
    # Snapshot row index (pointers only — full rows loaded lazily from hashed sources)
    manifest["row_index"] = [
        {
            "i": i,
            "family": r.get("decomp_family"),
            "cell_id": r.get("cell_id"),
            "session_i": r.get("session_i"),
            "action_id": r.get("action_id") or r.get("session_id"),
        }
        for i, r in enumerate(load_rows_from_sources(manifest, out_dir=out))
    ]
    jpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    mpath.write_text(
        "\n".join(
            [
                f"# {FREEZE_NAME}",
                "",
                f"- at: `{manifest['at']}`",
                f"- n_actions: `{manifest['n_actions']}`",
                f"- immutable: `{manifest['immutable']}`",
                f"- fit_must_not_modify: `{manifest['fit_must_not_modify']}`",
                f"- evidence_status: `{(manifest.get('evidence') or {}).get('status')}`",
                f"- plant_config_id: `{manifest.get('plant_config_id')}`",
                "",
                "## Source hashes",
                "",
            ]
            + [
                f"- `{fam}`: `{block.get('sha256')}` (n={block.get('n_rows')})"
                for fam, block in (manifest.get("sources") or {}).items()
            ]
            + ["", "Do not modify source artifacts after freeze.", ""]
        ),
        encoding="utf-8",
    )
    manifest["artifact_json"] = str(jpath).replace("\\", "/")
    manifest["artifact_md"] = str(mpath).replace("\\", "/")
    return manifest


def load_rows_from_sources(
    manifest: dict[str, Any],
    *,
    out_dir: Path | None = None,
    verify_hashes: bool = True,
) -> list[dict[str, Any]]:
    """Load full action rows from frozen source paths; optionally verify sha256."""
    out = Path(out_dir) if out_dir else OUT
    rows: list[dict[str, Any]] = []
    for fam, block in (manifest.get("sources") or {}).items():
        path = Path(str(block["path"]))
        if not path.exists():
            # fallback relative to out_dir
            path = out / FAMILY_FILES[fam]
        if verify_hashes:
            digest = _sha256_file(path)
            if digest != block.get("sha256"):
                raise RuntimeError(
                    f"frozen_corpus_hash_mismatch family={fam} "
                    f"expected={block.get('sha256')} got={digest}"
                )
        payload = json.loads(path.read_text(encoding="utf-8"))
        for r in payload.get("rows") or []:
            rr = dict(r)
            rr.setdefault("decomp_family", fam)
            rows.append(rr)
    return rows


def load_frozen_corpus(
    *,
    freeze_path: Path | None = None,
    out_dir: Path | None = None,
    verify_hashes: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = Path(out_dir) if out_dir else OUT
    path = Path(freeze_path) if freeze_path else out / f"{FREEZE_NAME}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing_freeze_manifest:{path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("immutable") or not manifest.get("fit_must_not_modify"):
        raise RuntimeError("freeze_manifest_missing_immutability_flags")
    rows = load_rows_from_sources(manifest, out_dir=out, verify_hashes=verify_hashes)
    return manifest, rows
