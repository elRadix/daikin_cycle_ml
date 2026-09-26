"""Batch 28 tests: wire-up of custom_attribute_map, selected_attributes,
comfort_min_c, dhw_pendulum_cycles_per_hour."""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.const import (
    DEFAULT_COMFORT_MIN_C,
    DEFAULT_DHW_PENDULUM_CPH,
    DEFAULT_RETENTION_ENABLED,
    DEFAULT_CYCLE_RETENTION_DAYS,
    DEFAULT_ALERT_RETENTION_DAYS,
    DEFAULT_VACUUM_ENABLED,
    REQUIRED_ATTRIBUTES,
    ATTR_INV_FREQUENCY_RPS,
)
from custom_components.daikin_cycle_ml.engine import attribute_reader as ar_mod


def _state(attrs):
    s = MagicMock()
    s.attributes = attrs
    return s


def test_read_basic_no_options():
    s = _state({ATTR_INV_FREQUENCY_RPS: "30.0"})
    out = ar_mod.read(s)
    assert out[ATTR_INV_FREQUENCY_RPS] == 30.0


def test_read_custom_map_renames_actual_to_standard():
    s = _state({"my_rps": "40.0", "other": 1})
    out = ar_mod.read(s, custom_map={ATTR_INV_FREQUENCY_RPS: "my_rps"})
    assert ATTR_INV_FREQUENCY_RPS in out
    assert out[ATTR_INV_FREQUENCY_RPS] == 40.0
    assert "my_rps" not in out
    assert out["other"] == 1.0


def test_read_custom_map_no_op_when_missing():
    s = _state({ATTR_INV_FREQUENCY_RPS: "30.0"})
    out = ar_mod.read(s, custom_map={ATTR_INV_FREQUENCY_RPS: "nonexistent"})
    # Fallback: original key retained
    assert out[ATTR_INV_FREQUENCY_RPS] == 30.0


def test_read_selected_filters_non_required():
    s = _state({
        ATTR_INV_FREQUENCY_RPS: "30.0",
        "some_optional": 5.0,
    })
    out = ar_mod.read(s, selected=[])
    # REQUIRED_ATTRIBUTES always survive
    assert ATTR_INV_FREQUENCY_RPS in out
    # non-required filtered out (empty selection)
    assert "some_optional" not in out


def test_read_selected_keeps_listed():
    s = _state({
        ATTR_INV_FREQUENCY_RPS: "30.0",
        "extra_attr": 5.0,
    })
    out = ar_mod.read(s, selected=["extra_attr"])
    assert ATTR_INV_FREQUENCY_RPS in out
    assert out["extra_attr"] == 5.0


def test_read_selected_none_means_no_filter():
    s = _state({ATTR_INV_FREQUENCY_RPS: "30.0", "extra": 5.0})
    out = ar_mod.read(s, selected=None)
    assert "extra" in out


def test_comfort_min_uses_default_constant():
    """coordinator._async_refresh_stooklijn path uses DEFAULT_COMFORT_MIN_C."""
    from custom_components.daikin_cycle_ml import coordinator as co_mod
    src = inspect.getsource(co_mod)
    assert "DEFAULT_COMFORT_MIN_C" in src
    assert DEFAULT_COMFORT_MIN_C == 20.0


def test_maintenance_constants_exported():
    assert DEFAULT_RETENTION_ENABLED is True
    assert DEFAULT_CYCLE_RETENTION_DAYS == 90
    assert DEFAULT_ALERT_RETENTION_DAYS == 30
    assert DEFAULT_VACUUM_ENABLED is True


def test_dhw_pendulum_default():
    assert DEFAULT_DHW_PENDULUM_CPH == 3


def test_config_flow_options_has_dhw_pendulum():
    from custom_components.daikin_cycle_ml.config_flow import (
        DaikinCycleMLOptionsFlow,
    )
    src = inspect.getsource(DaikinCycleMLOptionsFlow.async_step_pendulum)
    assert "dhw_pendulum_cycles_per_hour" in src


def test_config_flow_options_maintenance_uses_defaults():
    from custom_components.daikin_cycle_ml.config_flow import (
        DaikinCycleMLOptionsFlow,
    )
    src = inspect.getsource(DaikinCycleMLOptionsFlow.async_step_maintenance)
    assert "DEFAULT_RETENTION_ENABLED" in src
    assert "DEFAULT_CYCLE_RETENTION_DAYS" in src


def test_dead_constants_removed():
    from custom_components.daikin_cycle_ml import const as c
    assert not hasattr(c, "DEFAULT_TIMER_RECONCILE_ON_START")
    assert not hasattr(c, "DEFAULT_ALERT_GROUP_ENABLED")
