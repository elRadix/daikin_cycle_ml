"""v1.19.8 #source_stale_fp: threshold tolerance test.

Observed incident (prod-1, 2026-11-04 13:58:57):
  - Alert fired at age=62.5s (threshold=60s)
  - Recorder proved source alive (30s cadence, no gap)
  - FP caused by transient hass.states.get() returning None
    (or tick delay), NOT by source outage

Fix: raise SOURCE_STALE_FACTOR 2.0 -> 4.0 (60s -> 120s).

R617: all imports at module level — phcc resets sys.path during
hass fixture setup, function-level imports fail with ModuleNotFoundError.
"""
from custom_components.daikin_cycle_ml.binary_sensor import (
    SOURCE_STALE_FACTOR,
)
from custom_components.daikin_cycle_ml.const import (
    UPDATE_INTERVAL_SECONDS,
)


def test_source_stale_factor_is_4():
    """v1.19.8: factor raised to tolerate single missed tick."""
    assert SOURCE_STALE_FACTOR == 4.0


def test_source_stale_threshold_is_120s():
    """4.0 * 30s = 120s threshold — matches user expectation."""
    assert SOURCE_STALE_FACTOR * UPDATE_INTERVAL_SECONDS == 120.0


def test_observed_fp_age_62_5_does_not_trigger():
    """Direct regression test for prod-1 2026-11-04 incident.

    age=62.5s was FP under old threshold (60s). Under new
    threshold (120s) it must not trigger.
    """
    threshold = SOURCE_STALE_FACTOR * UPDATE_INTERVAL_SECONDS
    age_s = 62.5
    assert age_s < threshold, (
        f"62.5s stale should NOT trigger at threshold={threshold}s"
    )
