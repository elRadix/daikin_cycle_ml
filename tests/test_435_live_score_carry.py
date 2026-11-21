"""#435: the live score of an open run is carried into every snapshot.

The coordinator builds a new DataSnapshot on every 30 s tick, while the
live score is recomputed every 5 minutes. Before the fix the ticks in
between left ``quality_live`` at None, so ``quality_today.live_score``
read null 9 ticks out of 10 (#435 diagnostics: a 24 h run open, live
score null, no live pill on the Daily summary card).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)

MOD = "custom_components.daikin_cycle_ml.coordinator"


def _coord(state: str = "running") -> DaikinCycleMLCoordinator:
    coord = object.__new__(DaikinCycleMLCoordinator)
    coord.options = {}
    coord._last_quality_live_ts = 0.0
    coord.detector = SimpleNamespace(  # type: ignore[assignment]
        state=state,
        partial_record=lambda now: {"duration_s": 3600.0, "mode": "heating"},
    )
    return coord


@pytest.mark.asyncio
async def test_score_carried_between_refreshes():
    coord = _coord()
    with patch(f"{MOD}.score_cycle", return_value=88) as score:
        first = DataSnapshot()
        await coord._maybe_refresh_quality_live(1000.0, first)
        second = DataSnapshot()
        await coord._maybe_refresh_quality_live(1030.0, second)
        third = DataSnapshot()
        await coord._maybe_refresh_quality_live(1290.0, third)
    assert score.call_count == 1  # still throttled to one scoring per 5 min
    assert (first.quality_live, first.quality_live_duration_s) == (88, 3600.0)
    assert (second.quality_live, second.quality_live_duration_s) == (88, 3630.0)
    assert (third.quality_live, third.quality_live_duration_s) == (88, 3890.0)


@pytest.mark.asyncio
async def test_rescored_after_five_minutes():
    coord = _coord()
    with patch(f"{MOD}.score_cycle", side_effect=[88, 91]):
        await coord._maybe_refresh_quality_live(1000.0, DataSnapshot())
        snap = DataSnapshot()
        await coord._maybe_refresh_quality_live(1300.0, snap)
    assert snap.quality_live == 91 and snap.quality_live_duration_s == 3600.0


@pytest.mark.asyncio
async def test_idle_clears_the_carried_score():
    coord = _coord()
    with patch(f"{MOD}.score_cycle", return_value=88):
        await coord._maybe_refresh_quality_live(1000.0, DataSnapshot())
    coord.detector.state = "idle"  # type: ignore[attr-defined]
    idle = DataSnapshot()
    await coord._maybe_refresh_quality_live(1030.0, idle)
    assert idle.quality_live is None and idle.quality_live_duration_s is None
    coord.detector.state = "running"  # type: ignore[attr-defined]
    nothing = DataSnapshot()
    await coord._maybe_refresh_quality_live(1060.0, nothing)  # throttled, cache cleared
    assert nothing.quality_live is None and nothing.quality_live_duration_s is None


@pytest.mark.asyncio
async def test_failed_scoring_is_not_carried():
    coord = _coord()
    with patch(f"{MOD}.score_cycle", side_effect=RuntimeError("boom")):
        await coord._maybe_refresh_quality_live(1000.0, DataSnapshot())
    snap = DataSnapshot()
    await coord._maybe_refresh_quality_live(1030.0, snap)
    assert snap.quality_live is None and snap.quality_live_duration_s is None
