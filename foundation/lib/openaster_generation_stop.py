"""OpenAster response-boundary stop IDs for train/eval generation parity.

Training supervises ``OPENASTER_EOS_TOKEN`` (``<|im_end|>``). Generation must
stop on that same token ID — never on ``tokenizer.eos_token_id`` alone when it
diverges (classic Qwen ChatML: 151643 ``<|endoftext|>`` vs 151645 ``<|im_end|>``).
"""
from __future__ import annotations

from typing import Any

from voice_core.intent_packet import OPENASTER_EOS_TOKEN

# Documented Qwen2 ChatML IDs (vocabulary may remap on OpenAster bases).
QWEN_CHATML_IM_END_ID = 151645
QWEN_CHATML_END_OF_TEXT_ID = 151643
QWEN_CHATML_IM_START_ID = 151644


def resolve_response_eos_id(tokenizer: Any) -> int:
    """Primary trained response terminator: ``<|im_end|>`` token id."""
    eos_id = tokenizer.convert_tokens_to_ids(OPENASTER_EOS_TOKEN)
    if eos_id is None or int(eos_id) < 0:
        raise ValueError(f"unresolved_openaster_eos:{OPENASTER_EOS_TOKEN}:{eos_id}")
    return int(eos_id)


def configured_stop_ids(
    tokenizer: Any, *, also_accept_tokenizer_eos: bool = True
) -> list[int]:
    """Stop IDs for ``model.generate``: primary ``<|im_end|>``, optional tokenizer eos.

    Never returns *only* ``tokenizer.eos_token_id`` when that differs from the
    trained response boundary.
    """
    primary = resolve_response_eos_id(tokenizer)
    stops = [primary]
    if also_accept_tokenizer_eos:
        tok_eos = getattr(tokenizer, "eos_token_id", None)
        if tok_eos is not None and int(tok_eos) >= 0 and int(tok_eos) != primary:
            stops.append(int(tok_eos))
    return stops


def eos_mismatch_detected(tokenizer: Any) -> bool:
    """True when tokenizer.eos_token_id differs from trained ``<|im_end|>`` id."""
    primary = resolve_response_eos_id(tokenizer)
    tok_eos = getattr(tokenizer, "eos_token_id", None)
    if tok_eos is None:
        return False
    return int(tok_eos) != primary


def classify_generation_stop(
    generated_token_ids: list[int],
    *,
    stop_ids: list[int],
    primary_eos_id: int,
    max_new_tokens: int,
) -> dict[str, Any]:
    """Inspect generated ids and record stop metadata (no post-hoc text trim)."""
    configured = [int(x) for x in stop_ids]
    primary = int(primary_eos_id)
    if not generated_token_ids:
        return {
            "terminating_token_id": None,
            "configured_stop_ids": configured,
            "primary_response_eos_id": primary,
            "terminated_by_eos": False,
            "terminated_by_response_eos": False,
            "stop_reason": "empty",
        }
    last = int(generated_token_ids[-1])
    hit_stop = last in set(configured)
    hit_primary = last == primary
    if hit_stop:
        reason = "response_eos" if hit_primary else "tokenizer_eos"
    elif len(generated_token_ids) >= int(max_new_tokens):
        reason = "max_new_tokens"
    else:
        reason = "other"
    return {
        "terminating_token_id": last,
        "configured_stop_ids": configured,
        "primary_response_eos_id": primary,
        "terminated_by_eos": hit_stop,
        "terminated_by_response_eos": hit_primary,
        "stop_reason": reason,
    }


def generation_contains_fabricated_turn(
    generated_token_ids: list[int], tokenizer: Any
) -> bool:
    """True if decoded continuation embeds a new ChatML user/tool turn."""
    if not generated_token_ids:
        return False
    text = tokenizer.decode(generated_token_ids, skip_special_tokens=False)
    markers = (
        "<|im_start|>user",
        "<|im_start|>tool",
        "<|im_start|>assistant",
        "\nuser\n",
        "\ntool\n",
    )
    # First assistant turn framing is already in the prompt; a second im_start
    # after content indicates runaway roleplay.
    lowered = text.lower()
    for marker in markers:
        if marker.lower() in lowered:
            return True
    return False


def stop_metadata_for_row(stop_info: dict[str, Any]) -> dict[str, Any]:
    """Fields every evaluation row must carry for stop-boundary audit."""
    return {
        "terminating_token_id": stop_info.get("terminating_token_id"),
        "configured_stop_ids": list(stop_info.get("configured_stop_ids") or []),
        "primary_response_eos_id": stop_info.get("primary_response_eos_id"),
        "terminated_by_eos": bool(stop_info.get("terminated_by_eos")),
        "terminated_by_response_eos": bool(
            stop_info.get("terminated_by_response_eos")
        ),
        "stop_reason": stop_info.get("stop_reason"),
    }
