"""v1.12.0: transient classification tests (issue #105)."""
from __future__ import annotations

import datetime as _dt

from custom_components.daikin_cycle_ml.coordinator import (
    _classify_transient,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


# ---- _classify_transient branch coverage ----

def _rec(**kw):
    base = {"duration_s": None, "dT_max": None, "rps_max": None}
    base.update(kw)
    return base


def test_classify_short_duration():
    assert _classify_transient(_rec(duration_s=60)) is True


def test_classify_near_max_all_match():
    assert _classify_transient(_rec(
        duration_s=200, dT_max=2.5, rps_max=45
    )) is True


def test_classify_near_max_dt_too_high():
    assert _classify_transient(_rec(
        duration_s=200, dT_max=5.0, rps_max=45
    )) is False


def test_classify_near_max_rps_too_low():
    assert _classify_transient(_rec(
        duration_s=200, dT_max=2.5, rps_max=30
    )) is False


def test_classify_normal():
    assert _classify_transient(_rec(
        duration_s=600, dT_max=5.0, rps_max=30
    )) is False


def test_classify_dur_none():
    assert _classify_transient(_rec(duration_s=None)) is False


def test_classify_dt_none_near_max():
    assert _classify_transient(_rec(
        duration_s=200, dT_max=None, rps_max=45
    )) is False


def test_classify_rps_none_near_max():
    assert _classify_transient(_rec(
        duration_s=200, dT_max=2.5, rps_max=None
    )) is False


# ---- store helpers ----

def _today_noon() -> float:
    return _dt.datetime.combine(
        _dt.date.today(), _dt.time(12, 0)
    ).timestamp()


def _cycle(start_ts: float, transient: int) -> dict:
    return {
        "start_ts": start_ts, "end_ts": start_ts + 60,
        "duration_s": 60, "mode": "heating",
        "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 30, "rps_avg": 20.0,
        "outdoor_temp": 10.0,
        "buh_used": 0, "defrost_used": 0,
        "is_transient": transient,
    }


def test_non_transient_today_filters():
    noon = _today_noon()
    s = CycleStore()
    s.add_cycle(_cycle(noon - 100, 0))
    s.add_cycle(_cycle(noon - 200, 1))
    s.add_cycle(_cycle(noon - 300, 0))
    result = s.non_transient_today(noon + 100)
    assert len(result) == 2
    assert all(not c.get("is_transient") for c in result)


def test_non_transient_in_window_filters():
    noon = _today_noon()
    s = CycleStore()
    s.add_cycle(_cycle(noon - 100, 0))
    s.add_cycle(_cycle(noon - 200, 1))
    s.add_cycle(_cycle(noon - 300, 1))
    s.add_cycle(_cycle(noon - 5000, 0))  # outside 3600s window
    assert s.non_transient_in_window(noon, 3600) == 1


# ---- integration: baseline guard + sensor attrs ----

import datetime as _dt2  # noqa: E402
from typing import Any
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from custom_components.daikin_cycle_ml.coordinator import (  # noqa: E402
    DaikinCycleMLCoordinator,
)


class _Snap:
    def __init__(self) -> None:
        self.mode = "heating"
        self.anomaly = None
        self.advice = None
        self.cluster_id = None


def _make_coord() -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {"action_advice_enabled": False}
    c.db = MagicMock()
    c.db.async_insert_cycle = AsyncMock(return_value=101)
    c.db.async_insert_features = AsyncMock(return_value=None)
    c.db.async_update_cycle_cluster = AsyncMock(return_value=None)
    c._collect_cycle_averages = AsyncMock(
        return_value=(5.0, 30.0, 21.0)
    )
    c._assign_cluster = MagicMock(return_value=2)
    c._maybe_rollup_day = AsyncMock(return_value=None)
    c.adaptive = MagicMock()
    c.adaptive.observe_cycle = MagicMock(return_value=None)
    _bl = MagicMock()
    _bl.update = MagicMock(return_value=None)
    c.baseline = MagicMock()
    c.baseline.get = MagicMock(return_value=_bl)
    c._clamp_duration = lambda d, m: d  # type: ignore[method-assign]
    return c


def _rec_full(transient: int, dur: float = 600.0) -> dict[str, Any]:
    return {
        "start_ts": 1000.0, "end_ts": 1000.0 + dur, "duration_s": dur,
        "mode": "heating", "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 30, "rps_avg": 20.0, "thermal_kw_avg": 2.5,
        "buh_used": 0, "defrost_used": 0, "is_transient": transient,
    }


async def test_baseline_skipped_for_transient_cycle(monkeypatch):
    """is_transient=1 -> baseline.update not called (FALSE branch)."""
    c = _make_coord()
    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(
        co, "extract_feature_vector", lambda *a, **k: [0.0] * 12
    )
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec_full(1), _Snap())
    bl = c.baseline.get.return_value
    bl.update.assert_not_called()


async def test_baseline_called_for_non_transient_cycle(monkeypatch):
    """is_transient=0 -> baseline.update called (TRUE branch)."""
    c = _make_coord()
    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(
        co, "extract_feature_vector", lambda *a, **k: [0.0] * 12
    )
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec_full(0), _Snap())
    bl = c.baseline.get.return_value
    bl.update.assert_called_once()


def test_attrs_today_includes_transient_fields():
    """_attrs_today surfaces transient/non-transient counts + ratio."""
    from custom_components.daikin_cycle_ml.sensor import _attrs_today
    now = _dt2.datetime.combine(
        _dt2.date.today(), _dt2.time(12, 0)
    ).timestamp()
    cycles = [
        _cycle(now - 100, 0),
        _cycle(now - 200, 1),
        _cycle(now - 300, 0),
        _cycle(now - 400, 1),
    ]
    c = MagicMock()
    c.store.cycles_today = MagicMock(return_value=cycles)
    c.store.cycles_in_window = MagicMock(return_value=4)
    c.store.get = MagicMock(side_effect=lambda k, d=None: {
        "short_runs_today": 0,
        "short_offs_today": 0,
    }.get(k, d))
    s = MagicMock()
    result = _attrs_today(s, c)
    assert result["transient_cycles_today"] == 2
    assert result["non_transient_cycles_today"] == 2
    assert result["transient_ratio_pct"] == 50.0


# ---- proactive: helper edge cases (defense in depth) ----

def test_non_transient_today_mixed_returns_only_real():
    """40 mixed cycles, 15 transient -> 25 non-transient."""
    noon = _today_noon()
    s = CycleStore()
    for i in range(40):
        trans = 1 if i < 15 else 0
        s.add_cycle(_cycle(noon - i * 100, trans))
    result = s.non_transient_today(noon + 100)
    assert len(result) == 25
    assert all(not c.get("is_transient") for c in result)


def test_non_transient_today_all_transient_returns_empty():
    noon = _today_noon()
    s = CycleStore()
    for i in range(5):
        s.add_cycle(_cycle(noon - i * 100, 1))
    assert len(s.non_transient_today(noon + 100)) == 0


def test_non_transient_today_all_real_returns_all():
    noon = _today_noon()
    s = CycleStore()
    for i in range(7):
        s.add_cycle(_cycle(noon - i * 100, 0))
    assert len(s.non_transient_today(noon + 100)) == 7


def test_non_transient_in_window_excludes_outside():
    """Out-of-window real cycle must not count."""
    noon = _today_noon()
    s = CycleStore()
    s.add_cycle(_cycle(noon - 100, 0))
    s.add_cycle(_cycle(noon - 3700, 0))
    assert s.non_transient_in_window(noon, 3600) == 1


def test_non_transient_in_window_filters_mixed():
    """Only non-transient in-window cycles count."""
    noon = _today_noon()
    s = CycleStore()
    s.add_cycle(_cycle(noon - 100, 0))
    s.add_cycle(_cycle(noon - 200, 1))
    s.add_cycle(_cycle(noon - 300, 0))
    s.add_cycle(_cycle(noon - 400, 1))
    s.add_cycle(_cycle(noon - 5000, 0))
    assert s.non_transient_in_window(noon, 3600) == 2


def test_non_transient_in_window_all_real():
    noon = _today_noon()
    s = CycleStore()
    for i in range(6):
        s.add_cycle(_cycle(noon - i * 100, 0))
    assert s.non_transient_in_window(noon, 3600) == 6
