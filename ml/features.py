"""Feature vector extraction for Daikin Cycle ML (Batch 7a).

Pure Python, no numpy. Every feature is a float; missing fields
default to 0.0 to preserve vector shape.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

_LOGGER = logging.getLogger(__name__)

FEATURE_NAMES: tuple[str, ...] =(
    "duration_s",
    "dT_max",
    "dT_avg",
    "rps_max",
    "rps_avg",
    "outdoor_temp",
    "buh_used",
    "defrost_used",
    "cop_avg",
    "lwt_avg",
    "indoor_temp_avg",
    "thermal_kw_avg",
)

VECTOR_LEN = len(FEATURE_NAMES)
VECTOR_LEN_LEGACY = 8

REQUIRED_FOR_VALID: tuple[str, ...] = (
    "duration_s",
    "dT_max",
    "rps_max",
)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None


def extract_feature_vector(
    record: Mapping[str, Any],
    *,
    cop_avg: float | None = None,
    lwt_avg: float | None = None,
    indoor_temp_avg: float | None = None,
    thermal_kw_avg: float = 0.0,
) -> list[float]:
    """Return fixed-length vector (VECTOR_LEN). Missing -> 0.0."""
    out: list[float] = []
    overrides = {
        "cop_avg": cop_avg,
        "lwt_avg": lwt_avg,
        "indoor_temp_avg": indoor_temp_avg,
        "thermal_kw_avg": thermal_kw_avg,
}
    for name in FEATURE_NAMES:
        if name in overrides and overrides[name] is not None:
            out.append(float(overrides[name]))
        else:
            v = _as_float(record.get(name))
            out.append(v if v is not None else 0.0)
    return out


def is_valid_record(record: Mapping[str, Any]) -> bool:
    """True iff all REQUIRED_FOR_VALID are numeric (not None, not str)."""
    if not record:
        return False
    for name in REQUIRED_FOR_VALID:
        if _as_float(record.get(name)) is None:
            return False
    return True


def extract_many(records: list[Mapping[str, Any]]) -> list[list[float]]:
    """Extract vectors, skipping invalid records."""
    return [extract_feature_vector(r) for r in records if is_valid_record(r)]
