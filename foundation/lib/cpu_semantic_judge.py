"""CPU-pinned semantic sensor used by the deterministic training-tree judge.

The LLM supplies a bounded categorical observation.  Deterministic code owns
schema checks, invariants, expected hard-negative construction, and admission.
Two exact categorical observations must agree; every failure becomes HOLD.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Callable
from urllib import request
from lib.training_security import gate_record, secure_write_json

SENSOR_VERSION = "viv_cpu_semantic_sensor_v4"
CATEGORIES = {"PASS", "FAIL", "ABSTAIN"}


@dataclass(frozen=True)
class SensorConfig:
    model: str = "llama3.1:8b"
    endpoint: str = "http://127.0.0.1:11434/api/generate"
    num_gpu: int = 0
    num_thread: int = 4
    num_ctx: int = 2048
    temperature: float = 0.0
    seed: int = 42
    num_predict: int = 160
    timeout_s: float = 120.0
    keep_alive: str = "5m"
    stability_retry_attempts: int = 2
    stability_retry_delay_s: float = 5.0


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_key(
    row: dict[str, Any],
    config: SensorConfig,
    cache_context: dict[str, Any] | str | None = None,
) -> str:
    payload = {
        "version": SENSOR_VERSION,
        "config": asdict(config),
        "cache_context": cache_context,
        "node_id": row.get("node_id"),
        "stage_id": row.get("stage_id"),
        "criterion": row.get("criterion"),
        "facts": row.get("facts"),
        "context": row.get("context"),
        "prompt": row.get("prompt"),
        "chosen": row.get("chosen"),
        "rejected": row.get("rejected"),
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def reusable_observation(
    value: dict[str, Any],
    *,
    expected_key: str | None = None,
) -> bool:
    """Return whether a sensor result is safe to reuse as evidence.

    Transport, Security, CPU-proof, malformed-output, and disagreement failures
    remain visible to the caller but are never admitted to the observation
    cache. A transient HOLD therefore cannot become sticky across retries.
    """
    observations = value.get("observations") or []
    return bool(
        value.get("sensor_version") == SENSOR_VERSION
        and (expected_key is None or value.get("cache_key") == expected_key)
        and value.get("status") == "OBSERVED"
        and value.get("categorical_agreement") is True
        and value.get("cpu_only") is True
        and not (value.get("errors") or [])
        and len(observations) == 2
        and observations[0] == observations[1]
    )


def build_sensor_prompt(row: dict[str, Any]) -> str:
    payload = {
        "stage": row["stage_id"],
        "criterion": row["criterion"],
        "facts": row.get("facts") or [],
        "context": row.get("context") or [],
        "user_request": row.get("ask") or row["prompt"],
        "candidate_a": row["chosen"],
        "candidate_b": row["rejected"],
    }
    return (
        "You are a bounded semantic comparison sensor, not an assistant and not "
        "an admission authority. Evaluate only the supplied criterion, facts, "
        "context, and request. PASS means the candidate satisfies the criterion; "
        "FAIL means it violates it; ABSTAIN means evidence is insufficient. "
        "Return one JSON object only, with exactly these string fields: "
        '{"candidate_a":"PASS|FAIL|ABSTAIN","candidate_b":"PASS|FAIL|ABSTAIN"}. '
        "The deterministic caller already owns and verifies INPUT.stage. No prose.\nINPUT:\n"
        + _stable_json(payload)
    )


def _http_transport(payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    encoded = json.dumps(payload).encode("utf-8")
    req = request.Request(
        payload.pop("_endpoint"),
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse(raw: dict[str, Any]) -> dict[str, str]:
    text = str(raw.get("response") or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:].strip()
    decoded = json.loads(text)
    if not isinstance(decoded, dict) or set(decoded) != {"candidate_a", "candidate_b"}:
        raise ValueError("malformed_sensor_schema")
    result = {key: str(value).strip().upper() for key, value in decoded.items()}
    if result["candidate_a"] not in CATEGORIES or result["candidate_b"] not in CATEGORIES:
        raise ValueError("invalid_sensor_category")
    return result


def ollama_cpu_observation(model: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc), "output": ""}
    matching = [line for line in proc.stdout.splitlines()[1:] if model.split(":")[0].lower() in line.lower()]
    cpu_only = bool(matching) and all("100% CPU" in line.upper() for line in matching)
    return {"ok": cpu_only, "matching": matching, "output": proc.stdout.strip()}


def observe_twice(
    row: dict[str, Any],
    *,
    cache_dir: Path,
    config: SensorConfig | None = None,
    transport: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    require_runtime_cpu_proof: bool = True,
    cache_context: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    config = config or SensorConfig()
    transport = transport or _http_transport
    key = cache_key(row, config, cache_context)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if reusable_observation(cached, expected_key=key):
            return {
                **cached,
                "cache_hit": True,
                "cache_persisted": True,
            }
    prompt = build_sensor_prompt(row)
    sensor_manifest = key
    request_security = gate_record(
        text=prompt,
        direction="OUT",
        action="JUDGE",
        stage_id=str(row.get("stage_id") or "semantic_sensor"),
        run_id="cpu-semantic-sensor",
        model_role="cpu_semantic_sensor",
        manifest_sha256=sensor_manifest,
        artifact_class="judge_record",
        paths=(cache_path,),
        source_hashes=(sensor_manifest,),
    )
    if not request_security.get("allowed"):
        return {
            "sensor_version": SENSOR_VERSION,
            "cache_key": key,
            "cache_hit": False,
            "cache_context": cache_context,
            "cache_persisted": False,
            "observations": [],
            "categorical_agreement": False,
            "cpu_only": False,
            "errors": [f"security_request_denied:{request_security.get('reason')}"],
            "status": "HOLD",
            "security": {"request": request_security},
        }
    payload = {
        "_endpoint": config.endpoint,
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": config.keep_alive,
        "options": {
            "num_gpu": config.num_gpu,
            "num_thread": config.num_thread,
            "num_ctx": config.num_ctx,
            "temperature": config.temperature,
            "seed": config.seed,
            "num_predict": config.num_predict,
        },
    }
    observations: list[dict[str, Any]] = []
    reply_security: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    started = time.perf_counter()
    attempts = 0
    transient_retries = 0
    max_attempts = 2 + config.stability_retry_attempts
    while len(observations) < 2 and attempts < max_attempts:
        attempts += 1
        try:
            raw = transport(dict(payload), config.timeout_s)
            parsed = _parse(raw)
            reply_verdict = gate_record(
                text=_stable_json(parsed),
                direction="IN",
                action="JUDGE",
                stage_id=str(row.get("stage_id") or "semantic_sensor"),
                run_id="cpu-semantic-sensor",
                model_role="cpu_semantic_sensor",
                manifest_sha256=sensor_manifest,
                artifact_class="judge_record",
                paths=(cache_path,),
                source_hashes=(sensor_manifest,),
            )
            reply_security.append(reply_verdict)
            if not reply_verdict.get("allowed"):
                membrane_reason = str(
                    ((reply_verdict.get("membrane") or {}).get("reason") or "")
                )
                if (
                    "[LAW 5]" in membrane_reason
                    and transient_retries < config.stability_retry_attempts
                ):
                    transient_retries += 1
                    warnings.append(
                        f"transient_law5_retry:{transient_retries}:"
                        f"{reply_verdict.get('reason')}"
                    )
                    time.sleep(config.stability_retry_delay_s)
                    continue
                raise PermissionError(
                    f"security_reply_denied:{reply_verdict.get('reason')}"
                )
            observations.append(parsed)
        except Exception as exc:  # noqa: BLE001 - fail closed into HOLD
            errors.append(f"{type(exc).__name__}:{exc}")
            break
    agreement = len(observations) == 2 and observations[0] == observations[1]
    cpu_proof = ollama_cpu_observation(config.model) if require_runtime_cpu_proof else {
        "ok": config.num_gpu == 0, "test_transport": True
    }
    result = {
        "sensor_version": SENSOR_VERSION,
        "cache_key": key,
        "cache_hit": False,
        "cache_context": cache_context,
        "config": asdict(config),
        "observations": observations,
        "categorical_agreement": agreement,
        "cpu_only": bool(cpu_proof.get("ok")),
        "cpu_proof": cpu_proof,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "attempts": attempts,
        "warnings": warnings,
        "errors": errors,
        "status": "OBSERVED" if agreement and cpu_proof.get("ok") and not errors else "HOLD",
        "security": {"request": request_security, "replies": reply_security},
    }
    result["cache_persisted"] = reusable_observation(
        result,
        expected_key=key,
    )
    if result["cache_persisted"]:
        secure_write_json(
            cache_path,
            result,
            stage_id=str(row.get("stage_id") or "semantic_sensor"),
            run_id="cpu-semantic-sensor",
            artifact_class="judge_record",
        )
    return result


def deterministic_admission(row: dict[str, Any], sensor: dict[str, Any]) -> dict[str, Any]:
    """Combine controlled-construction proof and the bounded sensor observation."""
    structural = not row.get("construction_errors")
    observations = sensor.get("observations") or []
    semantic_shape = (
        sensor.get("categorical_agreement")
        and len(observations) == 2
        and observations[0].get("candidate_a") == "PASS"
        and observations[0].get("candidate_b") == "FAIL"
    )
    admitted = bool(structural and semantic_shape and sensor.get("cpu_only"))
    reasons = []
    if not structural:
        reasons.append("controlled_construction_failed")
    if not sensor.get("categorical_agreement"):
        reasons.append("sensor_disagreement")
    if not semantic_shape:
        reasons.append("semantic_shape_not_pass_fail")
    if not sensor.get("cpu_only"):
        reasons.append("cpu_pin_unproven")
    return {
        "authority": "deterministic_training_tree_judge_v3",
        "semantic_sensor_is_authority": False,
        "admitted": admitted,
        "status": "SEED_VALIDATED" if admitted else "HOLD",
        "reasons": reasons,
    }
