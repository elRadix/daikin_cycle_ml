"""Tests for v1.6.0-C2: SPF sensors + season_start_month."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    _attrs_spf_state,
)


def _now() -> float:
    return time.time()


def _mk_coord(spf_state=None, opts=None, rows=None, raise_on_fetch=False):
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    if raise_on_fetch:
        c.db.async_fetch_cop_samples_between = AsyncMock(side_effect=RuntimeError("db"))
    else:
        c.db.async_fetch_cop_samples_between = AsyncMock(return_value=rows or [])
    c.db.async_set_model_state = AsyncMock()
    c.options = opts or {}
    c._spf_state_cache = spf_state if spf_state is not None else {}
    return c


@pytest.mark.asyncio
async def test_refresh_spf_no_db():
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c._spf_state_cache = {"spf_season": 99.0}
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache == {"spf_season": 99.0}


@pytest.mark.asyncio
async def test_refresh_spf_empty_rows():
    c = _mk_coord(rows=[])
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["spf_season"] is None
    assert c._spf_state_cache["spf_season_n"] == 0
    assert c._spf_state_cache["spf_ytd"] is None
    assert c._spf_state_cache["scop_365d"] is None


@pytest.mark.asyncio
async def test_refresh_spf_with_data():
    rows = [{"ts": _now()-100, "cop": 4.0}, {"ts": _now()-200, "cop": 5.0}]
    c = _mk_coord(rows=rows)
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["spf_season"] == 4.5
    assert c._spf_state_cache["spf_season_n"] == 2
    assert c._spf_state_cache["spf_ytd"] == 4.5
    assert c._spf_state_cache["scop_365d"] == 4.5


@pytest.mark.asyncio
async def test_refresh_spf_filters_nonpositive():
    rows = [
        {"ts": _now()-100, "cop": 4.0},
        {"ts": _now()-200, "cop": 0.0},
        {"ts": _now()-300, "cop": -1.0},
        {"ts": _now()-400, "cop": "nan"},
    ]
    c = _mk_coord(rows=rows)
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["spf_season"] == 4.0
    assert c._spf_state_cache["spf_season_n"] == 1


@pytest.mark.asyncio
async def test_refresh_spf_fetch_exception():
    c = _mk_coord(raise_on_fetch=True)
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["spf_season"] is None


@pytest.mark.asyncio
async def test_refresh_spf_option_default_10():
    c = _mk_coord(opts={})
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["season_start_month"] == 10


@pytest.mark.asyncio
async def test_refresh_spf_option_valid():
    c = _mk_coord(opts={"season_start_month": 9})
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["season_start_month"] == 9


@pytest.mark.asyncio
async def test_refresh_spf_option_out_of_range():
    c = _mk_coord(opts={"season_start_month": 99})
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["season_start_month"] == 10


@pytest.mark.asyncio
async def test_refresh_spf_option_nonnumeric():
    c = _mk_coord(opts={"season_start_month": "bad"})
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["season_start_month"] == 10


@pytest.mark.asyncio
async def test_refresh_spf_persists():
    c = _mk_coord()
    await c._refresh_spf_state(_now())
    assert c.db.async_set_model_state.await_count == 1
    args, _ = c.db.async_set_model_state.await_args
    assert args[0] == "spf_state"


@pytest.mark.asyncio
async def test_refresh_spf_persist_failure():
    c = _mk_coord()
    c.db.async_set_model_state = AsyncMock(side_effect=RuntimeError("db"))
    await c._refresh_spf_state(_now())
    assert c._spf_state_cache["season_start_month"] == 10


@pytest.mark.asyncio
async def test_maybe_refresh_spf_no_db():
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c._spf_state_cache = {}
    await c._maybe_refresh_spf(_now())
    assert c._spf_state_cache == {}


@pytest.mark.asyncio
async def test_maybe_refresh_spf_cold_start():
    c = _mk_coord(spf_state={})
    await c._maybe_refresh_spf(_now())
    assert "updated_ts" in c._spf_state_cache


@pytest.mark.asyncio
async def test_maybe_refresh_spf_fresh_skips():
    n = _now()
    c = _mk_coord(spf_state={"updated_ts": n - 100, "spf_season": 4.0})
    await c._maybe_refresh_spf(n)
    assert c._spf_state_cache["spf_season"] == 4.0
    assert c.db.async_fetch_cop_samples_between.await_count == 0


@pytest.mark.asyncio
async def test_maybe_refresh_spf_stale():
    n = _now()
    c = _mk_coord(spf_state={"updated_ts": n - 7200, "spf_season": 99.0})
    await c._maybe_refresh_spf(n)
    assert c.db.async_fetch_cop_samples_between.await_count > 0
    assert c._spf_state_cache["spf_season"] is None


def test_snapshot_has_spf_state():
    s = DataSnapshot()
    assert hasattr(s, "spf_state")
    assert s.spf_state == {}


def test_sensor_defs_has_spf_keys():
    keys = {sd["key"] for sd in SENSOR_DEFS}
    assert "spf_season" in keys
    assert "spf_ytd" in keys
    assert "scop_running_365d" in keys


def test_spf_sensors_unit_and_class():
    from homeassistant.components.sensor import SensorStateClass
    for sd in SENSOR_DEFS:
        if sd["key"] in ("spf_season", "spf_ytd", "scop_running_365d"):
            assert sd["unit"] == "SPF"
            assert sd["state_class"] == SensorStateClass.MEASUREMENT


def test_spf_value_fn_reads_state():
    s = SimpleNamespace(spf_state={"spf_season": 4.1, "spf_ytd": 3.9, "scop_365d": 4.0})
    for sd in SENSOR_DEFS:
        if sd["key"] == "spf_season":
            assert sd["value_fn"](s, MagicMock()) == 4.1
        elif sd["key"] == "spf_ytd":
            assert sd["value_fn"](s, MagicMock()) == 3.9
        elif sd["key"] == "scop_running_365d":
            assert sd["value_fn"](s, MagicMock()) == 4.0


def test_spf_value_fn_empty():
    s = SimpleNamespace(spf_state={})
    for sd in SENSOR_DEFS:
        if sd["key"] in ("spf_season", "spf_ytd", "scop_running_365d"):
            assert sd["value_fn"](s, MagicMock()) is None


def test_attrs_spf_state_full():
    s = SimpleNamespace(spf_state={
        "season_start_month": 10,
        "spf_season": 4.1, "spf_season_n": 100,
        "spf_ytd": 3.9, "spf_ytd_n": 500,
        "scop_365d": 4.0, "scop_365d_n": 1500,
        "updated_ts": 12345.0,
    })
    a = _attrs_spf_state(s, MagicMock())
    assert a["season_start_month"] == 10
    assert a["spf_season_n"] == 100
    assert a["spf_ytd"] == 3.9
    assert a["spf_ytd_n"] == 500
    assert a["scop_365d"] == 4.0
    assert a["scop_365d_n"] == 1500
    assert a["updated_ts"] == 12345.0


def test_attrs_spf_state_empty():
    s = SimpleNamespace(spf_state={})
    a = _attrs_spf_state(s, MagicMock())
    assert all(v is None for v in a.values())


def test_attrs_spf_state_none():
    s = SimpleNamespace(spf_state=None)
    a = _attrs_spf_state(s, MagicMock())
    assert all(v is None for v in a.values())


@pytest.mark.parametrize("key", ["spf_season", "spf_ytd", "scop_running_365d"])
def test_translation_in_3_files(key):
    import json
    from pathlib import Path
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    for fn in ("strings.json", "translations/en.json", "translations/nl.json"):
        data = json.loads((base / fn).read_text())
        assert key in data["entity"]["sensor"]
        assert "name" in data["entity"]["sensor"][key]


def test_translation_nl_differs_en():
    import json
    from pathlib import Path
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    en = json.loads((base / "translations/en.json").read_text())
    nl = json.loads((base / "translations/nl.json").read_text())
    assert en["entity"]["sensor"]["spf_season"]["name"] == "SPF season"
    assert nl["entity"]["sensor"]["spf_season"]["name"] == "SPF seizoen"


def test_maintenance_translation_has_season_start_month():
    import json
    from pathlib import Path
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    for fn in ("strings.json", "translations/en.json", "translations/nl.json"):
        data = json.loads((base / fn).read_text())
        step = data["options"]["step"]["maintenance"]
        assert "season_start_month" in step["data"]
        assert "season_start_month" in step["data_description"]


# ============================================================
# Runtime smoke tests (promoted from pre-commit smoke, v1.6.0-C2)
# These guard against:
#   - import-time regressions
#   - OptionsFlow schema validation drift (str/int coercion)
#   - translation JSON corrupt
#   - SENSOR_DEFS structural drift
# ============================================================


def test_runtime_import_package():
    """Package must import cleanly (no circular imports)."""
    from custom_components.daikin_cycle_ml import async_setup_entry  # noqa: F401


def test_runtime_import_all_modules():
    """Every public module must import without error."""
    import importlib
    for mod in (
        "custom_components.daikin_cycle_ml.coordinator",
        "custom_components.daikin_cycle_ml.sensor",
        "custom_components.daikin_cycle_ml.config_flow",
        "custom_components.daikin_cycle_ml.const",
        "custom_components.daikin_cycle_ml.binary_sensor",
        "custom_components.daikin_cycle_ml.diagnostics",
        "custom_components.daikin_cycle_ml.services",
    ):
        importlib.import_module(mod)


def test_runtime_sensor_defs_count_and_unique_keys():
    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
    assert len(SENSOR_DEFS) == 39
    keys = [s["key"] for s in SENSOR_DEFS]
    assert len(set(keys)) == len(keys), "duplicate SENSOR_DEFS keys"


def test_runtime_spf_scop_slug_match():
    """SPF/SCOP names must slugify to their key."""
    import re

    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS

    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    for sd in SENSOR_DEFS:
        if sd["key"].startswith(("spf_", "scop_")):
            assert _slug(sd["name"]) == sd["key"], (
                f"{sd['name']!r} -> {_slug(sd['name'])!r} != {sd['key']!r}"
            )


def test_runtime_datasnapshot_new_fields():
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    s = DataSnapshot()
    assert s.spf_state == {}
    assert s.cop_combined_today == {}


def test_runtime_coordinator_methods_present():
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    assert hasattr(DaikinCycleMLCoordinator, "_refresh_spf_state")
    assert hasattr(DaikinCycleMLCoordinator, "_maybe_refresh_spf")


def test_runtime_translations_parse_all_3():
    import json
    from pathlib import Path
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    for fn in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((base / fn).read_text())
        for k in ("spf_season", "spf_ytd", "scop_running_365d", "cop_combined_today"):
            assert k in d["entity"]["sensor"], f"{k} missing in {fn}"
        step = d["options"]["step"]["maintenance"]
        assert "season_start_month" in step["data"]
        assert "season_start_month" in step["data_description"]


def test_runtime_optionsflow_season_schema_accepts_int():
    import voluptuous as vol
    schema = vol.Schema({
        vol.Required("season_start_month", default=10): vol.All(
            vol.Coerce(int),
            vol.In({1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}),
        ),
    })
    assert schema({"season_start_month": 10})["season_start_month"] == 10


def test_runtime_optionsflow_season_schema_accepts_str():
    """HA frontend serializes dropdown values as strings sometimes."""
    import voluptuous as vol
    schema = vol.Schema({
        vol.Required("season_start_month", default=10): vol.All(
            vol.Coerce(int),
            vol.In({1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}),
        ),
    })
    assert schema({"season_start_month": "10"})["season_start_month"] == 10


def test_runtime_optionsflow_season_schema_rejects_out_of_range():
    import pytest as _pytest
    import voluptuous as vol
    schema = vol.Schema({
        vol.Required("season_start_month", default=10): vol.All(
            vol.Coerce(int),
            vol.In({1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}),
        ),
    })
    with _pytest.raises(vol.MultipleInvalid):
        schema({"season_start_month": 13})
    with _pytest.raises(vol.MultipleInvalid):
        schema({"season_start_month": 0})


def test_runtime_optionsflow_season_schema_rejects_nonnumeric():
    import pytest as _pytest
    import voluptuous as vol
    schema = vol.Schema({
        vol.Required("season_start_month", default=10): vol.All(
            vol.Coerce(int),
            vol.In({1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}),
        ),
    })
    with _pytest.raises(vol.MultipleInvalid):
        schema({"season_start_month": "October"})
