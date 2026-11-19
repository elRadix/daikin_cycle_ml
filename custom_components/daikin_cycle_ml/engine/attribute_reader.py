"""Normalize ESPAltherma attribute values for Daikin Cycle ML."""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from ..const import (
    ATTR_BE_COP,
    ATTR_COP,
    ATTR_DHW_TANK_TEMP,
    ATTR_FLOW_SENSOR,
    ATTR_INDOOR_AMBIENT_R1T,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_2_RPS,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LEAVING_WATER_BEFORE_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_TARGET_COND_TEMP,
    REQUIRED_ATTRIBUTES,
)
from .attribute_compat import build_compat_view

_LOGGER = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"^\{.*\}$")
_PLACEHOLDER_RE = re.compile(r"^Conv \d+ not avail\.$")
_NULL_STRINGS = {
    "", "---", "unknown", "unavailable", "none", "nan", "null",
    "inf", "infinity", "-inf", "+inf",  # v1.20.0 #281 GAP-3
}
_TRUE_STRINGS = {"on", "true", "yes", "1"}
_FALSE_STRINGS = {"off", "false", "no", "0"}

# #423: values that are numbers. ESPAltherma v2 delivers every state as
# text, and "0" / "1" were read as False / True before the number check,
# so a counter or measurement of exactly 0 or 1 was lost ("Stats: Defrosts
# today" = "1" -> True -> rejected by the native readers).
NUMERIC_PREFIXES: tuple[str, ...] = ("Stats: ", "Unit meter: ")
NUMERIC_ATTRIBUTES: frozenset[str] = frozenset({
    ATTR_BE_COP, ATTR_COP, ATTR_DHW_TANK_TEMP, ATTR_FLOW_SENSOR,
    ATTR_INDOOR_AMBIENT_R1T, ATTR_INLET_WATER_R4T, ATTR_INV_FREQUENCY_2_RPS,
    ATTR_INV_FREQUENCY_RPS, ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LEAVING_WATER_BEFORE_BUH, ATTR_LW_SETPOINT, ATTR_OUTDOOR_AIR_R1T,
    ATTR_TARGET_COND_TEMP, "INV primary current (A)", "Water pressure",
})


def is_numeric_key(key: Any) -> bool:
    """#423: True for attributes whose value is a number."""
    return isinstance(key, str) and (
        key in NUMERIC_ATTRIBUTES or key.startswith(NUMERIC_PREFIXES)
    )


def _clean_raw(value: str) -> str | None:
    """Trim and filter template/placeholder/null strings."""
    s = value.strip()
    if s.lower() in _NULL_STRINGS:
        return None
    if _TEMPLATE_RE.match(s) or _PLACEHOLDER_RE.match(s):
        return None
    return s


def _coerce_bool(value: Any) -> bool | None:
    """Convert ON/OFF/true/false/1/0 to bool, else None."""
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if s in _TRUE_STRINGS:
        return True
    if s in _FALSE_STRINGS:
        return False
    return None


def _to_float(value: Any) -> float | None:
    """Best-effort cast to float."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(value: Any, key: str | None = None) -> float | bool | str | None:
    """Normalize a raw ESPAltherma attribute.

    Returns float | bool | str | None. Strings survive for non-numeric
    attributes (mode names, valve states). Template garbage and
    placeholders are filtered to None. For a numeric ``key`` (#423) a
    number is read before ON/OFF, so "0" / "1" stay 0.0 / 1.0.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = _clean_raw(value)
    if cleaned is None:
        return None
    if is_numeric_key(key):
        num = _to_float(cleaned)
        if num is not None:
            return num
    b = _coerce_bool(cleaned)
    if b is not None:
        return b
    f = _to_float(cleaned)
    if f is not None:
        return f
    return cleaned


def read(
    state: Any,
    *,
    custom_map: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a normalized copy of state.attributes (or {} if no state).

    custom_map: {standard_key: actual_attribute_name}. Renames the actual
    attribute to the standard key so downstream code sees the canonical keys.
    """
    if state is None:
        return {}
    raw = getattr(state, "attributes", None)
    if not isinstance(raw, Mapping):
        return {}
    compat = build_compat_view(raw)
    result = {key: _normalize(val, key) for key, val in compat.items()}

    if custom_map:
        for standard, actual in custom_map.items():
            if isinstance(actual, str) and actual in result and actual != standard:
                result[standard] = result.pop(actual)

    return result


def missing_required(attrs: Mapping[str, Any]) -> list[str]:
    """Return required attribute keys that are absent or None.

    Accepts raw ESPAltherma attributes OR the output of read(). The
    compat view is applied internally so definition-file aliases
    (e.g. ``R1T-Outdoor air temp.``) resolve to canonical names.
    Values are normalized before the None check so placeholders
    such as ``---`` count as missing.
    """
    compat = build_compat_view(attrs)
    return [
        key for key in REQUIRED_ATTRIBUTES
        if _normalize(compat.get(key)) is None
    ]
