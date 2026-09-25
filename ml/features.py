"""Feature vector extraction for Daikin Cycle ML (Batch 7a).

Pure Python, no numpy. Every feature is a float; missing fields
default to 0.0 to preserve vector shape.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

_LOGGER = logging.getLogger(__name__)

FEATURE_NAMES: tuple[str, ...] = (
    "duration_s",
    "dT_max",
    "dT_avg",
    "rps_max",
    "rps_avg",
    "outdoor_temp",
    "buh_used",
    "defrost_used",
)

VECTOR_LEN = len(FEATURE_NAMES)

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


def extract_feature_vector(record: Mapping[str, Any]) -> list[float]:
    """Return fixed-length vector (VECTOR_LEN). Missing -> 0.0."""
    out: list[float] = []
    for name in FEATURE_NAMES:
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
