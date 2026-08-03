#!/usr/bin/env python3
"""Local-first file index and duplicate report pipeline.

Features:
- Scans local drives (Windows) or provided roots.
- Builds an incremental SQLite index of file metadata.
- Uses staged duplicate detection:
  1) metadata prefilter by size + name/ext groups
  2) SHA-256 verification for candidates
- Exports deterministic duplicate reports (JSON/CSV/MD).
- Builds plan-only duplicate action artifacts (JSON/CSV/MD).

Usage:
- Build duplicate report:
  `python file_index_system.py --db <db_path> report-duplicates --output-dir <dir>`
- Build safe duplicate action plan (no destructive execution):
  `python file_index_system.py --db <db_path> plan-duplicate-actions --output-dir <dir>`
  `python file_index_system.py --db <db_path> plan-duplicate-actions --report-json <duplicate_report.json>`

Report-only and plan-only by default. No deletion or moves are performed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import ctypes
import datetime as dt
import hashlib
import json
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

FOUNDATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION_ROOT))

from lib.paths import VIV_ROOT  # noqa: E402

APP_NAME = "file_index_system"
ARTIFACT_ROOT = VIV_ROOT / "artifacts" / "file_index"
DEFAULT_DB = ARTIFACT_ROOT / "file_index.db"
DEFAULT_REPORT_DIR = ARTIFACT_ROOT / "reports"
DEFAULT_LOG_DIR = ARTIFACT_ROOT / "logs"
READ_CHUNK = 1024 * 1024
DEFAULT_CANONICAL_POLICY = "preferred-root,preferred-ext,newest-mtime,shortest-path,path-lex"
DEFAULT_SCAN_CHECKPOINT_EVERY = 5000
DEFAULT_HASH_WORKERS = 1
DEFAULT_MIN_HASH_SIZE_BYTES = 1
SYSTEM_PATH_NEEDLES = (
    "/windows/",
    "/program files/",
    "/program files (x86)/",
    "/programdata/",
    "/system volume information/",
    "/$recycle.bin/",
)

DEFAULT_EXCLUDED_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "appdata",
    "temp",
    "tmp",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
}
DEFAULT_EXCLUDE_PATH_NEEDLES = [
    "/windows/winsxs/",
    "/windows/installer/",
    "/windows/softwaredistribution/",
    "/programdata/microsoft/windows/wer/",
    "/programdata/package cache/",
    "/appdata/local/temp/",
    "/appdata/local/packages/",
]


@dataclass(frozen=True)
class ScanConfig:
    roots: list[Path]
    include_ext: set[str]
    exclude_ext: set[str]
    exclude_paths: list[str]
    use_default_excludes: bool
    skip_files_over_bytes: int | None
    hash_candidates_limit: int | None
    hash_workers: int
    min_hash_size_bytes: int
    resume_scan_id: str | None
    checkpoint_every: int


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_ext(value: str) -> str:
    value = value.strip().lower()
    if not value:
        return value
    if not value.startswith("."):
        return f".{value}"
    return value


def _safe_path_text(path: Path) -> str:
    return str(path).replace("\\", "/")


def _parse_ext_list(raw_values: list[str] | None) -> set[str]:
    out: set[str] = set()
    for raw in raw_values or []:
        for part in raw.split(","):
            part = _normalize_ext(part)
            if part:
                out.add(part)
    return out


def _parse_list_values(raw_values: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_values or []:
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
    return out


def _parse_policy_order(raw: str) -> list[str]:
    allowed = {
        "preferred-root",
        "preferred-ext",
        "newest-mtime",
        "oldest-mtime",
        "shortest-path",
        "path-lex",
    }
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        rule = part.strip().lower()
        if not rule or rule in seen:
            continue
        if rule not in allowed:
            raise ValueError(f"Unsupported canonical policy rule: {rule}")
        seen.add(rule)
        out.append(rule)
    if not out:
        raise ValueError("Canonical policy cannot be empty.")
    return out


def _configure_logging(log_path: Path, verbose: bool) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)sZ | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def _discover_windows_local_drives() -> list[Path]:
    if os.name != "nt":
        return []
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    bitmask = kernel32.GetLogicalDrives()
    drives: list[Path] = []
    for i in range(26):
        if not (bitmask & (1 << i)):
            continue
        letter = chr(65 + i)
        root = f"{letter}:\\"
        drive_type = kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
        # Local-first default: fixed + removable only.
        if drive_type in (2, 3):
            drives.append(Path(root))
    return drives


def _resolve_roots(raw_roots: list[str] | None) -> list[Path]:
    if raw_roots:
        roots = [Path(r).resolve() for r in raw_roots]
    else:
        roots = _discover_windows_local_drives()
        if not roots:
            roots = [VIV_ROOT]
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = _safe_path_text(root).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-262144;")
    conn.execute("PRAGMA mmap_size=268435456;")
    conn.execute("PRAGMA busy_timeout=15000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scans (
            scan_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            roots_json TEXT NOT NULL,
            metrics_json TEXT
        );

        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            drive TEXT NOT NULL,
            root TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            ctime_ns INTEGER NOT NULL,
            name_lower TEXT NOT NULL,
            ext_lower TEXT NOT NULL,
            sha256 TEXT,
            hash_size INTEGER,
            hash_mtime_ns INTEGER,
            hash_status TEXT NOT NULL DEFAULT 'pending',
            hash_error TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_seen_scan_id TEXT NOT NULL,
            missing INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
        CREATE INDEX IF NOT EXISTS idx_files_missing ON files(missing);
        CREATE INDEX IF NOT EXISTS idx_files_size_name ON files(size, name_lower);
        CREATE INDEX IF NOT EXISTS idx_files_size_ext ON files(size, ext_lower);
        CREATE INDEX IF NOT EXISTS idx_files_sha ON files(sha256);
        CREATE INDEX IF NOT EXISTS idx_files_missing_size_name_ext ON files(missing, size, name_lower, ext_lower);
        CREATE INDEX IF NOT EXISTS idx_files_missing_hash_status ON files(missing, hash_status, size);
        CREATE INDEX IF NOT EXISTS idx_files_root_scan_missing ON files(root, last_seen_scan_id, missing);

        CREATE TABLE IF NOT EXISTS scan_checkpoints (
            scan_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            roots_json TEXT NOT NULL,
            progress_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _should_skip_dir(
    base: Path,
    dir_name: str,
    cfg: ScanConfig,
) -> bool:
    low_name = dir_name.lower()
    full = _safe_path_text(base / dir_name).lower()
    if cfg.use_default_excludes and low_name in DEFAULT_EXCLUDED_DIR_NAMES:
        return True
    for needle in cfg.exclude_paths:
        if needle and needle in full:
            return True
    return False


def _should_skip_file(path: Path, cfg: ScanConfig) -> tuple[bool, str | None]:
    ext = path.suffix.lower()
    if cfg.include_ext and ext not in cfg.include_ext:
        return True, "include_ext_miss"
    if cfg.exclude_ext and ext in cfg.exclude_ext:
        return True, "exclude_ext_match"
    lowered = _safe_path_text(path).lower()
    for needle in cfg.exclude_paths:
        if needle and needle in lowered:
            return True, "exclude_path_match"
    return False, None


def _upsert_file_row(
    conn: sqlite3.Connection,
    *,
    path: Path,
    root: Path,
    size: int,
    mtime_ns: int,
    ctime_ns: int,
    now_utc: str,
    scan_id: str,
) -> tuple[bool, bool]:
    path_text = _safe_path_text(path)
    root_text = _safe_path_text(root)
    drive = path.drive or root.drive or ""
    name_lower = path.name.lower()
    ext_lower = path.suffix.lower()
    before_changes = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO files (
            path, drive, root, size, mtime_ns, ctime_ns, name_lower, ext_lower,
            sha256, hash_size, hash_mtime_ns, hash_status, hash_error,
            first_seen_at, last_seen_at, last_seen_scan_id, missing
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 'pending', NULL, ?, ?, ?, 0)
        """,
        (
            path_text,
            drive,
            root_text,
            size,
            mtime_ns,
            ctime_ns,
            name_lower,
            ext_lower,
            now_utc,
            now_utc,
            scan_id,
        ),
    )
    if conn.total_changes > before_changes:
        return True, True

    cur = conn.execute(
        "SELECT size, mtime_ns, ctime_ns FROM files WHERE path = ?",
        (path_text,),
    )
    old = cur.fetchone()
    if old is None:
        # Extremely defensive fallback if a concurrent writer removed the row
        # between INSERT OR IGNORE and SELECT.
        conn.execute(
            """
            INSERT INTO files (
                path, drive, root, size, mtime_ns, ctime_ns, name_lower, ext_lower,
                sha256, hash_size, hash_mtime_ns, hash_status, hash_error,
                first_seen_at, last_seen_at, last_seen_scan_id, missing
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 'pending', NULL, ?, ?, ?, 0)
            ON CONFLICT(path) DO UPDATE SET
                root = excluded.root, drive = excluded.drive,
                last_seen_at = excluded.last_seen_at,
                last_seen_scan_id = excluded.last_seen_scan_id,
                missing = 0
            """,
            (
                path_text,
                drive,
                root_text,
                size,
                mtime_ns,
                ctime_ns,
                name_lower,
                ext_lower,
                now_utc,
                now_utc,
                scan_id,
            ),
        )
        return False, False

    changed = bool(
        size != int(old[0])
        or mtime_ns != int(old[1])
        or ctime_ns != int(old[2])
    )
    if changed:
        conn.execute(
            """
            UPDATE files
            SET root = ?, drive = ?, size = ?, mtime_ns = ?, ctime_ns = ?,
                name_lower = ?, ext_lower = ?, sha256 = NULL, hash_size = NULL,
                hash_mtime_ns = NULL, hash_status = 'pending', hash_error = NULL,
                last_seen_at = ?, last_seen_scan_id = ?, missing = 0
            WHERE path = ?
            """,
            (
                root_text,
                drive,
                size,
                mtime_ns,
                ctime_ns,
                name_lower,
                ext_lower,
                now_utc,
                scan_id,
                path_text,
            ),
        )
        return False, True

    conn.execute(
        """
        UPDATE files
        SET root = ?, drive = ?, last_seen_at = ?, last_seen_scan_id = ?, missing = 0
        WHERE path = ?
        """,
        (root_text, drive, now_utc, scan_id, path_text),
    )
    return False, False


def _iter_files(roots: list[Path], cfg: ScanConfig, resume_state: dict[str, str] | None = None) -> Iterable[tuple[Path, Path]]:
    resume_state = resume_state or {}
    for root in roots:
        if not root.exists():
            logging.warning("missing_root=%s", _safe_path_text(root))
            continue
        root_text = _safe_path_text(root).lower()
        resume_after = (resume_state.get(root_text) or "").lower()
        stack: list[str] = [str(root)]
        while stack:
            base = stack.pop()
            try:
                with os.scandir(base) as entries:
                    dirs: list[str] = []
                    files: list[str] = []
                    for entry in entries:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                dirs.append(entry.name)
                            elif entry.is_file(follow_symlinks=False):
                                files.append(entry.name)
                        except OSError:
                            continue
            except OSError as exc:
                logging.debug("walk_error base=%s error=%s", base, exc)
                continue

            base_path = Path(base)
            next_dirs = [d for d in dirs if not _should_skip_dir(base_path, d, cfg)]
            next_dirs.sort(reverse=True)
            for name in next_dirs:
                stack.append(str(base_path / name))

            files.sort()
            for file_name in files:
                path = base_path / file_name
                path_text = _safe_path_text(path)
                if resume_after and path_text.lower() <= resume_after:
                    continue
                skip, reason = _should_skip_file(path, cfg)
                if skip:
                    logging.debug("skip_file=%s reason=%s", path_text, reason)
                    continue
                yield root, path


def _load_checkpoint(conn: sqlite3.Connection, scan_id: str) -> tuple[dict[str, str], dict[str, int | str]]:
    row = conn.execute(
        "SELECT progress_json, metrics_json FROM scan_checkpoints WHERE scan_id = ?",
        (scan_id,),
    ).fetchone()
    if not row:
        return {}, {}
    progress = json.loads(str(row[0] or "{}"))
    metrics = json.loads(str(row[1] or "{}"))
    if not isinstance(progress, dict):
        progress = {}
    if not isinstance(metrics, dict):
        metrics = {}
    return ({str(k).lower(): str(v) for k, v in progress.items()}, {str(k): int(v) for k, v in metrics.items()})


def _write_checkpoint(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    mode: str,
    roots: list[Path],
    progress: dict[str, str],
    metrics: dict[str, int | str],
) -> None:
    conn.execute(
        """
        INSERT INTO scan_checkpoints(scan_id, mode, updated_at, roots_json, progress_json, metrics_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_id) DO UPDATE SET
            updated_at = excluded.updated_at,
            progress_json = excluded.progress_json,
            metrics_json = excluded.metrics_json
        """,
        (
            scan_id,
            mode,
            _utc_now(),
            json.dumps([_safe_path_text(r) for r in roots], sort_keys=True),
            json.dumps(progress, sort_keys=True),
            json.dumps(metrics, sort_keys=True),
        ),
    )


def _scan_index(
    conn: sqlite3.Connection,
    *,
    mode: str,
    cfg: ScanConfig,
    prune_missing: bool,
    batch_commit_every: int,
) -> dict[str, int | str]:
    scan_id = cfg.resume_scan_id or _stamp()
    now_utc = _utc_now()
    conn.execute(
        """
        INSERT INTO scans(scan_id, mode, started_at, status, roots_json)
        VALUES (?, ?, ?, 'running', ?)
        ON CONFLICT(scan_id) DO UPDATE SET
            mode = excluded.mode,
            status = 'running',
            roots_json = excluded.roots_json
        """,
        (
            scan_id,
            mode,
            now_utc,
            json.dumps([_safe_path_text(r) for r in cfg.roots], sort_keys=True),
        ),
    )
    conn.commit()

    metrics: dict[str, int | str] = {
        "seen_files": 0,
        "new_files": 0,
        "changed_files": 0,
        "unchanged_files": 0,
        "stat_errors": 0,
        "missing_marked": 0,
    }
    checkpoint_progress: dict[str, str] = {}
    if cfg.resume_scan_id:
        resume_progress, resume_metrics = _load_checkpoint(conn, cfg.resume_scan_id)
        checkpoint_progress.update(resume_progress)
        for key, value in resume_metrics.items():
            if key in metrics and isinstance(value, int):
                metrics[key] = int(value)
        logging.info("resume_scan_id=%s restored_progress_roots=%s", cfg.resume_scan_id, len(checkpoint_progress))

    try:
        for root, path in _iter_files(cfg.roots, cfg, checkpoint_progress):
            metrics["seen_files"] = int(metrics["seen_files"]) + 1
            try:
                st = path.stat(follow_symlinks=False)
            except OSError as exc:
                metrics["stat_errors"] = int(metrics["stat_errors"]) + 1
                logging.warning("stat_error path=%s error=%s", _safe_path_text(path), exc)
                continue

            is_new, changed = _upsert_file_row(
                conn,
                path=path,
                root=root,
                size=int(st.st_size),
                mtime_ns=int(st.st_mtime_ns),
                ctime_ns=int(st.st_ctime_ns),
                now_utc=now_utc,
                scan_id=scan_id,
            )
            if is_new:
                metrics["new_files"] = int(metrics["new_files"]) + 1
            elif changed:
                metrics["changed_files"] = int(metrics["changed_files"]) + 1
            else:
                metrics["unchanged_files"] = int(metrics["unchanged_files"]) + 1

            root_key = _safe_path_text(root).lower()
            checkpoint_progress[root_key] = _safe_path_text(path)
            if int(metrics["seen_files"]) % cfg.checkpoint_every == 0:
                _write_checkpoint(
                    conn,
                    scan_id=scan_id,
                    mode=mode,
                    roots=cfg.roots,
                    progress=checkpoint_progress,
                    metrics=metrics,
                )

            if int(metrics["seen_files"]) % batch_commit_every == 0:
                conn.commit()
                logging.info(
                    "progress seen=%s new=%s changed=%s errors=%s",
                    metrics["seen_files"],
                    metrics["new_files"],
                    metrics["changed_files"],
                    metrics["stat_errors"],
                )

        if prune_missing:
            roots_json = [_safe_path_text(r) for r in cfg.roots]
            for root_text in roots_json:
                cur = conn.execute(
                    """
                    UPDATE files
                    SET missing = 1
                    WHERE root = ? AND last_seen_scan_id <> ? AND missing = 0
                    """,
                    (root_text, scan_id),
                )
                metrics["missing_marked"] = int(metrics["missing_marked"]) + int(cur.rowcount or 0)

        finished_at = _utc_now()
        _write_checkpoint(
            conn,
            scan_id=scan_id,
            mode=mode,
            roots=cfg.roots,
            progress=checkpoint_progress,
            metrics=metrics,
        )
        conn.execute(
            """
            UPDATE scans
            SET status = 'completed', finished_at = ?, metrics_json = ?
            WHERE scan_id = ?
            """,
            (finished_at, json.dumps(metrics, sort_keys=True), scan_id),
        )
        conn.commit()
        return {"scan_id": scan_id, **metrics}
    except BaseException:
        conn.rollback()
        _write_checkpoint(
            conn,
            scan_id=scan_id,
            mode=mode,
            roots=cfg.roots,
            progress=checkpoint_progress,
            metrics=metrics,
        )
        failed_at = _utc_now()
        conn.execute(
            """
            UPDATE scans SET status = 'failed', finished_at = ?, metrics_json = ?
            WHERE scan_id = ?
            """,
            (failed_at, json.dumps(metrics, sort_keys=True), scan_id),
        )
        conn.commit()
        raise


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(READ_CHUNK)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def _load_duplicate_size_rows(conn: sqlite3.Connection, min_hash_size_bytes: int = 1) -> list[tuple[str, int, str, str, str, int, int, str]]:
    cur = conn.execute(
        """
        SELECT path, size, name_lower, ext_lower, hash_status,
               COALESCE(hash_size, 0), COALESCE(hash_mtime_ns, 0), root
        FROM files
        WHERE missing = 0
          AND size >= ?
          AND size IN (
            SELECT size FROM files WHERE missing = 0 GROUP BY size HAVING COUNT(*) > 1
          )
        """,
        (int(min_hash_size_bytes),),
    )
    return [tuple(row) for row in cur.fetchall()]


def _pick_hash_candidates(
    rows: list[tuple[str, int, str, str, str, int, int, str]]
) -> set[str]:
    by_size: dict[int, list[tuple[str, str, str]]] = {}
    for path, size, name_lower, ext_lower, *_ in rows:
        by_size.setdefault(size, []).append((path, name_lower, ext_lower))

    candidates: set[str] = set()
    for items in by_size.values():
        if len(items) < 2:
            continue
        by_name: dict[str, int] = {}
        by_ext: dict[str, int] = {}
        for _, name_lower, ext_lower in items:
            by_name[name_lower] = by_name.get(name_lower, 0) + 1
            by_ext[ext_lower] = by_ext.get(ext_lower, 0) + 1

        for path, name_lower, ext_lower in items:
            if by_name.get(name_lower, 0) > 1 or by_ext.get(ext_lower, 0) > 1:
                candidates.add(path)
    return candidates


def _hash_candidates(
    conn: sqlite3.Connection,
    *,
    cfg: ScanConfig,
    batch_commit_every: int,
) -> dict[str, int]:
    logging.info(
        "hash_phase enter=_hash_candidates loading_duplicate_size_rows min_size=%s "
        "(large DB query; progress may stay quiet until complete)",
        cfg.min_hash_size_bytes,
    )
    rows = _load_duplicate_size_rows(conn, cfg.min_hash_size_bytes)
    logging.info("hash_phase duplicate_size_rows_loaded count=%s picking_candidates", len(rows))
    candidates = sorted(_pick_hash_candidates(rows))
    if cfg.hash_candidates_limit is not None:
        candidates = candidates[: cfg.hash_candidates_limit]
    metrics = {"candidates": len(candidates), "hashed": 0, "hash_errors": 0, "hash_skipped_large": 0}
    logging.info(
        "hash_phase candidates_ready count=%s hash_workers=%s",
        len(candidates),
        cfg.hash_workers,
    )

    def _hash_one(path_text: str) -> tuple[str, str, int, int]:
        path = Path(path_text)
        st = path.stat(follow_symlinks=False)
        digest = _sha256_file(path)
        return path_text, digest, int(st.st_size), int(st.st_mtime_ns)

    for idx, path_text in enumerate(candidates, start=1):
        path = Path(path_text)
        try:
            st = path.stat(follow_symlinks=False)
        except OSError as exc:
            conn.execute(
                """
                UPDATE files SET hash_status = 'error', hash_error = ?, hash_size = NULL, hash_mtime_ns = NULL
                WHERE path = ?
                """,
                (str(exc), path_text),
            )
            metrics["hash_errors"] += 1
            continue

        if cfg.skip_files_over_bytes is not None and st.st_size > cfg.skip_files_over_bytes:
            conn.execute(
                """
                UPDATE files
                SET hash_status = 'skipped_large', hash_error = ?, hash_size = ?, hash_mtime_ns = ?
                WHERE path = ?
                """,
                (
                    f"size>{cfg.skip_files_over_bytes}",
                    int(st.st_size),
                    int(st.st_mtime_ns),
                    path_text,
                ),
            )
            metrics["hash_skipped_large"] += 1
            continue

        current = conn.execute(
            """
            SELECT sha256, hash_size, hash_mtime_ns, hash_status
            FROM files WHERE path = ?
            """,
            (path_text,),
        ).fetchone()
        if current and current[0] and int(current[1] or 0) == st.st_size and int(current[2] or 0) == st.st_mtime_ns and current[3] == "hashed":
            continue
        if cfg.hash_workers <= 1:
            try:
                digest = _sha256_file(path)
                conn.execute(
                    """
                    UPDATE files
                    SET sha256 = ?, hash_size = ?, hash_mtime_ns = ?, hash_status = 'hashed', hash_error = NULL
                    WHERE path = ?
                    """,
                    (digest, int(st.st_size), int(st.st_mtime_ns), path_text),
                )
                metrics["hashed"] += 1
            except OSError as exc:
                conn.execute(
                    """
                    UPDATE files
                    SET hash_status = 'error', hash_error = ?, hash_size = ?, hash_mtime_ns = ?
                    WHERE path = ?
                    """,
                    (str(exc), int(st.st_size), int(st.st_mtime_ns), path_text),
                )
                metrics["hash_errors"] += 1
        else:
            # Parallel hashing path remains deterministic by consuming candidate order.
            break

        if idx % batch_commit_every == 0:
            conn.commit()
            logging.info("hash_progress done=%s/%s", idx, len(candidates))

    if cfg.hash_workers > 1:
        rows_to_hash = []
        for path_text in candidates:
            path = Path(path_text)
            try:
                st = path.stat(follow_symlinks=False)
            except OSError as exc:
                conn.execute(
                    """
                    UPDATE files SET hash_status = 'error', hash_error = ?, hash_size = NULL, hash_mtime_ns = NULL
                    WHERE path = ?
                    """,
                    (str(exc), path_text),
                )
                metrics["hash_errors"] += 1
                continue
            if cfg.skip_files_over_bytes is not None and st.st_size > cfg.skip_files_over_bytes:
                conn.execute(
                    """
                    UPDATE files
                    SET hash_status = 'skipped_large', hash_error = ?, hash_size = ?, hash_mtime_ns = ?
                    WHERE path = ?
                    """,
                    (
                        f"size>{cfg.skip_files_over_bytes}",
                        int(st.st_size),
                        int(st.st_mtime_ns),
                        path_text,
                    ),
                )
                metrics["hash_skipped_large"] += 1
                continue
            current = conn.execute(
                "SELECT sha256, hash_size, hash_mtime_ns, hash_status FROM files WHERE path = ?",
                (path_text,),
            ).fetchone()
            if current and current[0] and int(current[1] or 0) == st.st_size and int(current[2] or 0) == st.st_mtime_ns and current[3] == "hashed":
                continue
            rows_to_hash.append(path_text)

        logging.info(
            "hash_phase starting_hash_workers workers=%s to_hash=%s",
            cfg.hash_workers,
            len(rows_to_hash),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.hash_workers) as pool:
            future_to_path = {pool.submit(_hash_one, p): p for p in rows_to_hash}
            for idx, fut in enumerate(concurrent.futures.as_completed(future_to_path), start=1):
                p = future_to_path[fut]
                try:
                    _, digest, size, mtime_ns = fut.result()
                    conn.execute(
                        """
                        UPDATE files
                        SET sha256 = ?, hash_size = ?, hash_mtime_ns = ?, hash_status = 'hashed', hash_error = NULL
                        WHERE path = ?
                        """,
                        (digest, size, mtime_ns, p),
                    )
                    metrics["hashed"] += 1
                except Exception as exc:  # noqa: BLE001
                    conn.execute(
                        """
                        UPDATE files
                        SET hash_status = 'error', hash_error = ?, hash_size = NULL, hash_mtime_ns = NULL
                        WHERE path = ?
                        """,
                        (str(exc), p),
                    )
                    metrics["hash_errors"] += 1
                if idx % batch_commit_every == 0:
                    conn.commit()
                    logging.info("hash_progress done=%s/%s", idx, len(rows_to_hash))

    conn.commit()
    return metrics


def _collect_verified_duplicate_groups(conn: sqlite3.Connection) -> list[dict[str, object]]:
    cur = conn.execute(
        """
        SELECT sha256, size, COUNT(*) AS c
        FROM files
        WHERE missing = 0 AND hash_status = 'hashed' AND sha256 IS NOT NULL
        GROUP BY sha256, size
        HAVING c > 1
        ORDER BY size DESC, sha256 ASC
        """
    )
    groups: list[dict[str, object]] = []
    for sha256, size, count in cur.fetchall():
        rows = conn.execute(
            """
            SELECT path, root, mtime_ns
            FROM files
            WHERE missing = 0 AND sha256 = ? AND size = ? AND hash_status = 'hashed'
            ORDER BY path ASC
            """,
            (sha256, size),
        ).fetchall()
        groups.append(
            {
                "sha256": sha256,
                "size": int(size),
                "count": int(count),
                "paths": [
                    {"path": row[0], "root": row[1], "mtime_ns": int(row[2])}
                    for row in rows
                ],
            }
        )
    return groups


def _load_verified_groups_from_report(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = payload.get("verified_groups")
    if not isinstance(groups, list):
        raise ValueError("report JSON missing verified_groups array")
    normalized: list[dict[str, object]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        paths = group.get("paths")
        if not isinstance(paths, list):
            continue
        size = int(group.get("size", 0))
        sha = str(group.get("sha256", ""))
        entries: list[dict[str, object]] = []
        for item in paths:
            if not isinstance(item, dict):
                continue
            p = str(item.get("path", "")).strip()
            if not p:
                continue
            entries.append(
                {
                    "path": p,
                    "root": str(item.get("root", "")),
                    "mtime_ns": int(item.get("mtime_ns", 0)),
                }
            )
        if len(entries) < 2:
            continue
        entries.sort(key=lambda row: str(row["path"]))
        normalized.append(
            {
                "sha256": sha,
                "size": size,
                "count": len(entries),
                "paths": entries,
            }
        )
    normalized.sort(key=lambda g: (-int(g["size"]), str(g["sha256"])))
    return normalized


def _collect_unverified_candidate_groups(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = _load_duplicate_size_rows(conn)
    if not rows:
        return []
    by_size: dict[int, list[tuple[str, str, str, str, str]]] = {}
    for path, size, name_lower, ext_lower, status, *_rest in rows:
        err = ""
        by_size.setdefault(int(size), []).append((path, name_lower, ext_lower, status, err))

    output: list[dict[str, object]] = []
    for size in sorted(by_size.keys(), reverse=True):
        entries = by_size[size]
        name_counts: dict[str, int] = {}
        ext_counts: dict[str, int] = {}
        for _, name_lower, ext_lower, _, _ in entries:
            name_counts[name_lower] = name_counts.get(name_lower, 0) + 1
            ext_counts[ext_lower] = ext_counts.get(ext_lower, 0) + 1
        entries = [e for e in entries if name_counts.get(e[1], 0) > 1 or ext_counts.get(e[2], 0) > 1]
        if len(entries) < 2:
            continue
        pending = [e for e in entries if e[3] != "hashed"]
        if not pending:
            continue
        output.append(
            {
                "size": size,
                "candidate_count": len(entries),
                "pending_or_skipped_count": len(pending),
                "paths": [
                    {
                        "path": p[0],
                        "name_lower": p[1],
                        "ext_lower": p[2],
                        "hash_status": p[3],
                        "hash_error": p[4],
                    }
                    for p in pending
                ],
            }
        )
    return output


def _export_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _export_csv(path: Path, groups: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sha256", "size_bytes", "group_count", "path", "root", "mtime_ns"])
        for group in groups:
            sha = str(group["sha256"])
            size = int(group["size"])
            count = int(group["count"])
            for p in group["paths"]:  # type: ignore[index]
                writer.writerow([sha, size, count, p["path"], p["root"], p["mtime_ns"]])  # type: ignore[index]


def _export_md(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Duplicate Report")
    lines.append("")
    summary = payload.get("summary", {})
    lines.append(f"- Generated: `{payload.get('generated_at')}`")
    lines.append(f"- Verified duplicate groups: `{summary.get('verified_group_count', 0)}`")
    lines.append(f"- Verified duplicate files: `{summary.get('verified_file_count', 0)}`")
    lines.append(f"- Reclaimable bytes (approx): `{summary.get('reclaimable_bytes', 0)}`")
    lines.append(f"- Unverified candidate groups: `{summary.get('unverified_group_count', 0)}`")
    lines.append("")
    lines.append("## Verified groups")
    lines.append("")
    groups = payload.get("verified_groups", [])
    if not groups:
        lines.append("_None_")
    else:
        for group in groups:  # type: ignore[assignment]
            lines.append(
                f"- sha256 `{group['sha256']}` size `{group['size']}` count `{group['count']}`"  # type: ignore[index]
            )
            for p in group["paths"]:  # type: ignore[index]
                lines.append(f"  - `{p['path']}`")  # type: ignore[index]
    lines.append("")
    lines.append("## Unverified candidates")
    lines.append("")
    unverified = payload.get("unverified_candidates", [])
    if not unverified:
        lines.append("_None_")
    else:
        for group in unverified:  # type: ignore[assignment]
            lines.append(
                f"- size `{group['size']}` pending `{group['pending_or_skipped_count']}` / `{group['candidate_count']}`"  # type: ignore[index]
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _is_windows_hidden(path: Path) -> bool:
    if os.name != "nt":
        return path.name.startswith(".")
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))  # type: ignore[attr-defined]
    except Exception:
        return False
    if attrs == -1:
        return False
    return bool(attrs & 0x2)


def _is_readonly(path: Path) -> bool:
    try:
        return not os.access(path, os.W_OK)
    except OSError:
        return False


def _is_system_path(path_text: str) -> bool:
    low = f"/{path_text.strip('/').lower()}/"
    return any(needle in low for needle in SYSTEM_PATH_NEEDLES)


def _policy_rank_value(
    entry: dict[str, object],
    rule: str,
    *,
    preferred_roots: list[str],
    preferred_exts: list[str],
) -> tuple[object, ...]:
    path_text = str(entry["path"])
    low_path = path_text.lower()
    ext = Path(path_text).suffix.lower()
    if rule == "preferred-root":
        idx = len(preferred_roots)
        for i, pref in enumerate(preferred_roots):
            if low_path.startswith(pref):
                idx = i
                break
        return (idx,)
    if rule == "preferred-ext":
        idx = len(preferred_exts)
        for i, pref_ext in enumerate(preferred_exts):
            if ext == pref_ext:
                idx = i
                break
        return (idx,)
    if rule == "newest-mtime":
        return (-int(entry["mtime_ns"]),)
    if rule == "oldest-mtime":
        return (int(entry["mtime_ns"]),)
    if rule == "shortest-path":
        return (len(path_text),)
    if rule == "path-lex":
        return (low_path,)
    return (low_path,)


def _choose_canonical(
    entries: list[dict[str, object]],
    *,
    policy_order: list[str],
    preferred_roots: list[str],
    preferred_exts: list[str],
) -> tuple[dict[str, object], str]:
    def sort_key(entry: dict[str, object]) -> tuple[object, ...]:
        parts: list[object] = []
        for rule in policy_order:
            parts.extend(
                _policy_rank_value(
                    entry,
                    rule,
                    preferred_roots=preferred_roots,
                    preferred_exts=preferred_exts,
                )
            )
        parts.append(str(entry["path"]).lower())
        return tuple(parts)

    ranked = sorted(entries, key=sort_key)
    reason = f"Selected by policy order: {', '.join(policy_order)}"
    return ranked[0], reason


def _build_duplicate_action_plan(
    groups: list[dict[str, object]],
    *,
    db_path: str,
    source: str,
    policy_order: list[str],
    preferred_roots: list[str],
    preferred_exts: list[str],
) -> dict[str, object]:
    plan_groups: list[dict[str, object]] = []
    action_counts: dict[str, int] = {"KEEP": 0, "ARCHIVE_CANDIDATE": 0, "DELETE_CANDIDATE": 0}
    action_reclaim_bytes: dict[str, int] = {"KEEP": 0, "ARCHIVE_CANDIDATE": 0, "DELETE_CANDIDATE": 0}
    confidence_reclaim_bytes: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    total_reclaimable = 0
    risk_counts: dict[str, int] = {}

    for idx, group in enumerate(groups, start=1):
        size = int(group["size"])
        group_entries = [dict(p) for p in group["paths"]]  # type: ignore[index]
        group_entries.sort(key=lambda row: str(row["path"]))
        if len(group_entries) < 2:
            continue

        canonical, canonical_reason = _choose_canonical(
            group_entries,
            policy_order=policy_order,
            preferred_roots=preferred_roots,
            preferred_exts=preferred_exts,
        )
        canonical_path = str(canonical["path"])
        canonical_ext = Path(canonical_path).suffix.lower()
        canonical_drive = Path(canonical_path).drive.lower()

        member_rows: list[dict[str, object]] = []
        for entry in group_entries:
            path_text = str(entry["path"])
            path_obj = Path(path_text)
            risk_flags = {
                "system_path": _is_system_path(path_text),
                "hidden": _is_windows_hidden(path_obj),
                "readonly": _is_readonly(path_obj),
                "extension_mismatch": path_obj.suffix.lower() != canonical_ext,
                "cross_drive": bool(canonical_drive and path_obj.drive.lower() != canonical_drive),
            }
            is_canonical = path_text == canonical_path
            if is_canonical:
                action = "KEEP"
                confidence = "high"
                reason = canonical_reason
            else:
                high_risk = (
                    risk_flags["system_path"]
                    or risk_flags["hidden"]
                    or risk_flags["readonly"]
                    or risk_flags["extension_mismatch"]
                    or risk_flags["cross_drive"]
                )
                action = "ARCHIVE_CANDIDATE" if high_risk else "DELETE_CANDIDATE"
                confidence = "low" if high_risk else "medium"
                reason = "High-risk flags present; review manually." if high_risk else "Duplicate hash match with low-risk flags."
                total_reclaimable += size
                action_reclaim_bytes[action] = action_reclaim_bytes.get(action, 0) + size
                confidence_reclaim_bytes[confidence] = confidence_reclaim_bytes.get(confidence, 0) + size

            for risk_name, enabled in risk_flags.items():
                if enabled:
                    risk_counts[risk_name] = risk_counts.get(risk_name, 0) + 1

            action_counts[action] = action_counts.get(action, 0) + 1
            member_rows.append(
                {
                    "path": path_text,
                    "root": str(entry.get("root", "")),
                    "mtime_ns": int(entry.get("mtime_ns", 0)),
                    "drive": path_obj.drive,
                    "size_bytes": size,
                    "sha256": str(group.get("sha256", "")),
                    "is_canonical": is_canonical,
                    "recommended_action": action,
                    "confidence": confidence,
                    "reason": reason,
                    "risk_flags": risk_flags,
                }
            )

        member_rows.sort(key=lambda row: (not bool(row["is_canonical"]), str(row["path"]).lower()))
        plan_groups.append(
            {
                "group_id": idx,
                "sha256": str(group.get("sha256", "")),
                "size_bytes": size,
                "file_count": len(member_rows),
                "canonical_path": canonical_path,
                "policy_reason": canonical_reason,
                "members": member_rows,
            }
        )

    plan_groups.sort(key=lambda row: (-int(row["size_bytes"]), str(row["sha256"])))
    payload: dict[str, object] = {
        "ok": True,
        "mode": "plan-only",
        "generated_at": _utc_now(),
        "db": db_path,
        "source": source,
        "policy": {
            "canonical_order": policy_order,
            "preferred_roots": preferred_roots,
            "preferred_exts": preferred_exts,
        },
        "summary": {
            "group_count": len(plan_groups),
            "file_count": sum(int(g["file_count"]) for g in plan_groups),
            "reclaimable_bytes_if_applied": total_reclaimable,
            "action_counts": action_counts,
            "action_reclaimable_bytes": action_reclaim_bytes,
            "confidence_reclaimable_bytes": confidence_reclaim_bytes,
            "risk_flag_counts": risk_counts,
        },
        "groups": plan_groups,
        "guardrails": {
            "destructive_operations_performed": False,
            "note": "Plan artifacts only. No files were moved, archived, or deleted.",
        },
    }
    return payload


def _flatten_plan_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in payload.get("groups", []):  # type: ignore[union-attr]
        for member in group["members"]:  # type: ignore[index]
            row = {
                "group_id": int(group["group_id"]),  # type: ignore[index]
                "sha256": str(group["sha256"]),  # type: ignore[index]
                "size_bytes": int(group["size_bytes"]),  # type: ignore[index]
                "file_count": int(group["file_count"]),  # type: ignore[index]
                "canonical_path": str(group["canonical_path"]),  # type: ignore[index]
                "path": str(member["path"]),  # type: ignore[index]
                "root": str(member["root"]),  # type: ignore[index]
                "mtime_ns": int(member["mtime_ns"]),  # type: ignore[index]
                "drive": str(member["drive"]),  # type: ignore[index]
                "is_canonical": bool(member["is_canonical"]),  # type: ignore[index]
                "recommended_action": str(member["recommended_action"]),  # type: ignore[index]
                "confidence": str(member["confidence"]),  # type: ignore[index]
                "reason": str(member["reason"]),  # type: ignore[index]
            }
            risk_flags = member["risk_flags"]  # type: ignore[index]
            for key in ("system_path", "hidden", "readonly", "extension_mismatch", "cross_drive"):
                row[f"risk_{key}"] = bool(risk_flags.get(key, False))
            rows.append(row)
    rows.sort(key=lambda r: (int(r["group_id"]), not bool(r["is_canonical"]), str(r["path"]).lower()))
    return rows


def _export_action_plan_csv(path: Path, payload: dict[str, object]) -> None:
    rows = _flatten_plan_rows(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "group_id",
        "sha256",
        "size_bytes",
        "file_count",
        "canonical_path",
        "path",
        "root",
        "mtime_ns",
        "drive",
        "is_canonical",
        "recommended_action",
        "confidence",
        "reason",
        "risk_system_path",
        "risk_hidden",
        "risk_readonly",
        "risk_extension_mismatch",
        "risk_cross_drive",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _export_action_plan_md(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary", {})
    lines: list[str] = [
        "# Duplicate Action Plan (Safe / Non-Destructive)",
        "",
        f"- Generated: `{payload.get('generated_at')}`",
        "- Mode: `plan-only` (no file changes executed)",
        f"- Groups: `{summary.get('group_count', 0)}`",
        f"- Files: `{summary.get('file_count', 0)}`",
        f"- Reclaimable bytes (if applied manually): `{summary.get('reclaimable_bytes_if_applied', 0)}`",
        "",
        "## Guardrails",
        "",
        "- This tool generates recommendations only.",
        "- It never moves, archives, or deletes files.",
        "",
        "## Group Recommendations",
        "",
    ]
    groups = payload.get("groups", [])
    if not groups:
        lines.append("_No verified duplicate groups found._")
    else:
        for group in groups:  # type: ignore[assignment]
            lines.append(
                f"- Group `{group['group_id']}` size `{group['size_bytes']}` keep `{group['canonical_path']}`"
            )
            for member in group["members"]:  # type: ignore[index]
                risks = [name for name, value in member["risk_flags"].items() if value]  # type: ignore[index]
                risk_text = ", ".join(risks) if risks else "none"
                lines.append(
                    f"  - `{member['recommended_action']}` `{member['path']}` confidence `{member['confidence']}` risks `{risk_text}`"
                )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _path_prefix(path_text: str, depth: int = 3) -> str:
    norm = path_text.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return norm
    if len(parts) <= depth:
        return "/".join(parts)
    return "/".join(parts[:depth])


def _risk_tier(row: dict[str, object]) -> str:
    if bool(row.get("risk_system_path")) or bool(row.get("risk_readonly")):
        return "high"
    if bool(row.get("risk_hidden")) or bool(row.get("risk_cross_drive")) or bool(row.get("risk_extension_mismatch")):
        return "medium"
    return "low"


def _build_space_recovery_summary(plan_payload: dict[str, object]) -> dict[str, object]:
    rows = _flatten_plan_rows(plan_payload)
    actionable = [r for r in rows if str(r.get("recommended_action")) in {"DELETE_CANDIDATE", "ARCHIVE_CANDIDATE"}]
    by_drive: dict[str, dict[str, int]] = {}
    by_prefix: dict[str, dict[str, int]] = {}
    by_tier: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    cluster_rows: list[dict[str, object]] = []

    for row in actionable:
        drive = str(row.get("drive") or "?")
        size = int(row.get("size_bytes") or 0)
        path_text = str(row.get("path") or "")
        prefix = _path_prefix(path_text)
        tier = _risk_tier(row)

        drive_stats = by_drive.setdefault(drive, {"bytes": 0, "files": 0})
        drive_stats["bytes"] += size
        drive_stats["files"] += 1

        prefix_stats = by_prefix.setdefault(prefix, {"bytes": 0, "files": 0})
        prefix_stats["bytes"] += size
        prefix_stats["files"] += 1
        by_tier[tier] = by_tier.get(tier, 0) + size

    groups = plan_payload.get("groups", [])
    for group in groups:  # type: ignore[assignment]
        members = group.get("members", [])  # type: ignore[union-attr]
        reclaimable = sum(int(m.get("size_bytes", 0)) for m in members if str(m.get("recommended_action")) != "KEEP")
        cluster_rows.append(
            {
                "group_id": int(group.get("group_id", 0)),
                "size_bytes": int(group.get("size_bytes", 0)),
                "file_count": int(group.get("file_count", 0)),
                "reclaimable_bytes": reclaimable,
                "canonical_path": str(group.get("canonical_path", "")),
            }
        )

    top_drives = sorted(
        [{"drive": drive, **stats} for drive, stats in by_drive.items()],
        key=lambda r: (-int(r["bytes"]), str(r["drive"])),
    )
    top_prefixes = sorted(
        [{"path_prefix": pref, **stats} for pref, stats in by_prefix.items()],
        key=lambda r: (-int(r["bytes"]), str(r["path_prefix"])),
    )
    top_clusters = sorted(cluster_rows, key=lambda r: (-int(r["reclaimable_bytes"]), -int(r["size_bytes"]), int(r["group_id"])))

    conservative = [r for r in actionable if str(r.get("confidence")) == "medium" and _risk_tier(r) == "low"]
    conservative.sort(key=lambda r: (-int(r["size_bytes"]), str(r["path"])))

    return {
        "generated_at": _utc_now(),
        "summary": {
            "actionable_files": len(actionable),
            "actionable_reclaimable_bytes": sum(int(r["size_bytes"]) for r in actionable),
            "reclaimable_bytes_by_risk_tier": by_tier,
        },
        "top_drives": top_drives[:20],
        "top_path_prefixes": top_prefixes[:50],
        "largest_duplicate_clusters": top_clusters[:50],
        "conservative_first_pass_candidates": conservative[:200],
    }


def _export_space_recovery_csv(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "key", "bytes", "files", "extra"])
        for row in payload.get("top_drives", []):  # type: ignore[union-attr]
            writer.writerow(["drive", row["drive"], row["bytes"], row["files"], ""])
        for row in payload.get("top_path_prefixes", []):  # type: ignore[union-attr]
            writer.writerow(["path_prefix", row["path_prefix"], row["bytes"], row["files"], ""])
        for row in payload.get("largest_duplicate_clusters", []):  # type: ignore[union-attr]
            writer.writerow(
                [
                    "cluster",
                    row["group_id"],
                    row["reclaimable_bytes"],
                    row["file_count"],
                    row["canonical_path"],
                ]
            )


def _export_space_recovery_md(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary", {})
    lines = [
        "# Space Recovery Prioritization (Plan-Only)",
        "",
        f"- Generated: `{payload.get('generated_at')}`",
        f"- Actionable files: `{summary.get('actionable_files', 0)}`",
        f"- Actionable reclaimable bytes: `{summary.get('actionable_reclaimable_bytes', 0)}`",
        "",
        "## Top Drives",
        "",
    ]
    drives = payload.get("top_drives", [])
    if not drives:
        lines.append("_None_")
    else:
        for row in drives:  # type: ignore[assignment]
            lines.append(f"- `{row['drive']}` reclaim `{row['bytes']}` bytes across `{row['files']}` files")
    lines += ["", "## Top Path Prefixes", ""]
    prefixes = payload.get("top_path_prefixes", [])
    if not prefixes:
        lines.append("_None_")
    else:
        for row in prefixes[:25]:  # type: ignore[index]
            lines.append(f"- `{row['path_prefix']}` reclaim `{row['bytes']}` bytes across `{row['files']}` files")
    lines += ["", "## Largest Duplicate Clusters", ""]
    clusters = payload.get("largest_duplicate_clusters", [])
    if not clusters:
        lines.append("_None_")
    else:
        for row in clusters[:25]:  # type: ignore[index]
            lines.append(
                f"- group `{row['group_id']}` reclaim `{row['reclaimable_bytes']}` bytes, files `{row['file_count']}`, keep `{row['canonical_path']}`"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_summarize_space_recovery(args: argparse.Namespace) -> int:
    plan_json = Path(args.plan_json) if args.plan_json else Path(args.output_dir) / "duplicate_action_plan_latest.json"
    if not plan_json.exists():
        raise FileNotFoundError(f"Action plan JSON not found: {plan_json}")
    payload = json.loads(plan_json.read_text(encoding="utf-8"))
    summary_payload = _build_space_recovery_summary(payload)
    summary_payload["source_plan_json"] = _safe_path_text(plan_json)
    report_dir = Path(args.output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    base = f"space_recovery_prioritization_{_stamp()}"
    emitted: dict[str, str] = {}
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    if "json" in formats:
        p = report_dir / f"{base}.json"
        _export_json(p, summary_payload)
        _export_json(report_dir / "space_recovery_prioritization_latest.json", summary_payload)
        emitted["json"] = _safe_path_text(p)
    if "csv" in formats:
        p = report_dir / f"{base}.csv"
        _export_space_recovery_csv(p, summary_payload)
        _export_space_recovery_csv(report_dir / "space_recovery_prioritization_latest.csv", summary_payload)
        emitted["csv"] = _safe_path_text(p)
    if "md" in formats:
        p = report_dir / f"{base}.md"
        _export_space_recovery_md(p, summary_payload)
        _export_space_recovery_md(report_dir / "space_recovery_prioritization_latest.md", summary_payload)
        emitted["md"] = _safe_path_text(p)
    out = {"ok": True, "summary": summary_payload["summary"], "artifacts": emitted}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def _build_scan_config(args: argparse.Namespace) -> ScanConfig:
    include_ext = _parse_ext_list(args.include_ext)
    exclude_ext = _parse_ext_list(args.exclude_ext)
    exclude_paths = [p.strip().lower().replace("\\", "/") for p in (args.exclude_path or []) if p.strip()]
    if not args.no_default_excludes:
        for needle in DEFAULT_EXCLUDE_PATH_NEEDLES:
            if needle not in exclude_paths:
                exclude_paths.append(needle)
    roots = _resolve_roots(args.roots)
    if not roots:
        raise ValueError("No roots resolved. Provide --roots explicitly.")
    return ScanConfig(
        roots=roots,
        include_ext=include_ext,
        exclude_ext=exclude_ext,
        exclude_paths=exclude_paths,
        use_default_excludes=not args.no_default_excludes,
        skip_files_over_bytes=args.skip_files_over_bytes,
        hash_candidates_limit=args.hash_candidates_limit,
        hash_workers=max(1, int(args.hash_workers)),
        min_hash_size_bytes=max(1, int(args.min_hash_size_bytes)),
        resume_scan_id=args.resume_scan_id,
        checkpoint_every=max(500, int(args.checkpoint_every)),
    )


def _add_common_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--roots",
        nargs="*",
        help="Optional explicit roots. Default: auto-discovered local drives.",
    )
    parser.add_argument(
        "--exclude-path",
        action="append",
        help="Substring path exclusion (case-insensitive), repeatable.",
    )
    parser.add_argument(
        "--include-ext",
        action="append",
        help="Only include extensions (e.g. .jpg,.png), repeatable.",
    )
    parser.add_argument(
        "--exclude-ext",
        action="append",
        help="Exclude extensions (e.g. .iso,.tmp), repeatable.",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable built-in system/temp directory exclusions.",
    )
    parser.add_argument(
        "--skip-files-over-bytes",
        type=int,
        default=None,
        help="Skip hashing (not indexing) for files larger than this many bytes.",
    )
    parser.add_argument(
        "--hash-candidates-limit",
        type=int,
        default=None,
        help="Optional max number of candidate files to hash per run.",
    )
    parser.add_argument(
        "--hash-workers",
        type=int,
        default=DEFAULT_HASH_WORKERS,
        help="Worker threads for candidate hashing. Default 1 (deterministic, single-threaded).",
    )
    parser.add_argument(
        "--min-hash-size-bytes",
        type=int,
        default=DEFAULT_MIN_HASH_SIZE_BYTES,
        help="Ignore tiny files below this size in hash candidate selection.",
    )
    parser.add_argument(
        "--resume-scan-id",
        default=None,
        help="Resume an interrupted scan using checkpoint state for this scan id.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=DEFAULT_SCAN_CHECKPOINT_EVERY,
        help="Persist scan checkpoint every N seen files.",
    )
    parser.add_argument(
        "--batch-commit-every",
        type=int,
        default=1000,
        help="Commit every N indexed/hashed files for resilience.",
    )


def cmd_scan_full(args: argparse.Namespace) -> int:
    cfg = _build_scan_config(args)
    conn = _connect_db(Path(args.db))
    try:
        metrics = _scan_index(
            conn,
            mode="scan_full",
            cfg=cfg,
            prune_missing=True,
            batch_commit_every=args.batch_commit_every,
        )
        hash_metrics = _hash_candidates(
            conn,
            cfg=cfg,
            batch_commit_every=args.batch_commit_every,
        )
        out = {
            "ok": True,
            "mode": "scan_full",
            "db": _safe_path_text(Path(args.db)),
            "roots": [_safe_path_text(r) for r in cfg.roots],
            "metrics": metrics,
            "hash_metrics": hash_metrics,
            "at": _utc_now(),
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    finally:
        conn.close()


def cmd_scan_update(args: argparse.Namespace) -> int:
    cfg = _build_scan_config(args)
    conn = _connect_db(Path(args.db))
    try:
        metrics = _scan_index(
            conn,
            mode="scan_update",
            cfg=cfg,
            prune_missing=bool(args.prune_missing),
            batch_commit_every=args.batch_commit_every,
        )
        hash_metrics = _hash_candidates(
            conn,
            cfg=cfg,
            batch_commit_every=args.batch_commit_every,
        )
        out = {
            "ok": True,
            "mode": "scan_update",
            "db": _safe_path_text(Path(args.db)),
            "roots": [_safe_path_text(r) for r in cfg.roots],
            "prune_missing": bool(args.prune_missing),
            "metrics": metrics,
            "hash_metrics": hash_metrics,
            "at": _utc_now(),
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    finally:
        conn.close()


def cmd_report_duplicates(args: argparse.Namespace) -> int:
    conn = _connect_db(Path(args.db))
    try:
        verified_groups = _collect_verified_duplicate_groups(conn)
        unverified = _collect_unverified_candidate_groups(conn)
        verified_file_count = sum(int(g["count"]) for g in verified_groups)
        reclaimable = sum(int(g["size"]) * (int(g["count"]) - 1) for g in verified_groups)
        payload: dict[str, object] = {
            "ok": True,
            "generated_at": _utc_now(),
            "db": _safe_path_text(Path(args.db)),
            "summary": {
                "verified_group_count": len(verified_groups),
                "verified_file_count": verified_file_count,
                "reclaimable_bytes": reclaimable,
                "unverified_group_count": len(unverified),
            },
            "verified_groups": verified_groups,
            "unverified_candidates": unverified,
        }

        report_dir = Path(args.output_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        base = f"duplicate_report_{_stamp()}"
        emitted: dict[str, str] = {}
        formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
        if "json" in formats:
            json_path = report_dir / f"{base}.json"
            _export_json(json_path, payload)
            _export_json(report_dir / "duplicate_report_latest.json", payload)
            emitted["json"] = _safe_path_text(json_path)
        if "csv" in formats:
            csv_path = report_dir / f"{base}.csv"
            _export_csv(csv_path, verified_groups)
            _export_csv(report_dir / "duplicate_report_latest.csv", verified_groups)
            emitted["csv"] = _safe_path_text(csv_path)
        if "md" in formats:
            md_path = report_dir / f"{base}.md"
            _export_md(md_path, payload)
            _export_md(report_dir / "duplicate_report_latest.md", payload)
            emitted["md"] = _safe_path_text(md_path)

        out = {"ok": True, "summary": payload["summary"], "artifacts": emitted}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    finally:
        conn.close()


def cmd_plan_duplicate_actions(args: argparse.Namespace) -> int:
    policy_order = _parse_policy_order(args.canonical_policy)
    preferred_roots = [p.lower().replace("\\", "/").rstrip("/") for p in _parse_list_values(args.preferred_root)]
    preferred_exts = [_normalize_ext(p).lower() for p in _parse_list_values(args.preferred_ext)]
    source = "db"
    if args.report_json:
        groups = _load_verified_groups_from_report(Path(args.report_json))
        source = f"report:{_safe_path_text(Path(args.report_json))}"
    else:
        conn = _connect_db(Path(args.db))
        try:
            groups = _collect_verified_duplicate_groups(conn)
        finally:
            conn.close()

    payload = _build_duplicate_action_plan(
        groups,
        db_path=_safe_path_text(Path(args.db)),
        source=source,
        policy_order=policy_order,
        preferred_roots=preferred_roots,
        preferred_exts=preferred_exts,
    )

    report_dir = Path(args.output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    base = f"duplicate_action_plan_{_stamp()}"
    emitted: dict[str, str] = {}
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    if "json" in formats:
        json_path = report_dir / f"{base}.json"
        _export_json(json_path, payload)
        _export_json(report_dir / "duplicate_action_plan_latest.json", payload)
        emitted["json"] = _safe_path_text(json_path)
    if "csv" in formats:
        csv_path = report_dir / f"{base}.csv"
        _export_action_plan_csv(csv_path, payload)
        _export_action_plan_csv(report_dir / "duplicate_action_plan_latest.csv", payload)
        emitted["csv"] = _safe_path_text(csv_path)
    if "md" in formats:
        md_path = report_dir / f"{base}.md"
        _export_action_plan_md(md_path, payload)
        _export_action_plan_md(report_dir / "duplicate_action_plan_latest.md", payload)
        emitted["md"] = _safe_path_text(md_path)

    out = {"ok": True, "mode": "plan-only", "summary": payload["summary"], "artifacts": emitted}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index local files and generate duplicate reports/action plans (report-only, plan-only)."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="SQLite index path.",
    )
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_DIR / f"{APP_NAME}_{_stamp()}.log"),
        help="Log file path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_full = sub.add_parser(
        "scan-full",
        help="Full scan of roots; marks previously seen missing files.",
    )
    _add_common_scan_args(p_full)
    p_full.set_defaults(func=cmd_scan_full)

    p_update = sub.add_parser(
        "scan-update",
        help="Incremental update; optional missing-file prune.",
    )
    _add_common_scan_args(p_update)
    p_update.add_argument(
        "--prune-missing",
        action="store_true",
        help="Mark unseen files as missing for provided roots.",
    )
    p_update.set_defaults(func=cmd_scan_update)

    p_report = sub.add_parser(
        "report-duplicates",
        help="Export duplicate report from current index.",
    )
    p_report.add_argument(
        "--output-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory for report artifacts.",
    )
    p_report.add_argument(
        "--formats",
        default="json,csv,md",
        help="Comma-separated output formats: json,csv,md.",
    )
    p_report.set_defaults(func=cmd_report_duplicates)

    p_plan = sub.add_parser(
        "plan-duplicate-actions",
        help="Build non-destructive duplicate action plan artifacts (no move/delete execution).",
        description=(
            "Generate deterministic duplicate action recommendations only. "
            "This command is plan-only and never performs destructive operations."
        ),
    )
    p_plan.add_argument(
        "--report-json",
        default=None,
        help="Optional existing duplicate_report JSON input; otherwise pulls verified groups from --db.",
    )
    p_plan.add_argument(
        "--output-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory for action plan artifacts.",
    )
    p_plan.add_argument(
        "--formats",
        default="json,csv,md",
        help="Comma-separated output formats: json,csv,md.",
    )
    p_plan.add_argument(
        "--canonical-policy",
        default=DEFAULT_CANONICAL_POLICY,
        help=(
            "Ordered canonical selection rules (comma-separated): "
            "preferred-root,preferred-ext,newest-mtime,oldest-mtime,shortest-path,path-lex."
        ),
    )
    p_plan.add_argument(
        "--preferred-root",
        action="append",
        help="Preferred canonical root prefixes (repeatable or comma-separated).",
    )
    p_plan.add_argument(
        "--preferred-ext",
        action="append",
        help="Preferred canonical extensions, e.g. .flac,.wav (repeatable or comma-separated).",
    )
    p_plan.set_defaults(func=cmd_plan_duplicate_actions)

    p_space = sub.add_parser(
        "summarize-space-recovery",
        help="Build ranked cleanup-first prioritization from plan-only duplicate action output.",
    )
    p_space.add_argument(
        "--plan-json",
        default=None,
        help="Optional duplicate action plan JSON path. Defaults to <output-dir>/duplicate_action_plan_latest.json.",
    )
    p_space.add_argument(
        "--output-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory for prioritization artifacts.",
    )
    p_space.add_argument(
        "--formats",
        default="json,csv,md",
        help="Comma-separated output formats: json,csv,md.",
    )
    p_space.set_defaults(func=cmd_summarize_space_recovery)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(Path(args.log_file), bool(args.verbose))
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        logging.exception("fatal_error=%s", exc)
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "at": _utc_now()},
                indent=2,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
