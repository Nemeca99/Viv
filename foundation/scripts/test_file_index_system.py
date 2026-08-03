#!/usr/bin/env python3
"""Focused regression checks for file_index_system scan idempotency."""
from __future__ import annotations

import tempfile
from pathlib import Path

import file_index_system as fis


def _make_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_upsert_is_idempotent_for_same_path() -> None:
    with tempfile.TemporaryDirectory(prefix="fis_upsert_") as td:
        root = Path(td)
        db_path = root / "index.db"
        target = root / "same.txt"
        _make_file(target, b"abc")
        st = target.stat()

        conn = fis._connect_db(db_path)
        try:
            first = fis._upsert_file_row(
                conn,
                path=target,
                root=root,
                size=int(st.st_size),
                mtime_ns=int(st.st_mtime_ns),
                ctime_ns=int(st.st_ctime_ns),
                now_utc=fis._utc_now(),
                scan_id="scan-a",
            )
            second = fis._upsert_file_row(
                conn,
                path=target,
                root=root,
                size=int(st.st_size),
                mtime_ns=int(st.st_mtime_ns),
                ctime_ns=int(st.st_ctime_ns),
                now_utc=fis._utc_now(),
                scan_id="scan-a",
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM files WHERE path = ?", (fis._safe_path_text(target),)).fetchone()
            assert first == (True, True), first
            assert second == (False, False), second
            assert int(count[0]) == 1, count
        finally:
            conn.close()


def test_scan_resume_reprocess_is_safe() -> None:
    with tempfile.TemporaryDirectory(prefix="fis_resume_") as td:
        root = Path(td)
        scan_root = root / "scan_root"
        db_path = root / "index.db"
        target = scan_root / "resume.txt"
        _make_file(target, b"resume")

        conn = fis._connect_db(db_path)
        try:
            cfg1 = fis.ScanConfig(
                roots=[scan_root],
                include_ext=set(),
                exclude_ext=set(),
                exclude_paths=[],
                use_default_excludes=False,
                skip_files_over_bytes=None,
                hash_candidates_limit=None,
                hash_workers=1,
                min_hash_size_bytes=1,
                resume_scan_id=None,
                checkpoint_every=500,
            )
            first = fis._scan_index(
                conn,
                mode="scan_update",
                cfg=cfg1,
                prune_missing=False,
                batch_commit_every=10,
            )

            cfg2 = fis.ScanConfig(
                roots=[scan_root],
                include_ext=set(),
                exclude_ext=set(),
                exclude_paths=[],
                use_default_excludes=False,
                skip_files_over_bytes=None,
                hash_candidates_limit=None,
                hash_workers=1,
                min_hash_size_bytes=1,
                resume_scan_id=str(first["scan_id"]),
                checkpoint_every=500,
            )
            second = fis._scan_index(
                conn,
                mode="scan_update",
                cfg=cfg2,
                prune_missing=False,
                batch_commit_every=10,
            )

            assert int(first["new_files"]) == 1, first
            assert int(second["stat_errors"]) == 0, second
            rows = conn.execute("SELECT COUNT(*) FROM files").fetchone()
            assert int(rows[0]) == 1, rows
        finally:
            conn.close()


def main() -> int:
    test_upsert_is_idempotent_for_same_path()
    test_scan_resume_reprocess_is_safe()
    print("test_file_index_system: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
