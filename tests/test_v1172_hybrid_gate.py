"""v1.17.2: hybrid indicators gated on is_hybrid (diagnostics leak fix)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)

_COORD_MOD = "custom_components.daikin_cycle_ml.coordinator"


def _bare(model: str = "epra12eav3") -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=MagicMock())
    c.source_entity = "sensor.test_source"
    c.options = {}
    c.entry = MagicMock()
    c.entry.data = {"model": model}
    c.store = MagicMock()
    c.store.daily_reset_if_needed = MagicMock(return_value=False)
    c.detector = MagicMock()
    c.detector.state = "running"
    c.detector.snapshot = MagicMock(
        return_value={"mode": "heating", "start_ts": 1700000000.0}
    )
    c.detector.update = MagicMock(return_value=None)
    c.db = None
    c._runtime_day_key = ""
    c._energy_day_key = ""
    c._track_setpoint = MagicMock()
    c._read_power_w = MagicMock(return_value=1500.0)
    c._read_cop = MagicMock(return_value=3.5)
    c._compute_setpoint_oscillating = MagicMock(return_value=False)
    c._accumulate_cycle_samples = MagicMock()
    c._process_new_cycle = AsyncMock(return_value=None)
    c._tick_buh_and_defrost = MagicMock()
    c._tick_energy = MagicMock()
    c._maybe_persist_accumulators = AsyncMock(return_value=None)
    c._maybe_reset_daily_accumulators = MagicMock()
    # Short-circuit calls after the hybrid block
    c._maybe_collect_cop_sample = AsyncMock(return_value=None)
    c._refresh_cop_today = AsyncMock(return_value=None)
    c._maybe_refresh_stooklijn = AsyncMock(return_value=None)
    c._refresh_7d_rollups = AsyncMock(return_value=None)
    c._async_dispatch_alerts = AsyncMock(return_value=None)
    c._async_check_repairs = AsyncMock(return_value=None)
    return c


# ESPAltherma v2 devices occasionally publish hybrid-only attributes
# even on non-hybrid models (template drift). Simulate that here.
_LEAKED_ATTRS = {
    "Hybrid Op. Mode": "H/P only",
    "INV frequency 2 (rps)": 8.0,
    "BE COP": 1.2,
    "Operation Mode": "Heating",
}


@pytest.mark.asyncio
async def test_hybrid_indicators_gated_on_non_hybrid(monkeypatch):
    """Non-EVLQ + leaked hybrid attrs -> hybrid-only fields must be empty/None."""
    c = _bare(model="epra12eav3")
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: dict(_LEAKED_ATTRS))
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda a: [])
    snap = await c._async_update_data()
    assert snap.is_hybrid is False
    # v1.17.2: no leak
    assert snap.hybrid_mode == ""
    assert snap.inv_freq_secondary is None
    assert snap.boiler_efficiency_cop is None


@pytest.mark.asyncio
async def test_hybrid_indicators_populated_on_hybrid(monkeypatch):
    """EVLQ + hybrid attrs -> hybrid-only fields populated correctly."""
    c = _bare(model="evlq05cv3")
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: dict(_LEAKED_ATTRS))
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda a: [])
    snap = await c._async_update_data()
    assert snap.is_hybrid is True
    assert snap.hybrid_mode == "H/P only"
    assert snap.inv_freq_secondary == 8.0
    assert snap.boiler_efficiency_cop == 1.2
