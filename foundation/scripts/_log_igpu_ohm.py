#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime

ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
entry = (
    f"## 2026-07-26\n\n"
    f"- [{ts}] **GPU i_gpu software Ohm path.** No native HWiNFO/NVML GPU `[A]`. "
    f"`lib/hwinfo_telemetry.py` reconstructs board amps as sum of measured "
    f"PCIe+8-pin Input Power/Voltage (`software_ohm_from_measured_hwinfo_rails`, "
    f"non-independent). Observe triad now available (`s_electrical` live); "
    f"Master still unchanged / no authority. Tests PASS. "
    f"Evidence: `artifacts/auto/rid_electrical/observe_latest.json`.\n\n"
)
cl = Path(r"L:/.cursor/CHANGELOG.md")
text = cl.read_text(encoding="utf-8")
# Insert under existing ## 2026-07-26 if present, else prepend
marker = "## 2026-07-26\n"
if "GPU i_gpu software Ohm path" not in text:
    if text.startswith(marker):
        # after first heading + blank line
        idx = text.find("\n", len(marker))
        # find first bullet block insert after heading
        insert_at = len(marker) + (1 if text[len(marker) : len(marker) + 1] == "\n" else 0)
        if text[len(marker) : len(marker) + 1] == "\n":
            insert_at = len(marker) + 1
        bullet = (
            f"- [{ts}] **GPU i_gpu software Ohm path.** No native HWiNFO/NVML GPU `[A]`. "
            f"`lib/hwinfo_telemetry.py` reconstructs board amps as sum of measured "
            f"PCIe+8-pin Input Power/Voltage (`software_ohm_from_measured_hwinfo_rails`, "
            f"non-independent). Observe triad available; Master unchanged. Tests PASS.\n"
        )
        cl.write_text(text[:insert_at] + bullet + text[insert_at:], encoding="utf-8")
    else:
        cl.write_text(entry + text.lstrip(), encoding="utf-8")

sj = Path(r"L:/Continue/FSAA/reports/session_journal.md")
sj_line = (
    f"- [{ts}] GPU amp via software Ohm from measured HWiNFO PCIe+8-pin P/V "
    f"(~1.63 A live). Observe S_electrical now computed; i_gpu stamped "
    f"non-independent; Master authority still withheld. Next: shadow A/B "
    f"vs Master with complete triad, still no authority write.\n"
)
sj_text = sj.read_text(encoding="utf-8")
if "GPU amp via software Ohm" not in sj_text:
    if sj_text.startswith("# Session Journal\n"):
        rest = sj_text[len("# Session Journal\n") :]
        if rest.startswith("\n"):
            rest = rest[1:]
        sj.write_text("# Session Journal\n\n" + sj_line + rest, encoding="utf-8")
    else:
        sj.write_text(sj_line + sj_text, encoding="utf-8")

idx = Path(r"L:/Continue/FSAA/reports/run_log_index.json")
import json

d = json.loads(idx.read_text(encoding="utf-8"))
d["updated_at"] = ts
d["phase"] = "rid_electrical_igpu_ohm"
d["run_id"] = "rid_electrical_igpu_ohm_v1"
d.setdefault("paths", {})["rid_electrical_observe"] = (
    "L:/Continue/Viv/foundation/artifacts/auto/rid_electrical/observe_latest.json"
)
idx.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
print("logged", ts)
