#!/usr/bin/env python3
"""Immutable production accounting registry release loader.

Production accounting paths load coefficients/rules only via a frozen release.
Silent mutation of a loaded release is forbidden; any change requires a new release ID.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS

CAMPAIGN = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
RELEASE_PATH = CAMPAIGN / "ACCOUNTING_REGISTRY_RELEASE_V1.json"
RELEASE_ID = "accounting_registry_v1"

_LOADED: dict[str, Any] | None = None
_LOADED_SHA256: str | None = None


class RegistryReleaseImmutabilityError(RuntimeError):
    """Raised when a caller attempts to mutate a loaded release payload."""


class _FrozenDict(dict):
    """Dict that rejects in-place mutation after freeze."""

    _frozen: bool = False

    def _check(self) -> None:
        if self._frozen:
            raise RegistryReleaseImmutabilityError(
                "silent mutation of accounting registry release is forbidden; "
                "issue a new release ID instead"
            )

    def __setitem__(self, key: Any, value: Any) -> None:  # noqa: ANN401
        self._check()
        super().__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:  # noqa: ANN401
        self._check()
        super().__delitem__(key)

    def clear(self) -> None:
        self._check()
        super().clear()

    def pop(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        self._check()
        return super().pop(*args, **kwargs)

    def popitem(self) -> Any:  # noqa: ANN401
        self._check()
        return super().popitem()

    def update(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self._check()
        super().update(*args, **kwargs)

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        self._check()
        return super().setdefault(*args, **kwargs)

    def freeze(self) -> "_FrozenDict":
        self._frozen = True
        return self


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return _sha256_bytes(path.read_bytes())


def release_path() -> Path:
    return RELEASE_PATH


def load_registry_release(
    *,
    path: Path | None = None,
    force_reload: bool = False,
) -> dict[str, Any]:
    """Load the frozen release. Returns a deep copy that is mutation-guarded."""
    global _LOADED, _LOADED_SHA256
    p = Path(path) if path is not None else RELEASE_PATH
    if not p.exists():
        raise FileNotFoundError(f"registry release missing: {p}")

    raw = p.read_bytes()
    digest = _sha256_bytes(raw)
    if (
        not force_reload
        and _LOADED is not None
        and _LOADED_SHA256 == digest
        and str(p.resolve()) == str(RELEASE_PATH.resolve())
    ):
        return _freeze_payload(deepcopy(_LOADED))

    data = json.loads(raw.decode("utf-8"))
    if not data.get("immutable"):
        raise ValueError("registry release missing immutable=true")
    if not data.get("silent_mutate_forbidden"):
        raise ValueError("registry release missing silent_mutate_forbidden=true")
    rid = data.get("release_id")
    if rid != RELEASE_ID and path is None:
        raise ValueError(f"unexpected release_id={rid!r}; expected {RELEASE_ID!r}")

    if path is None:
        _LOADED = data
        _LOADED_SHA256 = digest
    return _freeze_payload(deepcopy(data))


def _freeze_payload(data: dict[str, Any]) -> dict[str, Any]:
    frozen = _FrozenDict(data)
    frozen.freeze()
    return frozen


def get_release_id(*, path: Path | None = None) -> str:
    rel = load_registry_release(path=path)
    return str(rel.get("release_id") or RELEASE_ID)


def get_approved_components(*, path: Path | None = None) -> tuple[str, ...]:
    rel = load_registry_release(path=path)
    comps = rel.get("approved_components") or []
    return tuple(str(c) for c in comps)


def get_rejected_components(*, path: Path | None = None) -> tuple[str, ...]:
    rel = load_registry_release(path=path)
    comps = rel.get("rejected_components") or []
    return tuple(str(c) for c in comps)


def assert_release_intact(*, path: Path | None = None) -> dict[str, Any]:
    """Verify on-disk release still matches recorded content hashes where present."""
    p = Path(path) if path is not None else RELEASE_PATH
    rel = load_registry_release(path=p, force_reload=True)
    checks: dict[str, Any] = {"ok": True, "mismatches": []}
    for key, meta in (rel.get("source_artifacts") or {}).items():
        if not isinstance(meta, dict):
            continue
        ap = meta.get("path")
        expect = meta.get("sha256")
        if not ap or not expect:
            continue
        got = sha256_file(Path(ap))
        if got != expect:
            checks["ok"] = False
            checks["mismatches"].append({"key": key, "expected": expect, "got": got})
    checks["release_id"] = rel.get("release_id")
    checks["path"] = str(p).replace("\\", "/")
    return checks
