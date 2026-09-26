"""Batch 24 tests: _build_alert_context coverage."""
from __future__ import annotations

import time
from collections import deque
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)


def _bare_coord(options=None, store=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c._setpoint_history = deque()
    c._last_setpoint = None
    c.store = store if store is not None else MagicMock()
    return c


def _default_store_mock():
    st = MagicMock()
    st.cycles_in_window.return_value = 0
    st.cycles_today.return_value = []
    st.off_time_since_last.return_value = None
    return st


def test_smoke_returns_all_keys():
    c = _bare_coord(store=_default_store_mock())
    ctx = c._build_alert_context(DataSnapshot())
    assert isinstance(ctx, dict)
    for key in ("pendulum", "short_run", "short_off",
                "ml_anomaly", "setpoint_osc"):
        assert key in ctx, f"missing {key}"


def test_cph_filled_from_store():
    st = _default_store_mock()
    st.cycles_in_window.return_value = 5
    c = _bare_coord(store=st)
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["pendulum"]["cph"] == 5


def test_cycles_today_len():
    st = _default_store_mock()
    st.cycles_today.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
    c = _bare_coord(store=st)
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["pendulum"]["cycles_today"] == 3


def test_store_exceptions_are_swallowed():
    st = MagicMock()
    st.cycles_in_window.side_effect = RuntimeError("boom")
    st.cycles_today.side_effect = RuntimeError("boom")
    st.off_time_since_last.side_effect = RuntimeError("boom")
    c = _bare_coord(store=st)
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["pendulum"]["cph"] == 0
    assert ctx["pendulum"]["cycles_today"] == 0


def test_advice_title_extracted():
    adv = MagicMock()
    adv.title = "Widen hysteresis"
    c = _bare_coord(store=_default_store_mock())
    snap = DataSnapshot(advice=[adv])
    ctx = c._build_alert_context(snap)
    assert "Widen hysteresis" in ctx["pendulum"]["advice"]


def test_advice_falls_back_to_text_attr():
    adv = MagicMock(spec=["text"])
    adv.text = "Legacy text"
    c = _bare_coord(store=_default_store_mock())
    snap = DataSnapshot(advice=[adv])
    ctx = c._build_alert_context(snap)
    assert "Legacy text" in ctx["pendulum"]["advice"]


def test_last_record_duration_min():
    st = _default_store_mock()
    c = _bare_coord(store=st)
    snap = DataSnapshot(last_record={"duration_s": 900.0})
    ctx = c._build_alert_context(snap)
    assert ctx["short_run"]["duration_min"] == 15


def test_last_record_bad_duration_safe():
    st = _default_store_mock()
    c = _bare_coord(store=st)
    snap = DataSnapshot(last_record={"duration_s": "junk"})
    ctx = c._build_alert_context(snap)
    assert ctx["short_run"]["duration_min"] == "?"


def test_off_time_filled():
    st = _default_store_mock()
    st.off_time_since_last.return_value = 600.0  # 10 min
    c = _bare_coord(store=st)
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["short_off"]["off_min"] == 10


def test_anomaly_fills_ml_block():
    anom = MagicMock()
    anom.max_abs_z = 2.5
    anom.top_dim = 3  # valid index into FEATURE_NAMES
    anom.severity = "warning"
    c = _bare_coord(store=_default_store_mock())
    snap = DataSnapshot(mode="Heating", anomaly=anom)
    ctx = c._build_alert_context(snap)
    assert ctx["ml_anomaly"]["z_max"] == 2.5
    assert ctx["ml_anomaly"]["mode"] == "Heating"
    assert ctx["ml_anomaly"]["top_dim"] != "?"


def test_anomaly_out_of_range_top_dim():
    anom = MagicMock()
    anom.max_abs_z = 1.1
    anom.top_dim = 999
    anom.severity = None
    c = _bare_coord(store=_default_store_mock())
    snap = DataSnapshot(anomaly=anom)
    ctx = c._build_alert_context(snap)
    assert "dim 999" in str(ctx["ml_anomaly"]["top_dim"])


def test_anomaly_bad_z_safe():
    anom = MagicMock()
    anom.max_abs_z = "junk"
    anom.top_dim = None
    anom.severity = None
    c = _bare_coord(store=_default_store_mock())
    snap = DataSnapshot(anomaly=anom)
    ctx = c._build_alert_context(snap)
    assert ctx["ml_anomaly"]["z_max"] == "?"


def test_setpoint_osc_context_uses_history_len():
    c = _bare_coord(
        options={"setpoint_osc_window_min": 60,
                 "setpoint_oscillation_threshold": 8},
        store=_default_store_mock(),
    )
    now = time.time()
    c._setpoint_history = deque([(now, x) for x in (35.0, 34.5, 35.0)])
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["setpoint_osc"]["osc_count"] == 3
    assert ctx["setpoint_osc"]["window_min"] == 60
    assert ctx["setpoint_osc"]["threshold"] == 8


def test_snap_none_safe():
    c = _bare_coord(store=_default_store_mock())
    ctx = c._build_alert_context(None)
    assert isinstance(ctx, dict)
    assert ctx["pendulum"]["advice"] == ""


def test_options_threshold_defaults_used():
    c = _bare_coord(store=_default_store_mock())
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["short_run"]["threshold_min"] == 20
    assert ctx["short_off"]["threshold_min"] == 5
    assert ctx["pendulum"]["target_cph"] == 4
    assert ctx["pendulum"]["target_cpd"] == 40
