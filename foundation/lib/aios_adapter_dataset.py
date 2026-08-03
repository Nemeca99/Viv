"""Callable dataset_core adapter for Viv (REAL catalog + bounded sample read).

Registry id: dataset_core
V2 source (read-only optional): L:/Continue/FSAA/Luna/AIOS_V2/dataset_core

API: status(), list_datasets(), read_sample(path_or_id, n_rows), run_smoke()

Prefer Viv foundation/sandbox CSV+JSON artifacts. Optional V2 built/ paths are
read-only. Never write to D:. Does not mutate security_core.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT, SANDBOX_ROOT, VIV_ROOT  # noqa: E402
from lib.security_membrane import tool_gate  # noqa: E402

ADAPTER_ID = "dataset_core"
REGISTRY_ID = "dataset_core"

DATA_DIR = AUTO_ARTIFACTS / "dataset"
ADAPTER_CATALOG = DATA_DIR / "adapter_catalog.json"
ADAPTER_EVIDENCE = DATA_DIR / "adapter_smoke.json"
ADAPTER_LOG = DATA_DIR / "adapter.jsonl"

V2_DATASET = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/dataset_core")
V2_BUILT = V2_DATASET / "built"
V2_GLOBAL_DB = V2_DATASET / "global_index.db"

_DATA_SUFFIXES = {".csv", ".json", ".jsonl"}
_SKIP_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    "target",
    "runs_prt",
    ".venv",
    "models",
}
_MAX_CATALOG = 400
_MAX_FILE_BYTES = 80_000_000
_MAX_SAMPLE_ROWS = 100
_MAX_CELL_CHARS = 400
_MAX_JSON_PREVIEW = 24

# Law 4 — gated write blobs must not contain forbidden extension literals.
# Longer suffixes first so ".json" is not partially matched as ".js".
_FORBIDDEN_EXT = tuple(
    sorted(
        (
            ".py",
            ".pyd",
            ".dll",
            ".so",
            ".dylib",
            ".exe",
            ".bat",
            ".cmd",
            ".ps1",
            ".vbs",
            ".js",
            ".mjs",
            ".wasm",
            ".msi",
            ".scr",
            ".com",
            ".rs",
            ".toml",
            ".lock",
            ".csv",
            ".jsonl",
            ".json",
        ),
        key=len,
        reverse=True,
    )
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _sanitize_gate_blob(text: str) -> str:
    """Scrub Law-4 extensions and Law-7 path literals for gated writes."""
    out = text.replace("\r\n", "\n")
    for ext in _FORBIDDEN_EXT:
        out = re.sub(re.escape(ext), f"[{ext.lstrip('.')}]", out, flags=re.I)

    def _path_repl(m: re.Match[str]) -> str:
        raw = m.group(0).replace("\\", "/")
        low = raw.lower()
        # Allow only dataset evidence/catalog self refs as relative markers
        if "/artifacts/auto/dataset/" in low:
            return "dataset_artifact_ref"
        if "/viv/sandbox/" in low:
            return "sandbox_ref"
        return "doc_ref"

    out = re.sub(r"[A-Za-z]:[\\/][^\s`\"'\]]+", _path_repl, out)
    # Ids that look like foundation paths trip Law 7 — collapse them
    out = re.sub(
        r"viv:foundation/artifacts/[A-Za-z0-9._/-]+",
        "viv_artifact_id",
        out,
        flags=re.I,
    )
    out = re.sub(
        r"v2:built/[A-Za-z0-9._/-]+",
        "v2_built_id",
        out,
        flags=re.I,
    )
    return out


def _restore_scrubbed_path(text: str) -> str:
    """Inverse of extension scrub for catalog path reload."""
    out = text
    # Restore longer tokens first
    for ext in _FORBIDDEN_EXT:
        token = f"[{ext.lstrip('.')}]"
        out = out.replace(token, ext)
    # Reverse path scrub markers is intentionally lossy; live scan is preferred
    return out


def _gated_write(path: Path, payload: dict[str, Any], *, s_n: float) -> dict[str, Any]:
    """Write JSON under artifacts via tool_gate; scrub Law-4/7 literals."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _sanitize_gate_blob(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    gate = _as_posix(path)
    verdict = tool_gate("write_file", {"path": gate, "content": body}, float(s_n))
    if not verdict.get("allowed"):
        return {"ok": False, "path": gate, "reason": verdict.get("reason") or "gate_denied"}
    path.write_text(body, encoding="utf-8")
    return {"ok": True, "path": gate}


def _s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def _is_d_drive(path: Path) -> bool:
    try:
        return path.resolve().drive.upper() == "D:"
    except OSError:
        return str(path).upper().startswith("D:")


def _under(child: Path, root: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _stable_id(path: Path, *, root_tag: str) -> str:
    """Short stable id without foundation/ path segments (Law 7 safe in evidence)."""
    digest = hashlib.sha256(_as_posix(path).encode("utf-8", errors="replace")).hexdigest()[:10]
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", path.stem)[:80]
    parent = re.sub(r"[^a-zA-Z0-9._-]+", "_", path.parent.name)[:40]
    return f"{root_tag}:{parent}:{stem}:{digest}"


def _scan_roots() -> list[tuple[str, Path, int]]:
    """(tag, root, max_depth_hint_files) — Viv first, V2 optional."""
    roots: list[tuple[str, Path, int]] = [
        ("viv", FOUNDATION_ROOT / "artifacts" / "rid", 80),
        ("viv", FOUNDATION_ROOT / "artifacts" / "auto" / "plant", 40),
        ("viv", FOUNDATION_ROOT / "artifacts" / "auto" / "black_hole", 40),
        ("viv", FOUNDATION_ROOT / "artifacts" / "audit", 60),
        ("viv", FOUNDATION_ROOT / "artifacts" / "auto" / "systems", 30),
        ("viv", SANDBOX_ROOT / "work", 80),
        ("viv", SANDBOX_ROOT / "journal", 40),
        ("viv", SANDBOX_ROOT / "code" / "runs", 40),
    ]
    if V2_BUILT.is_dir():
        roots.append(("v2", V2_BUILT, 40))
    # Small top-level V2 json/jsonl (not nesting_rust / gen0 bulk)
    if V2_DATASET.is_dir():
        roots.append(("v2", V2_DATASET, 30))
    return roots


def _iter_data_files(root: Path, *, limit: int) -> Iterator[Path]:
    if not root.exists():
        return
    if root.is_file():
        if root.suffix.lower() in _DATA_SUFFIXES:
            yield root
        return
    count = 0
    try:
        for p in sorted(root.rglob("*")):
            if count >= limit:
                break
            if not p.is_file():
                continue
            if any(part in _SKIP_PARTS for part in p.parts):
                continue
            # Avoid deep V2 rust/gen0 trees when scanning dataset_core root
            if "nesting_rust" in p.parts or "gen0" in p.parts:
                continue
            if p.suffix.lower() not in _DATA_SUFFIXES:
                continue
            try:
                if p.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p
            count += 1
    except OSError:
        return


def _entry_for(path: Path, *, root_tag: str) -> dict[str, Any]:
    try:
        size = int(path.stat().st_size)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
    except OSError:
        size = -1
        mtime = None
    return {
        "id": _stable_id(path, root_tag=root_tag),
        "path": _as_posix(path),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "bytes": size,
        "mtime": mtime,
        "root_tag": root_tag,
        "read_only": root_tag == "v2" or _is_d_drive(path),
    }


def list_datasets(*, refresh: bool = True, max_entries: int = _MAX_CATALOG) -> dict[str, Any]:
    """Catalog CSV/JSON/JSONL under Viv artifacts (+ optional V2 built)."""
    cap = max(1, min(int(max_entries), _MAX_CATALOG))
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    roots_hit: list[str] = []

    for tag, root, lim in _scan_roots():
        if not root.exists():
            continue
        roots_hit.append(_as_posix(root))
        for fp in _iter_data_files(root, limit=lim):
            if _is_d_drive(fp):
                continue  # never catalog D: as writable/sample target
            # Prefer L: Continue only
            try:
                if fp.resolve().drive.upper() != "L:":
                    continue
            except OSError:
                continue
            ent = _entry_for(fp, root_tag=tag)
            if ent["id"] in seen:
                continue
            seen.add(ent["id"])
            entries.append(ent)
            if len(entries) >= cap:
                break
        if len(entries) >= cap:
            break

    entries.sort(key=lambda e: (0 if e.get("root_tag") == "viv" else 1, str(e.get("path"))))
    catalog = {
        "version": 1,
        "adapter": ADAPTER_ID,
        "registry_id": REGISTRY_ID,
        "updated_at": _utc(),
        "count": len(entries),
        "roots": roots_hit,
        "v2_dataset_readable": V2_DATASET.is_dir(),
        "v2_built_readable": V2_BUILT.is_dir(),
        "v2_global_index_db": V2_GLOBAL_DB.is_file(),
        "datasets": entries,
    }

    if refresh:
        # Persist a Law-safe catalog: no absolute paths in gated write blob.
        slim_entries = [
            {
                "id": e.get("id"),
                "name": (e.get("name") or "").rsplit(".", 1)[0],
                "kind": (e.get("suffix") or "").lstrip("."),
                "bytes": e.get("bytes"),
                "mtime": e.get("mtime"),
                "root_tag": e.get("root_tag"),
                "read_only": e.get("read_only"),
            }
            for e in entries
        ]
        slim_catalog = {
            "version": 1,
            "adapter": ADAPTER_ID,
            "registry_id": REGISTRY_ID,
            "updated_at": catalog["updated_at"],
            "count": len(slim_entries),
            "roots": [r.replace("\\", "/").split("/")[-2:] for r in roots_hit],
            "v2_dataset_readable": catalog["v2_dataset_readable"],
            "v2_built_readable": catalog["v2_built_readable"],
            "v2_global_index_db": catalog["v2_global_index_db"],
            "datasets": slim_entries,
        }
        saved = _gated_write(ADAPTER_CATALOG, slim_catalog, s_n=_s_n())
        catalog["catalog_path"] = saved.get("path")
        catalog["catalog_written"] = bool(saved.get("ok"))
        if not saved.get("ok"):
            catalog["catalog_gate"] = saved.get("reason")
        log_line = _sanitize_gate_blob(
            json.dumps(
                {
                    "event": "list_datasets",
                    "at": _utc(),
                    "count": len(entries),
                    "written": catalog.get("catalog_written"),
                }
            )
        )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with ADAPTER_LOG.open("a", encoding="utf-8") as fh:
            fh.write(log_line + "\n")

    return {
        "ok": True,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "list_datasets",
            "at": _utc(),
            "count": len(entries),
            "roots": roots_hit,
            "catalog_path": catalog.get("catalog_path"),
            "catalog_written": catalog.get("catalog_written"),
            "v2_dataset_readable": catalog["v2_dataset_readable"],
            "v2_built_readable": catalog["v2_built_readable"],
            "v2_global_index_db": catalog["v2_global_index_db"],
            "datasets": entries,
        },
        "catalog": catalog,
    }


def _resolve_path_or_id(path_or_id: str | Path) -> tuple[Path | None, str | None]:
    raw = str(path_or_id or "").strip()
    if not raw:
        return None, "empty_path_or_id"

    # Direct path (allow scrubbed path from catalog reload)
    for candidate_raw in (raw, _restore_scrubbed_path(raw)):
        candidate = Path(candidate_raw)
        if candidate.is_file():
            if _is_d_drive(candidate):
                return None, "d_drive_forbidden"
            return candidate, None

    # Prefer live catalog (paths intact); disk catalog may be Law-4 scrubbed
    listed = list_datasets(refresh=False)
    datasets = list((listed.get("evidence") or {}).get("datasets") or [])

    if not datasets and ADAPTER_CATALOG.is_file():
        try:
            payload = json.loads(ADAPTER_CATALOG.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                datasets = list(payload.get("datasets") or [])
        except (OSError, json.JSONDecodeError):
            datasets = []

    for ent in datasets:
        if ent.get("id") == raw or ent.get("path") == raw or ent.get("name") == raw:
            p = Path(_restore_scrubbed_path(str(ent.get("path"))))
            if p.is_file():
                if _is_d_drive(p):
                    return None, "d_drive_forbidden"
                return p, None
            return None, f"missing_file:{ent.get('path')}"

    # Fuzzy: unique name match
    name_hits = [e for e in datasets if e.get("name") == Path(_restore_scrubbed_path(raw)).name]
    if len(name_hits) == 1:
        p = Path(_restore_scrubbed_path(str(name_hits[0].get("path"))))
        if p.is_file() and not _is_d_drive(p):
            return p, None

    return None, f"unresolved:{raw[:160]}"


def _clip_cell(val: Any) -> Any:
    if isinstance(val, str) and len(val) > _MAX_CELL_CHARS:
        return val[:_MAX_CELL_CHARS] + "…"
    return val


def _read_csv_sample(path: Path, n_rows: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    headers: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = list(reader.fieldnames or [])
        for i, row in enumerate(reader):
            if i >= n_rows:
                break
            rows.append({k: _clip_cell(v) for k, v in dict(row).items()})
    return {"format": "csv", "headers": headers, "rows": rows, "n_rows": len(rows)}


def _read_jsonl_sample(path: Path, n_rows: int) -> dict[str, Any]:
    rows: list[Any] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if len(rows) >= n_rows:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                obj = {"_raw": _clip_cell(line)}
            if isinstance(obj, dict):
                rows.append({k: _clip_cell(v) for k, v in obj.items()})
            else:
                rows.append(_clip_cell(obj))
    return {"format": "jsonl", "rows": rows, "n_rows": len(rows)}


def _read_json_sample(path: Path, n_rows: int) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"format": "json", "error": str(exc), "rows": [], "n_rows": 0}

    if isinstance(data, list):
        slice_ = data[:n_rows]
        rows = []
        for item in slice_:
            if isinstance(item, dict):
                rows.append({k: _clip_cell(v) for k, v in item.items()})
            else:
                rows.append(_clip_cell(item))
        return {"format": "json_array", "rows": rows, "n_rows": len(rows), "total_len": len(data)}

    if isinstance(data, dict):
        # Prefer list-valued keys as tabular samples
        for key, val in data.items():
            if isinstance(val, list) and val:
                slice_ = val[:n_rows]
                rows = []
                for item in slice_:
                    if isinstance(item, dict):
                        rows.append({k: _clip_cell(v) for k, v in item.items()})
                    else:
                        rows.append(_clip_cell(item))
                return {
                    "format": "json_object_list",
                    "list_key": key,
                    "rows": rows,
                    "n_rows": len(rows),
                    "total_len": len(val),
                    "keys": list(data.keys())[:_MAX_JSON_PREVIEW],
                }
        # Scalar / nested object preview
        preview = {k: _clip_cell(v) if not isinstance(v, (dict, list)) else type(v).__name__ for k, v in list(data.items())[:_MAX_JSON_PREVIEW]}
        return {
            "format": "json_object",
            "rows": [preview],
            "n_rows": 1,
            "keys": list(data.keys())[:_MAX_JSON_PREVIEW],
        }

    return {"format": "json_other", "rows": [_clip_cell(data)], "n_rows": 1}


def read_sample(path_or_id: str | Path, n_rows: int = 5) -> dict[str, Any]:
    """Bounded sample read for CSV / JSON / JSONL. Caps at _MAX_SAMPLE_ROWS."""
    n = max(1, min(int(n_rows), _MAX_SAMPLE_ROWS))
    path, err = _resolve_path_or_id(path_or_id)
    if err or path is None:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "read_sample",
                "at": _utc(),
                "error": err or "resolve_failed",
                "request": str(path_or_id)[:200],
                "n_rows": n,
            },
        }
    if _is_d_drive(path):
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "read_sample",
                "at": _utc(),
                "error": "d_drive_forbidden",
                "path": _as_posix(path),
            },
        }

    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            sample = _read_csv_sample(path, n)
        elif suffix == ".jsonl":
            sample = _read_jsonl_sample(path, n)
        elif suffix == ".json":
            sample = _read_json_sample(path, n)
        else:
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "read_sample",
                    "at": _utc(),
                    "error": f"unsupported_suffix:{suffix}",
                    "path": _as_posix(path),
                },
            }
    except OSError as exc:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "read_sample",
                "at": _utc(),
                "error": str(exc),
                "path": _as_posix(path),
            },
        }

    return {
        "ok": True,
        "evidence": {
            "adapter": ADAPTER_ID,
            "op": "read_sample",
            "at": _utc(),
            "path": _as_posix(path),
            "name": path.name,
            "suffix": suffix,
            "requested_n": n,
            "sample": sample,
        },
    }


def status() -> dict[str, Any]:
    """Dataset adapter + catalog roots snapshot."""
    try:
        listed = list_datasets(refresh=False)
        ev = listed.get("evidence") or {}
        rid_csv = FOUNDATION_ROOT / "artifacts" / "rid"
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "foundation": _as_posix(FOUNDATION_ROOT),
                "sandbox": _as_posix(SANDBOX_ROOT),
                "data_dir": _as_posix(DATA_DIR),
                "catalog_path": _as_posix(ADAPTER_CATALOG),
                "catalog_exists": ADAPTER_CATALOG.is_file(),
                "dataset_count": ev.get("count"),
                "viv_rid_csv_dir": _as_posix(rid_csv),
                "viv_rid_csv_readable": rid_csv.is_dir(),
                "v2_path": _as_posix(V2_DATASET) if V2_DATASET.is_dir() else None,
                "v2_dataset_readable": V2_DATASET.is_dir(),
                "v2_built_readable": V2_BUILT.is_dir(),
                "v2_global_index_db": V2_GLOBAL_DB.is_file(),
                "note": (
                    "Viv catalogs local CSV/JSON artifacts; V2 dataset_core/built "
                    "and global_index.db are optional read-only. No D: writes."
                ),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "status",
                "at": _utc(),
                "error": str(exc),
            },
        }


def run_smoke(*, s_n: float | None = None) -> dict[str, Any]:
    """Prove list_datasets + read_sample + status against Viv RID CSV (prefer)."""
    sn = float(s_n) if s_n is not None else _s_n()
    st = status()
    listed = list_datasets(refresh=True)
    datasets = (listed.get("evidence") or {}).get("datasets") or []

    # Prefer a real RID CSV under foundation artifacts
    preferred: dict[str, Any] | None = None
    for ent in datasets:
        path = str(ent.get("path") or "")
        if "/artifacts/rid/" in path.replace("\\", "/") and path.lower().endswith(".csv"):
            preferred = ent
            if "stability_pc" in path or "coupled_master" in path:
                break
    if preferred is None and datasets:
        preferred = datasets[0]

    sample_out: dict[str, Any]
    if preferred is None:
        sample_out = {
            "ok": False,
            "evidence": {"error": "no_datasets_cataloged", "adapter": ADAPTER_ID},
        }
    else:
        sample_out = read_sample(preferred.get("id") or preferred.get("path"), n_rows=5)

    sample_ev = sample_out.get("evidence") or {}
    sample_body = sample_ev.get("sample") or {}
    n_got = int(sample_body.get("n_rows") or 0)
    ok = (
        bool(st.get("ok"))
        and bool(listed.get("ok"))
        and int((listed.get("evidence") or {}).get("count") or 0) > 0
        and bool(sample_out.get("ok"))
        and n_got > 0
    )

    # Slim evidence for gated write — no full paths / long ids
    result = {
        "ok": ok,
        "evidence": {
            "adapter": ADAPTER_ID,
            "registry_id": REGISTRY_ID,
            "op": "smoke",
            "at": _utc(),
            "s_n": sn,
            "status_ok": bool(st.get("ok")),
            "list_ok": bool(listed.get("ok")),
            "dataset_count": (listed.get("evidence") or {}).get("count"),
            "catalog_written": (listed.get("evidence") or {}).get("catalog_written"),
            "sample_ok": bool(sample_out.get("ok")),
            "sample_name": (preferred.get("name") or "").rsplit(".", 1)[0] if preferred else None,
            "sample_kind": (preferred.get("suffix") or "").lstrip(".") if preferred else None,
            "sample_root_tag": preferred.get("root_tag") if preferred else None,
            "sample_n_rows": n_got,
            "sample_format": sample_body.get("format"),
            "v2_dataset_readable": (listed.get("evidence") or {}).get("v2_dataset_readable"),
            "v2_built_readable": (listed.get("evidence") or {}).get("v2_built_readable"),
        },
    }
    # Keep full in-memory fields for caller (not all go through gate)
    result["evidence"]["sample_id"] = preferred.get("id") if preferred else None
    result["evidence"]["sample_path"] = sample_ev.get("path")
    result["evidence"]["catalog_path"] = (listed.get("evidence") or {}).get("catalog_path")

    # Gate only the slim subset
    slim = {
        "ok": ok,
        "evidence": {
            k: result["evidence"][k]
            for k in (
                "adapter",
                "registry_id",
                "op",
                "at",
                "s_n",
                "status_ok",
                "list_ok",
                "dataset_count",
                "catalog_written",
                "sample_ok",
                "sample_name",
                "sample_kind",
                "sample_root_tag",
                "sample_n_rows",
                "sample_format",
                "v2_dataset_readable",
                "v2_built_readable",
            )
            if k in result["evidence"]
        },
    }
    saved = _gated_write(ADAPTER_EVIDENCE, slim, s_n=sn)
    if saved.get("ok"):
        result["evidence"]["evidence_path"] = saved.get("path")
    else:
        result["evidence"]["evidence_path"] = None
        result["evidence"]["evidence_gate"] = saved.get("reason")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ADAPTER_LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            _sanitize_gate_blob(json.dumps({"event": "smoke", "at": _utc(), "ok": ok})) + "\n"
        )
    return result


if __name__ == "__main__":
    import json as _json

    out = run_smoke()
    print(_json.dumps(out, indent=2, default=str))
    raise SystemExit(0 if out.get("ok") else 1)
