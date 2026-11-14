"""Runtime counter resolution: native ESPAltherma v2 stats + computed fallback.

v1.22.7: introduced for BUH wall-time counter. Native
``Stats: Backup heater today (min)`` is preferred when present (v2 ESPAltherma
only). Otherwise the coordinator's computed ``_buh_total_s`` (wall-time, capped
per tick) is used — which is the only source available on v1 ESPAltherma.

v1.22.8 will extend this module for defrost / compressor-starts / COP / heat
counters with per-sensor ``source`` attributes.
"""

from __future__ import annotations

import math

from typing import Any, Optional

_INVALID_STRINGS = frozenset({"", "unknown", "unavailable", "---", "none", "null"})


def _read_float(attrs: dict[str, Any], key: str) -> Optional[float]:
    """Read a numeric attribute safely. None on missing / parse-fail / negative.

    Strict: requires ``attrs`` to be a real dict (not a Mock), and ``raw`` to be
    str/int/float/bool. Mocks or arbitrary objects are rejected to prevent
    ``float(MagicMock) == 1.0`` false-positives.
    """
    if not isinstance(attrs, dict):
        return None
    raw = attrs.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool):  # v1.22.8: reject bool (subclass of int)
        return None
    if isinstance(raw, str) and raw.strip().lower() in _INVALID_STRINGS:
        return None
    if not isinstance(raw, (str, int, float, bool)):
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(v):  # v1.22.8: reject inf/NaN (would OverflowError on int())
        return None
    return v if v >= 0.0 else None


def read_native_buh_minutes(attrs: dict[str, Any]) -> Optional[float]:
    """Return native ``Stats: Backup heater today (min)`` if valid, else None."""
    return _read_float(attrs, "Stats: Backup heater today (min)")


def read_native_compressor_minutes(attrs: dict[str, Any]) -> Optional[float]:
    """v1.22.8: Return native ``Stats: Compressor run today (min)`` if valid, else None.

    ESPAltherma v2 only. This counter includes cross-midnight cycles and the
    currently-open cycle (firmware-side), so it is the ground truth when
    available. When absent (v1 ESPAltherma or plain sensor.althermasensors
    without Stats: attributes), callers must fall back to the computed path.
    """
    return _read_float(attrs, "Stats: Compressor run today (min)")


def read_native_defrost_count(attrs: dict[str, Any]) -> Optional[float]:
    """v1.22.8: Return native ``Stats: Defrosts today`` if valid, else None."""
    return _read_float(attrs, "Stats: Defrosts today")


def read_native_compressor_starts(attrs: dict[str, Any]) -> Optional[float]:
    """v1.22.8: Return native ``Stats: Compressor starts today`` if valid, else None."""
    return _read_float(attrs, "Stats: Compressor starts today")


def defrost_count_today(attrs: dict[str, Any], computed: int) -> tuple[int, str]:
    """Defrost count today: native ``Stats: Defrosts today`` (v2) → computed."""
    native = _read_float(attrs, "Stats: Defrosts today")
    if native is not None:
        return int(native), "native"
    return computed, "computed"


def compressor_starts_today(attrs: dict[str, Any], computed: int) -> tuple[int, str]:
    """Compressor starts today: native ``Stats: Compressor starts today`` (v2) → computed."""
    native = _read_float(attrs, "Stats: Compressor starts today")
    if native is not None:
        return int(native), "native"
    return computed, "computed"

