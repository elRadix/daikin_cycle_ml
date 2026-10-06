"""v1.6.1 - R286/R287: energy tick must skip standby/idle, no unknown fallback.

R286: `_tick_energy` must only accumulate when compressor is running or BUH
is active. Prevents standby power (e.g. 21 W controller draw) from being
booked as heating consumption (prod finding 2026-10-06).

R287: no fallback to "heating" for unknown modes. Unknown means the detector
has not classified the cycle yet; those ticks are skipped.

R286b: BUH-only fallback - BUH is resistive, so accumulate electrical only
when thermal computation is unavailable but BUH is on and power is known.

Note: `_tick_energy` uses `self._last_energy_tick_ts or now` which treats
0.0 as falsy. Tests therefore seed `_last_energy_tick_ts` with a non-zero
value to get the intended dt_s.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml import coordinator as coord_mod
from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)

SEED_TS = 100.0  # non-zero seed so dt_s = now - SEED_TS


def _bare(detector_state: str = "idle") -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    det = MagicMock()
    det.state = detector_state
    c.detector = det
    c._last_energy_tick_ts = SEED_TS
    c._energy_acc = {
        "heating": {"th": 0.0, "el": 0.0},
        "dhw": {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    return c


def _acc(c: DaikinCycleMLCoordinator) -> dict[str, dict[str, float]]:
    return c._ensure_energy_acc()


# --- R286: skip idle/cooldown -----------------------------------------------


def test_r286_skip_when_detector_idle() -> None:
    c = _bare(detector_state="idle")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(2.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 30.0, mode="heating", power_w=500.0, cop=4.0)
    a = _acc(c)
    assert a["heating"]["el"] == 0.0
    assert a["heating"]["th"] == 0.0


def test_r286_skip_when_detector_cooldown() -> None:
    c = _bare(detector_state="cooldown")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(2.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 30.0, mode="heating", power_w=500.0, cop=4.0)
    a = _acc(c)
    assert a["heating"]["el"] == 0.0
    assert a["heating"]["th"] == 0.0


def test_r286_skip_standby_21w_over_1h() -> None:
    """Reproduces prod bug: 21 W standby must not enter energy accumulators."""
    c = _bare(detector_state="idle")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(0.1, "flow_dt")):
        for i in range(1, 121):  # 120 ticks x 30 s = 1 h
            c._tick_energy({}, now=SEED_TS + i * 30.0, mode="heating", power_w=21.0, cop=None)
    a = _acc(c)
    assert a["heating"]["el"] == 0.0
    assert a["heating"]["th"] == 0.0
    assert a["dhw"]["el"] == 0.0
    assert a["cooling"]["el"] == 0.0


# --- R287: no unknown-mode fallback -----------------------------------------


def test_r287_skip_unknown_mode_with_running_detector() -> None:
    c = _bare(detector_state="running")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(3.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 30.0, mode="unknown", power_w=600.0, cop=4.0)
    a = _acc(c)
    assert a["heating"]["el"] == 0.0
    assert a["heating"]["th"] == 0.0


def test_r287_skip_unknown_mode_with_idle_detector() -> None:
    c = _bare(detector_state="idle")
    c._tick_energy({}, now=SEED_TS + 30.0, mode="unknown", power_w=600.0, cop=4.0)
    a = _acc(c)
    assert a["heating"]["el"] == 0.0
    assert a["heating"]["th"] == 0.0


# --- Accumulation when compressor running -----------------------------------


def test_accumulate_heating_running() -> None:
    c = _bare(detector_state="running")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(5.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 30.0, mode="heating", power_w=1200.0, cop=4.16)
    a = _acc(c)
    assert a["heating"]["th"] == pytest.approx(5.0 * 30.0 / 3600.0)
    assert a["heating"]["el"] == pytest.approx(1.2 * 30.0 / 3600.0)
    assert a["dhw"]["th"] == 0.0
    assert a["cooling"]["th"] == 0.0


def test_accumulate_dhw_running() -> None:
    c = _bare(detector_state="running")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(3.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 30.0, mode="dhw", power_w=800.0, cop=3.75)
    a = _acc(c)
    assert a["dhw"]["th"] > 0
    assert a["dhw"]["el"] > 0
    assert a["heating"]["th"] == 0.0


def test_accumulate_cooling_running() -> None:
    c = _bare(detector_state="running")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(4.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 30.0, mode="cooling", power_w=900.0, cop=4.44)
    a = _acc(c)
    assert a["cooling"]["th"] > 0
    assert a["cooling"]["el"] > 0
    assert a["heating"]["th"] == 0.0


def test_cop_fallback_when_no_power_sensor() -> None:
    """power_w=None + cop=4.0, kw_th=4.0 -> kw_el = kw_th/cop = 1.0."""
    c = _bare(detector_state="running")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(4.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 30.0, mode="heating", power_w=None, cop=4.0)
    a = _acc(c)
    assert a["heating"]["th"] == pytest.approx(4.0 * 30.0 / 3600.0)
    assert a["heating"]["el"] == pytest.approx(1.0 * 30.0 / 3600.0)


# --- R286b: BUH-only fallback ----------------------------------------------


def test_buh_only_step1_counts_electrical_only() -> None:
    """BUH active without compressor and no thermal -> el only, no th."""
    c = _bare(detector_state="idle")
    attrs = {ATTR_BUH_STEP1: True, ATTR_BUH_STEP2: False}
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(None, "none")):
        c._tick_energy(attrs, now=SEED_TS + 30.0, mode="heating", power_w=2000.0, cop=None)
    a = _acc(c)
    assert a["heating"]["el"] == pytest.approx(2.0 * 30.0 / 3600.0)
    assert a["heating"]["th"] == 0.0


def test_buh_only_step2_counts() -> None:
    c = _bare(detector_state="idle")
    attrs = {ATTR_BUH_STEP1: False, ATTR_BUH_STEP2: True}
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(None, "none")):
        c._tick_energy(attrs, now=SEED_TS + 30.0, mode="heating", power_w=3000.0, cop=None)
    a = _acc(c)
    assert a["heating"]["el"] == pytest.approx(3.0 * 30.0 / 3600.0)


def test_buh_only_no_power_sensor_skipped() -> None:
    c = _bare(detector_state="idle")
    attrs = {ATTR_BUH_STEP1: True, ATTR_BUH_STEP2: False}
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(None, "none")):
        c._tick_energy(attrs, now=SEED_TS + 30.0, mode="heating", power_w=None, cop=None)
    a = _acc(c)
    assert a["heating"]["el"] == 0.0


def test_buh_step_values_must_be_true_not_truthy() -> None:
    """String "on" or 1 must NOT be treated as BUH active (strict identity)."""
    c = _bare(detector_state="idle")
    attrs = {ATTR_BUH_STEP1: 1, ATTR_BUH_STEP2: "on"}
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(None, "none")):
        c._tick_energy(attrs, now=SEED_TS + 30.0, mode="heating", power_w=2000.0, cop=None)
    a = _acc(c)
    assert a["heating"]["el"] == 0.0


# --- dt_s behavior ----------------------------------------------------------


def test_dt_s_zero_returns_early() -> None:
    """Same timestamp -> dt_s=0 -> no accumulation."""
    c = _bare(detector_state="running")
    # SEED_TS is set, use now == SEED_TS so dt_s == 0
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(5.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS, mode="heating", power_w=1200.0, cop=4.0)
    a = _acc(c)
    assert a["heating"]["th"] == 0.0


def test_dt_s_capped_at_300s() -> None:
    """Gap of 600 s -> capped at 300 s (R288: cap raised from 120 s)."""
    c = _bare(detector_state="running")
    with patch.object(coord_mod, "_compute_thermal_power_live", return_value=(5.0, "flow_dt")):
        c._tick_energy({}, now=SEED_TS + 600.0, mode="heating", power_w=1200.0, cop=4.0)
    a = _acc(c)
    assert a["heating"]["th"] == pytest.approx(5.0 * 300.0 / 3600.0)


# --- R288: dt_s cap 300s + warn >60s (energy) ------------------------------


def test_r288_gap_30s_no_warning_full_dt(caplog) -> None:
    import logging as _logging
    c = _bare(detector_state="running")
    with caplog.at_level(
        _logging.WARNING,
        logger="custom_components.daikin_cycle_ml.coordinator",
    ):
        with patch.object(
            coord_mod, "_compute_thermal_power_live", return_value=(5.0, "flow_dt")
        ):
            c._tick_energy({}, now=SEED_TS + 30.0, mode="heating",
                           power_w=1200.0, cop=4.0)
    assert not any("energy tick gap" in r.getMessage() for r in caplog.records)
    a = _acc(c)
    assert a["heating"]["th"] == pytest.approx(5.0 * 30.0 / 3600.0)


def test_r288_gap_90s_warns_full_dt(caplog) -> None:
    import logging as _logging
    c = _bare(detector_state="running")
    with caplog.at_level(
        _logging.WARNING,
        logger="custom_components.daikin_cycle_ml.coordinator",
    ):
        with patch.object(
            coord_mod, "_compute_thermal_power_live", return_value=(5.0, "flow_dt")
        ):
            c._tick_energy({}, now=SEED_TS + 90.0, mode="heating",
                           power_w=1200.0, cop=4.0)
    assert any("energy tick gap" in r.getMessage() for r in caplog.records)
    a = _acc(c)
    assert a["heating"]["th"] == pytest.approx(5.0 * 90.0 / 3600.0)


def test_r288_gap_400s_warns_and_caps_at_300(caplog) -> None:
    import logging as _logging
    c = _bare(detector_state="running")
    with caplog.at_level(
        _logging.WARNING,
        logger="custom_components.daikin_cycle_ml.coordinator",
    ):
        with patch.object(
            coord_mod, "_compute_thermal_power_live", return_value=(5.0, "flow_dt")
        ):
            c._tick_energy({}, now=SEED_TS + 400.0, mode="heating",
                           power_w=1200.0, cop=4.0)
    assert any("energy tick gap" in r.getMessage() for r in caplog.records)
    a = _acc(c)
    assert a["heating"]["th"] == pytest.approx(5.0 * 300.0 / 3600.0)


# --- R288b: same cap on BUH runtime accumulator ----------------------------


def _bare_runtime():
    c = _bare(detector_state="idle")
    c._last_runtime_tick_ts = SEED_TS
    c._buh_step1_s = 0.0
    c._buh_step2_s = 0.0
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._defrost_start_ts = None
    c._last_defrost_ts = None
    c._prev_defrost = False
    return c


def test_r288b_gap_30s_no_warning(caplog) -> None:
    import logging as _logging
    c = _bare_runtime()
    attrs = {ATTR_BUH_STEP1: True, ATTR_BUH_STEP2: False}
    with caplog.at_level(
        _logging.WARNING,
        logger="custom_components.daikin_cycle_ml.coordinator",
    ):
        c._tick_buh_and_defrost(attrs, now=SEED_TS + 30.0)
    assert not any("buh tick gap" in r.getMessage() for r in caplog.records)
    assert c._buh_step1_s == pytest.approx(30.0)


def test_r288b_gap_90s_warns_full_dt(caplog) -> None:
    import logging as _logging
    c = _bare_runtime()
    attrs = {ATTR_BUH_STEP1: True, ATTR_BUH_STEP2: False}
    with caplog.at_level(
        _logging.WARNING,
        logger="custom_components.daikin_cycle_ml.coordinator",
    ):
        c._tick_buh_and_defrost(attrs, now=SEED_TS + 90.0)
    assert any("buh tick gap" in r.getMessage() for r in caplog.records)
    assert c._buh_step1_s == pytest.approx(90.0)


def test_r288b_gap_400s_warns_and_caps_at_300(caplog) -> None:
    import logging as _logging
    c = _bare_runtime()
    attrs = {ATTR_BUH_STEP1: True, ATTR_BUH_STEP2: False}
    with caplog.at_level(
        _logging.WARNING,
        logger="custom_components.daikin_cycle_ml.coordinator",
    ):
        c._tick_buh_and_defrost(attrs, now=SEED_TS + 400.0)
    assert any("buh tick gap" in r.getMessage() for r in caplog.records)
    assert c._buh_step1_s == pytest.approx(300.0)
