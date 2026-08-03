#!/usr/bin/env python3
"""Forensic dump: tokens_short unstable_signature / repeat-order confound."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_ledger_campaign import evaluate_cell_repeatability  # noqa: E402

ROOT = AUTO_ARTIFACTS / "rid_electrical" / "sessions"
OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"


def main() -> int:
    ids = [
        "ledger_tokens__tokens_short_r1_20260727T045806Z",
        "ledger_tokens__tokens_short_r2_20260727T045851Z",
        "ledger_tokens__tokens_short_r3_20260727T045935Z",
    ]
    rows = []
    table = []
    for sid in ids:
        d = ROOT / sid
        a = json.loads((d / "controlled_action.json").read_text(encoding="utf-8"))
        samples = [
            json.loads(l)
            for l in (d / "samples.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        phases: dict[str, list] = {}
        for s in samples:
            phases.setdefault(str(s.get("phase")), []).append(s)
        dur = None
        if a.get("mono_start_s") is not None and a.get("mono_end_s") is not None:
            dur = float(a["mono_end_s"]) - float(a["mono_start_s"])
        en = a.get("E_net_j")
        eg = a.get("E_gross_j")
        e_per_s = (float(en) / dur) if en is not None and dur and dur > 0 else None
        g_per_s = (float(eg) / dur) if eg is not None and dur and dur > 0 else None
        sv = a.get("session_validated") or {}
        idle = sv.get("idle_baseline") or {}
        infer = a.get("infer") or {}
        temps = a.get("temperatures") or {}
        phase_summary = {}
        for ph, ss in phases.items():
            boards = []
            for s in ss:
                pr = s.get("P_rails") or {}
                wc = pr.get("w_cpu")
                wg = pr.get("w_gpu")
                if wc is not None and wg is not None:
                    boards.append(float(wc) + float(wg))
            phase_summary[ph] = {
                "n": len(ss),
                "mono_span_s": (
                    float(ss[-1]["mono_s"]) - float(ss[0]["mono_s"]) if len(ss) > 1 else 0.0
                ),
                "P_board_mean_w": (sum(boards) / len(boards)) if boards else None,
            }
        row = {
            "session_id": sid,
            "repeat_i": a.get("repeat_i"),
            "token_count": a.get("token_count"),
            "eval_count": infer.get("eval_count"),
            "prompt_eval_count": infer.get("prompt_eval_count"),
            "ollama_wall_s": infer.get("wall_s"),
            "E_gross_j": eg,
            "E_net_j": en,
            "P_idle_baseline_w": sv.get("P_idle_baseline_w") or a.get("P_idle_baseline_w"),
            "idle_baseline_source": idle.get("source"),
            "idle_baseline_n": idle.get("n"),
            "duration_action_s": dur,
            "P_mean_w": a.get("P_mean_w"),
            "P_peak_w": a.get("P_peak_w"),
            "E_net_per_active_s": e_per_s,
            "E_gross_per_active_s": g_per_s,
            "coverage_pct": (a.get("quality") or {}).get("sample_coverage_pct"),
            "confidence": a.get("confidence"),
            "temps": temps,
            "phase_summary": phase_summary,
            "window_vs_wall_ratio": (
                (dur / float(infer["wall_s"]))
                if dur and infer.get("wall_s")
                else None
            ),
        }
        table.append(row)
        rows.append(a)

    ev = evaluate_cell_repeatability(rows)
    e_vals = [float(r["E_net_j"]) for r in rows]
    e_per = [t["E_net_per_active_s"] for t in table if t["E_net_per_active_s"] is not None]
    diagnosis = {
        "cell_id": "tokens__tokens_short",
        "outcome": ev.get("outcome"),
        "CV_E": ev.get("CV_E"),
        "CV_P": ev.get("CV_P"),
        "mu_E_net_j": ev.get("mu_E_net_j"),
        "E_net_series_j": e_vals,
        "E_net_per_active_s_series": e_per,
        "CV_E_net_per_active_s": (
            statistics.pstdev(e_per) / abs(statistics.fmean(e_per))
            if len(e_per) >= 2 and abs(statistics.fmean(e_per)) > 1e-9
            else None
        ),
        "findings": [
            "Token count constant at 88 (64 eval + 24 prompt) — independent variable held.",
            "E_net rises monotonically across repeats (repeat-order confound).",
            "Action integration duration not equal to Ollama wall time (windowing confound on r2/r3).",
            "E_net/dt also rises across repeats — not duration-only; plant/baseline/execution state changing.",
            "Thermal: coolant flat ~31C; GPU max rises 54→64→65C across repeats.",
            "Learning admission remains withheld; do not interpret token-length effect.",
        ],
        "verdict": {
            "measurement_path_valid": True,
            "repeat_order_confound_detected": True,
            "token_signature_established": False,
            "learning_withheld": True,
        },
        "repeats": table,
        "cell_eval": ev,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    jpath = OUT / "forensic_tokens_short_unstable.json"
    mpath = OUT / "forensic_tokens_short_unstable.md"
    jpath.write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")
    lines = [
        "# Forensic: tokens__tokens_short → unstable_signature",
        "",
        f"- **Outcome:** `{ev.get('outcome')}`",
        f"- **CV_E:** {ev.get('CV_E')} (gate ≤ 0.20)",
        f"- **CV_P:** {ev.get('CV_P')} (gate ≤ 0.15)",
        f"- **E_net series:** {e_vals}",
        f"- **E_net/Δt series:** {e_per}",
        f"- **CV(E_net/Δt):** {diagnosis['CV_E_net_per_active_s']}",
        "",
        "## Verdict",
        "",
        "```",
        "measurement path valid",
        "+ repeat-order confound detected",
        "+ token signature not established",
        "+ learning remains withheld",
        "```",
        "",
        "## Side-by-side",
        "",
    ]
    for t in table:
        lines.append(
            f"### r{t['repeat_i']}\n"
            f"- tokens={t['token_count']} wall_s={t['ollama_wall_s']}\n"
            f"- E_gross={t['E_gross_j']} E_net={t['E_net_j']} P_idle={t['P_idle_baseline_w']}\n"
            f"- duration_action_s={t['duration_action_s']} P_mean={t['P_mean_w']} P_peak={t['P_peak_w']}\n"
            f"- E_net/Δt={t['E_net_per_active_s']} window/wall={t['window_vs_wall_ratio']}\n"
            f"- temps={t['temps']}\n"
            f"- phases={t['phase_summary']}\n"
        )
    lines.extend(["## Findings", ""])
    for f in diagnosis["findings"]:
        lines.append(f"- {f}")
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: diagnosis[k] for k in (
        "outcome", "CV_E", "CV_P", "E_net_series_j", "E_net_per_active_s_series",
        "CV_E_net_per_active_s", "verdict", "findings"
    )}, indent=2))
    print("artifact", str(jpath).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
