# Regression fence: v0.6.0 alert context real values.
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def test_v0_6_0_alert_context_formats_real_values():
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.states = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.options = {}
    c.entry = MagicMock()
    c.entry.entry_id = 'test'
    c.data = MagicMock()
    c.data.mode = 'heating'
    c.data.attributes = {}
    c.store = MagicMock()
    c.store.last_cycle = MagicMock(return_value=None)
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_today = MagicMock(return_value=[])
    c.store.off_time_since_last = MagicMock(return_value=None)
    c.db = MagicMock()
    c._setpoint_history = deque()
    c._last_setpoint = None
    c._last_alert_sent = {}

    snap = SimpleNamespace(
        mode='heating',
        attributes={'outdoor_temp': 5.5, 'flow_lmin': 12.3},
        advice=[], anomaly=None, last_record=None,
    )
    ctx = c._build_alert_context(snap)
    assert ctx['pendulum']['outdoor'] == '5.5'
    assert ctx['pendulum']['outdoor'] != '?'
