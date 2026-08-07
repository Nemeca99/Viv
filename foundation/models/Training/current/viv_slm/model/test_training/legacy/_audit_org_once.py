#!/usr/bin/env python3
"""One-shot evidence audit for legacy organization (read-only)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = Path(r"L:\Continue\.venv\Scripts\python.exe")


def sha256_file(p: Path, prefix: int = 16) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:prefix]


def file_meta(p: Path) -> dict:
    if not p.is_file():
        return {"exists": False}
    st = p.stat()
    return {
        "exists": True,
        "size": st.st_size,
        "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        "sha256_16": sha256_file(p),
    }


def peek_checkpoint(p: Path) -> dict:
    out = file_meta(p)
    if not out.get("exists"):
        return out
    try:
        import torch

        obj = torch.load(p, map_location="cpu", weights_only=False)
        if isinstance(obj, dict):
            keys = sorted(obj.keys())
            out["ckpt_keys"] = keys[:40]
            for k in ("step", "global_step", "epoch", "vocab_size", "n_vocab"):
                if k in obj:
                    out[k] = obj[k]
            # common nesting
            for nest in ("config", "model_config", "args", "meta", "hparams"):
                if nest in obj and isinstance(obj[nest], dict):
                    cfg = obj[nest]
                    out[f"{nest}_keys"] = sorted(cfg.keys())[:30]
                    for k in ("vocab_size", "n_vocab", "n_embd", "n_layer", "n_head", "step"):
                        if k in cfg:
                            out[f"{nest}.{k}"] = cfg[k]
            # state dict vocab hint from embedding
            sd = obj.get("model") or obj.get("state_dict") or obj.get("model_state_dict")
            if isinstance(sd, dict):
                for ek in (
                    "tok_emb.weight",
                    "transformer.wte.weight",
                    "embed.weight",
                    "embedding.weight",
                    "wte.weight",
                ):
                    if ek in sd:
                        out["embed_rows"] = int(sd[ek].shape[0])
                        out["embed_key"] = ek
                        break
                if "embed_rows" not in out:
                    for k, v in sd.items():
                        if hasattr(v, "ndim") and v.ndim == 2 and "emb" in k.lower():
                            out["embed_rows"] = int(v.shape[0])
                            out["embed_key"] = k
                            break
        else:
            out["ckpt_type"] = type(obj).__name__
    except Exception as e:
        out["peek_error"] = f"{type(e).__name__}: {e}"
    return out


def main() -> int:
    report: dict = {"root": str(ROOT)}
    manifest = json.loads((ROOT / "legacy" / "MOVE_MANIFEST.json").read_text(encoding="utf-8"))
    moved_ok = True
    moved_rows = []
    for m in manifest["moved"]:
        newp = ROOT / m["new_path"]
        shimp = ROOT / m["shim_path"]
        row = {
            "old_path": m["old_path"],
            "legacy_exists": newp.is_file(),
            "legacy_size": newp.stat().st_size if newp.is_file() else None,
            "shim_exists": shimp.is_file(),
            "shim_size": shimp.stat().st_size if shimp.is_file() else None,
            "shim_style": m["shim_style"],
        }
        if newp.is_file() and shimp.is_file():
            shim_txt = shimp.read_text(encoding="utf-8", errors="replace")
            row["shim_looks_thin"] = shimp.stat().st_size < newp.stat().st_size and (
                "runpy" in shim_txt or "legacy." in shim_txt or "Compatibility shim" in shim_txt
            )
            row["shim_head"] = shim_txt.splitlines()[:3]
        else:
            moved_ok = False
            row["shim_looks_thin"] = False
        if not row["legacy_exists"] or not row["shim_exists"]:
            moved_ok = False
        moved_rows.append(row)
    report["manifest_paths_ok"] = moved_ok
    report["moved"] = moved_rows

    keepers = [
        "run_uml_mix_layer.py",
        "uml_mix_recipe.json",
        "UML_TRAINING_THESIS.md",
        "run_uml_equation_ab.py",
        "run_uml_mix_ads.py",
        "run_uml_mix_ads_precision.py",
        "run_increments_until_plateau.py",
        "run_teacher_until_plateau.py",
    ]
    keepers += sorted(p.name for p in ROOT.glob("run_uml_*.py"))
    keepers = list(dict.fromkeys(keepers))
    report["keepers"] = {
        name: {
            "exists": (ROOT / name).is_file(),
            "size": (ROOT / name).stat().st_size if (ROOT / name).is_file() else None,
        }
        for name in keepers
    }
    report["keepers_all_present"] = all(v["exists"] for v in report["keepers"].values())

    # checkpoints
    report["layer_survivor"] = peek_checkpoint(ROOT / "runs" / "uml_mix_layers" / "layer_survivor.pt")
    report["efficient"] = peek_checkpoint(ROOT / "checkpoints" / "efficient" / "specialist.pt")
    report["deep"] = peek_checkpoint(ROOT / "checkpoints" / "deep" / "specialist.pt")
    report["warm_start_source"] = peek_checkpoint(ROOT / "runs" / "uml_mix_ads_precision" / "warm_start.pt")
    report["deep_step5000_source"] = peek_checkpoint(ROOT / "runs" / "deep" / "checkpoint_step_05000.pt")

    # hash match restore sources
    for label, cur, src in (
        ("efficient_vs_warm_start", report["efficient"], report["warm_start_source"]),
        ("deep_vs_step5000", report["deep"], report["deep_step5000_source"]),
    ):
        report[label] = {
            "size_match": cur.get("size") == src.get("size"),
            "sha_match": cur.get("sha256_16") == src.get("sha256_16"),
            "cur_size": cur.get("size"),
            "src_size": src.get("size"),
            "cur_sha": cur.get("sha256_16"),
            "src_sha": src.get("sha256_16"),
            "cur_embed": cur.get("embed_rows"),
            "src_embed": src.get("embed_rows"),
        }

    bdir = ROOT / "legacy" / "mint_smoke_overwrite_backup"
    backup_files = []
    if bdir.is_dir():
        for p in sorted(bdir.rglob("*")):
            if p.is_file():
                meta = file_meta(p)
                meta["rel"] = str(p.relative_to(ROOT))
                if p.suffix == ".pt":
                    meta.update({k: v for k, v in peek_checkpoint(p).items() if k.startswith("embed") or k in ("vocab_size", "step", "peek_error")})
                backup_files.append(meta)
    report["mint_backup"] = backup_files
    restore_note = ROOT / "legacy" / "mint_smoke_overwrite_backup" / "RESTORE_NOTE.json"
    report["restore_note_exists"] = restore_note.is_file()
    if restore_note.is_file():
        report["restore_note"] = json.loads(restore_note.read_text(encoding="utf-8"))

    # mint bare CLI (must refuse)
    bare = subprocess.run(
        [str(PY), str(ROOT / "mint_specialists.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    report["mint_bare"] = {
        "returncode": bare.returncode,
        "stdout": bare.stdout[:500],
        "stderr": bare.stderr[:500],
        "refuses": bare.returncode == 2 and "--execute" in (bare.stderr + bare.stdout),
    }
    # hash after bare to confirm no overwrite
    report["efficient_after_bare"] = file_meta(ROOT / "checkpoints" / "efficient" / "specialist.pt")
    report["deep_after_bare"] = file_meta(ROOT / "checkpoints" / "deep" / "specialist.pt")
    report["bare_did_not_overwrite"] = (
        report["efficient_after_bare"].get("sha256_16") == report["efficient"].get("sha256_16")
        and report["deep_after_bare"].get("sha256_16") == report["deep"].get("sha256_16")
    )

    # mint --help via --execute? Don't execute mint. Check if --help alone still blocked
    help_bare = subprocess.run(
        [str(PY), str(ROOT / "mint_specialists.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    report["mint_help_without_execute"] = {
        "returncode": help_bare.returncode,
        "stderr": help_bare.stderr[:400],
        "stdout": help_bare.stdout[:400],
        "note": "help alone should still be blocked by --execute guard (safer)",
    }

    # spot-check other shims --help
    shim_help = {}
    for name in (
        "run_rid_breakthrough.py",
        "run_rid_adapter_ab.py",
        "analyze_val_errors.py",
        "run_acc99_campaign.py",
    ):
        r = subprocess.run(
            [str(PY), str(ROOT / name), "--help"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
        shim_help[name] = {
            "returncode": r.returncode,
            "stdout_head": (r.stdout or "")[:300],
            "stderr_head": (r.stderr or "")[:300],
            "okish": r.returncode in (0, 2) or "usage" in (r.stdout + r.stderr).lower() or "help" in (r.stdout + r.stderr).lower(),
        }
    report["shim_help"] = shim_help

    # import mint main
    sys.path.insert(0, str(ROOT))
    try:
        from legacy.mint_specialists import main as mint_main

        report["mint_import_main"] = {"ok": callable(mint_main)}
    except Exception as e:
        report["mint_import_main"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # SANDBOX parent check in one legacy body
    sample = (ROOT / "legacy" / "run_rid_breakthrough.py").read_text(encoding="utf-8", errors="replace")
    report["legacy_sandbox_parent_contract"] = {
        "parents[1]_present": "parents[1]" in sample or 'parents[1]' in sample,
        "snippet_hits": [ln.strip() for ln in sample.splitlines() if "SANDBOX" in ln or "parents[" in ln][:8],
    }

    out_path = ROOT / "legacy" / "_audit_org_once_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "manifest_paths_ok": report["manifest_paths_ok"],
        "keepers_all_present": report["keepers_all_present"],
        "mint_bare_refuses": report["mint_bare"]["refuses"],
        "bare_did_not_overwrite": report["bare_did_not_overwrite"],
        "efficient_vs_warm_start": report["efficient_vs_warm_start"],
        "deep_vs_step5000": report["deep_vs_step5000"],
        "layer_survivor_size": report["layer_survivor"].get("size"),
        "layer_survivor_embed": report["layer_survivor"].get("embed_rows"),
        "efficient_embed": report["efficient"].get("embed_rows"),
        "deep_embed": report["deep"].get("embed_rows"),
        "mint_backup_count": len(backup_files),
        "report": str(out_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
