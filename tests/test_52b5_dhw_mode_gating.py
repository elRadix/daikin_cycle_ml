"""Batch 52b5: DHW-mode gating for short_run/short_off/pendulum."""
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import binary_sensor as bs


def _mk_coord(options=None, last_cycle=None, off_time=0,
              cycles_hour=0, cycles_hour_dhw=0, cycles_today=None):
    c = MagicMock()
    c.options = options or {}
    c.store = MagicMock()
    c.store.last_cycle = MagicMock(return_value=last_cycle)
    c.store.off_time_since_last = MagicMock(return_value=off_time)
    c.store.cycles_in_window = MagicMock(return_value=cycles_hour)
    c.store.cycles_in_window_mode = MagicMock(return_value=cycles_hour_dhw)
    c.store.cycles_today = MagicMock(return_value=cycles_today or [])
    return c


def _mk_snap(mode="heating"):
    s = MagicMock()
    s.mode = mode
    return s


def test_short_run_skips_dhw_cycle():
    c = _mk_coord(last_cycle={"duration_s": 180, "mode": "dhw"})
    s = _mk_snap(mode="dhw")
    assert bs._is_short_run(s, c) is False


def test_short_run_skips_dhw_uppercase():
    c = _mk_coord(last_cycle={"duration_s": 60, "mode": "DHW"})
    s = _mk_snap(mode="dhw")
    assert bs._is_short_run(s, c) is False


def test_short_run_fires_for_heating():
    c = _mk_coord(
        options={"short_run_threshold_min": 20},
        last_cycle={"duration_s": 180, "mode": "heating"},
    )
    s = _mk_snap(mode="heating")
    assert bs._is_short_run(s, c) is True


def test_short_run_fires_for_unknown_mode():
    c = _mk_coord(
        options={"short_run_threshold_min": 20},
        last_cycle={"duration_s": 180, "mode": "unknown"},
    )
    s = _mk_snap(mode="unknown")
    assert bs._is_short_run(s, c) is True


def test_short_off_skips_dhw_current():
    c = _mk_coord(last_cycle={"duration_s": 300, "mode": "heating"},
                  off_time=60)
    s = _mk_snap(mode="dhw")
    assert bs._is_short_off(s, c) is False


def test_short_off_skips_dhw_last():
    c = _mk_coord(last_cycle={"duration_s": 300, "mode": "dhw"}, off_time=60)
    s = _mk_snap(mode="heating")
    assert bs._is_short_off(s, c) is False


def test_short_off_fires_heating():
    c = _mk_coord(
        options={"short_off_threshold_min": 5},
        last_cycle={"duration_s": 1800, "mode": "heating"},
        off_time=60,
    )
    s = _mk_snap(mode="heating")
    assert bs._is_short_off(s, c) is True


def test_pendulum_hourly_excludes_dhw():
    c = _mk_coord(
        options={"pendulum_cycles_per_hour": 4},
        cycles_hour=6,
        cycles_hour_dhw=6,
    )
    s = _mk_snap()
    assert bs._is_pendulum_hourly(s, c) is False


def test_pendulum_hourly_counts_heating_only():
    c = _mk_coord(
        options={"pendulum_cycles_per_hour": 4},
        cycles_hour=6,
        cycles_hour_dhw=1,
    )
    s = _mk_snap()
    assert bs._is_pendulum_hourly(s, c) is True


def test_pendulum_hourly_no_dhw_unchanged():
    c = _mk_coord(
        options={"pendulum_cycles_per_hour": 4},
        cycles_hour=5,
        cycles_hour_dhw=0,
    )
    s = _mk_snap()
    assert bs._is_pendulum_hourly(s, c) is True
