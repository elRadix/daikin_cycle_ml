"""Timer / duration helpers for Daikin Cycle ML."""
from __future__ import annotations

import logging
import time

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_DURATION_MIN = 240
STALE_THRESHOLD_S = 3600.0


def clamp_cycle_duration(
    seconds: float | int | None,
    max_min: int = DEFAULT_MAX_DURATION_MIN,
) -> int:
    """Clamp a duration in seconds to [0, max_min*60], as int."""
    if seconds is None:
        return 0
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return 0
    if s < 0:
        return 0
    max_s = max(0, int(max_min)) * 60
    return int(min(s, max_s))


def is_stale(
    last_ts: float | None,
    now: float | None = None,
    threshold_s: float = STALE_THRESHOLD_S,
) -> bool:
    """Return True if last_ts is None or older than threshold_s."""
    if last_ts is None:
        return True
    if now is None:
        now = time.time()
    return (now - last_ts) > threshold_s


def reconcile(
    last_ts: float | None,
    now: float,
    expected_interval_s: float = 30.0,
    gap_factor: float = 3.0,
) -> float | None:
    """Return last_ts if plausibly continuous, else None (restart)."""
    if last_ts is None:
        return None
    if last_ts > now:
        return None
    if (now - last_ts) > expected_interval_s * gap_factor:
        return None
    return last_ts
