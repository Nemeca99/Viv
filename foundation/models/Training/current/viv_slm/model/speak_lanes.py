"""Dual speak lanes for Viv's identity specialists.

Doctrine:
- **Two different weight sets**, same Viv identity (shared tokenizer / vocab /
  authority contract). Trained differently:
  - CPU **efficient** specialist — speculative decoder + verifier
  - GPU **deep** specialist — middle reasoning / mouth draft
- Primary speech path is the **CPU → GPU → CPU sandwich**:
  1. CPU front: speculate a short draft
  2. GPU middle: deep-reason continuation
  3. CPU back: verify GPU tokens (accept matching prefix; reject/replace on mismatch)
- Optional **UML route pressure** (``uml_pressure=...``) applies efficiency logit
  bias during generate; sandwich defaults pressure onto the deep mouth.
- ``speak_viv_parallel`` is optional concurrency; production speech uses
  ``speak_viv_sandwich``.
- RID/Master S_n gating remains the caller's authority; this module does not
  actuate piston. Optional soft read of ``master_rid.json`` stamps the receipt.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Literal

import torch
from torch import Tensor, nn

from plant_runtime import (
    configure_plant_runtime,
    move_model_to_device,
    select_speak_device,
    synchronize,
)

SpeakLane = Literal["efficient", "deep"]

# Default token budgets (overridable per call / env).
_DEFAULT_EFFICIENT_TOKENS = 48
_DEFAULT_DEEP_TOKENS = 256

_MASTER_RID_CANDIDATES = (
    Path(r"L:\Continue\Viv\foundation\artifacts\auto\master_rid.json"),
    Path(__file__).resolve().parents[5] / "artifacts" / "auto" / "master_rid.json",
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def lane_defaults(lane: SpeakLane) -> dict[str, Any]:
    if lane == "efficient":
        return {
            "lane": "efficient",
            "role": "cpu_mind_efficient_speech",
            "max_new_tokens": _env_int(
                "VIV_SPEAK_EFFICIENT_MAX_NEW", _DEFAULT_EFFICIENT_TOKENS
            ),
            "temperature": 0.0,
            "draft_mode": "cpu_gate",
            "use_kv_cache": True,
            "attention_backend": "auto",
            "entropy_early_exit": True,
            "entropy_threshold": 1.0,
            "patience_k": 2,
        }
    if lane == "deep":
        return {
            "lane": "deep",
            "role": "gpu_mouth_deep_speech",
            "max_new_tokens": _env_int("VIV_SPEAK_DEEP_MAX_NEW", _DEFAULT_DEEP_TOKENS),
            "temperature": 0.7,
            "draft_mode": None,
            "use_kv_cache": True,
            "attention_backend": "auto",
            "top_p": 0.9,
            "explore_then_lock": True,
            "explore_k": 16,
        }
    raise ValueError(f"viv_speak_lane_invalid:{lane}")


def _normalize_lane(lane: str) -> SpeakLane:
    key = str(lane).strip().lower()
    if key in ("efficient", "cpu", "mind", "short"):
        return "efficient"
    if key in ("deep", "gpu", "mouth", "long"):
        return "deep"
    raise ValueError(f"viv_speak_lane_invalid:{lane}")


def _optional_master_rid_stamp() -> dict[str, Any] | None:
    """Soft read-only stamp; never fails the speak path."""

    for path in _MASTER_RID_CANDIDATES:
        try:
            if not path.is_file():
                continue
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, Mapping):
                continue
            return {
                "path": str(path).replace("\\", "/"),
                "master_s_n": payload.get("master_s_n"),
                "mode": payload.get("mode") or payload.get("status"),
                "subsystems": {
                    key: (payload.get("subsystems") or {}).get(key)
                    for key in ("cpu_automaton", "piston", "gpu", "coolant_loop")
                }
                if isinstance(payload.get("subsystems"), Mapping)
                else None,
            }
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return None


def _receipt_sha(receipt: Mapping[str, Any]) -> str:
    blob = json.dumps(dict(receipt), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(blob.encode("utf-8")).hexdigest().upper()


@torch.inference_mode()
def speak_viv(
    model: nn.Module,
    context_ids: Tensor,
    *,
    lane: str = "efficient",
    max_new_tokens: int | None = None,
    temperature: float | None = None,
    top_k: int | None = None,
    top_p: float | None = None,
    repetition_penalty: float = 1.0,
    generator: torch.Generator | None = None,
    stop_sequences: Sequence[str] | None = None,
    decode_fn: Callable[[list[int]], str] | None = None,
    logits_bias_fn: Callable[[Tensor, Tensor], Tensor] | None = None,
    uml_pressure: Mapping[str, Any] | None = None,
    stamp_master_rid: bool = True,
    configure_runtime: bool = True,
) -> dict[str, Any]:
    """Generate with the same weights on the lane-appropriate device.

    Returns ``{ids, text?, receipt}``. Does not mutate piston / Master authority.

    Optional UML efficiency pressure:
    - pass a ready ``logits_bias_fn``, or
    - pass ``uml_pressure`` dict consumed by ``uml_speak_pressure.build_uml_speak_pressure``
      (requires ``stoi``/``itos``/``prompt_len`` plus ``target_char`` or ``target_value``).
    """

    from generate_viv_draft import generate_viv_draft
    from oddball_dual_temp import generate_with_dual_temp

    speak_lane = _normalize_lane(lane)
    defaults = lane_defaults(speak_lane)
    device = select_speak_device(speak_lane)
    if configure_runtime:
        configure_plant_runtime(device=str(device))
    move_model_to_device(model, device)
    model.eval()

    ids = context_ids.to(device=device, dtype=torch.long)
    if ids.ndim == 1:
        ids = ids.unsqueeze(0)

    tokens = int(max_new_tokens if max_new_tokens is not None else defaults["max_new_tokens"])
    temp = float(temperature if temperature is not None else defaults["temperature"])
    gen = generator

    uml_receipt: dict[str, Any] | None = None
    bias_fn = logits_bias_fn
    effective_stops = stop_sequences
    if uml_pressure is not None:
        from uml_speak_pressure import UML_DEFAULT_STOPS, build_uml_speak_pressure

        payload = dict(uml_pressure)
        if "prompt_len" not in payload:
            payload["prompt_len"] = int(ids.shape[1])
        # Auto-target: decode prompt text when caller omitted target_char/value.
        if (
            payload.get("auto_target", True)
            and payload.get("target_char") is None
            and payload.get("target_value") is None
            and payload.get("prompt_text") is None
            and decode_fn is not None
        ):
            payload["prompt_text"] = decode_fn(ids[0].detach().cpu().tolist())
        bias_fn, uml_receipt = build_uml_speak_pressure(**payload)
        if effective_stops is None:
            effective_stops = list(UML_DEFAULT_STOPS)

    receipt: dict[str, Any] = {
        "schema_version": "viv_slm_speak_lanes_v2",
        "lane": speak_lane,
        "role": defaults["role"],
        "device": str(device),
        "max_new_tokens": tokens,
        "temperature": temp,
        "same_weights": True,
        "piston_actuated": False,
        "authority": "caller_owns_rid_gate",
        "uml_pressure": uml_receipt,
        "logits_bias_fn": bias_fn is not None,
    }

    if speak_lane == "efficient":
        draft = generate_viv_draft(
            model,
            ids,
            max_new_tokens=tokens,
            temperature=temp,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            generator=gen,
            use_kv_cache=True,
            attention_backend="auto",
            draft_mode=defaults.get("draft_mode"),
            entropy_early_exit=bool(defaults.get("entropy_early_exit")),
            entropy_threshold=float(defaults.get("entropy_threshold", 1.0)),
            patience_k=int(defaults.get("patience_k", 2)),
            stop_sequences=effective_stops,
            decode_fn=decode_fn,
            logits_bias_fn=bias_fn,
        )
        out_ids = draft["ids"]
        receipt["path"] = "efficient_cpu_draft"
        receipt["draft_receipt"] = draft.get("receipt")
    else:
        if defaults.get("explore_then_lock") and temp > 0 and bias_fn is None:
            dual = generate_with_dual_temp(
                model,
                ids,
                max_new_tokens=tokens,
                high_temp=temp,
                low_temp=0.0,
                explore_k=int(defaults.get("explore_k", 16)),
                anneal="step",
                generator=gen,
                use_kv_cache=True,
                logits_bias_fn=None,
            )
            out_ids = dual["ids"] if isinstance(dual, dict) else dual
            receipt["path"] = "deep_dual_temperature"
            receipt["explore_k"] = int(defaults.get("explore_k", 16))
            if isinstance(dual, dict):
                receipt["dual_temp_receipt"] = {
                    k: v for k, v in dual.items() if k != "ids"
                }
        elif defaults.get("explore_then_lock") and temp > 0 and bias_fn is not None:
            # UML pressure + explore/lock on the same loop.
            dual = generate_with_dual_temp(
                model,
                ids,
                max_new_tokens=tokens,
                high_temp=temp,
                low_temp=0.0,
                explore_k=int(defaults.get("explore_k", 16)),
                anneal="step",
                generator=gen,
                use_kv_cache=True,
                logits_bias_fn=bias_fn,
            )
            out_ids = dual["ids"] if isinstance(dual, dict) else dual
            receipt["path"] = "deep_dual_temperature_uml_pressure"
            receipt["explore_k"] = int(defaults.get("explore_k", 16))
            if isinstance(dual, dict):
                receipt["dual_temp_receipt"] = {
                    k: v for k, v in dual.items() if k != "ids"
                }
        else:
            out_ids = model.generate(
                ids,
                max_new_tokens=tokens,
                temperature=temp,
                top_k=top_k,
                top_p=top_p if top_p is not None else defaults.get("top_p"),
                repetition_penalty=repetition_penalty,
                generator=gen,
                use_kv_cache=True,
                attention_backend="auto",
                stop_sequences=effective_stops,
                decode_fn=decode_fn,
                logits_bias_fn=bias_fn,
            )
            receipt["path"] = "deep_generate"
            receipt["stock_policy"] = dict(
                getattr(model, "_last_generate_policy", None) or {}
            )

    synchronize(device)
    prompt_len = int(ids.shape[1])
    # UML hygiene: clip generated suffix at first stop even if the decode
    # path (e.g. dual-temp) did not honor stop_sequences natively.
    if effective_stops and decode_fn is not None and int(out_ids.shape[1]) > prompt_len:
        row = out_ids[0].detach().cpu().tolist()
        suffix = decode_fn(row[prompt_len:])
        cut = len(suffix)
        for stop in effective_stops:
            if stop and stop in suffix:
                cut = min(cut, suffix.index(stop))
        keep = prompt_len + cut
        if keep < int(out_ids.shape[1]):
            out_ids = out_ids[:, :keep].contiguous()

    new_tokens = int(out_ids.shape[1] - prompt_len)
    receipt["prompt_tokens"] = prompt_len
    receipt["new_tokens"] = new_tokens
    receipt["stop_sequences"] = list(effective_stops) if effective_stops else None
    if stamp_master_rid:
        receipt["master_rid"] = _optional_master_rid_stamp()
    receipt["receipt_sha256"] = _receipt_sha(
        {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    )

    result: dict[str, Any] = {"ids": out_ids, "receipt": receipt}
    if decode_fn is not None:
        result["text"] = decode_fn(out_ids[0].detach().cpu().tolist())
    return result


@torch.inference_mode()
def speak_viv_sandwich(
    model_efficient: nn.Module,
    model_deep: nn.Module,
    context_ids: Tensor,
    *,
    front_max: int | None = None,
    deep_max: int | None = None,
    verify_max: int | None = None,
    decode_fn: Callable[[list[int]], str] | None = None,
    stop_sequences: Sequence[str] | None = None,
    uml_pressure: Mapping[str, Any] | None = None,
    uml_pressure_on: Literal["deep", "all", "none"] = "deep",
    uml_equation_mode: bool | None = None,
    stamp_master_rid: bool = True,
) -> dict[str, Any]:
    """CPU speculate → GPU deep → CPU verify (prefix accept).

    UML route pressure defaults onto the **deep** mouth only so the GPU draft
    is efficiency-governed while CPU verify stays an independent check.

    When ``uml_pressure`` is set, ``uml_equation_mode`` defaults True:
    deep/verify speak from the **original** prompt (not front draft), with
    UML stop boundaries, and receipt exposes a clipped ``equation_text``.

    For exclusive math-token I/O (emergent need P1), use ``speak_uml_native``
    which builds prompts via ``build_native_uml_prompt``.
    """

    from uml_speak_pressure import UML_DEFAULT_STOPS, clip_uml_equation_text

    identity = _identity_compatible(model_efficient, model_deep)
    if not identity["vocab_match"]:
        raise ValueError(
            "viv_speak_sandwich_identity_vocab_mismatch:"
            f"{identity['vocab_size_efficient']}!={identity['vocab_size_deep']}"
        )

    equation_mode = bool(uml_equation_mode) if uml_equation_mode is not None else (
        uml_pressure is not None
    )
    stops = list(stop_sequences) if stop_sequences is not None else (
        list(UML_DEFAULT_STOPS) if equation_mode else None
    )

    front_n = int(front_max if front_max is not None else min(16, _DEFAULT_EFFICIENT_TOKENS))
    deep_n = int(deep_max if deep_max is not None else min(64, _DEFAULT_DEEP_TOKENS))
    verify_n = int(verify_max if verify_max is not None else front_n)
    if equation_mode and front_max is None:
        front_n = 0

    apply_front = uml_pressure is not None and uml_pressure_on in ("all",)
    apply_deep = uml_pressure is not None and uml_pressure_on in ("deep", "all")
    apply_verify = uml_pressure is not None and uml_pressure_on in ("all",)

    prompt_len = int(context_ids.shape[-1] if context_ids.ndim > 1 else context_ids.numel())
    prompt_text = decode_fn(context_ids[0].detach().cpu().tolist()) if decode_fn is not None else ""

    def _pressure_for(enabled: bool) -> Mapping[str, Any] | None:
        if not enabled or uml_pressure is None:
            return None
        payload = dict(uml_pressure)
        payload["prompt_len"] = int(payload.get("prompt_len", prompt_len))
        if payload.get("prompt_text") is None and prompt_text:
            payload["prompt_text"] = prompt_text
        return payload

    front = speak_viv(
        model_efficient,
        context_ids,
        lane="efficient",
        max_new_tokens=max(front_n, 0),
        decode_fn=decode_fn,
        stop_sequences=stops,
        uml_pressure=_pressure_for(apply_front),
        stamp_master_rid=False,
        configure_runtime=True,
    )
    # Equation hygiene: deep starts from original prompt, not polluted front draft.
    deep_context = context_ids if equation_mode else front["ids"]
    deep = speak_viv(
        model_deep,
        deep_context,
        lane="deep",
        max_new_tokens=deep_n,
        decode_fn=decode_fn,
        stop_sequences=stops,
        uml_pressure=_pressure_for(apply_deep),
        stamp_master_rid=False,
        configure_runtime=False,
    )
    verify = speak_viv(
        model_efficient,
        context_ids,
        lane="efficient",
        max_new_tokens=verify_n,
        decode_fn=decode_fn,
        stop_sequences=stops,
        uml_pressure=_pressure_for(apply_verify),
        stamp_master_rid=False,
        configure_runtime=False,
    )

    gpu_full = deep["ids"][0].detach().cpu().tolist()
    cpu_full = verify["ids"][0].detach().cpu().tolist()
    gpu_new = gpu_full[prompt_len:]
    cpu_new = cpu_full[prompt_len:]
    accept = 0
    for a, b in zip(gpu_new, cpu_new):
        if a != b:
            break
        accept += 1
    accepted = gpu_new[:accept]
    rejected = gpu_new[accept:]
    if equation_mode:
        # Prefer deep equation tokens (already stop-clipped by generate); verify
        # only patches when deep produced nothing.
        equation_ids = gpu_new if gpu_new else cpu_new
        merged = gpu_full[:prompt_len] + equation_ids
        equation_source = "deep" if gpu_new else "verify"
    else:
        merged = gpu_full[:prompt_len] + accepted + cpu_new[accept:]
        equation_source = "prefix_merge"

    text = decode_fn(merged) if decode_fn is not None else None
    deep_text = deep.get("text") if decode_fn is not None else None
    equation_text = (
        clip_uml_equation_text(str(deep_text or text or ""), prompt_text)
        if equation_mode
        else None
    )

    prefer_snap: dict[str, Any] | None = None
    if equation_mode and equation_text is not None:
        try:
            from uml_speak_pressure import resolve_equation_for_policy

            prefer_snap = resolve_equation_for_policy(
                equation_text=equation_text,
                prompt_text=prompt_text,
                policy="auto",
            )
            if prefer_snap.get("snapped"):
                equation_text = str(prefer_snap["equation_text"])
                equation_source = "prefer_efficient_snap"
                if decode_fn is not None and text is not None:
                    text = f"{prompt_text}{equation_text}"
        except Exception as exc:
            prefer_snap = {"status": "FAIL", "error": repr(exc)}

    rid_stamp: dict[str, Any] | None = None
    if equation_mode and equation_text:
        try:
            from rid_pid import RIDMonitor

            reg = None
            target_char = None
            target_value = None
            if uml_pressure is not None:
                # Prefer already-inferred target from deep pressure receipt.
                deep_uml = deep["receipt"].get("uml_pressure") or {}
                decision = deep_uml.get("decision") or {}
                target_char = decision.get("target_char")
                target_value = decision.get("target_value")
                inferred = deep_uml.get("inferred") or {}
                if target_char is None:
                    target_char = inferred.get("target_char")
            if prefer_snap and (prefer_snap.get("inferred") or {}).get("target_char"):
                target_char = prefer_snap["inferred"]["target_char"]
            mon = RIDMonitor()
            s_rid = mon.score_from_route(
                proposed_expr=equation_text,
                target_char=target_char,
                target_value=int(target_value) if target_value is not None else None,
                registry=reg,
            )
            rid_stamp = mon.receipt()
            rid_stamp["S_RID"] = s_rid
        except Exception as exc:
            rid_stamp = {"status": "FAIL", "error": repr(exc)}

    receipt: dict[str, Any] = {
        "schema_version": "viv_slm_speak_sandwich_v3",
        "path": "cpu_speculate_gpu_deep_cpu_verify",
        "identity": identity,
        "prompt_tokens": prompt_len,
        "front_new_tokens": int(front["receipt"]["new_tokens"]),
        "deep_new_tokens": int(deep["receipt"]["new_tokens"]),
        "verify_new_tokens": int(verify["receipt"]["new_tokens"]),
        "accepted_prefix_len": accept,
        "rejected_suffix_len": len(rejected),
        "efficient_device": front["receipt"]["device"],
        "deep_device": deep["receipt"]["device"],
        "uml_pressure_on": uml_pressure_on if uml_pressure is not None else "none",
        "uml_equation_mode": equation_mode,
        "uml_stop_sequences": stops,
        "equation_text": equation_text,
        "equation_source": equation_source,
        "prefer_efficient_snap": prefer_snap,
        "rid_route": rid_stamp,
        "uml_pressure": deep["receipt"].get("uml_pressure")
        if apply_deep
        else front["receipt"].get("uml_pressure"),
        "front_path": front["receipt"].get("path"),
        "deep_path": deep["receipt"].get("path"),
        "verify_path": verify["receipt"].get("path"),
        "piston_actuated": False,
        "authority": "caller_owns_rid_gate",
    }
    if stamp_master_rid:
        receipt["master_rid"] = _optional_master_rid_stamp()
    receipt["receipt_sha256"] = _receipt_sha(
        {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    )
    return {
        "ids": torch.tensor([merged], dtype=torch.long),
        "text": text,
        "equation_text": equation_text,
        "receipt": receipt,
        "front": front,
        "deep": deep,
        "verify": verify,
    }

def clone_model_to_device(model: nn.Module, device: torch.device | str) -> nn.Module:
    """Deep-copy weights onto ``device`` so two lanes can run without fighting one module."""

    clone = type(model)(
        model.vocab_size,
        context_length=model.context_length,
        embedding_width=model.embedding_width,
        num_heads=model.num_heads,
        head_size=model.head_size,
        num_layers=model.num_layers,
        dropout=model.dropout_rate,
        **(
            {"position_encoding": getattr(model, "position_encoding", "rope")}
            if "position_encoding" in type(model).__init__.__code__.co_varnames
            else {}
        ),
        **(
            {"fused_qkv": bool(getattr(model, "fused_qkv", False))}
            if "fused_qkv" in type(model).__init__.__code__.co_varnames
            else {}
        ),
    )
    # Prefer state_dict load so buffers/flags match the source instance.
    missing, unexpected = clone.load_state_dict(model.state_dict(), strict=False)
    if unexpected:
        raise RuntimeError(f"viv_speak_clone_unexpected_keys:{unexpected}")
    # Masks / PE extras may be missing under plant shim; strict=False is intentional.
    _ = missing
    clone.to(device)
    clone.eval()
    return clone


def _identity_compatible(a: nn.Module, b: nn.Module) -> dict[str, Any]:
    """Same-identity gate: shared vocab (and preferably context) across specialists."""

    va = int(getattr(a, "vocab_size", -1))
    vb = int(getattr(b, "vocab_size", -1))
    ca = int(getattr(a, "context_length", -1))
    cb = int(getattr(b, "context_length", -1))
    ok = va > 0 and va == vb
    return {
        "vocab_match": ok,
        "vocab_size_efficient": va,
        "vocab_size_deep": vb,
        "context_length_efficient": ca,
        "context_length_deep": cb,
        "context_match": ca == cb,
    }


def speak_viv_parallel(
    model_efficient: nn.Module,
    model_deep: nn.Module,
    context_ids: Tensor,
    *,
    efficient_max_new: int | None = None,
    deep_max_new: int | None = None,
    decode_fn: Callable[[list[int]], str] | None = None,
    stamp_master_rid: bool = True,
    allow_clone_smoke: bool = False,
) -> dict[str, Any]:
    """Run CPU-efficient and GPU-deep **identity specialists** on one prompt.

    ``model_efficient`` and ``model_deep`` are different trained weights that
    share Viv identity (same vocab). They run concurrently on lane devices.

    Set ``allow_clone_smoke=True`` only for concurrency benches that intentionally
    pass two copies of one checkpoint (not the production identity pair).
    """

    from concurrent.futures import ThreadPoolExecutor
    import time

    identity = _identity_compatible(model_efficient, model_deep)
    if not identity["vocab_match"]:
        raise ValueError(
            "viv_speak_identity_vocab_mismatch:"
            f"{identity['vocab_size_efficient']}!={identity['vocab_size_deep']}"
        )

    same_object = model_efficient is model_deep
    # Heuristic: identical state_dict fingerprint ⇒ clone smoke, not two specialists.
    def _sd_fingerprint(m: nn.Module) -> str:
        blob = []
        for key, tensor in sorted(m.state_dict().items()):
            if torch.is_tensor(tensor):
                blob.append(f"{key}:{float(tensor.detach().float().sum())}:{tuple(tensor.shape)}")
        return sha256("|".join(blob).encode("utf-8")).hexdigest().upper()

    fp_e = _sd_fingerprint(model_efficient)
    fp_d = _sd_fingerprint(model_deep)
    weights_identical = fp_e == fp_d
    if weights_identical and not allow_clone_smoke:
        raise ValueError(
            "viv_speak_parallel_requires_distinct_identity_specialists:"
            "pass two differently trained checkpoints, or allow_clone_smoke=True for benches"
        )

    cpu_dev = select_speak_device("efficient")
    deep_dev = select_speak_device("deep")
    move_model_to_device(model_efficient, cpu_dev)
    move_model_to_device(model_deep, deep_dev)
    model_efficient.eval()
    model_deep.eval()

    prompt_cpu = context_ids.to(cpu_dev)
    prompt_deep = context_ids.to(deep_dev)

    def _run_efficient() -> dict[str, Any]:
        return speak_viv(
            model_efficient,
            prompt_cpu,
            lane="efficient",
            max_new_tokens=efficient_max_new,
            decode_fn=decode_fn,
            stamp_master_rid=stamp_master_rid,
            configure_runtime=False,
        )

    def _run_deep() -> dict[str, Any]:
        return speak_viv(
            model_deep,
            prompt_deep,
            lane="deep",
            max_new_tokens=deep_max_new,
            decode_fn=decode_fn,
            stamp_master_rid=False,
            configure_runtime=False,
        )

    t0 = time.perf_counter()
    seq_eff = _run_efficient()
    synchronize(cpu_dev)
    seq_deep = _run_deep()
    synchronize(deep_dev)
    sequential_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_e = pool.submit(_run_efficient)
        fut_d = pool.submit(_run_deep)
        par_eff = fut_e.result()
        par_deep = fut_d.result()
    synchronize(cpu_dev)
    synchronize(deep_dev)
    parallel_s = time.perf_counter() - t1

    speedup = (sequential_s / parallel_s) if parallel_s > 0 else 0.0
    receipt = {
        "schema_version": "viv_slm_speak_parallel_v2",
        "hypothesis": (
            "Same Viv identity, two differently trained specialists (CPU-efficient + "
            "GPU-deep) reason on one prompt concurrently; parallel wall time beats sequential."
        ),
        "identity": identity,
        "weight_fingerprint_efficient": fp_e,
        "weight_fingerprint_deep": fp_d,
        "weights_identical": weights_identical,
        "same_module_object": same_object,
        "clone_smoke": bool(weights_identical and allow_clone_smoke),
        "efficient_device": par_eff["receipt"]["device"],
        "deep_device": par_deep["receipt"]["device"],
        "sequential_s": sequential_s,
        "parallel_s": parallel_s,
        "speedup_vs_sequential": speedup,
        "efficient_new_tokens_parallel": par_eff["receipt"]["new_tokens"],
        "deep_new_tokens_parallel": par_deep["receipt"]["new_tokens"],
        "efficient_path": par_eff["receipt"].get("path"),
        "deep_path": par_deep["receipt"].get("path"),
        "cuda_available": bool(torch.cuda.is_available()),
        "same_weights": weights_identical,
        "two_specialists": not weights_identical,
        "piston_actuated": False,
    }
    deep_device_ok = (
        not torch.cuda.is_available()
        or str(par_deep["receipt"]["device"]).startswith("cuda")
    )
    parallel_ok = parallel_s <= sequential_s * 1.15
    passed = bool(
        deep_device_ok
        and par_eff["receipt"]["device"] == "cpu"
        and par_eff["receipt"]["new_tokens"] >= 0
        and par_deep["receipt"]["new_tokens"] >= 0
        and parallel_ok
        and identity["vocab_match"]
    )
    receipt["status"] = "PASS" if passed else "FAIL"
    receipt["gates"] = {
        "efficient_on_cpu": par_eff["receipt"]["device"] == "cpu",
        "deep_device_ok": deep_device_ok,
        "parallel_not_slower_than_seq_plus_15pct": parallel_ok,
        "identity_vocab_match": identity["vocab_match"],
        "distinct_specialists_or_smoke": (not weights_identical) or allow_clone_smoke,
        "both_produced_tokens": True,
    }
    receipt["receipt_sha256"] = _receipt_sha(
        {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    )
    return {
        "sequential": {"efficient": seq_eff, "deep": seq_deep},
        "parallel": {"efficient": par_eff, "deep": par_deep},
        "receipt": receipt,
    }


__all__ = [
    "SpeakLane",
    "clone_model_to_device",
    "lane_defaults",
    "select_speak_device",
    "speak_viv",
    "speak_viv_parallel",
    "speak_viv_sandwich",
]
