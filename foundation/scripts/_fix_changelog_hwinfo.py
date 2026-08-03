#!/usr/bin/env python3
from pathlib import Path

p = Path(r"L:/.cursor/CHANGELOG.md")
lines = p.read_text(encoding="utf-8").splitlines(True)
cleaned = [ln for ln in lines if "HWiNFO CSV electrical meters wired" not in ln]
entry = (
    "## 2026-07-26\n\n"
    "- [2026-07-26 20:38:37] **HWiNFO CSV electrical meters wired (observe-only).** "
    "`lib/hwinfo_telemetry.py` reads `L:/Continue/Viv/foundation/lib/sensors/hwinfo.CSV`; "
    "admits exact preferred columns only (CPU Package Power, Vcore, VR VCC Current SVID IOUT, "
    "GPU Core Voltage). Inventory + observe refreshed. `i_gpu` still missing → "
    "`s_electrical=null`, Master unchanged. Tests PASS. Evidence: "
    "`artifacts/auto/rid_electrical/{meter_inventory,observe}_latest.json`.\n\n"
)
text = "".join(cleaned).lstrip()
p.write_text(entry + text, encoding="utf-8")
final = p.read_text(encoding="utf-8")
print("count", final.count("HWiNFO CSV electrical meters wired"))
print("starts", final[:80].replace("\n", "\\n"))
