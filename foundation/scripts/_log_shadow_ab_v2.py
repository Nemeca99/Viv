#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
import json

ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
bullet = (
    f"- [{ts}] **Electrical shadow A/B v2 (Delta_info gate).** "
    "`rid_electrical_shadow_ab_v2`: live observe samples; "
    "Delta_info = Master+electrical vs Master baseline (held-out one-step MAE); "
    "derived I_GPU stamped; admission withheld. Live 30s run verdict "
    "`INCONCLUSIVE_LOW_SIGNAL` (Master S_n flat). Artifacts: "
    "`artifacts/auto/rid_electrical/ab-report-rid_electrical_shadow_ab_v2.{json,md}`.\n"
)
cl = Path(r"L:/.cursor/CHANGELOG.md")
t = cl.read_text(encoding="utf-8")
if "Electrical shadow A/B v2" not in t:
    if t.startswith("## 2026-07-26\n"):
        i = len("## 2026-07-26\n")
        if t[i : i + 1] == "\n":
            i += 1
        cl.write_text(t[:i] + bullet + t[i:], encoding="utf-8")
    else:
        cl.write_text("## 2026-07-26\n\n" + bullet + "\n" + t.lstrip(), encoding="utf-8")

sj = Path(r"L:/Continue/FSAA/reports/session_journal.md")
line = (
    f"- [{ts}] Locked Delta_info shadow gate for electrical. 30-sample A/B: "
    "verdict INCONCLUSIVE_LOW_SIGNAL (Master flat); I_GPU Ohm-derived stamped; "
    "admission withheld; Master disk unchanged. Rerun under load for valid info-gain.\n"
)
st = sj.read_text(encoding="utf-8")
if "Delta_info shadow gate" not in st:
    if st.startswith("# Session Journal\n"):
        rest = st[len("# Session Journal\n") :]
        if rest.startswith("\n"):
            rest = rest[1:]
        sj.write_text("# Session Journal\n\n" + line + rest, encoding="utf-8")

idx = Path(r"L:/Continue/FSAA/reports/run_log_index.json")
d = json.loads(idx.read_text(encoding="utf-8"))
d["updated_at"] = ts
d["phase"] = "rid_electrical_shadow_ab_v2"
d["run_id"] = "rid_electrical_shadow_ab_v2"
d["status"] = "inconclusive_low_signal"
d.setdefault("paths", {})["rid_electrical_shadow_ab"] = (
    "L:/Continue/Viv/foundation/artifacts/auto/rid_electrical/"
    "ab-report-rid_electrical_shadow_ab_v2.json"
)
idx.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
print("logged", ts)
