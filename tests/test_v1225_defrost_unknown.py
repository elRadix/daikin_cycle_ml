"""Red test for Issue #308: Real coordinator method fails on unknown/unavailable."""
import pytest
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.const import (
    ATTR_DEFROST_OPERATION,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ENERGY_DT_CAP_S,
)

def _mock_coord():
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    coord._defrost_count_today = 0
    coord._prev_defrost = False
    coord._defrost_start_ts = None
    coord._defrost_duration_s = 0.0
    coord._defrost_prior_s = None
    coord._last_defrost_ts = None
    coord._buh_step1_s = 0.0
    coord._buh_step2_s = 0.0
    coord._last_runtime_tick_ts = 1000.0
    return coord

def test_real_tick_buh_and_defrost_unknown_sequence():
    """A defrost interrupted by 'unknown' must NOT be double-counted."""
    coord = _mock_coord()

    # 1. Start defrost (on) - tijd is nu 1010.0 (dt=10s)
    coord._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: "on", ATTR_BUH_STEP1: "off"}, 1010.0)
    assert coord._defrost_count_today == 1, "First 'on' should count"
    assert coord._prev_defrost is True, "State should be ON"
    assert coord._buh_step1_s == 0.0, "BUH should be off"

    # 2. Sensor drops to unknown (mid-defrost) - tijd is nu 1110.0 (dt=100s)
    coord._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: "unknown", ATTR_BUH_STEP1: "unknown"}, 1110.0)
    assert coord._defrost_count_today == 1, "Unknown should not increment count"
    assert coord._prev_defrost is True, "Unknown must preserve the active defrost state (NOT turn off)"
    assert coord._buh_step1_s == 0.0, "BUH unknown should not accumulate"

    # 3. Sensor recovers to 'on' (still the same defrost) - tijd is nu 1210.0 (dt=100s)
    coord._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: "on", ATTR_BUH_STEP1: "off"}, 1210.0)
    assert coord._defrost_count_today == 1, "Recovery to 'on' should NOT double-count"

    # 4. Defrost ends (off) - tijd is nu 1310.0 (dt=100s)
    # BUH step 1 wordt nu 'on', dus er moet 100s geaccumuleerd worden.
    coord._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: "off", ATTR_BUH_STEP1: "on"}, 1310.0)
    assert coord._defrost_count_today == 1, "Final 'off' should close the defrost"
    assert coord._prev_defrost is False, "State should be OFF"
    assert coord._buh_step1_s == 100.0, "BUH should accumulate 100s"
