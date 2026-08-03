#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
import json

ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
bullet = (
    f"- [{ts}] **Electrical info-gain roadmap (Phases 1–7 scaffold).** "
    "Goal reframed: prove prediction/decision value, not Master admission. "
    "Session workloads + enriched JSONL; shadow A/B v3 whole-session holdout; "
    "ablation; role decision; advisory Q_i; flag-gated canary (write off). "
    "Smoke: 5 profiles, Master unchanged. Evidence under "
    "`artifacts/auto/rid_electrical/`.\n"
)
cl = Path(r"L:/.cursor/CHANGELOG.md")
t = cl.read_text(encoding="utf-8")
if "Electrical info-gain roadmap" not in t:
    if t.startswith("## 2026-07-26\n"):
        i = len("## 2026-07-26\n")
        if t[i : i + 1] == "\n":
            i += 1
        cl.write_text(t[:i] + bullet + t[i:], encoding="utf-8")
    else:
        cl.write_text("## 2026-07-26\n\n" + bullet + "\n" + t.lstrip(), encoding="utf-8")

sj = Path(r"L:/Continue/FSAA/reports/session_journal.md")
line = (
    f"- [{ts}] Shipped electrical info-gain stack: workload sessions, "
    "enriched capture, session-held-out Delta_info v3, ablation, role card, "
    "advisory routing, canary scaffold (default off). Smoke 5/5 sessions; "
    "Master disk unchanged; lifecycle measured_in_shadow.\n"
)
st = sj.read_text(encoding="utf-8")
if "electrical info-gain stack" not in st:
    if st.startswith("# Session Journal\n"):
        rest = st[len("# Session Journal\n") :]
        if rest.startswith("\n"):
            rest = rest[1:]
        sj.write_text("# Session Journal\n\n" + line + rest, encoding="utf-8")

idx = Path(r"L:/Continue/FSAA/reports/run_log_index.json")
d = json.loads(idx.read_text(encoding="utf-8"))
d["updated_at"] = ts
d["phase"] = "rid_electrical_info_gain_roadmap"
d["run_id"] = "rid_electrical_info_gain_v1"
d["status"] = "online_shadow"
paths = d.setdefault("paths", {})
paths["rid_electrical_sessions"] = (
    "L:/Continue/Viv/foundation/artifacts/auto/rid_electrical/sessions/"
)
paths["rid_electrical_shadow_ab_v3"] = (
    "L:/Continue/Viv/foundation/artifacts/auto/rid_electrical/"
    "ab-report-rid_electrical_shadow_ab_v3.json"
)
paths["rid_electrical_ablation"] = (
    "L:/Continue/Viv/foundation/artifacts/auto/rid_electrical/ablation_latest.json"
)
paths["rid_electrical_role"] = (
    "L:/Continue/Viv/foundation/artifacts/auto/rid_electrical/role_decision_latest.json"
)
idx.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
print("logged", ts)
