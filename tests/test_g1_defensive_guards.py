"""v1.14.0: defensive guards — bare coordinator fixtures + cycles_today."""
import pytest
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _bare():
    return object.__new__(DaikinCycleMLCoordinator)


def test_read_power_without_power_sensor_attr():
    c = _bare()
    assert c._read_power() is None


def test_read_power_w_without_power_sensor_attr():
    c = _bare()
    assert c._read_power_w() is None


def test_errors_total_class_default():
    assert DaikinCycleMLCoordinator._errors_total == 0


def test_cycles_today_skips_future_start_ts():
    s = CycleStore()
    import time
    now = time.time()
    s.add_cycle({"start_ts": now - 60, "end_ts": now, "duration_s": 60,
                 "mode": "heating", "quality_score": 80})
    s.add_cycle({"start_ts": now + 3600, "end_ts": now + 3660, "duration_s": 60,
                 "mode": "heating", "quality_score": 80})
    today = s.cycles_today(now)
    assert len(today) == 1, f"expected 1 past cycle, got {len(today)}"


def test_cycles_today_60s_tolerance():
    s = CycleStore()
    import time
    now = time.time()
    s.add_cycle({"start_ts": now + 30, "end_ts": now + 90, "duration_s": 60,
                 "mode": "heating", "quality_score": 80})
    today = s.cycles_today(now)
    assert len(today) == 1, "30s future within tolerance should pass"


def test_cycles_today_non_numeric_start_ts_skipped():
    s = CycleStore()
    import time
    now = time.time()
    s.add_cycle({"start_ts": "invalid", "duration_s": 60, "mode": "heating"})
    s.add_cycle({"start_ts": None, "duration_s": 60, "mode": "heating"})
    s.add_cycle({"start_ts": now - 60, "duration_s": 60, "mode": "heating"})
    assert len(s.cycles_today(now)) == 1
