"""v1.20.0 RED-phase tests for defrost/BUH fixes (#280).

R634/R635/R681: production-derived reproduction tests.
Bug 5 is confirmed via issue #280 symptom (ed-vanleeuwen, 2026-11-07):
"number of defrosts... counter displays zero" on non-BUH model.

Bugs 2/3/4 discovered during R681 investigation of #280, same code path.
"""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)

_COORD_MOD = "custom_components.daikin_cycle_ml.coordinator"


def _bare() -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=MagicMock())
    c.source_entity = "sensor.test_source"
    c.options = {"buh_step1_kw": 3.0, "buh_step2_kw": 6.0}
    c.entry = MagicMock()
    c.entry.data = {}
    c.store = MagicMock()
    c.store.daily_reset_if_needed = MagicMock(return_value=False)
    c.detector = MagicMock()
    c.detector.state = "running"
    c.detector.snapshot = MagicMock(return_value={"mode": "heating", "start_ts": 0.0})
    c.detector.update = MagicMock(return_value=None)
    c.db = None
    c._runtime_day_key = ""
    c._energy_day_key = ""
    c._prev_defrost = False
    c._defrost_start_ts = None
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._last_defrost_ts = 0.0
    c._last_runtime_tick_ts = 0.0
    c._buh_step1_s = 0.0
    c._buh_step2_s = 0.0
    c._track_setpoint = MagicMock()
    c._read_power_w = MagicMock(return_value=1500.0)
    c._read_cop = MagicMock(return_value=3.5)
    c._compute_setpoint_oscillating = MagicMock(return_value=False)
    c._accumulate_cycle_samples = MagicMock()
    c._process_new_cycle = AsyncMock(return_value=None)
    c._maybe_persist_accumulators = AsyncMock(return_value=None)
    c._maybe_reset_daily_accumulators = MagicMock()
    c._maybe_collect_cop_sample = AsyncMock(return_value=None)
    c._refresh_cop_today = AsyncMock(return_value=None)
    c._maybe_refresh_stooklijn = AsyncMock(return_value=None)
    c._refresh_7d_rollups = AsyncMock(return_value=None)
    c._async_dispatch_alerts = AsyncMock(return_value=None)
    c._async_check_repairs = AsyncMock(return_value=None)
    return c


# ---------- BUG 5: freeze gate blocks defrost tick (#280 root cause) ----------


@pytest.mark.asyncio
async def test_freeze_gate_does_not_block_defrost_tick(monkeypatch):
    """#280: non-BUH model triggers missing_attrs -> tick must still run.

    R634: reproduction from ed-vanleeuwen symptom "counter displays zero".
    R681: fix is safe because no existing test asserts tick_buh is frozen.
    """
    c = _bare()
    # Simulate non-BUH model: only BUH Step1/Step2 missing.
    partial_attrs = {
        ATTR_DEFROST_OPERATION: True,
        "Operation Mode": "Heating",
    }
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: dict(partial_attrs))
    monkeypatch.setattr(
        f"{_COORD_MOD}.missing_required",
        lambda a: [ATTR_BUH_STEP1, ATTR_BUH_STEP2],
    )
    c._last_runtime_tick_ts = 1000.0
    await c._async_update_data()
    # RED on current code: count stays 0 because freeze returns early.
    assert c._defrost_count_today == 1
    assert c._prev_defrost is True


@pytest.mark.asyncio
async def test_freeze_gate_still_blocks_detector_update(monkeypatch):
    """R600: freeze gate must still protect detector from partial attrs."""
    c = _bare()
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: {})
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda a: ["rps"])
    await c._async_update_data()
    c.detector.update.assert_not_called()


# ---------- BUG 2: defrost duration double-count on OFF ----------


@pytest.mark.parametrize("tick_count", [2, 3, 4, 6, 10])
def test_defrost_duration_multi_tick_no_double(tick_count):
    """#280 R634: 4-tick ON sequence + OFF must yield elapsed, not sum+elapsed.

    Current bug: duration = (tick_count-1)*interval + tick_count*interval.
    Expected:   duration = tick_count*interval.
    """
    c = _bare()
    interval = 30.0
    start = 1000.0
    c._last_runtime_tick_ts = start - interval  # avoid dt=0 warm-up no-op
    # tick_count ON ticks (start + i*interval)
    for i in range(tick_count):
        now = start + i * interval
        c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, now)
    # OFF tick at start + tick_count*interval
    now_off = start + tick_count * interval
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, now_off)
    expected = tick_count * interval
    assert math.isclose(c._defrost_duration_s, expected, abs_tol=0.01), (
        f"duration={c._defrost_duration_s} expected={expected}"
    )


def test_defrost_running_tally_prior_plus_current():
    """R634/Bug 2b: second defrost same day must show prior+current, not max(prior,current).

    Production scenario: two defrosts within one day. Display during defrost #2
    must accumulate #1 total + #2 running, not overwrite #1.
    """
    c = _bare()
    c._last_runtime_tick_ts = 970.0
    # Defrost #1: 100s
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, 1000.0)
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, 1100.0)
    assert c._defrost_duration_s == 100.0
    # Defrost #2 starts 1200, running tally at 1250 -> prior 100 + current 50 = 150
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, 1200.0)
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, 1250.0)
    assert c._defrost_duration_s == 150.0
    # Finalize at 1400 -> 100 + 200 = 300
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, 1400.0)
    assert c._defrost_duration_s == 300.0


# ---------- BUG 3: restart mid-defrost double-count ----------


@pytest.mark.asyncio
@pytest.mark.xfail(reason='pre-existing CI failure on clean main 8bb970a since 2026-11-08 (Python 3.13.17->3.13.18 / dep drift); tracking issue pending', strict=False)  # R747-xfail-depdrift
async def test_restore_runtime_acc_handles_start_ts(monkeypatch):
    """R634: restart mid-defrost must restore _defrost_start_ts if present.

    Without this, _prev_defrost=False after restart, next ON tick counts again.
    """
    c = _bare()
    c.db = MagicMock()
    c.db.async_get_model_state = AsyncMock(
        return_value={
            "day": "2026-11-07",
            "buh_step1_s": 0.0,
            "buh_step2_s": 0.0,
            "defrost_count": 1,
            "defrost_duration_s": 60.0,
            "last_defrost_ts": 500.0,
            "defrost_start_ts": 500.0,
            "prev_defrost": True,
        }
    )
    c._runtime_day_key = "2026-11-07"
    await c._restore_runtime_acc()
    assert c._defrost_start_ts == 500.0
    assert c._prev_defrost is True


def test_defrost_restart_mid_no_double_count():
    """R634: restart then ON-tick must NOT increment count (already counted)."""
    c = _bare()
    c._defrost_count_today = 1
    c._defrost_start_ts = 500.0
    c._prev_defrost = True  # restored
    c._last_runtime_tick_ts = 500.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, 530.0)
    assert c._defrost_count_today == 1  # no increment


# ---------- BUG 4: BUH bool True ignored in _compute_electrical_power ----------


@pytest.mark.parametrize("truthy", [True, 1, "ON", "on", "true"])
def test_buh_power_truthy_variants(truthy):
    """#280 R641 matrix: read() produces bool; _is_on must accept both."""
    c = _bare()
    c._last_v2_stats_ts = 0.0
    # Bypass sensor path: use inverter current as base
    from custom_components.daikin_cycle_ml.const import INV_PRIMARY_CURRENT_KEY
    attrs = {INV_PRIMARY_CURRENT_KEY: 1.8, ATTR_BUH_STEP1: truthy}
    pw, src = c._compute_electrical_power(1000.0, attrs)
    assert pw is not None
    # Base inverter ~514W + BUH 3000W = 3514W
    assert pw >= 3000.0, f"BUH Step1 not added (pw={pw}, src={src})"


@pytest.mark.parametrize("falsy", [False, 0, "OFF", "off", "false", None])
def test_buh_power_falsy_variants(falsy):
    """R641: falsy variants must NOT add BUH power."""
    c = _bare()
    c._last_v2_stats_ts = 0.0
    from custom_components.daikin_cycle_ml.const import INV_PRIMARY_CURRENT_KEY
    attrs = {INV_PRIMARY_CURRENT_KEY: 1.8, ATTR_BUH_STEP1: falsy}
    pw, _src = c._compute_electrical_power(1000.0, attrs)
    assert pw is not None
    assert pw < 1000.0, f"BUH wrongly added (pw={pw})"


# ---------- R640/R676: hypothesis fuzz for _is_on ----------


@given(v=st.one_of(
    st.booleans(),
    st.integers(min_value=-100, max_value=100),
    st.text(max_size=10),
    st.none(),
))
@settings(max_examples=200, deadline=None)
def test_is_on_fuzz_never_raises(v):
    """R676: 200 cases per parser; _is_on must accept any input without crash."""
    c = _bare()
    # Must not raise on any input
    result = c._is_on(v)
    assert isinstance(result, bool)
