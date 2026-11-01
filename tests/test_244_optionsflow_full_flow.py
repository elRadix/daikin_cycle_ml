"""#244 — Full-flow invariant tests for OptionsFlow chain semantics.

Six layers (each class = one concern):
  TestChain       — step sequences via repeated _save (Hafid's scenario)
  TestCrossStep   — parametrized: every non-device step preserves sensors
  TestOwnership   — steps only mutate their own keys
  TestReconfigure — reconfigure does not route through OptionsFlow._save
  TestIdempotency — save twice / empty submit
  TestWizard      — static: no wizard step replaces self._data in place
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

import pytest

from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLConfigFlow as CF,
)
from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLOptionsFlow as OF,
)

_SENSOR_VALUES: dict[str, str] = {
    "power_sensor_entity": "sensor.P",
    "cop_sensor_entity": "sensor.C",
    "indoor_temp_sensor": "sensor.I",
}
_SENSOR_KEYS = tuple(_SENSOR_VALUES)

_STEP_INPUTS: dict[str, dict[str, Any]] = {
    "cop_calc": {"electrical": {"supply_phases": "3", "buh_step1_kw": 3.0}},
    "pendulum": {"pendulum_cycles_per_hour": 5.0, "pendulum_cycles_per_day": 50.0},
    "quality_ml": {"good_run_threshold_min": 50.0, "target_cycles_per_day": 10.0},
    "notifications": {"notify_service": "notify.mobile", "notification_language": "en"},
    "notifications_delivery": {"persistent_enabled": False, "notify_emoji_enabled": True},
    "notifications_quiet_hours": {"quiet_hours_enabled": True, "quiet_hours_start": "23:00"},
    "notifications_content": {"status_update_enabled": True, "action_advice_enabled": False},
    "notifications_enabled": {"alert_enabled_short_run": True},
    "notifications_dedup": {"alert_agg_short_run_min": 45.0},
    "advanced": {"retention_enabled": False, "vacuum_enabled": True},
}


class _Entry:
    def __init__(self, options: dict[str, Any]) -> None:
        self.options = dict(options)
        self.data: dict[str, Any] = {}


class _Flow(OF):
    def __init__(self, entry: _Entry) -> None:
        self._entry = entry

    @property
    def config_entry(self) -> _Entry:  # type: ignore[override]
        return self._entry

    def async_create_entry(self, data: dict[str, Any]) -> Any:  # type: ignore[override]
        self._entry.options = dict(data)
        return ("created", data)


def _run_save(
    existing: dict[str, Any],
    user_input: dict[str, Any],
    *,
    sensor_step: bool = False,
) -> dict[str, Any]:
    return _Flow(_Entry(existing))._save(user_input, sensor_step=sensor_step)[1]


class TestChain:
    """Hafid's scenario: device → notifications → advanced, sensors preserved."""

    def test_device_then_notifications_then_advanced(self) -> None:
        opts: dict[str, Any] = {}
        opts = _run_save(
            opts,
            {"sensors": dict(_SENSOR_VALUES),
             "detection": {"compressor_rps_threshold": 2.5}},
            sensor_step=True,
        )
        assert opts["power_sensor_entity"] == "sensor.P"

        opts = _run_save(opts, _STEP_INPUTS["notifications"])
        assert opts["power_sensor_entity"] == "sensor.P"
        assert opts["notify_service"] == "notify.mobile"

        opts = _run_save(opts, _STEP_INPUTS["advanced"])
        assert opts["power_sensor_entity"] == "sensor.P"
        assert opts["notify_service"] == "notify.mobile"
        assert opts["retention_enabled"] is False

    def test_full_chain_preserves_all_sensors(self) -> None:
        opts: dict[str, Any] = dict(_SENSOR_VALUES)
        for step_input in _STEP_INPUTS.values():
            opts = _run_save(opts, step_input)
        for k, v in _SENSOR_VALUES.items():
            assert opts[k] == v, f"{k} wiped after full chain of 10 steps"


class TestCrossStep:
    """Every non-device step must leave sensor mappings untouched."""

    @pytest.mark.parametrize("step", sorted(_STEP_INPUTS))
    def test_non_device_step_preserves_sensors(self, step: str) -> None:
        opts = _run_save(_SENSOR_VALUES, _STEP_INPUTS[step])
        for k, v in _SENSOR_VALUES.items():
            assert opts[k] == v, f"{step} wiped {k}"

    @pytest.mark.parametrize("step", sorted(_STEP_INPUTS))
    def test_non_device_step_no_none_injection(self, step: str) -> None:
        """Sensors absent in existing + step input → must stay absent."""
        opts = _run_save({}, _STEP_INPUTS[step])
        for k in _SENSOR_KEYS:
            assert k not in opts, f"{step} injected None for {k}"


class TestOwnership:
    """Each step should only mutate its own keys; others survive unchanged."""

    def test_non_device_steps_preserve_unrelated_keys(self) -> None:
        seed = {"unrelated_from_other_step": 42, "shared_opt": "old"}
        for step_input in _STEP_INPUTS.values():
            result = _run_save(seed, step_input)
            assert result["unrelated_from_other_step"] == 42
            assert result["shared_opt"] == "old"

    def test_device_step_preserves_unrelated_keys(self) -> None:
        seed = {"notify_service": "notify.X", "retention_enabled": True}
        result = _run_save(
            seed,
            {"sensors": {"power_sensor_entity": "sensor.P"}},
            sensor_step=True,
        )
        assert result["notify_service"] == "notify.X"
        assert result["retention_enabled"] is True
        assert result["power_sensor_entity"] == "sensor.P"


class TestReconfigure:
    """Reconfigure must NOT route through OptionsFlow._save.

    Reconfigure uses async_update_and_abort(data_updates=..., options=...).
    If someone ever routes it through _save(), the sensor_step=False default
    would preserve stale options instead of replacing them on reconfigure.
    This static check guards that boundary.
    """

    def test_reconfigure_does_not_call_save(self) -> None:
        for name in ("async_step_reconfigure_basic", "async_step_reconfigure_full"):
            if not hasattr(CF, name):
                continue
            src = inspect.getsource(getattr(CF, name))
            assert "self._save" not in src, (
                f"{name} routes through OptionsFlow._save; "
                "reconfigure must use async_update_and_abort directly"
            )


class TestIdempotency:
    """Repeated saves with same input must produce identical options."""

    def test_save_twice_same_input(self) -> None:
        seed = dict(_SENSOR_VALUES)
        once = _run_save(seed, _STEP_INPUTS["notifications"])
        twice = _run_save(once, _STEP_INPUTS["notifications"])
        assert once == twice

    def test_empty_submit_preserves_everything(self) -> None:
        seed = {**_SENSOR_VALUES,
                "notify_service": "notify.X",
                "retention_enabled": True}
        result = _run_save(seed, {})
        for k, v in seed.items():
            assert result[k] == v, f"empty submit wiped {k}"

    def test_empty_submit_on_empty_existing(self) -> None:
        """Fresh install + empty submit → empty dict (no phantom None keys)."""
        assert _run_save({}, {}) == {}


class TestWizard:
    """Initial ConfigFlow: self._data must accumulate across 14 steps.

    Any step that does `self._data = ...` (assignment) instead of
    `self._data.update(...)` or `self._data[k] = v` wipes prior steps.
    Static AST check — no schema knowledge required.
    """

    _EXEMPT_STEPS: frozenset[str] = frozenset({
        "async_step_reconfigure",
        "async_step_reconfigure_basic",
        "async_step_reconfigure_full",
    })

    def test_no_wizard_step_replaces_data_dict(self) -> None:
        violations: list[str] = []
        for name in dir(CF):
            if not name.startswith("async_step_") or name in self._EXEMPT_STEPS:
                continue
            method = getattr(CF, name)
            try:
                src = inspect.getsource(method)
            except (OSError, TypeError):
                continue
            src = textwrap.dedent(src)
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                        and target.attr == "_data"
                    ):
                        violations.append(name)
                        break
        assert not violations, (
            "steps replace self._data in place, wiping accumulated wizard data: "
            f"{sorted(set(violations))}. Use .update() or [k]=v instead."
        )
