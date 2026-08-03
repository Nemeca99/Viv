"""Callable vision_core adapter — image/meta presence without heavy CV (REAL).

Registry id: vision_core
V2 source (read-only survey): L:/Continue/FSAA/Luna/AIOS_V2/vision_core

API: status(), list_images(limit), image_meta(path), run_smoke()

Does NOT port V2 effector (SendInput), foveal capture, or stereoscopic tensors.
Reports real Viv artifact images (PNG/JPEG) with lightweight meta (PIL if present,
else PNG IHDR / JPEG SOF parse). cv2 is optional and never required.
Does not mutate security_core. Does not write to D:.
"""
from __future__ import annotations

import importlib.util
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

from lib.paths import ARTIFACTS, AUTO_ARTIFACTS, RID_ARTIFACTS  # noqa: E402

ADAPTER_ID = "vision_core"
REGISTRY_ID = "vision_core"

V2_VISION = Path(r"L:/Continue/FSAA/Luna/AIOS_V2/vision_core")
EVIDENCE_DIR = AUTO_ARTIFACTS / "vision"
ADAPTER_EVIDENCE = EVIDENCE_DIR / "adapter_smoke.json"

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_V2_MARKERS = (
    "effector.py",
    "foveal_capture.py",
    "stereoscopic_vision.py",
)
_SCAN_ROOTS = (RID_ARTIFACTS, AUTO_ARTIFACTS / "black_hole", ARTIFACTS)
_MAX_LIST = 80
_MAX_READ = 512_000


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_posix(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _s_n() -> float:
    try:
        from lib.master_rid import load_master_rid

        return float(load_master_rid().master_s_n)
    except Exception:  # noqa: BLE001
        return 0.5


def _has_mod(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _v2_presence() -> dict[str, Any]:
    markers: dict[str, bool] = {}
    if V2_VISION.is_dir():
        for rel in _V2_MARKERS:
            markers[rel] = (V2_VISION / rel).is_file()
    return {
        "v2_path": _as_posix(V2_VISION),
        "v2_on_disk": V2_VISION.is_dir(),
        "markers": markers,
        "marker_hits": sum(1 for v in markers.values() if v),
        "viv_ports_v2_effector": False,
        "viv_ports_v2_foveal": False,
        "viv_ports_v2_stereo": False,
        "viv_loads_cv2": False,
        "note": (
            "V2 vision_core surveyed read-only (effector/foveal/stereo not absorbed). "
            "Viv reports artifact image meta only."
        ),
    }


def _file_row(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return {
        "name": path.name,
        "path": _as_posix(path),
        "bytes": st.st_size,
        "suffix": path.suffix.lower(),
        "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
    }


def _list_image_paths(limit: int = 40) -> list[Path]:
    top = max(1, min(int(limit), _MAX_LIST))
    found: list[Path] = []
    seen: set[str] = set()
    for root in _SCAN_ROOTS:
        if not root.is_dir():
            continue
        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in _IMAGE_SUFFIXES:
                    continue
                key = _as_posix(path)
                if key in seen:
                    continue
                seen.add(key)
                found.append(path)
                if len(found) >= top:
                    return found
        except OSError:
            continue
    return found


def _png_ihdr(data: bytes) -> dict[str, Any] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    # IHDR chunk starts at offset 8
    length = struct.unpack(">I", data[8:12])[0]
    if data[12:16] != b"IHDR" or length < 13:
        return None
    w, h, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    return {
        "format": "PNG",
        "width": int(w),
        "height": int(h),
        "bit_depth": int(bit_depth),
        "color_type": int(color_type),
        "parser": "png_ihdr",
    }


def _jpeg_sof(data: bytes) -> dict[str, Any] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        if i + 4 > n:
            break
        seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
        # SOF0..SOF3, SOF5..SOF7, SOF9..SOF11, SOF13..SOF15
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if i + 9 < n:
                precision = data[i + 4]
                height, width = struct.unpack(">HH", data[i + 5 : i + 9])
                return {
                    "format": "JPEG",
                    "width": int(width),
                    "height": int(height),
                    "precision": int(precision),
                    "parser": "jpeg_sof",
                }
        i += 2 + seg_len
    return None


def _meta_pil(path: Path) -> dict[str, Any] | None:
    if not _has_mod("PIL"):
        return None
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            return {
                "format": im.format or path.suffix.lstrip(".").upper(),
                "width": int(im.width),
                "height": int(im.height),
                "mode": im.mode,
                "parser": "PIL",
            }
    except Exception:  # noqa: BLE001
        return None


def _meta_struct(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as fh:
            data = fh.read(_MAX_READ)
    except OSError:
        return None
    suf = path.suffix.lower()
    if suf == ".png":
        return _png_ihdr(data)
    if suf in {".jpg", ".jpeg"}:
        return _jpeg_sof(data)
    # Try both for mislabeled files
    return _png_ihdr(data) or _jpeg_sof(data)


def status() -> dict[str, Any]:
    """V2 survey + Viv image inventory. Returns {ok, evidence}."""
    try:
        images = [_file_row(p) for p in _list_image_paths(24)]
        images = [r for r in images if r]
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "registry_id": REGISTRY_ID,
                "op": "status",
                "at": _utc(),
                "s_n": _s_n(),
                "v2": _v2_presence(),
                "deps": {
                    "PIL": _has_mod("PIL"),
                    "cv2": _has_mod("cv2"),
                    "numpy": _has_mod("numpy"),
                },
                "image_count_sample": len(images),
                "images_sample": images[:12],
                "scan_roots": [_as_posix(r) for r in _SCAN_ROOTS],
                "viv_mode": "artifact_image_meta",
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


def list_images(limit: int = 20) -> dict[str, Any]:
    """List Viv artifact images under RID / black_hole / artifacts."""
    top = max(1, min(int(limit), _MAX_LIST))
    try:
        paths = _list_image_paths(top)
        rows = [r for r in (_file_row(p) for p in paths) if r]
        return {
            "ok": len(rows) > 0,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "list_images",
                "at": _utc(),
                "s_n": _s_n(),
                "n_requested": top,
                "n_returned": len(rows),
                "images": rows,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "list_images",
                "at": _utc(),
                "error": str(exc),
            },
        }


def image_meta(path: str) -> dict[str, Any]:
    """Return width/height/format for a Viv-plane image path (no CV pipeline)."""
    raw = (path or "").strip()
    if not raw:
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "image_meta",
                "at": _utc(),
                "error": "empty_path",
            },
        }
    try:
        p = Path(raw)
        if not p.is_file():
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "image_meta",
                    "at": _utc(),
                    "path": _as_posix(p),
                    "error": "not_found",
                },
            }
        # Stay on L: Continue / Viv artifacts when possible
        try:
            p.resolve().relative_to(Path(r"L:/Continue").resolve())
        except ValueError:
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "image_meta",
                    "at": _utc(),
                    "path": _as_posix(p),
                    "error": "outside_continue_plane",
                    "viv_writes_d": False,
                },
            }
        row = _file_row(p) or {}
        meta = _meta_pil(p) or _meta_struct(p)
        if not meta or not meta.get("width") or not meta.get("height"):
            return {
                "ok": False,
                "evidence": {
                    "adapter": ADAPTER_ID,
                    "op": "image_meta",
                    "at": _utc(),
                    **row,
                    "error": "meta_unavailable",
                    "deps": {"PIL": _has_mod("PIL"), "cv2": _has_mod("cv2")},
                },
            }
        return {
            "ok": True,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "image_meta",
                "at": _utc(),
                **row,
                **meta,
                "cv2_used": False,
                "v2_effector_used": False,
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "evidence": {
                "adapter": ADAPTER_ID,
                "op": "image_meta",
                "at": _utc(),
                "path": raw,
                "error": str(exc),
            },
        }


def run_smoke() -> dict[str, Any]:
    """PASS only with real image list + real width/height meta."""
    st = status()
    li = list_images(8)
    sev = st.get("evidence") or {}
    lev = li.get("evidence") or {}
    images = lev.get("images") or []
    meta_result: dict[str, Any] = {
        "ok": False,
        "evidence": {"error": "no_images"},
    }
    if images:
        meta_result = image_meta(str(images[0].get("path") or ""))
    mev = meta_result.get("evidence") or {}
    v2 = sev.get("v2") or {}
    ok = (
        bool(st.get("ok"))
        and bool(li.get("ok"))
        and int(lev.get("n_returned") or 0) > 0
        and bool(meta_result.get("ok"))
        and int(mev.get("width") or 0) > 0
        and int(mev.get("height") or 0) > 0
        and mev.get("cv2_used") is False
        and mev.get("v2_effector_used") is False
        and v2.get("viv_ports_v2_effector") is False
        and v2.get("viv_loads_cv2") is False
    )
    evidence = {
        "adapter": ADAPTER_ID,
        "op": "smoke",
        "at": _utc(),
        "s_n": sev.get("s_n"),
        "status_ok": bool(st.get("ok")),
        "list_ok": bool(li.get("ok")),
        "n_images": lev.get("n_returned"),
        "meta_ok": bool(meta_result.get("ok")),
        "meta_path": mev.get("path"),
        "width": mev.get("width"),
        "height": mev.get("height"),
        "format": mev.get("format"),
        "parser": mev.get("parser"),
        "v2_on_disk": v2.get("v2_on_disk"),
        "v2_marker_hits": v2.get("marker_hits"),
        "PIL": (sev.get("deps") or {}).get("PIL"),
        "cv2": (sev.get("deps") or {}).get("cv2"),
        "status": st,
        "list_images": li,
        "image_meta": meta_result,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        slim = {
            "ok": ok,
            "at": evidence["at"],
            "n_images": evidence["n_images"],
            "meta_path": evidence["meta_path"],
            "width": evidence["width"],
            "height": evidence["height"],
            "parser": evidence["parser"],
            "v2_on_disk": evidence["v2_on_disk"],
            "cv2_used": False,
        }
        ADAPTER_EVIDENCE.write_text(json.dumps(slim, indent=2), encoding="utf-8")
        evidence["evidence_path"] = _as_posix(ADAPTER_EVIDENCE)
    except OSError as exc:
        evidence["evidence_write_error"] = str(exc)
    return {"ok": ok, "evidence": evidence}


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
