"""v1.19.6 FASE 5B: _is_short_run must parse is_transient numerically.

Pre-v1.19.6 _is_short_run used `if last.get("is_transient"):`. A string
"0" or "false" is truthy -> short_run silently skipped (false negative).
Consistency with _is_transient_int in store.py: parse numerically,
unknown values -> non-transient.
"""

from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.binary_sensor import _is_short_run
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore


class _FakeCoord:
    def __init__(self, last_cycle, options=None):
        self.store = CycleStore()
        if last_cycle is not None:
            self.store.add_cycle(last_cycle)
        self.options = options or {"short_run_threshold_min": 20}


def _snap(mode="heating"):
    s = DataSnapshot()
    s.mode = mode
    return s


def _last(**overrides):
    """Short cycle (5 min, end_ts 100s ago) so it's below threshold (20 min).

    v1.19.7 #259: timestamps must be recent (not 1970); the freshness
    guard blocks stale cycles. This helper's intent is to test
    is_transient parsing, not freshness.
    """
    now = time.time()
    base = {
        "start_ts": now - 400, "end_ts": now - 100, "duration_s": 300,
        "mode": "heating", "dT_max": 5.0, "rps_max": 30,
        "is_transient": 0,
    }
    base.update(overrides)
    return base


def test_short_run_int_1_is_transient():
    """GUARD: is_transient=1 -> skip."""
    c = _FakeCoord(_last(is_transient=1))
    assert _is_short_run(_snap(), c) is False


def test_short_run_bool_true_is_transient():
    """GUARD: is_transient=True -> skip."""
    c = _FakeCoord(_last(is_transient=True))
    assert _is_short_run(_snap(), c) is False


def test_short_run_int_0_fires():
    """GUARD: is_transient=0 + short cycle -> fires."""
    c = _FakeCoord(_last(is_transient=0))
    assert _is_short_run(_snap(), c) is True


def test_short_run_string_zero_fires():
    """RED: is_transient='0' (string) must be treated as 0 -> fires.

    Pre-fix: truthy string -> skip -> False (wrong).
    Post-fix: _is_transient_int('0') == 0 -> fires -> True.
    """
    c = _FakeCoord(_last(is_transient="0"))
    assert _is_short_run(_snap(), c) is True


def test_short_run_string_false_fires():
    """RED: is_transient='false' -> unknown -> treated as non-transient."""
    c = _FakeCoord(_last(is_transient="false"))
    assert _is_short_run(_snap(), c) is True


def test_short_run_string_true_skips():
    """RED: is_transient='true' -> unknown -> treated as 0 -> fires (not skip).

    Note: pre-fix 'true' was truthy -> skipped; post-fix also treats it as
    non-transient per the FASE 5A policy (unparseable -> 0). This is a
    behavioral change: unknown values are treated as real, not transient.
    """
    c = _FakeCoord(_last(is_transient="true"))
    # Post-fix: 0 (unknown treated as non-transient) -> short cycle -> fires
    assert _is_short_run(_snap(), c) is True


def test_short_run_missing_is_transient_fires():
    """GUARD: missing key (legacy) -> fires."""
    rec = _last()
    del rec["is_transient"]
    c = _FakeCoord(rec)
    assert _is_short_run(_snap(), c) is True


def test_short_run_corrupt_last_returns_false():
    """RED: last_cycle() returns non-dict (corrupt) -> False, no crash."""
    class _BadStore(CycleStore):
        def last_cycle(self):
            return "corrupt"

    class _Coord:
        def __init__(self):
            self.store = _BadStore()
            self.options = {"short_run_threshold_min": 20}

    # Pre-fix: AttributeError. Post-fix: False.
    assert _is_short_run(_snap(), _Coord()) is False
