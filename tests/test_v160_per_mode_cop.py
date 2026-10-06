"""Tests for v1.6.0-C1a: per-mode COP sensors."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    _attrs_cop_hourly_mode,
    _cop_hourly_mode_mean,
)


def _snap(**kw):
    base = dict(cop_hourly_day={}, cop_hourly_week={}, cop_hourly_month={})
    base.update(kw)
    return SimpleNamespace(**base)


def _coord():
    return MagicMock()


@pytest.mark.parametrize("period", ["day", "week", "month"])
@pytest.mark.parametrize("mode", ["heating", "dhw", "cooling"])
def test_mean_returns_value(period, mode):
    snap = _snap(**{f"cop_hourly_{period}": {"by_mode": {mode: {"cop_mean": 4.2}}}})
    assert _cop_hourly_mode_mean(mode, period)(snap, _coord()) == 4.2


def test_mean_missing_mode_returns_none():
    snap = _snap(cop_hourly_day={"by_mode": {"heating": {"cop_mean": 4.2}}})
    assert _cop_hourly_mode_mean("dhw", "day")(snap, _coord()) is None


def test_mean_empty_period_returns_none():
    assert _cop_hourly_mode_mean("dhw", "day")(_snap(), _coord()) is None


def test_mean_none_period_returns_none():
    snap = SimpleNamespace(cop_hourly_day=None)
    assert _cop_hourly_mode_mean("dhw", "day")(snap, _coord()) is None


def test_mean_no_by_mode_returns_none():
    snap = _snap(cop_hourly_day={"n_hours": 5})
    assert _cop_hourly_mode_mean("dhw", "day")(snap, _coord()) is None


@pytest.mark.parametrize("period", ["day", "week", "month"])
@pytest.mark.parametrize("mode", ["heating", "dhw", "cooling"])
def test_attrs_all_fields(period, mode):
    bm = {"n_hours": 8, "n_samples": 40, "cop_mean": 4.2,
          "cop_p10": 3.5, "cop_p90": 5.0, "cop_min": 3.0, "cop_max": 5.5}
    snap = _snap(**{f"cop_hourly_{period}": {"by_mode": {mode: bm}}})
    a = _attrs_cop_hourly_mode(mode, period)(snap, _coord())
    assert a["period"] == period and a["mode"] == mode
    assert a["n_hours"] == 8 and a["cop_mean"] == 4.2
    assert a["by_mode"] == {mode: bm}


def test_attrs_missing_mode():
    snap = _snap(cop_hourly_day={"by_mode": {"heating": {"cop_mean": 4.2}}})
    a = _attrs_cop_hourly_mode("dhw", "day")(snap, _coord())
    assert a["mode"] == "dhw" and a["cop_mean"] is None


def test_attrs_empty():
    a = _attrs_cop_hourly_mode("dhw", "day")(_snap(), _coord())
    assert a["by_mode"] == {} and a["cop_mean"] is None


def test_sensor_defs_has_all_9_keys():
    keys = {s["key"] for s in SENSOR_DEFS}
    for mode in ("heating", "dhw", "cooling"):
        for period in ("day", "week", "month"):
            assert f"cop_{mode}_{period}" in keys


def test_per_mode_have_unit_and_class():
    from homeassistant.components.sensor import SensorStateClass
    for s in SENSOR_DEFS:
        if s["key"].startswith(("cop_heating_", "cop_dhw_", "cop_cooling_")):
            assert s["unit"] == "COP"
            assert s["state_class"] == SensorStateClass.MEASUREMENT


def test_sensor_defs_total_27():
    assert len(SENSOR_DEFS) == 45


@pytest.mark.parametrize("mode", ["heating", "dhw", "cooling"])
@pytest.mark.parametrize("period", ["day", "week", "month"])
def test_translation_in_all_3_files(mode, period):
    import json
    from pathlib import Path
    key = f"cop_{mode}_{period}"
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    for fn in ("strings.json", "translations/en.json", "translations/nl.json"):
        data = json.loads((base / fn).read_text())
        node = data["entity"]["sensor"]
        assert key in node, f"{key} missing in {fn}"
        assert "name" in node[key]


def test_nl_differs_from_en():
    import json
    from pathlib import Path
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    en = json.loads((base / "translations/en.json").read_text())
    nl = json.loads((base / "translations/nl.json").read_text())
    assert en["entity"]["sensor"]["cop_dhw_day"]["name"] == "COP DHW (day)"
    assert nl["entity"]["sensor"]["cop_dhw_day"]["name"] == "COP SWW (dag)"


def test_existing_cop_keys_kept():
    keys = {s["key"] for s in SENSOR_DEFS}
    for k in ("cop_today", "cop_mean_day", "cop_mean_week",
              "cop_mean_month", "cop_curve_recent"):
        assert k in keys


# ============================================================
# Runtime smoke (v1.6.0-C1a additions)
# ============================================================

def test_c1a_runtime_import_package():
    from custom_components.daikin_cycle_ml import async_setup_entry  # noqa: F401


def test_c1a_runtime_count_27():
    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
    assert len(SENSOR_DEFS) == 45


def test_c1a_runtime_9_cop_keys_slug_match():
    import re

    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS

    def _slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    for sd in SENSOR_DEFS:
        if sd["key"].startswith(("cop_heating_", "cop_dhw_", "cop_cooling_")):
            assert _slug(sd["name"]) == sd["key"], (
                f"{sd['name']!r} -> {_slug(sd['name'])!r} != {sd['key']!r}"
            )
