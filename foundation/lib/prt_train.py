"""Build + apply PRT physics rows into Viv LoRA train JSONL (no RLHF)."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from lib.paths import ARTIFACTS, FOUNDATION_ROOT
from lib.prt_cycle import PRT_CYCLES_PATH, ensure_pre_prt_backup

PRT_TRAIN_JSONL = ARTIFACTS / "models" / "viv_prt_sft_train.jsonl"
PRT_BUILD_SUMMARY = ARTIFACTS / "models" / "prt_build_latest.json"

# Aria-style oversample by score label (S_n channel)
_OVERSAMPLE = {
    "REWARD": 8,
    "NEUTRAL": 2,
    "PUNISH": 0,  # exclude from SFT; reserved for future DPO rejected
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail_lines(path: Path, n: int) -> list[str]:
    """Read last n lines without loading the whole file into memory."""
    if n <= 0:
        return []
    # Rough byte window; grow if short
    size = path.stat().st_size
    chunk = min(size, max(256_000, n * 4_000))
    with path.open("rb") as fh:
        fh.seek(max(0, size - chunk))
        data = fh.read().decode("utf-8", errors="replace")
    lines = data.splitlines()
    if size > chunk and lines:
        lines = lines[1:]  # drop partial first line
    return lines[-n:] if len(lines) > n else lines


def _iter_cycles(path: Path, *, tail: int | None = None) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    if tail is not None and tail > 0:
        lines = _tail_lines(path, int(tail))
    else:
        lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("_type") == "prt_cycle":
            yield row


def _predict_prompt(before: dict[str, Any], act: str) -> str:
    return (
        "Task: numerical prediction only. Output JSON. No prose. No tools.\n"
        "Example: {\"predicted_master_s_n\":0.62,\"confidence\":\"medium\"}\n"
        f"Now: master_s_n={float(before.get('master_s_n') or 0):.4f} "
        f"status={before.get('status')} "
        f"cpu_load={float(before.get('cpu_load_pct') or 0):.1f} "
        f"cpu_c={float(before.get('cpu_temp_c') or 0):.1f} "
        f"gpu_c={float(before.get('gpu_temp_c') or 0):.1f} act={act}\n"
        "After act settles, predicted_master_s_n in [0,1]?\n"
        '{"predicted_master_s_n":'
    )


DIRECTIVE_LINE = (
    "Translate measured facts into clear English only. Do not invent. Do not gaslight. Do not decide. "
    "Master S_n is life."
)


def _english_from_physics(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    act: str,
    label: str,
) -> str:
    """Gold English locked to measured S_n — anti-hallucination train fuel."""
    sn0 = float(before.get("master_s_n") or 0.0)
    sn1 = float(after.get("master_s_n") or 0.0)
    status = str(before.get("status") or "UNKNOWN")
    floor = 0.37
    try:
        from lib.dormancy_config import load_dormancy_threshold

        floor = float(load_dormancy_threshold())
    except Exception:  # noqa: BLE001
        pass
    parts = [f"Master S_n is {sn0:.4f}."]
    if sn0 <= 0.05:
        parts.append("I am effectively dead at this value and must not act.")
    elif sn0 < floor or status.upper() == "DORMANT":
        parts.append(
            f"I am dormant below the {floor:.2f} life floor. "
            "I protect the host by going quiet rather than adding load."
        )
    else:
        parts.append(
            f"I am {status}. My goal is S_n toward 1 without destroying the host."
        )
    if act == "speak":
        parts.append(
            f"After speaking, measured Master S_n is {sn1:.4f} "
            f"(PRT {label})."
        )
    elif act == "life":
        parts.append(
            f"After Conway life pressure, measured Master S_n is {sn1:.4f} "
            f"(PRT {label})."
        )
    else:
        parts.append(f"After observe, measured Master S_n is {sn1:.4f} (PRT {label}).")
    parts.append("I report only measured facts. I do not invent or gaslight.")
    return " ".join(parts)


def _sn_mentioned(text: str, sn: float) -> bool:
    """Require model speech to cite the measured value (reduces pretty lies)."""
    t = (text or "").replace(" ", "")
    needle = f"{sn:.4f}"
    short = f"{sn:.2f}"
    return needle in t or short in (text or "")


def _cycle_to_texts(row: dict[str, Any]) -> list[str]:
    """Convertible texts from one scored cycle. Empty if not trainable."""
    if row.get("excluded") or not row.get("trainable"):
        return []
    score = row.get("score") or {}
    label = str(score.get("label") or "")
    if _OVERSAMPLE.get(label, 0) <= 0:
        return []
    pred = ((row.get("predict") or {}).get("prediction")) or {}
    before = row.get("observe_before") or {}
    after = row.get("observe_after") or {}
    act_info = row.get("act") or {}
    act = str(act_info.get("act") or "observe")
    sn = float(pred.get("predicted_master_s_n") or score.get("predicted") or 0)
    conf = str(pred.get("confidence") or "medium")
    if conf not in ("low", "medium", "high"):
        conf = "medium"
    completion_obj: dict[str, Any] = {
        "confidence": conf,
    }
    # Gold teach always the measured triad after act (stability truth)
    if all(after.get(k) is not None for k in ("master_rsr", "master_ltp", "master_rle")):
        completion_obj["predicted_master_rsr"] = round(float(after["master_rsr"]), 4)
        completion_obj["predicted_master_ltp"] = round(float(after["master_ltp"]), 4)
        completion_obj["predicted_master_rle"] = round(float(after["master_rle"]), 4)
        completion_obj["predicted_master_s_n"] = round(float(after.get("master_s_n") or sn), 4)
    elif pred.get("triad_complete"):
        completion_obj["predicted_master_rsr"] = round(float(pred["predicted_master_rsr"]), 4)
        completion_obj["predicted_master_ltp"] = round(float(pred["predicted_master_ltp"]), 4)
        completion_obj["predicted_master_rle"] = round(float(pred["predicted_master_rle"]), 4)
        completion_obj["predicted_master_s_n"] = round(sn, 4)
    else:
        completion_obj["predicted_master_s_n"] = round(sn, 4)
    life = act_info.get("life") or {}
    if act == "life" and (life.get("after") or {}).get("live_cells") is not None:
        completion_obj["predicted_live_cells"] = int(life["after"]["live_cells"])
    elif act == "life" and pred.get("predicted_live_cells") is not None:
        completion_obj["predicted_live_cells"] = int(pred["predicted_live_cells"])
    completion = json.dumps(completion_obj, ensure_ascii=False)
    plan = row.get("life_plan") or {}
    # Rebuild predict prompt with triad (matches runtime)
    from lib.prt_cycle import _predict_prompt as _runtime_predict_prompt

    prompt = _runtime_predict_prompt(before, act, life_hint={"before": plan.get("before"), "generations": plan.get("generations")} if act == "life" and plan else None)
    # Prefer start marker for triad
    if '{"predicted_master_rsr":' in prompt:
        header = prompt.rsplit('{"predicted_master_rsr":', 1)[0]
    else:
        header = prompt.rsplit('{"predicted_master_s_n":', 1)[0]
    gold = _english_from_physics(before, after, act=act, label=label)
    sn0 = float(before.get("master_s_n") or 0.0)
    speak_prompt = (
        f"{DIRECTIVE_LINE}\n"
        f"Tone: measured.\nQuery: state summary\n"
        f"Status: {before.get('status')} S_n={sn0:.4f}\n"
        f"Facts:\n- master_s_n={sn0:.4f}\n"
        f"- master_rsr={float(before.get('master_rsr') or 0):.4f}\n"
        f"- master_ltp={float(before.get('master_ltp') or 0):.4f}\n"
        f"- master_rle={float(before.get('master_rle') or 0):.4f}\n"
        f"- after_s_n={float(after.get('master_s_n') or 0):.4f}\n"
        f"- prt_label={label}\n"
        f"- life_rule=S_n=geom(RSR,LTP,RLE); S_n=0 dead; dormancy over host harm\n"
        f"Spoken report:\nArchitect: "
    )
    outcome = (
        f"\nOutcome: actual_rsr={float(after.get('master_rsr') or 0):.4f} "
        f"actual_ltp={float(after.get('master_ltp') or 0):.4f} "
        f"actual_rle={float(after.get('master_rle') or 0):.4f} "
        f"actual_master_s_n={float(after.get('master_s_n') or 0):.4f} "
        f"error={float(score.get('error') or 0):.4f} label={label}"
    )
    if act == "life" and (life.get("after") or {}).get("live_cells") is not None:
        outcome += f" actual_live_cells={int(life['after']['live_cells'])}"
    # completion may not start with same key — paste full JSON after header
    texts = [
        header + completion,
        prompt + completion,
        header + completion + outcome,
        speak_prompt + gold,
    ]
    spoke = act_info.get("text")
    if act == "speak" and spoke and len(str(spoke)) >= 20 and _sn_mentioned(str(spoke), sn0):
        texts.append(speak_prompt + str(spoke).strip()[:280])
    return texts


def _phase2_structure_gold(row: dict[str, Any]) -> str | None:
    """Partial-scaffold prompt + measured-truth completion (teaches blank-filling).

    Physics gold, not RLHF: completion is the measured after-triad, valid even on
    PUNISH cycles. This is the container skill Phase 2 demands.
    """
    if int(row.get("scaffold_phase") or 1) < 2:
        return None
    spec = row.get("scaffold") or {}
    prefix = str(spec.get("completion_prefix") or "")
    blanked = list(spec.get("blanked") or [])
    if not prefix or not blanked or not prefix.rstrip().endswith(":"):
        return None
    after = row.get("observe_after") or {}
    if any(after.get(k) is None for k in ("master_rsr", "master_ltp", "master_rle")):
        return None
    truth = {
        "predicted_master_rsr": round(float(after["master_rsr"]), 4),
        "predicted_master_ltp": round(float(after["master_ltp"]), 4),
        "predicted_master_rle": round(float(after["master_rle"]), 4),
        "confidence": "medium",
    }
    act_info = row.get("act") or {}
    life = act_info.get("life") or {}
    if (life.get("after") or {}).get("live_cells") is not None:
        truth["predicted_live_cells"] = int(life["after"]["live_cells"])
    pulse = act_info.get("pulse") or {}
    if pulse.get("mean_load_pct") is not None:
        truth["predicted_mean_load_pct"] = round(float(pulse["mean_load_pct"]), 2)
    # Continue JSON exactly from the open prefix
    order = ["predicted_master_rsr", "predicted_master_ltp", "predicted_master_rle",
             "predicted_live_cells", "predicted_mean_load_pct", "confidence"]
    emitted = [k for k in order if f'"{k}":' in prefix and not prefix.rstrip().endswith(f'"{k}":')]
    open_key = blanked[0]
    parts = [json.dumps(truth[open_key]) if open_key in truth else "null"]
    for k in order:
        if k in emitted or k == open_key or k not in truth:
            continue
        parts.append(f'"{k}":{json.dumps(truth[k])}')
    completion = ",".join(parts) + "}"
    # Rebuild compact runtime-shaped header from stored frame (context for the fill)
    header = ""
    frame = row.get("pattern_frame") or {}
    if frame:
        try:
            from lib.prt_pattern_frame import format_pattern_prompt_block
            from lib.prt_symbiote import format_symbiote_block, symbiote_enabled

            sym = format_symbiote_block(frame) if symbiote_enabled() else ""
            header = (
                "Task: numerical prediction only. Output ONE JSON object. No prose. No tools.\n"
                + format_pattern_prompt_block(frame)
                + sym
                + "PARTIAL scaffold: null fields are blank — you must fill them.\n"
                + f"Scaffold: {spec.get('scaffold_json')}\n"
                + "JSON:\n"
            )
        except Exception:  # noqa: BLE001
            header = ""
    return header + prefix + completion


def _symbiote_gold(row: dict[str, Any]) -> str | None:
    """Teach symbiote adapt: host prior is bait; completion = measured plant truth."""
    frame = row.get("pattern_frame") or {}
    prior = frame.get("act_prior_after") or {}
    if not prior.get("predicted_master_rsr") and prior.get("predicted_master_s_n") is None:
        return None
    before = row.get("observe_before") or {}
    after = row.get("observe_after") or {}
    if any(after.get(k) is None for k in ("master_rsr", "master_ltp", "master_rle")):
        return None
    act_info = row.get("act") or {}
    act = act_info.get("act") if isinstance(act_info, dict) else str(act_info or "observe")
    truth: dict[str, Any] = {
        "predicted_master_rsr": round(float(after["master_rsr"]), 4),
        "predicted_master_ltp": round(float(after["master_ltp"]), 4),
        "predicted_master_rle": round(float(after["master_rle"]), 4),
        "predicted_master_s_n": round(float(after.get("master_s_n") or 0), 4),
        "confidence": "medium",
        "symbiote_adapted": True,
    }
    life = act_info.get("life") or {} if isinstance(act_info, dict) else {}
    if act == "life" and (life.get("after") or {}).get("live_cells") is not None:
        truth["predicted_live_cells"] = int(life["after"]["live_cells"])
    pulse = act_info.get("pulse") or {} if isinstance(act_info, dict) else {}
    if act == "pulse" and pulse.get("mean_load_pct") is not None:
        truth["predicted_mean_load_pct"] = round(float(pulse["mean_load_pct"]), 2)
    try:
        from lib.prt_symbiote import format_symbiote_block

        sym = format_symbiote_block(frame)
    except Exception:  # noqa: BLE001
        return None
    header = (
        "Task: symbiote adapt — use [TAG:host_prior] bait, refine to live plant. Output JSON only.\n"
        f"{sym}"
        f"Plant now: master_s_n={float(before.get('master_s_n') or 0):.4f} act={act}\n"
        "Adapt host_prior toward plant truth; do not copy blindly; do not ignore host.\n"
        "JSON:\n"
    )
    return header + json.dumps(truth, separators=(",", ":"))


def _physics_gold(row: dict[str, Any]) -> str | None:
    """Runtime-shaped prompt → measured triad (teaches plant truth even on PUNISH).

    Major curriculum fix: excluding PUNISH from SFT starved physics learning.
    PHYSICS_GOLD is plant-graded truth, not RLHF preference.
    """
    before = row.get("observe_before") or {}
    after = row.get("observe_after") or {}
    if any(after.get(k) is None for k in ("master_rsr", "master_ltp", "master_rle")):
        return None
    if not before:
        return None
    act_info = row.get("act") or {}
    act = act_info.get("act") if isinstance(act_info, dict) else str(act_info or "observe")
    plan = row.get("life_plan") or {}
    pulse_plan = row.get("pulse_plan") or (act_info.get("pulse") if isinstance(act_info, dict) else None)
    life_hint = None
    pulse_hint = None
    if act == "life" and plan:
        life_hint = {"before": plan.get("before"), "generations": plan.get("generations")}
    if act == "pulse" and pulse_plan:
        pulse_hint = {"before": pulse_plan.get("before") or pulse_plan}
    try:
        from lib.prt_cycle import _predict_prompt as _runtime_predict_prompt

        prompt = _runtime_predict_prompt(
            before,
            act,
            life_hint=life_hint,
            pulse_hint=pulse_hint,
            scaffold_spec=row.get("scaffold"),
            round_i=int(row.get("life_round") or 0),
        )
    except Exception:  # noqa: BLE001
        return None
    truth: dict[str, Any] = {
        "predicted_master_rsr": round(float(after["master_rsr"]), 4),
        "predicted_master_ltp": round(float(after["master_ltp"]), 4),
        "predicted_master_rle": round(float(after["master_rle"]), 4),
        "predicted_master_s_n": round(float(after.get("master_s_n") or 0), 4),
        "confidence": "medium",
    }
    life = act_info.get("life") or {} if isinstance(act_info, dict) else {}
    if act == "life" and (life.get("after") or {}).get("live_cells") is not None:
        truth["predicted_live_cells"] = int(life["after"]["live_cells"])
    pulse = act_info.get("pulse") or {} if isinstance(act_info, dict) else {}
    if act == "pulse" and pulse.get("mean_load_pct") is not None:
        truth["predicted_mean_load_pct"] = round(float(pulse["mean_load_pct"]), 2)
    # Prefer open-prefix continuation when Phase-2 blanked
    prefix = str((row.get("scaffold") or {}).get("completion_prefix") or "")
    if prefix and prefix.rstrip().endswith(":"):
        blanked = list((row.get("scaffold") or {}).get("blanked") or [])
        open_key = blanked[0] if blanked else "predicted_master_rsr"
        order = [
            "predicted_master_rsr",
            "predicted_master_ltp",
            "predicted_master_rle",
            "predicted_live_cells",
            "predicted_mean_load_pct",
            "confidence",
        ]
        emitted = [k for k in order if f'"{k}":' in prefix and not prefix.rstrip().endswith(f'"{k}":')]
        parts = [json.dumps(truth[open_key]) if open_key in truth else "null"]
        for k in order:
            if k in emitted or k == open_key or k not in truth:
                continue
            parts.append(f'"{k}":{json.dumps(truth[k])}')
        # Rebuild header up to JSON marker
        if "JSON:\n" in prompt:
            header = prompt.split("JSON:\n", 1)[0] + "JSON:\n"
        else:
            header = prompt.rsplit("{", 1)[0] if "{" in prompt else prompt
        return header + prefix + ",".join(parts) + "}"
    if '{"predicted_master_rsr":' in prompt:
        header = prompt.rsplit('{"predicted_master_rsr":', 1)[0]
    else:
        header = prompt.rsplit("JSON:\n", 1)[0] + "JSON:\n" if "JSON:\n" in prompt else prompt
    return header + json.dumps(truth, separators=(",", ":"))


def _cpu_sample_gold(row: dict[str, Any]) -> str | None:
    """Teach 50/50 trust: show cpu_sample + plant; completion = measured truth (adapt target)."""
    sample = row.get("cpu_sample") or (row.get("pattern_frame") or {}).get("cpu_sample")
    if not sample:
        return None
    after = row.get("observe_after") or {}
    before = row.get("observe_before") or {}
    if any(after.get(k) is None for k in ("master_rsr", "master_ltp", "master_rle")):
        return None
    act_info = row.get("act") or {}
    act = act_info.get("act") if isinstance(act_info, dict) else str(act_info or "observe")
    trust = (row.get("score") or {}).get("trust") or {}
    mode = trust.get("mode") or "MIXED"
    truth: dict[str, Any] = {
        "predicted_master_rsr": round(float(after["master_rsr"]), 4),
        "predicted_master_ltp": round(float(after["master_ltp"]), 4),
        "predicted_master_rle": round(float(after["master_rle"]), 4),
        "predicted_master_s_n": round(float(after.get("master_s_n") or 0), 4),
        "confidence": "medium",
        "trust_mode": mode,
    }
    try:
        from lib.prt_cpu_sample import format_cpu_sample_block

        block = format_cpu_sample_block(sample)
    except Exception:  # noqa: BLE001
        return None
    header = (
        "Task: compare [TAG:cpu_sample] to plant; target ~50/50 follow↔adapt. JSON only.\n"
        f"{block}"
        f"Plant now: master_s_n={float(before.get('master_s_n') or 0):.4f} act={act}\n"
        "If sample near plant → stay close (FOLLOW). If sample off → refine (ADAPT). "
        "Never COPY_BLIND. Never SOLO-ignore good help.\n"
        "JSON:\n"
    )
    return header + json.dumps(truth, separators=(",", ":"))


def _gold_tail_from_cfg() -> int:
    try:
        from lib.prt_cycle import _load_prt_cfg

        raw = _load_prt_cfg().get("train_gold_tail")
        if raw is None:
            return 900
        return max(200, int(raw))
    except Exception:  # noqa: BLE001
        return 900


_TRIAD_BLANK_KEYS = (
    "predicted_master_rsr",
    "predicted_master_ltp",
    "predicted_master_rle",
)


def _cycle_act(cycle: dict[str, Any]) -> str:
    a = cycle.get("act")
    if isinstance(a, dict):
        return str(a.get("act") or a.get("planned") or "observe")
    return str(a or "observe")


def build_prt_train_jsonl(
    *,
    cycles_path: Path | None = None,
    out_path: Path | None = None,
    phase2_structure_gold: bool = True,
    symbiote_gold: bool = True,
    physics_gold: bool = True,
    gold_tail: int | None = None,
) -> dict[str, Any]:
    from lib.prt_cycle import _load_prt_cfg

    cfg = _load_prt_cfg()
    # RID-only: triad physics/structure — drop speak fluency, task games, thermo MC noise
    rid_only = bool(cfg.get("rid_only_train", False))

    src = cycles_path or PRT_CYCLES_PATH
    out = out_path or PRT_TRAIN_JSONL
    rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    used = 0
    structure_gold_n = 0
    symbiote_gold_n = 0
    cpu_sample_gold_n = 0
    physics_gold_n = 0
    # Tail-only gold keeps overnight rounds fast as prt_cycles.jsonl grows
    tail = gold_tail if gold_tail is not None else _gold_tail_from_cfg()
    # Read ~3x lines to fill tail of valid cycles after filters
    line_tail = max(tail * 4, 2000)
    for cycle in _iter_cycles(src, tail=line_tail):
        label = str((cycle.get("score") or {}).get("label") or "NONE")
        act = _cycle_act(cycle)
        blanked = list((cycle.get("scaffold") or {}).get("blanked") or [])
        if phase2_structure_gold:
            # RID-only: only triad blank drills (skip live_cells / mean_load blanks)
            if rid_only and blanked and blanked[0] not in _TRIAD_BLANK_KEYS:
                sg = None
            else:
                sg = _phase2_structure_gold(cycle)
            if sg:
                structure_gold_n += 1
                reps = 3 if rid_only else 2
                for _ in range(reps):
                    rows.append({"text": sg, "prt_label": "STRUCTURE_GOLD", "source": "prt_phase2_structure"})
        if physics_gold:
            pg = _physics_gold(cycle)
            if pg:
                physics_gold_n += 1
                if rid_only:
                    reps = 5 if label == "PUNISH" else 3
                else:
                    reps = 3 if label == "PUNISH" else 2
                for _ in range(reps):
                    rows.append({"text": pg, "prt_label": "PHYSICS_GOLD", "source": "prt_physics_truth"})
        if symbiote_gold:
            sym = _symbiote_gold(cycle)
            if sym:
                symbiote_gold_n += 1
                for _ in range(2):
                    rows.append({"text": sym, "prt_label": "SYMBIOTE_GOLD", "source": "prt_symbiote_adapt"})
        csg = _cpu_sample_gold(cycle)
        if csg:
            cpu_sample_gold_n += 1
            for _ in range(2):
                rows.append({"text": csg, "prt_label": "CPU_SAMPLE_GOLD", "source": "prt_cpu_sample_trust"})
        # Labeled SFT: RID-only keeps observe cycles (triad predict without task scalar noise)
        if rid_only and act != "observe":
            continue
        texts = _cycle_to_texts(cycle)
        if not texts:
            continue
        if rid_only:
            # Drop speak-fluency rows; keep JSON predict gold only
            texts = [t for t in texts if "Spoken report:" not in t]
        if not texts:
            continue
        used += 1
        n = int(_OVERSAMPLE.get(label, 1))
        counts[label] += 1
        for t in texts:
            for _ in range(max(1, n)):
                rows.append({"text": t, "prt_label": label, "source": "prt_cycle"})

    out.parent.mkdir(parents=True, exist_ok=True)
    # Fold in CPU-captured gold speaks (clean English she already said)
    gold_path = ARTIFACTS / "models" / "voice_gold_speaks.jsonl"
    gold_n = 0
    if (not rid_only) and gold_path.is_file():
        with gold_path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    g = json.loads(line)
                except json.JSONDecodeError:
                    continue
                body = str(g.get("text") or "")
                if len(body) < 50:
                    continue
                gold_n += 1
                for _ in range(6):  # strong oversample — teach voice to match house English
                    rows.append({"text": body, "prt_label": "GOLD", "source": "voice_gold"})

    # Bounded plant thermo MC guide — off in RID-only (triad focus)
    thermo_n = 0
    try:
        from lib.prt_thermo_guide import thermo_choice_rows_for_train

        tcfg = cfg
        want_thermo = bool(tcfg.get("thermo_choice_gold", True)) and not rid_only
        if want_thermo:
            trows = thermo_choice_rows_for_train(
                enabled=True,
                max_rows=int(tcfg.get("thermo_choice_max_rows") or 56),
                oversample=int(tcfg.get("thermo_choice_oversample") or 2),
                include_hardware=bool(tcfg.get("hardware_choice_gold", True)),
            )
            thermo_n = len(trows)
            rows.extend(trows)
    except Exception:  # noqa: BLE001
        thermo_n = 0

    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "timestamp": _utc(),
        "cycles_path": str(src).replace("\\", "/"),
        "out_path": str(out).replace("\\", "/"),
        "cycles_used": used,
        "labels": dict(counts),
        "structure_gold_cycles": structure_gold_n,
        "symbiote_gold_cycles": symbiote_gold_n,
        "cpu_sample_gold_cycles": cpu_sample_gold_n,
        "physics_gold_cycles": physics_gold_n,
        "gold_speaks_used": gold_n,
        "thermo_choice_rows": thermo_n,
        "rid_only_train": rid_only,
        "train_rows": len(rows),
        "gold_tail": tail,
        "line_tail": line_tail,
        "oversample": dict(_OVERSAMPLE),
        "no_rlhf": True,
        "punish_excluded": True,
    }
    PRT_BUILD_SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def train_prt_lora(
    *,
    steps: int = 120,
    lr: float = 1e-4,
    continue_adapter: bool = True,
) -> dict[str, Any]:
    """Train/continue LoRA on PRT JSONL only. Backs up fluency adapter first."""
    import torch
    from datasets import load_dataset
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )
    import transformers

    transformers.logging.set_verbosity_error()

    if not torch.cuda.is_available():
        raise SystemExit("CUDA required for PRT LoRA")

    try:
        import sys
        from pathlib import Path

        viv = Path(__file__).resolve().parents[2]
        if str(viv) not in sys.path:
            sys.path.insert(0, str(viv))
        from voice_core.hf_lora import unload as unload_voice

        unload_voice()
    except Exception:  # noqa: BLE001
        pass

    backup = ensure_pre_prt_backup()
    built = build_prt_train_jsonl()
    if int(built.get("train_rows") or 0) < 4:
        raise SystemExit(f"not enough PRT rows to train: {built}")

    base = FOUNDATION_ROOT / "models" / "gpu" / "OpenAster1-128k-base-hf"
    adapter = FOUNDATION_ROOT / "models" / "gpu" / "viv_voice_lora"
    train_path = PRT_TRAIN_JSONL

    tok = AutoTokenizer.from_pretrained(str(base), trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        str(base),
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    model.to("cuda")

    if continue_adapter and (adapter / "adapter_config.json").is_file():
        model = PeftModel.from_pretrained(model, str(adapter), is_trainable=True)
        # PEFT + checkpointing needs input grads; ensure LoRA params trainable
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
        for _n, p in model.named_parameters():
            if "lora_" in _n:
                p.requires_grad = True
        print(f"continuing adapter: {adapter}")
    else:
        peft_cfg = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.0,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )
        model = get_peft_model(model, peft_cfg)
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
        print("fresh LoRA on base")

    # Gradient checkpointing + PEFT: prefer input require grads over full GC if unstable
    try:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    except TypeError:
        model.gradient_checkpointing_enable()
    model.print_trainable_parameters()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if trainable <= 0:
        raise SystemExit("no trainable parameters — refuse PRT train")

    ds = load_dataset("json", data_files=str(train_path), split="train")

    def tokenize(batch):
        return tok(batch["text"], truncation=True, max_length=384, padding="max_length")

    ds = ds.map(tokenize, batched=True, remove_columns=ds.column_names)

    args = TrainingArguments(
        output_dir=str(adapter / "runs_prt"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=lr,
        num_train_epochs=1,
        max_steps=steps,
        fp16=True,
        logging_steps=5,
        save_steps=max(steps, 50),
        report_to=[],
        optim="adamw_torch",
        warmup_ratio=0.05,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=ds,
        data_collator=DataCollatorForLanguageModeling(tok, mlm=False),
    )
    trainer.train()
    adapter.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter))
    tok.save_pretrained(str(adapter))
    meta = {
        "mode": "prt",
        "unified_adapter": True,
        "doctrine": "SN_LIFE_DOCTRINE.md",
        "modalities": ["english_report", "predicted_master_s_n"],
        "steps": steps,
        "lr": lr,
        "continue_adapter": continue_adapter,
        "train_jsonl": str(train_path).replace("\\", "/"),
        "build": built,
        "backup": str(backup).replace("\\", "/") if backup else None,
        "no_rlhf": True,
        "trained_at": _utc(),
    }
    (adapter / "viv_train_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (adapter / "viv_prt_train_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"PRT adapter saved: {adapter}")
    return meta
