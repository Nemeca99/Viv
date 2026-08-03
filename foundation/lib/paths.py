"""Viv foundation paths — single anchor for rebuild."""
from __future__ import annotations

from pathlib import Path

FOUNDATION_ROOT = Path(__file__).resolve().parents[1]
VIV_ROOT = FOUNDATION_ROOT.parent
CONTINUE_ROOT = VIV_ROOT.parent
AUTOMATION_ROOT = CONTINUE_ROOT / "automation"
FSAA_ROOT = CONTINUE_ROOT / "FSAA"
FSAA_SCRIPTS = FSAA_ROOT / "scripts"

ARTIFACTS = FOUNDATION_ROOT / "artifacts"
RID_ARTIFACTS = ARTIFACTS / "rid"
UML_ARTIFACTS = ARTIFACTS / "uml"
AUTO_ARTIFACTS = ARTIFACTS / "auto"
CARMA_ARTIFACTS = ARTIFACTS / "carma"
# Law 7 — Viv's sovereign playground (security_core MUTATION_SANDBOX_ROOTS)
SANDBOX_ROOT = VIV_ROOT / "sandbox"

for _p in (RID_ARTIFACTS, UML_ARTIFACTS, AUTO_ARTIFACTS, CARMA_ARTIFACTS, SANDBOX_ROOT):
    _p.mkdir(parents=True, exist_ok=True)
