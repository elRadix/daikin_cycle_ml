"""A3 fix-verification tests (post-fix; fix already applied on this branch).

Three categories:
  - repro_*: documents the bug shape; passes pre- and post-fix
  - fixed_*: only passes after the fix (would fail on pre-fix code)
  - refute_*: guards against the issue's wrong hypothesis reappearing
"""
import inspect
import time

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.diagnostics import _sampling_snapshot


class _A3aStub:
    def __init__(self, primed: bool = False) -> None:
        self._tick_timestamps = [time.time() - i * 30 for i in range(198)]
        self._samples_last_24h = 198
        self._samples_expected_24h = 2880
        self._gap_count_24h = 9
        self._largest_gap_s = 55.1
        self._last_gap_s = 55.1
        self._duplicate_ts_count = 0
        self._uptime_start_monotonic = time.monotonic() - 6210.0
        self._samples_window_primed = primed
        self._samples_expected_since_start = 207


def test_a3a_repro_label_misleading():
    """198/2880 = 6.9% label vs 198/207 = 95.7% actual (bug shape)."""
    snap = _sampling_snapshot(_A3aStub())
    assert snap["samples_last_24h"] / snap["samples_expected_24h"] < 0.10
    assert 198 / (6210.0 / 30.0) > 0.95


def test_a3a_fixed_exposes_window_label():
    """Post-fix: window='since_start' with truthful rate_pct=95.7."""
    snap = _sampling_snapshot(_A3aStub(primed=False))
    assert snap["samples_window"] == "since_start"
    assert snap["samples_since_start"] == 198
    assert snap["samples_expected_since_start"] == 207
    assert 94.0 <= snap["sample_rate_pct"] <= 96.0


class _FakeDB:
    """Non-empty rows → triggers 2-query path (days=1 + days=7)."""

    def __init__(self) -> None:
        self.fetch_cop_samples_calls: list[int] = []

    async def async_fetch_cop_samples(self, days: int = 1):
        self.fetch_cop_samples_calls.append(days)
        return [{"ts": time.time(), "cop": 3.5, "mode": "heating",
                 "boiler_active": 0}]


class _FakeDBEmpty:
    """Empty rows → triggers early-return path (1-query, P4 guard)."""

    def __init__(self) -> None:
        self.fetch_cop_samples_calls: list[int] = []

    async def async_fetch_cop_samples(self, days: int = 1):
        self.fetch_cop_samples_calls.append(days)
        return []


def _make_coord(db=None):
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    coord.db = db or _FakeDB()
    coord._is_hybrid_install = lambda: False
    coord._cop_today_cache = {}
    coord._cop_today_heating_cache = {}
    coord._cop_today_cache_ts = 0.0
    coord._cop_today_dirty = True
    return coord


@pytest.mark.asyncio
async def test_a3b_fixed_throttle_active():
    """300s span / 60s throttle = 5 windows × 2 queries = 10 (fixed)."""
    coord = _make_coord()
    now = time.time()
    for i in range(10):
        await coord._refresh_cop_today(now + i * 30)
    n = len(coord.db.fetch_cop_samples_calls)
    assert n == 10, f"expected 10 queries over 5 throttle windows, got {n}"
    assert coord.db.fetch_cop_samples_calls.count(1) == 5
    assert coord.db.fetch_cop_samples_calls.count(7) == 5


@pytest.mark.asyncio
async def test_a3b_throttle_resets_on_empty_rows():
    """P4 regression guard: empty-rows early-return must still set ts.

    Pre-P4-fix: first call returns before ts=now → second call at +30 is
    NOT throttled → 2 queries. Post-fix: ts set upfront → 1 query.
    """
    coord = _make_coord(db=_FakeDBEmpty())
    now = time.time()
    await coord._refresh_cop_today(now)
    assert coord._cop_today_cache_ts == now, "ts not set on empty rows (P4)"
    await coord._refresh_cop_today(now + 30)
    assert len(coord.db.fetch_cop_samples_calls) == 1, (
        "second call re-queried → P4 not fixed"
    )


def test_a3b_refute_issue_hypothesis():
    """Issue claims _refresh_daily_summary_recent is in tick — it is not."""
    src = inspect.getsource(DaikinCycleMLCoordinator._async_update_data)
    assert "_refresh_daily_summary_recent" not in src


def test_a3a_primed_24h_window():
    """primed=True arm: window='24h', since_start fields nulled."""
    snap = _sampling_snapshot(_A3aStub(primed=True))
    assert snap["samples_window"] == "24h"
    assert snap["samples_since_start"] is None
    assert snap["samples_expected_since_start"] is None


def test_a3a_zero_expected_yields_null_rate():
    """expected_since=0 arm: rate_pct=None (no ZeroDivisionError)."""
    stub = _A3aStub(primed=False)
    stub._samples_expected_since_start = 0
    assert _sampling_snapshot(stub)["sample_rate_pct"] is None


def test_a3a_non_int_last_yields_null_rate():
    """last is not int arm: rate_pct=None (defensive isinstance check)."""
    stub = _A3aStub(primed=False)
    stub._samples_last_24h = None
    assert _sampling_snapshot(stub)["sample_rate_pct"] is None


@pytest.mark.asyncio
async def test_a3b_db_none_early_return():
    """db is None arm: return without raising."""
    coord = _make_coord()
    coord.db = None
    await coord._refresh_cop_today(time.time())  # must not raise


def test_a3a_record_tick_health_primed_skips():
    coord = _make_coord()
    coord._samples_window_primed = True
    coord._tick_timestamps = [time.time()]
    coord._samples_expected_since_start = 999
    coord._record_tick_health()
    assert coord._samples_expected_since_start == 999


def test_a3a_record_tick_health_unprimed_computes():
    from datetime import timedelta
    coord = _make_coord()
    coord._samples_window_primed = False
    coord._tick_timestamps = [time.time()]
    coord._samples_expected_since_start = 0
    coord._uptime_start_monotonic = time.monotonic() - 6210.0
    coord.update_interval = timedelta(seconds=30)
    coord._record_tick_health()
    assert coord._samples_expected_since_start >= 205
