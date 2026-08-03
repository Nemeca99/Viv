#!/usr/bin/env python3
"""Count first-party Viv/AIOS source lines (exclude vendored/third-party/models)."""
from __future__ import annotations

import os
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    "vendor",
    "third_party",
    "third-party",
    ".tox",
    ".cache",
    "site-packages",
    "blobs",
    "snapshots",
    "refs",
}

CODE_EXT = {
    ".py",
    ".rs",
    ".ps1",
    ".mdc",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".css",
    ".html",
    ".sh",
    ".bat",
    ".cmd",
    ".sql",
    ".glsl",
}

CATS = {
    "python": {".py"},
    "rust": {".rs"},
    "powershell": {".ps1", ".bat", ".cmd"},
    "docs_md": {".md", ".mdc"},
    "config_json_yaml_toml": {".json", ".yaml", ".yml", ".toml"},
    "web_js_ts_css_html": {".ts", ".tsx", ".js", ".jsx", ".css", ".html"},
    "other_code": {".sh", ".sql", ".glsl"},
}

IMPL_EXT = {".py", ".rs", ".ps1"}


def is_skipped_dir(path: Path) -> bool:
    name = path.name.lower()
    if name in {s.lower() for s in SKIP_DIR_NAMES}:
        return True
    if "huggingface" in name or name.endswith("-hf"):
        return True
    # large model / weight trees under Viv
    if name in {"models"} and (path / "gpu").is_dir():
        # still walk models/Training/code; prune only gpu weight dumps later by file type
        return False
    return False


def path_blocked(path: Path) -> bool:
    s = str(path).replace("\\", "/").lower()
    needles = (
        "/.venv/",
        "/site-packages/",
        "/node_modules/",
        "/vendor/",
        "/third_party/",
        "/third-party/",
        "/.git/",
        "/models/gpu/",
    )
    return any(n in s for n in needles)


def is_code_file(path: Path) -> bool:
    if path_blocked(path):
        return False
    if path.suffix.lower() in {
        ".safetensors",
        ".bin",
        ".pt",
        ".pth",
        ".onnx",
        ".gguf",
        ".ckpt",
        ".pkl",
    }:
        return False
    return path.suffix.lower() in CODE_EXT


def count_tree(root: Path, *, impl_only: bool = False) -> dict:
    files = 0
    lines = 0
    by_cat = {k: {"files": 0, "lines": 0} for k in CATS}
    by_ext: dict[str, int] = {}
    if not root.exists():
        return {"root": str(root), "missing": True}
    for dirpath, dirnames, filenames in os.walk(root):
        p = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not is_skipped_dir(p / d)]
        for fn in filenames:
            fp = p / fn
            ext = fp.suffix.lower()
            if impl_only:
                if ext not in IMPL_EXT or path_blocked(fp):
                    continue
            elif not is_code_file(fp):
                continue
            try:
                nlines = len(fp.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                continue
            files += 1
            lines += nlines
            by_ext[ext] = by_ext.get(ext, 0) + nlines
            placed = False
            for cat, exts in CATS.items():
                if ext in exts:
                    by_cat[cat]["files"] += 1
                    by_cat[cat]["lines"] += nlines
                    placed = True
                    break
            if not placed:
                by_cat["other_code"]["files"] += 1
                by_cat["other_code"]["lines"] += nlines
    return {
        "root": str(root),
        "files": files,
        "lines": lines,
        "by_cat": by_cat,
        "by_ext": dict(sorted(by_ext.items(), key=lambda x: -x[1])),
    }


def main() -> None:
    scopes = [
        ("Viv", Path(r"L:/Continue/Viv")),
        ("Viv/foundation", Path(r"L:/Continue/Viv/foundation")),
        ("FSAA", Path(r"L:/Continue/FSAA")),
        ("automation", Path(r"L:/Continue/automation")),
        ("Continue/.cursor rules+hooks", Path(r"L:/Continue/.cursor")),
    ]

    print("FIRST-PARTY BROAD (authored-like text; no venv/node_modules/vendor/gpu weights)")
    print("=" * 72)
    broad_total_f = broad_total_l = 0
    for name, root in scopes:
        r = count_tree(root, impl_only=False)
        if r.get("missing"):
            print(f"{name}: MISSING")
            continue
        print(f"{name}: {r['files']:,} files, {r['lines']:,} lines")
        for cat, v in r["by_cat"].items():
            if v["lines"]:
                print(f"  {cat}: {v['files']:,} files, {v['lines']:,} lines")
        broad_total_f += r["files"]
        broad_total_l += r["lines"]
    print(f"TOTAL BROAD (listed scopes): {broad_total_f:,} files, {broad_total_l:,} lines")
    print()

    print("IMPLEMENTATION ONLY (.py / .rs / .ps1) — AIOS doctrine languages")
    print("=" * 72)
    impl_total_f = impl_total_l = 0
    for name, root in scopes:
        r = count_tree(root, impl_only=True)
        if r.get("missing"):
            continue
        print(f"{name}: {r['files']:,} files, {r['lines']:,} lines  {r['by_ext']}")
        impl_total_f += r["files"]
        impl_total_l += r["lines"]
    print(f"TOTAL IMPL (listed scopes): {impl_total_f:,} files, {impl_total_l:,} lines")
    print()

    viv = count_tree(Path(r"L:/Continue/Viv"), impl_only=True)
    vivb = count_tree(Path(r"L:/Continue/Viv"), impl_only=False)
    print("ANSWER FOCUS — L:/Continue/Viv only")
    print(f"  impl py/rs/ps1: {viv['files']:,} files, {viv['lines']:,} lines")
    print(f"  broad authored-like: {vivb['files']:,} files, {vivb['lines']:,} lines")


if __name__ == "__main__":
    main()
