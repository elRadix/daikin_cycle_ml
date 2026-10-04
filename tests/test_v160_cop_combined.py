"""Tests for v1.6.0-C1b: cop_today heating-only + cop_combined_today."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    _attrs_cop_combined_today,
)


def _mk_row(ts: float, cop: float, mode: str | None) -> dict:
    return {"ts": ts, "cop": cop, "mode": mode}


def _today_start() -> float:
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def _mk_coord(rows_today, rows_week=None):
    """Minimal coordinator stub for _refresh_cop_today."""
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_fetch_cop_samples = AsyncMock(
        side_effect=lambda days: rows_today if days == 1 else (rows_week or rows_today)
    )
    c._cop_today_cache = {}
    c._cop_today_heating_cache = {}
    return c


@pytest.mark.asyncio
async def test_refresh_cop_today_heating_only():
    ts = _today_start() + 3600
    rows = [
        _mk_row(ts, 4.0, "heating"),
        _mk_row(ts, 6.0, "heating"),
        _mk_row(ts, 2.0, "dhw"),
    ]
    c = _mk_coord(rows)
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_heating_cache["cop"] == 5.0
    assert c._cop_today_heating_cache["samples_today"] == 2


@pytest.mark.asyncio
async def test_refresh_cop_today_combined_blended():
    ts = _today_start() + 3600
    rows = [
        _mk_row(ts, 4.0, "heating"),
        _mk_row(ts, 6.0, "heating"),
        _mk_row(ts, 2.0, "dhw"),
    ]
    c = _mk_coord(rows)
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_cache["cop"] == 4.0
    assert c._cop_today_cache["samples_today"] == 3


@pytest.mark.asyncio
async def test_refresh_cop_today_no_heating_samples():
    ts = _today_start() + 3600
    rows = [_mk_row(ts, 3.0, "dhw")]
    c = _mk_coord(rows)
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_heating_cache == {}
    assert c._cop_today_cache["cop"] == 3.0


@pytest.mark.asyncio
async def test_refresh_cop_today_empty_rows():
    c = _mk_coord([])
    await c._refresh_cop_today(_today_start() + 1)
    assert c._cop_today_cache == {}
    assert c._cop_today_heating_cache == {}


@pytest.mark.asyncio
async def test_refresh_cop_today_db_none():
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c._cop_today_cache = {"cop": 99.0}
    c._cop_today_heating_cache = {"cop": 99.0}
    await c._refresh_cop_today(_today_start() + 1)
    assert c._cop_today_cache == {"cop": 99.0}


@pytest.mark.asyncio
async def test_refresh_cop_today_fetch_exception():
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_fetch_cop_samples = AsyncMock(side_effect=RuntimeError("db down"))
    c._cop_today_cache = {}
    c._cop_today_heating_cache = {}
    await c._refresh_cop_today(_today_start() + 1)
    assert c._cop_today_cache == {}


def test_snapshot_has_cop_combined_today():
    s = DataSnapshot()
    assert hasattr(s, "cop_combined_today")
    assert s.cop_combined_today == {}


def test_sensor_defs_has_cop_combined_today():
    keys = {sd["key"] for sd in SENSOR_DEFS}
    assert "cop_combined_today" in keys
    assert "cop_today" in keys


def test_cop_combined_today_unit_and_class():
    from homeassistant.components.sensor import SensorStateClass
    for sd in SENSOR_DEFS:
        if sd["key"] == "cop_combined_today":
            assert sd["unit"] == "COP"
            assert sd["state_class"] == SensorStateClass.MEASUREMENT
            break
    else:
        pytest.fail("cop_combined_today not in SENSOR_DEFS")


def test_attrs_cop_combined_today_reads_combined():
    s = SimpleNamespace(cop_combined_today={
        "cop": 4.1, "samples_today": 12, "cop_min": 3.2,
        "cop_max": 5.0, "baseline_cop_verlies_pct": 1.5,
    })
    a = _attrs_cop_combined_today(s, MagicMock())
    assert a["samples_today"] == 12
    assert a["cop_min"] == 3.2
    assert a["cop_max"] == 5.0
    assert a["baseline_cop_verlies_pct"] == 1.5


def test_attrs_cop_combined_today_empty():
    s = SimpleNamespace(cop_combined_today={})
    a = _attrs_cop_combined_today(s, MagicMock())
    assert a["samples_today"] is None


def test_attrs_cop_combined_today_none():
    s = SimpleNamespace(cop_combined_today=None)
    a = _attrs_cop_combined_today(s, MagicMock())
    assert a["samples_today"] is None


def test_cop_today_value_fn_heating_only():
    for sd in SENSOR_DEFS:
        if sd["key"] == "cop_today":
            s = SimpleNamespace(cop_today={"cop": 5.5}, cop_combined_today={"cop": 4.0})
            assert sd["value_fn"](s, MagicMock()) == 5.5
            break
    else:
        pytest.fail("cop_today not in SENSOR_DEFS")


def test_cop_combined_today_value_fn():
    for sd in SENSOR_DEFS:
        if sd["key"] == "cop_combined_today":
            s = SimpleNamespace(cop_today={"cop": 5.5}, cop_combined_today={"cop": 4.0})
            assert sd["value_fn"](s, MagicMock()) == 4.0
            break


def test_translation_cop_combined_today_in_all_3_files():
    import json
    from pathlib import Path
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    for fn in ("strings.json", "translations/en.json", "translations/nl.json"):
        data = json.loads((base / fn).read_text())
        assert "cop_combined_today" in data["entity"]["sensor"]
