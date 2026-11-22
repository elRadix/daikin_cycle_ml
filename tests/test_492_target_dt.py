"""#492: the Efficiency card's ΔT target follows the integration setting.

The reporter (EDLA09D3V3, underfloor heating) set the "Good dT threshold"
to 4 K in the integration; the card still said "your target 5 K" because
it only read its own `target_dt` option. `hp_specs` now carries
`target_dt_k` and the card uses it when its option is empty.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from tests.test_491_card_feedback import node
from tests.test_efficiency_native_card import _case, _set, _text
from tests.test_efficiency_native_card import _run as eff_run


def _coord(value) -> MagicMock:
    c = MagicMock()
    c.options = {"good_dt_threshold_k": value} if value is not None else {}
    c.datasheet_sources = {}
    return c


@pytest.mark.parametrize(("value", "expected"), [
    (4, 4.0), (4.0, 4.0), ("4", 4.0), (None, 5.0), (20, 5.0), (1, 5.0), (True, 5.0), ("x", 5.0),
])
def test_hp_specs_carries_the_integration_dt_target(value, expected):
    snap = DataSnapshot(datasheet={"model": "edla09d3v3", "kw": 9}, datasheet_model="edla09d3v3")
    assert sensor._attrs_hp_specs(snap, _coord(value))["target_dt_k"] == expected
    bare = DataSnapshot(datasheet=None, datasheet_model="edla09d3v3")
    assert sensor._attrs_hp_specs(bare, _coord(value))["target_dt_k"] == expected
    assert sensor._target_dt_k(None) == 5.0


@pytest.fixture(scope="module")
def out() -> dict:
    four = _set(_case("en"), "hp_specs", target_dt_k=4.0)
    return eff_run({
        "integration_4": four,
        "card_wins": {**_set(_case("en"), "hp_specs", target_dt_k=4.0), "config": {"target_dt": 6}},
        "none": _case("en"),
    })


@node
def test_card_uses_the_integration_target_unless_its_own_option_is_set(out):
    live = _text(out["cases"]["integration_4"]["html"]["live"])
    assert "(your target 4 K)" in live and "(your target 5 K)" not in live
    assert "Your target is 4 K" in live                             # help text
    assert "(your target 6 K)" in _text(out["cases"]["card_wins"]["html"]["live"])
    assert "(your target 5 K)" in _text(out["cases"]["none"]["html"]["live"])
