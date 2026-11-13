"""v1.20.0 #281: EPRA12EAV3 full-coverage E2E against user's real install.

R634: real-world reproduction. The fixture below is the complete 138-entity
list observed on a real EPRA12EAV3 install (provided 2026-11-07). This
test proves that:
  1. Discovery finds every sensor.* and binary_sensor.* entity
  2. Discovery ignores non-target domains (number.*, switch.*, update.*, button.*)
  3. Resolution finds exactly 22/26 CONSUMED attributes
  4. 4 legitimately-absent consumed attributes surface in missing_consumed:
     COP (computed), INV frequency 2 (no cascade), Hybrid Op. Mode (non-hybrid),
     Stats: Electricalinput estimated (firmware uses correct spelling)
  5. R1T-Outdoor air temp. alias resolves canonical Outdoor air temp.(R1T)
  6. BE_COP alias resolves canonical BE COP
  7. binary_sensor.* entities produce Python bool True/False

R598: real resolve_attrs, real discovery, real slug engine.
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_BE_COP,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_COP,
    ATTR_DEFROST_OPERATION,
    ATTR_DHW_TANK_TEMP,
    ATTR_FLOW_SENSOR,
    ATTR_HYBRID_OP_MODE,
    ATTR_INDOOR_AMBIENT_R1T,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_2_RPS,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_TARGET_COND_TEMP,
    ATTR_WATER_PUMP_OPERATION,
    REQUIRED_ATTRIBUTES,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.discovery import (
    build_slug_index,
    discover_entity_ids,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
    resolve_attrs,
)

DEFAULT_PREFIX = "sensor.espaltherma_"


EPRA12EAV3_ENTITIES: dict[str, str] = {
    # sensor.espaltherma_* (numeric/string values)
    "sensor.espaltherma_2nd_domestic_hot_water_temperature": "45.0",
    "sensor.espaltherma_becop": "0.0",
    "sensor.espaltherma_comp_inv_current_protection_retry_qty": "0",
    "sensor.espaltherma_compressor_outlet_temperature": "70.0",
    "sensor.espaltherma_dhw_setpoint": "55.0",
    "sensor.espaltherma_dhw_tank_temp_r5t": "55.0",
    "sensor.espaltherma_discharge_pipe_tempr2t": "70.0",
    "sensor.espaltherma_discharge_temp_protection_retry_qty": "0",
    "sensor.espaltherma_error_detailed_code": "0",
    "sensor.espaltherma_expansion_valve_1_pls": "200",
    "sensor.espaltherma_expansion_valve_2_pls": "200",
    "sensor.espaltherma_expansion_valve_4_pls": "200",
    "sensor.espaltherma_fan_1_step": "3",
    "sensor.espaltherma_fan_2_step": "3",
    "sensor.espaltherma_fan1_fin_temp": "25.0",
    "sensor.espaltherma_fan2_fin_temp": "25.0",
    "sensor.espaltherma_flow_sensor_lmin": "15.2",
    "sensor.espaltherma_freemem": "120000",
    "sensor.espaltherma_heat_exchanger_midtempr5t": "35.0",
    "sensor.espaltherma_high_pressure": "25.0",
    "sensor.espaltherma_high_pressuret": "60.0",
    "sensor.espaltherma_iu_capacity_code": "3",
    "sensor.espaltherma_iu_error_code": "0",
    "sensor.espaltherma_iu_error_type": "0",
    "sensor.espaltherma_iu_operation_mode": "Heating",
    "sensor.espaltherma_iu_pressure": "0",
    "sensor.espaltherma_indoor_ambient_temp_r1t": "21.5",
    "sensor.espaltherma_injection_tube_temperature": "5.0",
    "sensor.espaltherma_inlet_water_tempr4t": "30.0",
    "sensor.espaltherma_inv_compressor_qty": "1",
    "sensor.espaltherma_inv_fin_temp": "25.0",
    "sensor.espaltherma_inv_frequency_rps": "35",
    "sensor.espaltherma_inv_primary_current_a": "2.5",
    "sensor.espaltherma_inv_secondary_current_a": "3.0",
    "sensor.espaltherma_ip": "192.168.1.100",
    "sensor.espaltherma_leaving_water_temp_after_buh_r2t": "35.0",
    "sensor.espaltherma_leaving_water_temp_before_buh_r1t": "35.2",
    "sensor.espaltherma_liquid_pipe_temp": "8.5",
    "sensor.espaltherma_liquid_pipe_tempr6t": "8.5",
    "sensor.espaltherma_low_pressure": "10.0",
    "sensor.espaltherma_low_pressuret": "40.0",
    "sensor.espaltherma_lw_setpoint_main": "40.0",
    "sensor.espaltherma_m5batv": "24.0",
    "sensor.espaltherma_m5vin": "24.0",
    "sensor.espaltherma_operation_mode": "Heating",
    "sensor.espaltherma_ou_error_code": "0",
    "sensor.espaltherma_ou_error_type": "0",
    "sensor.espaltherma_ou_expansion_valve_3_pls": "200",
    "sensor.espaltherma_ou_heat_exch_tempr4t": "8.5",
    "sensor.espaltherma_outdoor_heat_exchanger_temp": "8.5",
    "sensor.espaltherma_pressure": "15.0",
    "sensor.espaltherma_pump_pwm_fdbk_0stby_1on_2warning_3elec_err_4blocked": "1",
    "sensor.espaltherma_r1toutdoor_air_temp": "8.5",
    "sensor.espaltherma_refrig_temp_liquid_side_r3t": "10.0",
    "sensor.espaltherma_refrigerant_pressure_sensor": "15.0",
    "sensor.espaltherma_rt_setpoint": "40.0",
    "sensor.espaltherma_stats_backup_heater_today_min": "0",
    "sensor.espaltherma_stats_compressor_run_today_min": "120",
    "sensor.espaltherma_stats_compressor_starts_last_hour": "1",
    "sensor.espaltherma_stats_compressor_starts_today": "15",
    "sensor.espaltherma_stats_cop_estimated": "4.5",
    "sensor.espaltherma_stats_cop_today_heating": "4.8",
    "sensor.espaltherma_stats_cop_today_hot_water": "3.2",
    "sensor.espaltherma_stats_defrosts_today": "2",
    "sensor.espaltherma_stats_electrical_input_estimated_kw": "0.81",
    "sensor.espaltherma_stats_electricity_today_cooling_kwh": "0.0",
    "sensor.espaltherma_stats_electricity_today_heating_kwh": "2.5",
    "sensor.espaltherma_stats_electricity_today_hot_water_kwh": "1.2",
    "sensor.espaltherma_stats_heat_output_kw": "4.5",
    "sensor.espaltherma_stats_heat_today_cooling_kwh": "0.0",
    "sensor.espaltherma_stats_heat_today_heating_kwh": "12.0",
    "sensor.espaltherma_stats_heat_today_hot_water_kwh": "3.8",
    "sensor.espaltherma_stats_last_pause_min": "5",
    "sensor.espaltherma_stats_last_run_min": "45",
    "sensor.espaltherma_suction_pipe_tempr3t": "10.0",
    "sensor.espaltherma_suction_temp": "10.0",
    "sensor.espaltherma_target_cond_temp": "38.0",
    "sensor.espaltherma_target_delta_t_cooling": "8.0",
    "sensor.espaltherma_target_delta_t_heating": "5.0",
    "sensor.espaltherma_target_discharge_temp": "70.0",
    "sensor.espaltherma_target_evap_temp": "5.0",
    "sensor.espaltherma_target_port_temperature": "40.0",
    "sensor.espaltherma_uptime": "86400",
    "sensor.espaltherma_water_pressure": "1.5",
    "sensor.espaltherma_water_pump_signal_0max100stop": "80",
    "sensor.espaltherma_wifirssi": "-45",
    # binary_sensor.espaltherma_* (on/off values)
    "binary_sensor.espaltherma_3way_valveondhwoffspace": "off",
    "binary_sensor.espaltherma_4_way_valve": "off",
    "binary_sensor.espaltherma_add_ext_rt_input_heat": "off",
    "binary_sensor.espaltherma_benefit_kwh_rate_power_supply": "off",
    "binary_sensor.espaltherma_boiler_dhw_demand": "off",
    "binary_sensor.espaltherma_boiler_operation_demand": "off",
    "binary_sensor.espaltherma_bsh": "off",
    "binary_sensor.espaltherma_buh_step1": "off",
    "binary_sensor.espaltherma_buh_step2": "off",
    "binary_sensor.espaltherma_bypass_valve_output": "off",
    "binary_sensor.espaltherma_circulation_pump_operation": "on",
    "binary_sensor.espaltherma_comp_inv_current_drop": "off",
    "binary_sensor.espaltherma_defrost_operation": "off",
    "binary_sensor.espaltherma_demand_signal": "on",
    "binary_sensor.espaltherma_discharge_temp_drop": "off",
    "binary_sensor.espaltherma_freeze_protection": "off",
    "binary_sensor.espaltherma_freeze_protection_for_water_piping": "off",
    "binary_sensor.espaltherma_hot_gas_bypass_valve_y3s": "off",
    "binary_sensor.espaltherma_iu_thermostat_onoff": "on",
    "binary_sensor.espaltherma_low_noise_control": "off",
    "binary_sensor.espaltherma_lp_bypass_valve_y2s": "off",
    "binary_sensor.espaltherma_main_rt_cooling": "off",
    "binary_sensor.espaltherma_main_rt_heating": "on",
    "binary_sensor.espaltherma_ou_crank_case_heater": "off",
    "binary_sensor.espaltherma_ou_discharge_temp_drop": "off",
    "binary_sensor.espaltherma_ou_thermostat_onoff": "on",
    "binary_sensor.espaltherma_oil_return_operation": "off",
    "binary_sensor.espaltherma_powerful_dhw_operation_onoff": "off",
    "binary_sensor.espaltherma_pressure_equalizing_operation": "off",
    "binary_sensor.espaltherma_pump_feedback_bit5": "off",
    "binary_sensor.espaltherma_pump_feedback_bit6": "off",
    "binary_sensor.espaltherma_pump_feedback_bit7": "off",
    "binary_sensor.espaltherma_pwr_consumption_limit_1": "off",
    "binary_sensor.espaltherma_pwr_consumption_limit_2": "off",
    "binary_sensor.espaltherma_pwr_consumption_limit_3": "off",
    "binary_sensor.espaltherma_pwr_consumption_limit_4": "off",
    "binary_sensor.espaltherma_reheat_onoff": "off",
    "binary_sensor.espaltherma_silent_mode": "off",
    "binary_sensor.espaltherma_solenoid_valve_1": "off",
    "binary_sensor.espaltherma_space_heating_operation_onoff": "on",
    "binary_sensor.espaltherma_system_off_onsystem_off": "on",
    "binary_sensor.espaltherma_tank_preheat_onoff": "off",
    "binary_sensor.espaltherma_thermal_protector_q1l_buh": "off",
    "binary_sensor.espaltherma_thermal_protector_bsh": "off",
    "binary_sensor.espaltherma_thermostat_onoff": "on",
    "binary_sensor.espaltherma_water_flow_switch": "on",
    "binary_sensor.espaltherma_water_pump_operation": "on",
    # NON-TARGET DOMAINS
    "number.espaltherma_hot_water_target": "48.0",
    "number.espaltherma_power_limit": "80",
    "switch.espaltherma_power_limit": "on",
    "update.espaltherma_firmware": "off",
    "button.espaltherma_hot_water_curve_restore": "unknown",
}


@pytest.fixture
def hass_with_epra12(hass):
    """Install user's real EPRA12EAV3 entity set into hass.states."""
    for eid, value in EPRA12EAV3_ENTITIES.items():
        hass.states.async_set(eid, value)
    return hass


def test_discovery_finds_all_target_domain_entities(hass_with_epra12) -> None:
    """All sensor + binary_sensor entities indexed; non-target ignored."""
    index = build_slug_index(hass_with_epra12)
    target_sensors = [e for e in EPRA12EAV3_ENTITIES if e.startswith("sensor.espaltherma_")]
    target_binaries = [e for e in EPRA12EAV3_ENTITIES if e.startswith("binary_sensor.espaltherma_")]
    expected_total = len(target_sensors) + len(target_binaries)
    assert len(index) == expected_total, (
        f"expected {expected_total}, got {len(index)}"
    )
    # Non-target domains not present
    for eid in index.values():
        domain = eid.split(".", 1)[0]
        assert domain in ("sensor", "binary_sensor"), f"non-target domain: {eid}"


def test_discover_entity_ids_includes_both_domains(hass_with_epra12) -> None:
    ids = discover_entity_ids(hass_with_epra12)
    sensor_ids = [i for i in ids if i.startswith("sensor.espaltherma_")]
    binary_ids = [i for i in ids if i.startswith("binary_sensor.espaltherma_")]
    assert len(sensor_ids) > 50
    assert len(binary_ids) > 40


@pytest.mark.asyncio
async def test_resolution_returns_21_attributes(hass_with_epra12) -> None:
    """EPRA12EAV3 has 22 of 26 CONSUMED attributes present (R1T before BUH included)."""
    result = resolve_attrs(hass_with_epra12)
    assert len(result.attrs) == 22, (
        f"expected 22, got {len(result.attrs)}: missing={result.missing_consumed}"
    )


@pytest.mark.asyncio
async def test_all_required_resolve(hass_with_epra12) -> None:
    result = resolve_attrs(hass_with_epra12)
    assert result.missing_required == []
    for label in REQUIRED_ATTRIBUTES:
        assert label in result.attrs, f"{label!r} not resolved"


@pytest.mark.asyncio
async def test_missing_consumed_is_exactly_the_4_expected(hass_with_epra12) -> None:
    result = resolve_attrs(hass_with_epra12)
    expected_missing = {
        ATTR_COP,
        ATTR_INV_FREQUENCY_2_RPS,
        ATTR_HYBRID_OP_MODE,
        "Stats: Electricalinput estimated (kW)",
    }
    assert set(result.missing_consumed) == expected_missing, (
        f"expected {expected_missing}, got {set(result.missing_consumed)}"
    )


@pytest.mark.asyncio
async def test_outdoor_r1t_alias_resolves(hass_with_epra12) -> None:
    result = resolve_attrs(hass_with_epra12)
    assert ATTR_OUTDOOR_AIR_R1T in result.attrs
    assert result.attrs[ATTR_OUTDOOR_AIR_R1T] == pytest.approx(8.5)


@pytest.mark.asyncio
async def test_be_cop_alias_resolves(hass_with_epra12) -> None:
    result = resolve_attrs(hass_with_epra12)
    assert ATTR_BE_COP in result.attrs, "BE COP not resolved"
    assert result.attrs[ATTR_BE_COP] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_binary_sensors_produce_bool(hass_with_epra12) -> None:
    result = resolve_attrs(hass_with_epra12)
    for label in (ATTR_3WAY_VALVE, ATTR_DEFROST_OPERATION,
                  ATTR_WATER_PUMP_OPERATION, ATTR_BUH_STEP1, ATTR_BUH_STEP2):
        value = result.attrs.get(label)
        assert isinstance(value, bool), (
            f"{label!r} should be bool, got {type(value).__name__}: {value!r}"
        )


@pytest.mark.asyncio
async def test_specific_values_resolve_correctly(hass_with_epra12) -> None:
    result = resolve_attrs(hass_with_epra12)
    assert result.attrs[ATTR_LEAVING_WATER_AFTER_BUH] == pytest.approx(35.0)
    assert result.attrs[ATTR_INLET_WATER_R4T] == pytest.approx(30.0)
    assert result.attrs[ATTR_FLOW_SENSOR] == pytest.approx(15.2)
    assert result.attrs[ATTR_LW_SETPOINT] == pytest.approx(40.0)
    assert result.attrs[ATTR_INV_FREQUENCY_RPS] == pytest.approx(35.0)
    assert result.attrs[ATTR_DHW_TANK_TEMP] == pytest.approx(55.0)
    assert result.attrs[ATTR_TARGET_COND_TEMP] == pytest.approx(38.0)
    assert result.attrs[ATTR_INDOOR_AMBIENT_R1T] == pytest.approx(21.5)


@pytest.mark.asyncio
async def test_stats_labels_resolve(hass_with_epra12) -> None:
    result = resolve_attrs(hass_with_epra12)
    assert "Stats: Heat output (kW)" in result.attrs
    assert result.attrs["Stats: Heat output (kW)"] == pytest.approx(4.5)
    assert "Stats: Electrical input estimated (kW)" in result.attrs
    assert result.attrs["Stats: Electrical input estimated (kW)"] == pytest.approx(0.81)


@pytest.mark.asyncio
async def test_stats_heat_output_drives_cop_source(hass_with_epra12) -> None:
    """With Stats heat output present, _read_cop_effective uses v2 path."""
    from unittest.mock import MagicMock

    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )

    result = resolve_attrs(hass_with_epra12)
    assert "Stats: Heat output (kW)" in result.attrs

    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.cop_sensor_entity = None
    c._read_cop = MagicMock(return_value=None)
    c._compute_electrical_power = MagicMock(return_value=(810.0, "v2_stats"))
    c.data = MagicMock()
    c.data.mode = "heating"

    cop, src = c._read_cop_effective(now=0.0, attrs=result.attrs)
    assert cop is not None
    assert cop == pytest.approx(5.556, abs=0.01)
    assert src == "espaltherma_heat_output"
