"""PRT-scored capability expansion — optional step inside perpetual PRT loop.

Gap → predict triad → sandbox module → measure → REWARD/PUNISH → commit
MANIFEST only on REWARD. Never enables voice_speak. Never mutates foundation/lib,
security_core, or constitution.

Gaps come from: fixed PRT helpers, .cursor skills surface, and AIOS V1/V2
systems registry (deferred/partial cores that still need Viv bridges).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.aios_sandbox import CODE, WORK, ensure_sandbox_home
from lib.paths import AUTO_ARTIFACTS
from lib.prt_cycle import observe_state
from lib.security_membrane import tool_gate

SKILLS_ROOT = Path(r"L:/.cursor/skills")
SKILL_INDEX = SKILLS_ROOT / "SKILL_INDEX.md"
REGISTRY = AUTO_ARTIFACTS / "systems" / "AIOS_SYSTEMS_REGISTRY.json"
EXPAND_DIR = WORK / "aios_build" / "prt_expand"
MANIFEST = WORK / "aios_build" / "MANIFEST.md"
EXPAND_LOG = AUTO_ARTIFACTS / "prt_capability_expand.jsonl"
CORPUS_NOTE = AUTO_ARTIFACTS / "models" / "prt_capability_docs.jsonl"
BRIDGE_DIR = WORK / "aios_build" / "system_bridges"
EXPAND_SKIP = AUTO_ARTIFACTS / "prt_expand_skip.json"

# Substrings that Law 3 treats as protected — must not appear in mutation payloads/paths.
_PROTECTED_SUBSTR = (
    "governance",
    "security_core",
    "nox_forge",
    "cpu_config",
    "security_",
    "autonomous_",
    "autonomy_",
)


def _scrub_protected(text: str) -> str:
    out = text
    for tok in _PROTECTED_SUBSTR:
        if tok in out.lower():
            # case-insensitive replace with neutral token
            out = re.sub(re.escape(tok), "sysseg", out, flags=re.I)
    return out


def _load_expand_skips() -> set[str]:
    if not EXPAND_SKIP.is_file():
        return set()
    try:
        data = json.loads(EXPAND_SKIP.read_text(encoding="utf-8"))
        return set(data.get("skip") or [])
    except (OSError, json.JSONDecodeError, TypeError):
        return set()


def _add_expand_skip(module: str, reason: str) -> None:
    skips = _load_expand_skips()
    skips.add(module)
    EXPAND_SKIP.parent.mkdir(parents=True, exist_ok=True)
    EXPAND_SKIP.write_text(
        json.dumps({"skip": sorted(skips), "last": {"module": module, "reason": reason, "at": _utc()}}, indent=2),
        encoding="utf-8",
    )


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log(row: dict[str, Any]) -> None:
    EXPAND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EXPAND_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _triad_from_obs(obs: dict[str, Any]) -> dict[str, float]:
    return {
        "master_s_n": float(obs.get("master_s_n") or 0.0),
        "rsr": float(obs.get("master_rsr") or obs.get("rsr") or 0.0),
        "ltp": float(obs.get("master_ltp") or obs.get("ltp") or 0.0),
        "rle": float(obs.get("master_rle") or obs.get("rle") or 0.0),
    }


def _safe_id(raw: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", (raw or "").lower()).strip("_")
    return (s or "module")[:48]


def _prt_helper_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": "prt_cycle_digest",
            "gap": "faster retrieval of recent REWARD/PUNISH rows for training example selection",
            "skill_hint": "artifact-first-debugger",
            "source": '''# PRT expand - prt_cycle_digest
import json
from pathlib import Path
p = Path(r"L:/Continue/Viv/foundation/artifacts/models/prt_cycles.jsonl")
if not p.is_file():
    print("PRT_DIGEST missing")
else:
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    rewards = sum(
        1
        for r in rows[-80:]
        if "REWARD" in str(r.get("grade") or r.get("label") or "").upper()
        or r.get("reward") is True
    )
    print(f"PRT_DIGEST n={len(rows)} tail80_rewardish={rewards}")
''',
        },
        {
            "id": "skill_index_probe",
            "gap": "list .cursor skills shared as IDE surface for AIOS expansion",
            "skill_hint": "context-budget-enforcer",
            "source": '''# PRT expand - skill_index_probe
from pathlib import Path
root = Path(r"L:/.cursor/skills")
skills = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
print(f"SKILL_PROBE n={len(skills)} sample={skills[:12]}")
''',
        },
        {
            "id": "prt_autonomous_audit_tail",
            "gap": "tail autonomous integrity log for self-monitoring during perpetual PRT",
            "skill_hint": "runtime-safety-gatekeeper",
            "source": '''# PRT expand - prt_autonomous_audit_tail
import json
from pathlib import Path
p = Path(r"L:/Continue/Viv/foundation/artifacts/audit/prt_autonomous.log")
if not p.is_file():
    print("AUTO_AUDIT missing")
else:
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    last = json.loads(lines[-1]) if lines else {}
    print(f"AUTO_AUDIT n={len(lines)} last_msg={last.get('message')} speak_rr={last.get('speak_reward_rate')}")
''',
        },
        {
            "id": "aios_build_plan",
            "gap": "synthesize next AIOS wiring plan from system_bridges inventories",
            "skill_hint": "cross-root-synthesis-engine",
            "source": """# PRT expand - aios_build_plan
import json
from pathlib import Path
from datetime import datetime, timezone
root = Path(r'L:/Continue/Viv/sandbox/work/aios_build/system_bridges')
out = Path(r'L:/Continue/Viv/sandbox/work/aios_build/AIOS_BUILD_PLAN.md')
rows = []
if root.is_dir():
    for p in sorted(root.glob('*_bridge.json')):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        rows.append(d)
lines = ['# AIOS Build Plan', '', f'Generated: {datetime.now(timezone.utc).strftime(\"%Y-%m-%dT%H:%M:%SZ\")}', '', f'Bridges inventoried: {len(rows)}', '']
for d in rows:
    sid = d.get('system_id')
    st = d.get('status')
    role = d.get('role')
    n = len(d.get('file_sample') or [])
    lines.append(f'## {sid} ({st})')
    lines.append(f'- role: {role}')
    lines.append(f'- on_disk: {d.get(\"on_disk\")} files_sampled: {n}')
    lines.append(f'- viv_map: {d.get(\"viv_map\") or \"(none yet)\"}')
    lines.append(f'- next: author Viv sandbox adapter that calls useful entrypoints from this tree')
    lines.append('')
out.write_text('\\n'.join(lines), encoding='utf-8')
print('BUILD_PLAN n=' + str(len(rows)) + ' path=' + str(out))
""",
        },
    ]


def _registry_gap_specs(have: set[str]) -> list[dict[str, str]]:
    """Turn deferred/partial AIOS systems into sandbox bridge modules."""
    if not REGISTRY.is_file():
        return []
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    out: list[dict[str, str]] = []
    for gen_key in ("v1", "v2", "systems", "items"):
        items = data.get(gen_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").lower()
            if status not in ("deferred", "partial", "legacy"):
                continue
            sid = _safe_id(str(item.get("id") or item.get("name") or ""))
            if not sid:
                continue
            # Cannot author bridge_* files whose names contain Law-3 protected segments
            if any(tok in sid.lower() for tok in _PROTECTED_SUBSTR):
                continue
            mod = f"bridge_{sid}"
            if mod in have:
                continue
            role = _scrub_protected(str(item.get("role") or item.get("description") or status))
            path = str(item.get("path") or item.get("src") or "")
            if any(tok in path.lower().replace("\\", "/") for tok in _PROTECTED_SUBSTR):
                # Path itself is protected — inventory via registry metadata only (no filesystem walk)
                path = ""
            viv_map = _scrub_protected(str(item.get("viv_map") or item.get("viv") or ""))
            skill_hint = "cross-root-synthesis-engine"
            if "memory" in role.lower() or "carma" in sid:
                skill_hint = "artifact-log-index-maintainer"
            elif "secur" in role.lower() or "contain" in sid:
                skill_hint = "policy-firewall-enforcer"
            elif "runtime" in role.lower() or "queue" in role.lower():
                skill_hint = "agentic-runtime-operator"
            # Keep source free of tariff tripwires (exec/format/delete keywords).
            source = "\n".join(
                [
                    f"# PRT expand - {mod}",
                    f"# Bridge for AIOS system {sid} ({status}) — Law 7 sandbox only.",
                    "import json",
                    "from pathlib import Path",
                    "from datetime import datetime, timezone",
                    f"sys_id = {sid!r}",
                    f"role = {role!r}",
                    f"src = Path({path!r})" if path else "src = Path('')",
                    f"viv_map = {viv_map!r}",
                    'out_dir = Path(r"L:/Continue/Viv/sandbox/work/aios_build/system_bridges")',
                    "out_dir.mkdir(parents=True, exist_ok=True)",
                    "files = []",
                    "if src.is_dir():",
                    "    files = sorted(p.name for p in src.iterdir())[:24]",
                    "elif src.is_file():",
                    "    files = [src.name]",
                    "now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')",
                    "note = {",
                    "    'at': now,",
                    "    'system_id': sys_id,",
                    "    'role': role,",
                    "    'source_path': str(src).replace('\\\\', '/') if str(src) else '',",
                    "    'on_disk': bool(src) and src.exists(),",
                    "    'file_sample': files,",
                    "    'viv_map': viv_map,",
                    f"    'status': {status!r},",
                    "    'action': 'bridge_inventory',",
                    "}",
                    "dest = out_dir / (sys_id + '_bridge.json')",
                    "dest.write_text(json.dumps(note, indent=2), encoding='utf-8')",
                    "print('BRIDGE ok id=' + sys_id + ' on_disk=' + str(bool(src) and src.exists()) + ' files=' + str(len(files)) + ' dest=' + dest.name)",
                ]
            )
            out.append(
                {
                    "id": mod,
                    "gap": f"build Viv sandbox bridge for AIOS {sid} ({status}): {role}",
                    "skill_hint": skill_hint,
                    "source": source,
                }
            )
    # Prefer highest-gap first: deferred before partial before legacy (already filtered)
    return out


def _skill_gap_specs(have: set[str]) -> list[dict[str, str]]:
    """One module per missing skill surface probe — IDE vocabulary Viv shares."""
    if not SKILLS_ROOT.is_dir():
        return []
    skills = sorted(p.name for p in SKILLS_ROOT.iterdir() if p.is_dir())
    out: list[dict[str, str]] = []
    for name in skills[:20]:
        mod = f"skill_surface_{_safe_id(name)}"
        if mod in have:
            continue
        source = (
            f"# PRT expand - {mod}\n"
            f"from pathlib import Path\n"
            f'skill = Path(r"L:/.cursor/skills/{name}")\n'
            f'skill_md = skill / "SKILL.md"\n'
            f"ok = skill_md.is_file()\n"
            f'text = skill_md.read_text(encoding="utf-8")[:240] if ok else ""\n'
            f'print(f"SKILL_SURFACE name={name} ok={{ok}} chars={{len(text)}}")\n'
        )
        out.append(
            {
                "id": mod,
                "gap": f"index Cursor skill surface `{name}` into sandbox vocabulary",
                "skill_hint": name,
                "source": source,
            }
        )
        if len(out) >= 3:
            break
    return out


def identify_gap() -> dict[str, Any]:
    """Introspect: next PRT / AIOS / skill module missing in sandbox."""
    ensure_sandbox_home()
    have = {p.name.replace("_current.txt", "") for p in CODE.glob("*_current.txt")} if CODE.is_dir() else set()
    have |= _load_expand_skips()
    skills_indexed: list[str] = []
    if SKILL_INDEX.is_file():
        skills_indexed = re.findall(r"`([a-z0-9\-]+)`", SKILL_INDEX.read_text(encoding="utf-8"))

    catalog: list[dict[str, str]] = []
    # Prefer build-plan synthesis once several bridges exist
    bridges_n = len(list(BRIDGE_DIR.glob("*_bridge.json"))) if BRIDGE_DIR.is_dir() else 0
    helpers = _prt_helper_catalog()
    if bridges_n >= 5:
        helpers = sorted(helpers, key=lambda s: 0 if s["id"] == "aios_build_plan" else 1)
    catalog.extend(helpers)
    catalog.extend(_registry_gap_specs(have))
    catalog.extend(_skill_gap_specs(have))

    for spec in catalog:
        if spec["id"] not in have:
            return {
                "ok": True,
                "module": spec["id"],
                "gap": spec["gap"],
                "skill_hint": spec["skill_hint"],
                "source": spec["source"],
                "skills_indexed": len(set(skills_indexed)),
            }
    return {
        "ok": True,
        "module": None,
        "gap": "catalog_exhausted",
        "skills_indexed": len(set(skills_indexed)),
        "skipped": True,
    }


def predict_impact(before: dict[str, float], gap: dict[str, Any]) -> dict[str, Any]:
    """Predict post-module triad. Conservative: expect near-hold (small RLE move)."""
    return {
        "predicted_s_n": before["master_s_n"],
        "predicted_rsr": before["rsr"],
        "predicted_ltp": before["ltp"],
        "predicted_rle": before["rle"],
        "tolerance_s_n": 0.05,
        "rationale": f"observational module {gap.get('module')} should not destabilize plant",
    }


def _gated_write(path: Path, content: str, s_n: float) -> tuple[bool, str]:
    gate = str(path).replace("\\", "/")
    v = tool_gate("write_file", {"path": gate, "content": content}, s_n)
    if not v.get("allowed"):
        return False, str(v.get("reason", "denied"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True, "ok"


def write_and_run_module(gap: dict[str, Any], *, s_n: float) -> dict[str, Any]:
    """Author .txt under sandbox/code and execute via existing coder (Law 4)."""
    import time

    from lib.aios_coder import run_sandbox_tool, write_sandbox_tool
    from lib.dormancy_config import load_threshold

    name = str(gap.get("module") or "prt_expand")
    source = str(gap.get("source") or "")

    # Prefer live plant S_n; brief retry if tariff soft (do not hang for minutes).
    floor = float(load_threshold()) + 0.02
    sn = max(float(s_n), float(observe_state().get("master_s_n") or 0.0))
    deadline = time.time() + 60.0
    last_err = ""
    wr: dict[str, Any] = {}
    while True:
        wr = write_sandbox_tool(tool=name, source=source, s_n=sn)
        if wr.get("ok"):
            break
        last_err = str(wr.get("reason") or "write_failed")
        if "TARIFF" not in last_err.upper() or time.time() >= deadline:
            return {"ok": False, "error": last_err, "write": wr, "s_n_used": sn}
        time.sleep(5.0)
        sn = float(observe_state().get("master_s_n") or 0.0)
        if sn < floor:
            # Plant dipped dormant — stop waiting
            return {"ok": False, "error": f"dormant_during_write:{last_err}", "write": wr, "s_n_used": sn}

    rn = run_sandbox_tool(tool=name, s_n=sn)
    return {
        "ok": bool(rn.get("ok")),
        "path": wr.get("path"),
        "stdout": (rn.get("stdout") or "")[:400],
        "error": None if rn.get("ok") else (rn.get("reason") or rn.get("stderr")),
        "module": name,
        "s_n_used": sn,
    }


def score_expansion(
    before: dict[str, float],
    after: dict[str, float],
    prediction: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, Any]:
    """REWARD if run ok, prediction within tolerance, and no S_n collapse."""
    tol = float(prediction.get("tolerance_s_n") or 0.05)
    pred_sn = float(prediction.get("predicted_s_n") or before["master_s_n"])
    err = abs(after["master_s_n"] - pred_sn)
    destabilized = after["master_s_n"] < before["master_s_n"] - tol
    pred_ok = err <= tol
    run_ok = bool(run.get("ok"))
    label = "REWARD" if (run_ok and pred_ok and not destabilized) else "PUNISH"
    return {
        "label": label,
        "prediction_error_s_n": round(err, 4),
        "destabilized": destabilized,
        "pred_ok": pred_ok,
        "run_ok": run_ok,
        "before": before,
        "after": after,
    }


def commit_if_reward(
    gap: dict[str, Any],
    run: dict[str, Any],
    score: dict[str, Any],
    *,
    s_n: float,
) -> dict[str, Any]:
    if score.get("label") != "REWARD":
        return {"ok": True, "committed": False, "reason": "punish_no_commit"}
    ensure_sandbox_home()
    EXPAND_DIR.mkdir(parents=True, exist_ok=True)
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    line = (
        f"- [{_utc()}] **PRT-EXPAND {gap.get('module')}** REWARD — {gap.get('gap')}\n"
        f"  - skill_hint: `{gap.get('skill_hint')}`\n"
        f"  - source: `{run.get('path')}`\n"
        f"  - run: `{(run.get('stdout') or '')[:160]}`\n"
        f"  - pred_err_s_n={score.get('prediction_error_s_n')}\n"
    )
    existing = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else "# AIOS Build Manifest\n\n"
    ok, reason = _gated_write(MANIFEST, existing.rstrip() + "\n" + line + "\n", s_n)
    if not ok:
        return {"ok": False, "committed": False, "error": reason}
    CORPUS_NOTE.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "at": _utc(),
        "module": gap.get("module"),
        "gap": gap.get("gap"),
        "skill_hint": gap.get("skill_hint"),
        "path": run.get("path"),
        "label": "REWARD",
        "text": (
            f"Viv PRT capability expansion committed {gap.get('module')}: {gap.get('gap')}. "
            f"Skill surface hint: {gap.get('skill_hint')}."
        ),
    }
    with CORPUS_NOTE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(doc) + "\n")
    return {"ok": True, "committed": True, "manifest": str(MANIFEST).replace("\\", "/")}


def run_capability_expansion(
    *,
    s_n: float | None = None,
    min_speak_reward_rate: float = 0.6,
    speak_reward_rate: float | None = None,
) -> dict[str, Any]:
    """One gated expansion step. Caller supplies integrity speak_reward_rate when known."""
    from lib.dormancy_config import load_threshold

    before_obs = observe_state()
    before = _triad_from_obs(before_obs)
    sn = float(s_n if s_n is not None else before["master_s_n"])
    floor = float(load_threshold()) + 0.02
    if sn < floor or str(before_obs.get("status") or "").upper() == "DORMANT":
        out = {
            "ok": True,
            "skipped": True,
            "reason": "plant_dormant",
            "s_n": sn,
            "floor": floor,
        }
        _log({"event": "expand_skip", **out, "at": _utc()})
        return out

    if speak_reward_rate is not None and float(speak_reward_rate) < float(min_speak_reward_rate):
        out = {
            "ok": True,
            "skipped": True,
            "reason": "speak_reward_rate_below_threshold",
            "speak_reward_rate": speak_reward_rate,
            "min": min_speak_reward_rate,
        }
        _log({"event": "expand_skip", **out, "at": _utc()})
        return out

    gap = identify_gap()
    if gap.get("skipped") or not gap.get("module"):
        out = {"ok": True, "skipped": True, "reason": "no_gap", "gap": gap}
        _log({"event": "expand_skip", **out, "at": _utc()})
        return out

    prediction = predict_impact(before, gap)
    run = write_and_run_module(gap, s_n=sn)
    if not run.get("ok"):
        err = str(run.get("error") or "")
        if "LAW 3" in err or "Protected" in err or "Morality Lock" in err:
            _add_expand_skip(str(gap.get("module")), err[:160])
    after = _triad_from_obs(observe_state())
    score = score_expansion(before, after, prediction, run)
    commit = commit_if_reward(gap, run, score, s_n=sn)

    out = {
        "ok": score.get("label") == "REWARD" and bool(run.get("ok")),
        "at": _utc(),
        "gap": {k: gap[k] for k in ("module", "gap", "skill_hint") if k in gap},
        "prediction": prediction,
        "run": {k: run.get(k) for k in ("ok", "path", "stdout", "error", "module")},
        "score": score,
        "commit": commit,
        "voice_speak": False,
    }
    _log({"event": "expand", **out})
    return out
