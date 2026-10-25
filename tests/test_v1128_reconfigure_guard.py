"""v1.12.8 hotfix - reconfigure guard for offline/empty source.

Bug: reconfigure showed 'missing 12 required attributes' when source
was momentarily unavailable (attrs = {}). Root cause: missing_required
called without checking state.state or len(attributes).

New guards in async_step_reconfigure_basic:
- state.state in ('unavailable','unknown') -> source_offline
- state.attributes empty (state Online) -> source_empty
- else -> existing missing_attributes
"""
from __future__ import annotations
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLConfigFlow,
)


def _make_state(state_str, attrs):
    st = MagicMock()
    st.state = state_str
    st.attributes = attrs if attrs is not None else {}
    st.last_changed = "2026-10-25T21:01:18Z"
    st.last_updated = "2026-10-25T21:01:18Z"
    return st


def _make_flow(state):
    flow = DaikinCycleMLConfigFlow()
    flow.hass = MagicMock()
    flow.hass.states.get = MagicMock(return_value=state)
    flow._get_reconfigure_entry = MagicMock(
        return_value=MagicMock(
            entry_id="test-entry",
            data={"source_sensor": "sensor.althermasensors"},
        )
    )
    flow.async_show_form = MagicMock(
        side_effect=lambda **kw: {
            "type": "form",
            "errors": dict(kw.get("errors") or {}),
        }
    )
    return flow


@pytest.mark.asyncio
async def test_reconfigure_unavailable_returns_source_offline():
    state = _make_state("unavailable", {})
    flow = _make_flow(state)
    result = await flow.async_step_reconfigure_basic(
        user_input={"source_sensor": "sensor.althermasensors"},
    )
    assert result["errors"]["source_sensor"] == "source_offline"


@pytest.mark.asyncio
async def test_reconfigure_empty_attrs_returns_source_empty():
    state = _make_state("Online", {})
    flow = _make_flow(state)
    result = await flow.async_step_reconfigure_basic(
        user_input={"source_sensor": "sensor.althermasensors"},
    )
    assert result["errors"]["source_sensor"] == "source_empty"


@pytest.mark.asyncio
async def test_reconfigure_partial_attrs_returns_missing_attributes():
    partial = {
        "Outdoor air temp.(R1T)": 10.3,
        "Inlet water temp.(R4T)": 24,
        "DHW tank temp. (R5T)": 43.7,
    }
    state = _make_state("Online", partial)
    flow = _make_flow(state)
    result = await flow.async_step_reconfigure_basic(
        user_input={"source_sensor": "sensor.althermasensors"},
    )
    assert result["errors"]["source_sensor"] == "missing_attributes"
