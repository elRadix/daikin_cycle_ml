"""Normalize ESPAltherma attribute values for Daikin Cycle ML."""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping

from ..const import REQUIRED_ATTRIBUTES

_LOGGER = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"^\{.*\}$")
_PLACEHOLDER_RE = re.compile(r"^Conv \d+ not avail\.$")
_NULL_STRINGS = {"", "---", "unknown", "unavailable", "none", "nan", "null"}
_TRUE_STRINGS = {"on", "true", "yes", "1"}
_FALSE_STRINGS = {"off", "false", "no", "0"}


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


def _normalize(value: Any) -> float | bool | str | None:
    """Normalize a raw ESPAltherma attribute.

    Returns float | bool | str | None. Strings survive for non-numeric
    attributes (mode names, valve states). Template garbage and
    placeholders are filtered to None.
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
    selected: list[str] | None = None,
) -> dict[str, Any]:
    """Return a normalized copy of state.attributes (or {} if no state).

    custom_map: {standard_key: actual_attribute_name}. Renames actual to
    standard in the result so the rest of the code sees the canonical keys.

    selected: list of attribute keys the user opted into. REQUIRED_ATTRIBUTES
    are always kept (cycle detection depends on them).
    """
    if state is None:
        return {}
    raw = getattr(state, "attributes", None)
    if not isinstance(raw, Mapping):
        return {}
    result = {key: _normalize(val) for key, val in raw.items()}

    if custom_map:
        for standard, actual in custom_map.items():
            if isinstance(actual, str) and actual in result and actual != standard:
                result[standard] = result.pop(actual)

    if selected is not None:
        allowed = set(selected) | set(REQUIRED_ATTRIBUTES)
        result = {k: v for k, v in result.items() if k in allowed}

    return result


def missing_required(attrs: Mapping[str, Any]) -> list[str]:
    """Return required attribute keys that are absent or None."""
    return [key for key in REQUIRED_ATTRIBUTES if attrs.get(key) is None]
