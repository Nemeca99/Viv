"""Focused tests for the deterministic support_core CPU boundary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
if str(FOUNDATION) not in sys.path:
    sys.path.insert(0, str(FOUNDATION))

from lib.support_core import (  # noqa: E402
    cache_summary,
    diagnostic_report,
    health_summary,
    make_cache_entry,
    module_status,
    redact_text,
)


def main() -> int:
    healthy = health_summary(
        [
            {"name": "venv", "ok": True, "detail": "available"},
            {"name": "foundation", "status": "PASS", "detail": "loaded"},
        ]
    )
    degraded = health_summary([{"name": "cache", "ok": False, "detail": "stale"}])
    critical = health_summary([{"name": "security", "ok": False, "critical": True}])
    assert healthy["state"] == "HEALTHY", healthy
    assert degraded["state"] == "DEGRADED", degraded
    assert critical["state"] == "CRITICAL", critical

    first = make_cache_entry("cached fragment", cache_id="cache-one", source="fixture", hit=True)
    second = make_cache_entry("another fragment", cache_id="cache-two", source="fixture", hit=False)
    summary = cache_summary([first, second])
    assert summary["state"] == "VERIFIED", summary
    assert summary["entry_count"] == 2 and summary["hit_rate"] == 0.5, summary
    tampered = {**first, "payload": "tampered"}
    assert cache_summary([tampered])["state"] == "PARTIAL"

    redacted = redact_text("Email user@example.com or call 555-123-4567.")
    assert redacted["changed"] is True, redacted
    assert "user@example.com" not in redacted["text"], redacted
    assert "555-123-4567" not in redacted["text"], redacted

    report = diagnostic_report(
        [{"name": "venv", "ok": True}],
        [first, second],
        sample_text="user@example.com",
    )
    assert report["ok"] is True and report["state"] == "HEALTHY", report
    assert report["live_probe_performed"] is False, report
    assert report["writes_performed"] is False, report
    assert module_status()["llm_authority"] is False

    print(
        json.dumps(
            {
                "ok": True,
                "healthy": healthy["state"],
                "degraded": degraded["state"],
                "critical": critical["state"],
                "cache": summary["state"],
                "hit_rate": summary["hit_rate"],
                "redactions": redacted["redactions"],
                "writes_performed": False,
                "execution_performed": False,
                "llm_authority": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
