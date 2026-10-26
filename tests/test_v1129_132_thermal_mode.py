"""Tests for #132: DHW thermal cascade prefers flow_dt (R486).

Bug 2 CONFIRMED: cascade previously preferred power_cop over flow_dt,
polluting DHW thermal with heating-biased user COP. Bug 1 REFUTED
(R4T is correct cold side for DHW, not R5T).
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine.physics import (
    get_physical_cop_ceiling,
)
from custom_components.daikin_cycle_ml.engine.thermal import (
    compute_thermal_power_live,
)


def test_dhw_prefers_flow_dt_over_power_cop() -> None:
    kw, src = compute_thermal_power_live(
        power_w=1000.0, cop=5.0,
        flow_lmin=26.7, dt_k=3.3,
        rps=36.0, mode="dhw",
    )
    assert src == "flow_dt"
    assert kw is not None
    assert 6.0 < kw < 6.3  # 26.7*4.18*3.3/60 = 6.136


def test_dhw_falls_back_to_power_cop_when_flow_dt_missing() -> None:
    kw, src = compute_thermal_power_live(
        power_w=1000.0, cop=4.0,
        flow_lmin=None, dt_k=None,
        rps=36.0, mode="dhw",
    )
    assert src == "power_cop"
    assert kw == pytest.approx(4.0)


def test_heating_prefers_power_cop() -> None:
    kw, src = compute_thermal_power_live(
        power_w=1000.0, cop=4.5,
        flow_lmin=26.7, dt_k=3.3,
        rps=36.0, mode="heating",
    )
    assert src == "power_cop"
    assert kw == pytest.approx(4.5)


def test_default_mode_is_heating() -> None:
    kw, src = compute_thermal_power_live(
        power_w=1000.0, cop=4.5,
        flow_lmin=26.7, dt_k=3.3,
        rps=36.0,
    )
    assert src == "power_cop"
    assert kw == pytest.approx(4.5)


def test_cooling_mode_uses_power_cop_first() -> None:
    kw, src = compute_thermal_power_live(
        power_w=800.0, cop=3.2,
        flow_lmin=20.0, dt_k=2.5,
        rps=30.0, mode="cooling",
    )
    assert src == "power_cop"


def test_physics_ceiling_carnot_reasonable() -> None:
    ceiling = get_physical_cop_ceiling("dhw", lwt=42.3, outdoor=10.0)
    assert ceiling is not None
    assert 4.0 < ceiling < 6.0


def test_physics_ceiling_lwt_le_outdoor_returns_none() -> None:
    ceiling = get_physical_cop_ceiling("heating", lwt=10.0, outdoor=15.0)
    assert ceiling is None


def test_physics_ceiling_non_hp_mode_returns_none() -> None:
    ceiling = get_physical_cop_ceiling("unknown", lwt=40.0, outdoor=10.0)
    assert ceiling is None
