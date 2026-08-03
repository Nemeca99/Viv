"""CPU-owned acronym and identity contract for Viv's rendered voice.

This module is deliberately small and deterministic.  It is a presentation
contract, not a language model, and it never invents expansions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AcronymSpec:
    acronym: str
    expansion: str
    source: str


# AIOS is an explicit operator-approved identity phrase.  The repository's
# doctrine documents SGI; the other entries are standard technical terms.
APPROVED_ACRONYMS: dict[str, AcronymSpec] = {
    "AI": AcronymSpec("AI", "Artificial Intelligence", "standard_term"),
    "AIOS": AcronymSpec("AIOS", "Adaptive Intelligent Operating System", "operator_contract"),
    "SGI": AcronymSpec("SGI", "Symbiotic General Intelligence", "VIV_COMPLETE_SUMMARY.md"),
    "CPU": AcronymSpec("CPU", "Central Processing Unit", "standard_term"),
    "GPU": AcronymSpec("GPU", "Graphics Processing Unit", "standard_term"),
    "EOS": AcronymSpec("EOS", "End of Sequence", "standard_term"),
}

CANONICAL_IDENTITY_INTRO = (
    "My name is Viv. I am an Adaptive Intelligent Operating System (AIOS)."
)
_ACRONYM_TOKEN = re.compile(r"(?<![A-Za-z])[A-Z][A-Z0-9]{1,}(?![A-Za-z])")
_DOTTED_ACRONYM_TOKEN = re.compile(r"(?<![A-Za-z])(?:[A-Z]\.){2,}(?![A-Za-z])")


def _normal(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def acronym_tokens(text: str) -> list[str]:
    """Return uppercase acronym-shaped tokens in source order."""
    return [match.group(0) for match in _ACRONYM_TOKEN.finditer(str(text or ""))]


def validate_acronym_usage(text: str) -> list[dict[str, str]]:
    """Return deterministic violations; an empty list means contract PASS.

    The first occurrence of an approved acronym in each response must use the
    exact ``Full Expansion (ACR)`` form.  Later occurrences may use the
    approved acronym alone.  Unknown uppercase acronym-shaped tokens fail
    closed because the CPU registry has no expansion for them.
    """
    raw = str(text or "")
    violations: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _ACRONYM_TOKEN.finditer(raw):
        token = match.group(0)
        spec = APPROVED_ACRONYMS.get(token)
        if spec is None:
            violations.append({"kind": "unapproved_acronym", "token": token})
            continue
        if token in seen:
            continue
        seen.add(token)
        prefix = raw[: match.start()]
        expected = f"{spec.expansion} ({spec.acronym})"
        # The acronym itself is at ``match.start()``; only the expansion and
        # opening parenthesis can precede it.
        expected_prefix = f"{spec.expansion} ("
        if not _normal(prefix).endswith(_normal(expected_prefix)):
            violations.append(
                {
                    "kind": "first_use_not_expanded",
                    "token": token,
                    "expected": expected,
                }
            )
    for match in _DOTTED_ACRONYM_TOKEN.finditer(raw):
        dotted = match.group(0)
        token = dotted.replace(".", "")
        spec = APPROVED_ACRONYMS.get(token)
        if spec is None:
            violations.append({"kind": "unapproved_acronym", "token": dotted})
        else:
            violations.append(
                {
                    "kind": "noncanonical_acronym_form",
                    "token": dotted,
                    "expected": f"{spec.expansion} ({spec.acronym})",
                }
            )
    return violations


def repair_acronym_usage(text: str) -> dict[str, object]:
    """Apply only registry-backed, lossless acronym repairs.

    Safe repairs are limited to:
    - inserting the required space in ``Expansion(ACR)``;
    - replacing a known incorrect AIOS expansion with the operator-approved
      expansion;
    - expanding the first bare occurrence of an approved acronym.

    Unknown or compound forms are never guessed.  They remain unresolved so
    the caller can hold or regenerate the response and retain the evidence.
    """
    import re

    original = str(text or "")
    repaired = original
    repairs: list[dict[str, str]] = []

    # Models sometimes preserve the acronym while inventing a near-miss
    # expansion (for example, ``Operating Suite = AIOS``).  This is safe to
    # repair because the acronym, the full phrase, and the replacement are
    # all registry-backed; unrelated prose is left untouched.
    wrong_aios = re.compile(
        r"\bAdaptive Intelligent\s+Operating\s+System\s*\(\s*"
        r"Adaptive Intelligent\s+Operating\s+"
        r"(?:Suite|Software|Substrate|Service)\s*(?:=|-)\s*AIOS\s*\)",
        flags=re.IGNORECASE,
    )
    repaired, count = wrong_aios.subn("Adaptive Intelligent Operating System (AIOS)", repaired)
    if count:
        repairs.append({"kind": "canonicalize_wrong_expansion", "token": "AIOS", "count": str(count)})

    # The token must be registry-approved before spacing is changed.
    for token, spec in APPROVED_ACRONYMS.items():
        pattern = re.compile(
            rf"(?<![A-Za-z])({re.escape(spec.expansion)})\(({re.escape(token)})\)(?![A-Za-z])"
        )
        fixed, count = pattern.subn(r"\1 (\2)", repaired)
        if count:
            repaired = fixed
            repairs.append({"kind": "insert_expansion_space", "token": token, "count": str(count)})

    # Expand only the first bare approved token when its expansion is absent.
    # Re-run the contract after spacing repair so an already-correct first use
    # is never duplicated.
    for token, spec in APPROVED_ACRONYMS.items():
        if not any(v.get("token") == token for v in validate_acronym_usage(repaired)):
            continue
        token_pattern = re.compile(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])")
        match = token_pattern.search(repaired)
        if match is None:
            continue
        replacement = f"{spec.expansion} ({token})"
        repaired = repaired[: match.start()] + replacement + repaired[match.end() :]
        repairs.append({"kind": "expand_first_use", "token": token, "count": "1"})

    unresolved = validate_acronym_usage(repaired)
    # Uppercase identity compounds are not token-shaped acronyms, so the
    # registry validator cannot see them.  Still log them as unresolved rather
    # than treating forms such as AIOSkynet or GPUVoice as clean prose.
    compound_pattern = re.compile(
        r"\b(?:AIOS|GPU|CPU|AI(?!OS)|SGI|EOS)[A-Za-z][A-Za-z0-9]*\b"
    )
    for match in compound_pattern.finditer(repaired):
        token = match.group(0)
        if not any(item.get("kind") == "compound_approved_prefix" and item.get("token") == token for item in unresolved):
            unresolved.append({"kind": "compound_approved_prefix", "token": token})
    return {
        "original": original,
        "repaired": repaired,
        "changed": repaired != original,
        "repairs": repairs,
        "unresolved": unresolved,
        "pass": not unresolved,
    }


def render_acronym_contract() -> str:
    return (
        "Acronym-Contract: Use only CPU-registry-approved acronyms. "
        "On first use in this response, write the full approved term followed "
        "by the acronym in parentheses. Never invent an acronym or expansion."
    )
