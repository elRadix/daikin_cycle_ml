"""Runtime + config-flow coverage for ESPAltherma beta / HPSU / DEFAULT variants.

Guards (Discussion #117 / Issue #150):
- R1T prefix (beta) resolves via compat view
- HPSU inlet (ERGA D ECH2O) resolves via compat view
- HPSU lwt_before_buh (EPRA D / ERGA D ECH2O) resolves
- DEFAULT.h fallback variants resolve
- Decoy attributes NEVER resolve to wrong canonical
- Placeholder values treated as missing by missing_required()
- cycle_detector.update() applies compat view internally
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_DHW_TANK_TEMP,
    ATTR_INLET_WATER_R4T,
    ATTR_OUTDOOR_AIR_R1T,
)
from custom_components.daikin_cycle_ml.engine.attribute_compat import (
    build_compat_view,
)
from custom_components.daikin_cycle_ml.engine.attribute_reader import (
    missing_required,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
)


def _base_attrs() -> dict:
    return {
        "Outdoor air temp.(R1T)": 7.5,
        "Inlet water temp.(R4T)": 32.1,
        "DHW tank temp. (R5T)": 45.0,
        "Leaving water temp. after BUH (R2T)": 35.0,
        "Operation Mode": "Heating",
        "I/U operation mode": "Heating",
        "3way valve(On:DHW_Off:Space)": "Off",
        "Defrost Operation": "OFF",
        "Flow sensor (l/min)": 14.5,
        "Water pump operation": "ON",
        "BUH Step1": "OFF",
        "BUH Step2": "OFF",
        "LW setpoint (main)": 35.0,
    }


class TestOutdoorPrefixBeta:
    def test_prefix_materializes_canonical_key(self) -> None:
        view = build_compat_view({"R1T-Outdoor air temp.": 7.5})
        assert view[ATTR_OUTDOOR_AIR_R1T] == 7.5

    def test_prefix_satisfies_config_flow(self) -> None:
        attrs = _base_attrs()
        attrs["R1T-Outdoor air temp."] = attrs.pop("Outdoor air temp.(R1T)")
        assert missing_required(attrs) == []

    def test_both_present_no_collision(self) -> None:
        attrs = _base_attrs()
        attrs["R1T-Outdoor air temp."] = 99.9
        view = build_compat_view(attrs)
        assert view[ATTR_OUTDOOR_AIR_R1T] == 7.5


class TestHpsuVariants:
    def test_hpsu_inlet_satisfies_config_flow(self) -> None:
        attrs = _base_attrs()
        attrs["[HPSU] Tr return Temp (R4T)"] = attrs.pop("Inlet water temp.(R4T)")
        assert missing_required(attrs) == []

    def test_hpsu_lwt_before_buh_resolves(self) -> None:
        view = build_compat_view({"[HPSU] Tv inflow Temp  (R1T)": 28.5})
        assert view["Leaving water temp. before BUH (R1T)"] == 28.5


class TestDefaultFallbacks:
    def test_default_inlet(self) -> None:
        view = build_compat_view({"Inlet temperature(R4T)": 30.0})
        assert view[ATTR_INLET_WATER_R4T] == 30.0

    def test_default_dhw(self) -> None:
        view = build_compat_view({"DHW temperature(R5T)": 50.0})
        assert view[ATTR_DHW_TANK_TEMP] == 50.0


class TestDecoys:
    @pytest.mark.parametrize("decoy", [
        "Indoor ambient temp. (R1T)",
        "Outlet PHE(R1T)",
        "Outlet Water Heat Exch. Temp. (R1T)",
        "[EKMIK] Bizone kit mixed leaving water temperature R1T",
    ])
    def test_r1t_decoys_never_match_outdoor(self, decoy: str) -> None:
        view = build_compat_view({decoy: 99.9})
        assert view.get(ATTR_OUTDOOR_AIR_R1T) != 99.9

    @pytest.mark.parametrize("decoy", [
        "O/U Heat Exch. Temp.(R4T)",
        "2 phase thermistor (R4T)",
    ])
    def test_r4t_decoys_never_match_inlet(self, decoy: str) -> None:
        view = build_compat_view({decoy: 99.9})
        assert view.get(ATTR_INLET_WATER_R4T) != 99.9

    @pytest.mark.parametrize("decoy", [
        "Heat exchanger mid-temp.(R5T)",
        "Entering brine temp.(R5T)",
    ])
    def test_r5t_decoys_never_match_dhw(self, decoy: str) -> None:
        view = build_compat_view({decoy: 99.9})
        assert view.get(ATTR_DHW_TANK_TEMP) != 99.9


class TestPlaceholders:
    @pytest.mark.parametrize("placeholder", ["---", "unknown", ""])
    def test_placeholder_outdoor_is_missing(self, placeholder: str) -> None:
        attrs = _base_attrs()
        attrs["Outdoor air temp.(R1T)"] = placeholder
        assert ATTR_OUTDOOR_AIR_R1T in missing_required(attrs)


class TestDetectorAppliesCompat:
    def test_update_with_beta_prefix_populates_outdoor_samples(self) -> None:
        det = CycleDetector()
        attrs = {
            "R1T-Outdoor air temp.": 7.5,
            "INV frequency (rps)": 45.0,
            "I/U operation mode": "Heating",
            "Inlet water temp.(R4T)": 32.0,
            "Leaving water temp. after BUH (R2T)": 35.0,
            "Flow sensor (l/min)": 14.0,
            "Water pump operation": "ON",
            "3way valve(On:DHW_Off:Space)": "Off",
            "BUH Step1": "OFF",
            "BUH Step2": "OFF",
            "Defrost Operation": "OFF",
        }
        det.update(attrs, now=1000.0, power_w=2000.0)
        det.update(attrs, now=1030.0, power_w=2000.0)
        assert det._outdoor_samples == [7.5, 7.5]
