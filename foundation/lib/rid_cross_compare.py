"""PC vs phone RID v1.2 benchmark comparison."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from lib.paths import RID_ARTIFACTS

PHONE_BASELINE = RID_ARTIFACTS / "phone_baseline_s24_v12.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_pc_run(glob_pattern: str = "rid_stability_efficiency_v1_2_*.json") -> Optional[Path]:
    files = sorted(RID_ARTIFACTS.glob(glob_pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _metric_delta(pc: float | None, phone: float | None) -> Optional[float]:
    if pc is None or phone is None:
        return None
    return round(pc - phone, 4)


def compare(phone_path: Path | None = None, pc_path: Path | None = None) -> dict[str, Any]:
    phone_file = phone_path or PHONE_BASELINE
    if not phone_file.is_file():
        raise FileNotFoundError(f"phone baseline missing: {phone_file}")
    phone = _load_json(phone_file)

    pc_file = pc_path or latest_pc_run()
    if pc_file is None or not pc_file.is_file():
        raise FileNotFoundError("no PC benchmark JSON in artifacts/rid — run: rid_main benchmark")

    pc = _load_json(pc_file)
    p_man = phone.get("manipulation") or {}
    p_cou = phone.get("coupling") or {}
    p_eff = phone.get("efficiency") or {}

    report: dict[str, Any] = {
        "schema": "viv.rid_cross_compare.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "phone": {
            "device": phone.get("device"),
            "source": phone.get("source"),
            "verdict": phone.get("verdict"),
            "path": str(phone_file),
        },
        "pc": {
            "platform": pc.get("platform"),
            "timestamp": pc.get("timestamp"),
            "verdict": pc.get("verdict"),
            "path": str(pc_file),
        },
        "metrics": {
            "corr_s_n_vs_e_rel": {
                "phone": p_cou.get("corr_s_n_vs_e_rel"),
                "pc": pc.get("corr_Sn_vs_e_rel"),
                "delta": _metric_delta(pc.get("corr_Sn_vs_e_rel"), p_cou.get("corr_s_n_vs_e_rel")),
            },
            "mean_d_e_rel": {
                "phone": p_cou.get("mean_d_e_rel_chaos_minus_clean"),
                "pc": pc.get("mean_d_e_rel_chaos_minus_clean"),
                "delta": _metric_delta(pc.get("mean_d_e_rel_chaos_minus_clean"), p_cou.get("mean_d_e_rel_chaos_minus_clean")),
            },
            "manipulation_d_s_n": {
                "phone": p_man.get("delta_s_n"),
                "pc": pc.get("manipulation_d_Sn"),
                "delta": _metric_delta(pc.get("manipulation_d_Sn"), p_man.get("delta_s_n")),
            },
            "pct_drop_eta_n1": {
                "phone": p_eff.get("pct_drop_n1_chaos_vs_clean"),
                "pc": None,
                "note": "PC JSON does not store per-n table; see CSV for raw rounds",
            },
            "baseline_eta_n1": {
                "phone": p_eff.get("baseline_eta_n1_clean"),
                "pc": pc.get("baseline_eta_n1"),
            },
        },
        "gates": {
            "phone_manipulation_ok": p_man.get("manipulation_ok"),
            "pc_manipulation_ok": pc.get("manipulation_ok"),
            "phone_supported": phone.get("verdict") == "SUPPORTED",
            "pc_valid_sample": bool(pc.get("manipulation_ok")),
        },
    }

    pc_v = str(pc.get("verdict") or "")
    if pc.get("manipulation_ok") and "SUPPORTED" in pc_v.upper():
        report["cross_verdict"] = "PC_REPLICATES_PHONE"
    elif pc.get("manipulation_ok") and "PARTIAL" in pc_v.upper():
        corr_pc = pc.get("corr_Sn_vs_e_rel")
        corr_ph = p_cou.get("corr_s_n_vs_e_rel")
        if corr_pc is not None and corr_ph is not None and corr_pc > 0.25:
            report["cross_verdict"] = "PC_PARTIAL_COUPLING_SAME_SIGN"
        else:
            report["cross_verdict"] = "PC_MANIPULATION_OK_COUPLING_WEAK"
    elif pc.get("manipulation_ok"):
        corr_pc = pc.get("corr_Sn_vs_e_rel")
        corr_ph = p_cou.get("corr_s_n_vs_e_rel")
        if corr_pc is not None and corr_ph is not None and corr_pc > 0.25:
            report["cross_verdict"] = "PC_PARTIAL_COUPLING_SAME_SIGN"
        else:
            report["cross_verdict"] = "PC_INCONCLUSIVE_COUPLING"
    else:
        report["cross_verdict"] = "PC_INCONCLUSIVE_MANIPULATION"

    report["summary"] = _summary_text(report)
    return report


def _summary_text(report: dict[str, Any]) -> str:
    m = report["metrics"]
    lines = [
        f"Phone (S24): {report['phone']['verdict']} | PC: {report['pc']['verdict']}",
        f"Cross: {report['cross_verdict']}",
        "",
        "Key metrics:",
        f"  corr(S_n, e_rel)  phone={m['corr_s_n_vs_e_rel']['phone']}  pc={m['corr_s_n_vs_e_rel']['pc']}",
        f"  d_Sn chaos-clean phone={m['manipulation_d_s_n']['phone']}  pc={m['manipulation_d_s_n']['pc']}",
        f"  manipulation_ok   phone={report['gates']['phone_manipulation_ok']}  pc={report['gates']['pc_manipulation_ok']}",
    ]
    if report["cross_verdict"] == "PC_INCONCLUSIVE_MANIPULATION":
        lines.append("")
        lines.append(
            "PC saboteur did not depress S_n enough. Rerun with: "
            "rid_main benchmark --seconds 10 --rounds 8 --saboteur-mem 2048"
        )
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = [
        "# RID v1.2 — PC vs Phone (S24)",
        "",
        report["summary"],
        "",
        "## Artifacts",
        f"- Phone baseline: `{report['phone']['path']}`",
        f"- PC run: `{report['pc']['path']}`",
        "",
        f"Generated: {report['generated_utc']}",
    ]
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
