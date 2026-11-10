"""Issue #316: live quality scoring during open cycle.

Problem: quality_today averages only CLOSED cycles, so users see 0%
while a long cycle runs (prod-1 evidence: cycle #341, 22.5h, quality
100 at close, 0% throughout). This test file covers the live scoring
feature that folds an in-progress cycle into quality_today.

Design:
- detector.partial_record(now)   -> build record from current accumulation
- coordinator._maybe_refresh_quality_live(now) -> throttled 5min scorer
- snap.quality_live             -> live int (or None when idle)
- sensor._compute_quality_today  -> avg(closed + [live] if present)
- sensor._attrs_quality_today    -> expose live fields as attributes
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    STATE_RUNNING,
    CycleDetector,
)


class _FakeStore:
    def __init__(self, cycles: list[dict]) -> None:
        self._cycles = cycles
        self._counters = {"good_cycles_today": 0, "bad_cycles_today": 0}

    def cycles_today(self, now: float) -> list[dict]:
        return self._cycles

    def get(self, key: str, default=0):
        return self._counters.get(key, default)


class _FakeDetector:
    def __init__(self, state: str = "idle") -> None:
        self.state = state


class _FakeCoord:
    def __init__(self, state: str = "idle", cycles: list[dict] | None = None):
        self.detector = _FakeDetector(state)
        self.store = _FakeStore(cycles or [])
        self.options: dict = {}


class _FakeSnap:
    def __init__(self, live: int | None = None, live_dur: float | None = None):
        self.quality_live = live
        self.quality_live_duration_s = live_dur


# --- detector.partial_record ---

def test_partial_record_returns_scoreable_dict_when_running() -> None:
    det = CycleDetector()
    det.update(
        {
            "INV frequency (rps)": 30,
            "Water pump operation": "ON",
            "Operation Mode": "Heating",
            "Leaving water temp. after BUH (R2T)": 35.0,
            "Inlet water temp.(R4T)": 28.0,
            "Flow sensor (l/min)": 15.0,
        },
        now=1000.0,
    )
    assert det.state == STATE_RUNNING
    rec = det.partial_record(now=2800.0)  # +30 min
    assert rec["duration_s"] == 1800
    assert rec["mode"] == "heating"
    assert rec["dT_max"] is not None and rec["dT_max"] > 0
    assert rec["buh_used"] is False


def test_partial_record_empty_when_idle() -> None:
    det = CycleDetector()
    assert det.partial_record(now=1000.0) == {}


def test_partial_record_does_not_reset_state() -> None:
    det = CycleDetector()
    det.update(
        {
            "INV frequency (rps)": 30,
            "Water pump operation": "ON",
            "Operation Mode": "Heating",
        },
        now=1000.0,
    )
    assert det.state == STATE_RUNNING
    rec1 = det.partial_record(now=2000.0)
    rec2 = det.partial_record(now=3000.0)
    assert det.state == STATE_RUNNING
    assert rec2["duration_s"] > rec1["duration_s"]


# --- sensor._compute_quality_today ---

def test_compute_quality_today_closed_only() -> None:
    from custom_components.daikin_cycle_ml.sensor import _compute_quality_today
    coord = _FakeCoord(state="idle", cycles=[{"quality_score": 80}, {"quality_score": 60}])
    snap = _FakeSnap(live=None)
    assert _compute_quality_today(snap, coord) == 70.0


def test_compute_quality_today_includes_live_when_cycle_open() -> None:
    from custom_components.daikin_cycle_ml.sensor import _compute_quality_today
    coord = _FakeCoord(state="running", cycles=[{"quality_score": 80}, {"quality_score": 60}])
    snap = _FakeSnap(live=90, live_dur=1800.0)
    assert _compute_quality_today(snap, coord) == pytest.approx(76.666, rel=0.01)


def test_compute_quality_today_live_only_no_closed() -> None:
    from custom_components.daikin_cycle_ml.sensor import _compute_quality_today
    coord = _FakeCoord(state="running", cycles=[])
    snap = _FakeSnap(live=75, live_dur=900.0)
    assert _compute_quality_today(snap, coord) == 75.0


def test_compute_quality_today_no_data_returns_none() -> None:
    from custom_components.daikin_cycle_ml.sensor import _compute_quality_today
    coord = _FakeCoord(state="idle", cycles=[])
    snap = _FakeSnap(live=None)
    assert _compute_quality_today(snap, coord) is None


# --- sensor._attrs_quality_today (live fields) ---

def test_attrs_quality_today_exposes_live_fields_when_open() -> None:
    from custom_components.daikin_cycle_ml.sensor import _attrs_quality_today
    coord = _FakeCoord(state="running", cycles=[])
    snap = _FakeSnap(live=85, live_dur=1200.0)
    attrs = _attrs_quality_today(snap, coord)
    assert attrs["live_score"] == 85
    assert attrs["is_cycle_open"] is True
    assert attrs["live_cycle_duration_s"] == 1200.0


def test_attrs_quality_today_no_live_when_idle() -> None:
    from custom_components.daikin_cycle_ml.sensor import _attrs_quality_today
    coord = _FakeCoord(state="idle", cycles=[])
    snap = _FakeSnap(live=None)
    attrs = _attrs_quality_today(snap, coord)
    assert attrs["live_score"] is None
    assert attrs["is_cycle_open"] is False
    assert attrs["live_cycle_duration_s"] is None

# --- coordinator._maybe_refresh_quality_live branches (#316) ---

@pytest.mark.asyncio
async def test_maybe_refresh_quality_live_partial_record_empty() -> None:
    """Detector running but partial_record returns {} -> clear fields."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )

    coord = object.__new__(DaikinCycleMLCoordinator)
    coord.options = {}
    coord._last_quality_live_ts = 0.0

    class _Det:
        state = "running"

        def partial_record(self, now: float) -> dict:
            return {}

    coord.detector = _Det()  # type: ignore[assignment]

    class _Snap:
        quality_live: int | None = 50
        quality_live_duration_s: float | None = 100.0

    snap = _Snap()
    await coord._maybe_refresh_quality_live(now=2000.0, snap=snap)  # type: ignore[arg-type]
    assert snap.quality_live is None
    assert snap.quality_live_duration_s is None


@pytest.mark.asyncio
async def test_maybe_refresh_quality_live_score_cycle_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exception in score_cycle -> warning + fields cleared."""
    from unittest.mock import patch

    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )

    coord = object.__new__(DaikinCycleMLCoordinator)
    coord.options = {}
    coord._last_quality_live_ts = 0.0

    class _Det:
        state = "running"

        def partial_record(self, now: float) -> dict:
            return {"duration_s": 100.0, "mode": "heating", "dT_max": 5.0}

    coord.detector = _Det()  # type: ignore[assignment]

    class _Snap:
        quality_live: int | None = 50
        quality_live_duration_s: float | None = 100.0

    snap = _Snap()
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.score_cycle",
        side_effect=RuntimeError("boom"),
    ):
        await coord._maybe_refresh_quality_live(now=2000.0, snap=snap)  # type: ignore[arg-type]
    assert snap.quality_live is None
    assert snap.quality_live_duration_s is None
    assert any(
        "live quality refresh failed" in rec.message for rec in caplog.records
    )

# --- coordinator._maybe_refresh_quality_live branches (#316) ---
