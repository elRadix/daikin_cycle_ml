"""Comprehensive tests for v1.22.5 DHW tail alert suppression (tHyEstes issue)."""
import time
from unittest.mock import MagicMock
import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.engine.status_report import ALERT_ADVICE


def _mock_coord(store):
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    coord.options = {
        "short_run_threshold_min": 20,
        "short_off_threshold_min": 5,
        "pendulum_cycles_per_hour": 4,
        "pendulum_cycles_per_day": 40,
        "short_cycling_min_cycles": 3,
        "short_cycling_window_min": 60,
    }
    coord._effective_threshold = lambda key, default: default
    coord._dhw_gap_threshold_s = 900.0
    coord.store = store
    return coord


def _mock_store(last, cycles=None):
    class MockStore:
        def last_cycle(self):
            return last

        def cycles(self):
            return cycles or []

        def cycles_in_window_mode(self, *args, **kwargs):
            return 0

        def count_short_in_window_mode(self, *args, **kwargs):
            return 0

        def non_transient_today(self, *args, **kwargs):
            return []

        def record_short_run(self):
            pass

    return MockStore()


@pytest.mark.parametrize(
    "is_dhw_tail_flag, prev_mode, gap_s, expected_result",
    [
        # 1. Directe flag (DB heeft het al gezet)
        (1, "heating", 0, False),
        # 2. Geen flag, maar gap < 900s na DHW
        (0, "dhw", 300, False),
        # 3. Geen flag, gap >= 900s na DHW (mag niet onderdrukken)
        (0, "dhw", 1000, True),
        # 4. Geen flag, vorige cyclus was geen DHW
        (0, "heating", 300, True),
        # 5. Slechts 1 cyclus in de store (edge case)
        (0, "dhw", 300, True),  # word overschreven in de test zelf
    ],
)
def test_alert_binary_states_dhw_tail_logic(
    is_dhw_tail_flag, prev_mode, gap_s, expected_result
):
    """Test de DHW tail detectie in _alert_binary_states."""
    now = time.time()

    last = {
        "duration_s": 240,  # 4 min (short run)
        "is_transient": 0,
        "is_dhw_tail": is_dhw_tail_flag,
        "start_ts": now,
        "end_ts": now + 240,
        "off_s": 60,  # Altijd een short off (60 < 300)
    }

    # De gap is exact de tijd tussen prev_cycle.end_ts en last.start_ts
    prev_cycle = {"mode": prev_mode, "end_ts": now - gap_s, "duration_s": 1800}
    cycles_list = [prev_cycle, last]

    # Edge case: for the last param, make cycles list have only 1 item
    if is_dhw_tail_flag == 0 and prev_mode == "dhw" and gap_s == 300 and expected_result is True:
        cycles_list = [last]

    store = _mock_store(last, cycles_list)
    coord = _mock_coord(store)
    snap = MagicMock()
    snap.anomaly = None

    result = coord._alert_binary_states(snap)
    assert result["short_run"] is expected_result, f"Failed on case: {is_dhw_tail_flag}, {prev_mode}, {gap_s}"
    # short_off should follow the same suppression logic
    assert result["short_off"] is expected_result


def test_status_report_advice_texts():
    """Verify that the incorrect Daikin advice has been replaced."""
    en_advice = ALERT_ADVICE["en"]["short_run"]
    assert "raise minimum run time" not in en_advice.lower()
    assert "lower the lwt setpoint" not in en_advice.lower()
    assert "pump speed" in en_advice.lower()
    assert "overshoot" in en_advice.lower()

    # Controleren of short_cycling_pattern ook is aangepast
    sc_advice = ALERT_ADVICE["en"]["short_cycling_pattern"]
    assert "raise minimum run time" not in sc_advice.lower()
    assert "overshoot" in sc_advice.lower()
