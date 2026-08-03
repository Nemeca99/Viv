#!/usr/bin/env python3
"""Install/verify isolated electrical-training dependency surface (sklearn)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
REQ = FOUNDATION / "requirements-electrical-training.txt"
ENV_LOCK = CAMPAIGN / "PRE_ACTION_TRAINING_ENV_LOCK.json"
PYTHON = Path(sys.executable)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pip(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), "-m", "pip", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def inventory() -> dict[str, str]:
    r = _pip("freeze")
    pkgs = {}
    for line in (r.stdout or "").splitlines():
        if "==" in line:
            name, ver = line.split("==", 1)
            pkgs[name.lower()] = ver.strip()
    return pkgs


def main() -> int:
    CAMPAIGN.mkdir(parents=True, exist_ok=True)
    pre = inventory()
    install = _pip("install", "-r", str(REQ))
    post = inventory()
    check = _pip("check")
    sk_ver = post.get("scikit-learn")
    try:
        import sklearn  # noqa: WPS

        import_ok = True
        import_ver = sklearn.__version__
    except Exception as exc:  # noqa: BLE001
        import_ok = False
        import_ver = str(exc)

    lock = {
        "ok": check.returncode == 0 and sk_ver == "1.9.0" and import_ok,
        "at": _utc(),
        "python": str(PYTHON),
        "requirements_file": str(REQ).replace("\\", "/"),
        "scikit_learn_pinned": "1.9.0",
        "scikit_learn_installed": sk_ver,
        "import_ok": import_ok,
        "import_version": import_ver,
        "pip_check_ok": check.returncode == 0,
        "pip_check_stdout": (check.stdout or "")[:2000],
        "pip_check_stderr": (check.stderr or "")[:2000],
        "install_returncode": install.returncode,
        "pre_inventory_n": len(pre),
        "post_inventory_n": len(post),
        "pre_sklearn": pre.get("scikit-learn"),
        "post_sklearn": post.get("scikit-learn"),
        "note": "sklearn imports confined to pre_action training/corpus scripts only.",
    }
    ENV_LOCK.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    print(json.dumps(lock, indent=2))
    return 0 if lock["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
