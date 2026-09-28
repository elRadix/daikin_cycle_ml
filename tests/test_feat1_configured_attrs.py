"""FEAT-1: configured_* attributes on cycle_state sensor.

Test-only additions. No source changes to verify here — purely attribute
exposure on the cycle_state container sensor.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.daikin_cycle_ml import sensor as sm
from custom_components.daikin_cycle_ml.const import DOMAIN


def _mk_entry(*, data=None, options=None, entry_id="e1"):
    return SimpleNamespace(
        data=data or {},
        options=options or {},
        entry_id=entry_id,
    )


def _mk_coord(entry):
    return SimpleNamespace(entry=entry, domain=DOMAIN)


def _mk_snap():
    return SimpleNamespace(state="idle")


def test_attrs_cycle_state_full_config():
    entry = _mk_entry(
        data={"source_sensor": "sensor.src", "model": "epra12eav3"},
        options={
            "power_sensor_entity": "sensor.wp_power",
            "cop_sensor_entity": "sensor.altherma_global_cop",
            "indoor_temp_sensor": "sensor.avg_home",
            "notification_language": "en",
        },
        entry_id="01M3J30P8QPBHG4V2N87WZ4GZT",
    )
    coord = _mk_coord(entry)
    out = sm._attrs_cycle_state(_mk_snap(), coord)

    assert out["configured_source_sensor"] == "sensor.src"
    assert out["configured_power_sensor"] == "sensor.wp_power"
    assert out["configured_cop_sensor"] == "sensor.altherma_global_cop"
    assert out["configured_indoor_sensor"] == "sensor.avg_home"
    assert out["configured_model"] == "epra12eav3"
    assert out["configured_language"] == "en"
    assert out["configured_entry_id"] == "01M3J30P8QPBHG4V2N87WZ4GZT"


def test_attrs_cycle_state_none_when_unset():
    entry = _mk_entry(
        data={"source_sensor": "sensor.src", "model": "epra12eav3"},
        options={},
        entry_id="e2",
    )
    coord = _mk_coord(entry)
    out = sm._attrs_cycle_state(_mk_snap(), coord)

    assert out["configured_power_sensor"] is None
    assert out["configured_cop_sensor"] is None
    assert out["configured_indoor_sensor"] is None
    assert out["configured_language"] == "en"  # default
    assert out["configured_source_sensor"] == "sensor.src"
    assert out["configured_model"] == "epra12eav3"


def test_attrs_cycle_state_no_entry():
    coord = SimpleNamespace()  # no .entry
    out = sm._attrs_cycle_state(_mk_snap(), coord)
    assert out == {}


def test_attrs_cycle_state_in_sensor_defs():
    """cycle_state in SENSOR_DEFS must have the new attr_fn wired."""
    defs = {d["key"]: d for d in sm.SENSOR_DEFS}
    assert "cycle_state" in defs
    assert defs["cycle_state"]["attr_fn"] is sm._attrs_cycle_state


def test_attrs_cycle_state_expected_keys():
    """Forward-compat: required keys present (R42)."""
    entry = _mk_entry(
        data={"source_sensor": "sensor.s", "model": "m"},
        options={},
        entry_id="e",
    )
    out = sm._attrs_cycle_state(_mk_snap(), _mk_coord(entry))
    assert set(out.keys()) >= {
        "configured_source_sensor",
        "configured_power_sensor",
        "configured_cop_sensor",
        "configured_indoor_sensor",
        "configured_model",
        "configured_language",
        "configured_entry_id",
    }
