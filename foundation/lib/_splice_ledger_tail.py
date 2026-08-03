from pathlib import Path

root = Path(__file__).resolve().parent
main = root / "rid_electrical_ledger_campaign.py"
tail = root / "_ledger_campaign_tail.py"
text = main.read_text(encoding="utf-8")
marker = "def evaluate_cell_repeatability"
i = text.index(marker)
new = text[:i] + tail.read_text(encoding="utf-8")
main.write_text(new, encoding="utf-8")
tail.unlink()
print("spliced ok", main.stat().st_size)
