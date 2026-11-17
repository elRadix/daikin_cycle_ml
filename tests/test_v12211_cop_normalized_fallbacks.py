"""v1.22.11 #388: cop_normalized_a7w35 null despite valid inputs.

Prod-1 2026-11-17: cop_normalized_a7w35=null met LWT=28.6°C,
T_out=8°C, model=epra12eav3, snap.cop≈6.1. De caller in
_async_update_data leest lwt_now uit _stooklijn_cache (None bij
buh_active/dhw_active) en cop_meas uit snap.cop (None bij
heat_unknown/no_dt). Beide hebben raw-attr fallback (R1T LWT,
Stats: COP estimated) die altijd aanwezig is.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _coord():
    c = object.__new__(DaikinCycleMLCoordinator)
    c.entry = MagicMock()
    c.entry.data = {"model": "epra12eav3"}
    c.entry.entry_id = "test"
    c._datasheet_user_loaded = True
    c._datasheet_defaults = None
    c._datasheet_cache = {}
    c._stooklijn_cache = {}
    c._datasheet_user = {}
    c._datasheet_merged = {}
    return c


def test_lwt_fallback_from_raw_attr():
    c = _coord()
    c._stooklijn_cache = {"huidige_lwt": None}
    snap = SimpleNamespace(attrs={"Leaving water temp. before BUH (R1T)": 28.6})
    assert c._resolve_lwt_for_datasheet(snap) == 28.6


def test_lwt_prefers_cache():
    c = _coord()
    c._stooklijn_cache = {"huidige_lwt": 31.4}
    snap = SimpleNamespace(attrs={"Leaving water temp. before BUH (R1T)": 28.6})
    assert c._resolve_lwt_for_datasheet(snap) == 31.4


def test_lwt_none_when_both_missing():
    c = _coord()
    c._stooklijn_cache = {"huidige_lwt": None}
    assert c._resolve_lwt_for_datasheet(SimpleNamespace(attrs={})) is None


def test_cop_fallback_from_stats():
    c = _coord()
    snap = SimpleNamespace(cop=None, attrs={"Stats: COP estimated": 6.02})
    assert c._resolve_cop_for_datasheet(snap) == 6.02


def test_cop_prefers_snap():
    c = _coord()
    snap = SimpleNamespace(cop=6.13, attrs={"Stats: COP estimated": 6.02})
    assert c._resolve_cop_for_datasheet(snap) == 6.13


@pytest.mark.asyncio
async def test_refresh_uses_fallbacks_end_to_end():
    from custom_components.daikin_cycle_ml.engine.model_datasheets import (
        load_bundled,
    )
    c = _coord()
    c._datasheet_merged = load_bundled()
    c._stooklijn_cache = {"huidige_lwt": None}
    snap = SimpleNamespace(
        attrs={
            "Leaving water temp. before BUH (R1T)": 28.6,
            "Stats: COP estimated": 6.02,
            "R1T-Outdoor air temp.": 8.0,
        },
        cop=None, last_record={},
    )
    lwt = c._resolve_lwt_for_datasheet(snap)
    cop = c._resolve_cop_for_datasheet(snap)
    t_out = c._resolve_outdoor_temp(snap)
    assert (lwt, cop, t_out) == (28.6, 6.02, 8.0)
    await c._refresh_datasheet_state(
        now=1000.0, lwt_now=lwt, t_out=t_out, cop_meas=cop,
    )
    assert c._datasheet_cache["cop_normalized_a7w35"] is not None
    assert c._datasheet_cache["cop_vs_datasheet_pct"] is not None
