"""v1.9.0 PR C hotfix — Test-all emitter uses shared delta.

Ensures _emit_all_test_alerts renders COP_LOW_THRESHOLD - TEST_ALERT_DELTA
for the cop_low demo, not a hardcoded literal.

Refs #66.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml import const
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare(options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = dict(options or {})
    c.data = MagicMock()
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._setpoint_history = []
    c._emit_alert = AsyncMock()
    c._build_alert_context = MagicMock(return_value={})
    return c


def test_emit_all_uses_shared_delta_for_cop_low():
    c = _bare()
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    expected = f"{const.COP_LOW_THRESHOLD - const.TEST_ALERT_DELTA:.2f}"
    assert expected in out, f"expected {expected} in test-all output"


def test_emit_all_cop_low_demo_below_threshold():
    c = _bare()
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    cop_val = const.COP_LOW_THRESHOLD - const.TEST_ALERT_DELTA
    assert cop_val < const.COP_LOW_THRESHOLD
    assert f"{cop_val:.2f}" in out
