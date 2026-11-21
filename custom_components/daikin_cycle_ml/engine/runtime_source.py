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
from typing import Any

_INVALID_STRINGS = frozenset({"", "unknown", "unavailable", "---", "none", "null"})


def _read_float(attrs: dict[str, Any], key: str) -> float | None:
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


def read_native_buh_minutes(attrs: dict[str, Any]) -> float | None:
    """Return native ``Stats: Backup heater today (min)`` if valid, else None."""
    return _read_float(attrs, "Stats: Backup heater today (min)")


def read_native_compressor_minutes(attrs: dict[str, Any]) -> float | None:
    """v1.22.8: Return native ``Stats: Compressor run today (min)`` if valid, else None.

    ESPAltherma v2 only. This counter includes cross-midnight cycles and the
    currently-open cycle (firmware-side), so it is the ground truth when
    available. When absent (v1 ESPAltherma or plain sensor.althermasensors
    without Stats: attributes), callers must fall back to the computed path.
    """
    return _read_float(attrs, "Stats: Compressor run today (min)")


def read_native_defrost_count(attrs: dict[str, Any]) -> float | None:
    """v1.22.8: Return native ``Stats: Defrosts today`` if valid, else None."""
    return _read_float(attrs, "Stats: Defrosts today")


def read_native_compressor_starts(attrs: dict[str, Any]) -> float | None:
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



# #466: ESPAltherma rolls its "today" counters over at local midnight only
# once the ESP has a clock (NTP); without one they count since boot
# (include/stats.h: day = -1 while the clock is not set). A Tweakers report
# showed 531 h of compressor run "today" at 14:24. A run or backup-heater
# total above the minutes since local midnight proves the counters are not
# daily, so none of the four is used and the computed values take over.
TODAY_KEYS: tuple[str, ...] = (
    "Stats: Compressor starts today",
    "Stats: Defrosts today",
    "Stats: Compressor run today (min)",
    "Stats: Backup heater today (min)",
)
TODAY_SLACK_MIN = 5.0  # ESP and Home Assistant clocks / time zone edges


def native_today_is_daily(attrs: dict[str, Any], minutes_today: float) -> bool:
    """False when a native today counter holds more minutes than today has
    (minutes_today: minutes since local midnight)."""
    limit = max(0.0, float(minutes_today)) + TODAY_SLACK_MIN
    for key in ("Stats: Compressor run today (min)", "Stats: Backup heater today (min)"):
        v = _read_float(attrs, key)
        if v is not None and v > limit:
            return False
    return True


def daily_attrs(attrs: dict[str, Any], minutes_today: float) -> dict[str, Any]:
    """The attributes, without the native today counters when they are not daily."""
    if not isinstance(attrs, dict) or native_today_is_daily(attrs, minutes_today):
        return attrs
    return {k: v for k, v in attrs.items() if k not in TODAY_KEYS}
