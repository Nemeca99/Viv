#!/usr/bin/env python3
"""One-shot, evidence-preserving repair for the known line-647 ledger fork."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "artifacts" / "audit" / "security_training_events.jsonl"
RECOVERY = ROOT / "artifacts" / "audit" / "security_training_ledger_recovery"
EXPECTED_SHA256 = "6e186af99471dfa1bc790bed5b45bdf890228c16ff181b24789d0021936f482d"
EXPECTED_LINES = 647
BACKUP_SNAPSHOT = "c111a143267f5f077d5162253502d80f9a12014680b655508e571bdae3bf91df"


def stable(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    original = LEDGER.read_bytes()
    original_hash = digest(original)
    if original_hash != EXPECTED_SHA256:
        raise SystemExit(f"refusing unexpected ledger sha256:{original_hash}")
    rows = [json.loads(line) for line in original.decode("utf-8").splitlines() if line]
    if len(rows) != EXPECTED_LINES:
        raise SystemExit(f"refusing unexpected ledger line count:{len(rows)}")

    previous = ""
    for index, row in enumerate(rows[:646], start=1):
        claimed = row.pop("event_hash")
        if row["previous_event_hash"] != previous or digest(stable(row)) != claimed:
            raise SystemExit(f"prefix verification failed at line:{index}")
        row["event_hash"] = claimed
        previous = claimed

    fork = rows[646]
    stale_parent = fork["previous_event_hash"]
    expected_stale_parent = rows[644]["event_hash"]
    if stale_parent != expected_stale_parent:
        raise SystemExit("line 647 is not the known concurrent-writer fork")
    fork["previous_event_hash"] = rows[645]["event_hash"]
    fork.pop("event_hash")
    fork["event_hash"] = digest(stable(fork))

    repaired = b"\n".join(stable(row) for row in rows) + b"\n"
    archive = RECOVERY / f"original_{original_hash}.jsonl"
    if archive.exists() and archive.read_bytes() != original:
        raise SystemExit("recovery archive collision")
    atomic_write(archive, original)
    atomic_write(LEDGER, repaired)
    manifest = {
        "schema_version": "security_training_ledger_recovery_v1",
        "reason": "cross_process_cached_head_fork",
        "repaired_line": 647,
        "original_sha256": original_hash,
        "repaired_sha256": digest(repaired),
        "original_event_hash": json.loads(original.decode("utf-8").splitlines()[646])[
            "event_hash"
        ],
        "repaired_event_hash": rows[646]["event_hash"],
        "original_archive": str(archive).replace("\\", "/"),
        "backup_snapshot": BACKUP_SNAPSHOT,
    }
    atomic_write(RECOVERY / "recovery_20260723.json", stable(manifest) + b"\n")
    print(json.dumps({"ok": True, **manifest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
