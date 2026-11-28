"""P1/P2 MQTT bridge as a source (#512, #309). Pure Python, no Home Assistant.

The P1/P2 MQTT bridge (Arnold Niessen) publishes the Daikin P1/P2 bus as
separate Home Assistant entities, one per value, under a prefix that differs
per installation (``bridge0_``, ``hc_``, and on one hybrid three prefixes
side by side: ``hc_``, ``wamtepomp_`` (the bridge's own spelling),
``warmtepomp_``). Entities are matched on their name *ending* (the role
suffix), so any prefix works, and translated into the ESPAltherma labels
the rest of the integration reads. Cycle detection, COP, alerts, ML, cards
and reports then work unchanged.

Facts from the two reference dumps (EPRA12EAV3 monobloc, EVLQ08CV3 hybrid):

- ``mode_compressor_rpm`` is the compressor frequency in Hz (= rps);
- ``temperature_r1t_hp2gas_water`` is *water* leaving the heat pump (equal
  to R2T), ESPAltherma's "Leaving water temp. before BUH (R1T)", never the
  outdoor temperature; the outdoor unit's sensor is ``temperature_outside_unit``;
- ``dhw_dhw`` is the hot-water *function* (on while space heating, also
  without a tank); the 3-way valve ``dhw_valve_dhw_tank`` says when the
  tank is heated;
- ``temperature_r5t_dhw_tank`` reads about -40 °C without a tank, and
  ``temperature_r9t_return_water`` reads 0.000 when not connected;
- ``power_production_gasboiler`` is not usable on its own (-97 W on the
  hybrid with the boiler off, 158 W on a monobloc without boiler): the
  boiler is read from ``mode_gasboiler_active``;
- most entities carry no ``unit_of_measurement`` (31 of 480 had one); the
  unit of every role is fixed here, never read from the entity.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..const import (
    ATTR_3WAY_VALVE,
    ATTR_BIVALENT_OPERATION,
    ATTR_BOILER_DHW_DEMAND,
    ATTR_BOILER_OPERATION_DEMAND,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_DHW_TANK_TEMP,
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LEAVING_WATER_BEFORE_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_WATER_PUMP_OPERATION,
    INV_PRIMARY_CURRENT_KEY,
    OP_MODE_COOLING,
    OP_MODE_HEATING,
    R5T_DISCONNECTED_THRESHOLD,
    REQUIRED_ATTRIBUTES,
    V2_STATS_HEAT_KEY,
    V2_STATS_KEY,
)

SENSOR, BINARY = "sensor", "binary_sensor"

# value kinds: plausible range and the unit shown in the setup
KINDS: dict[str, tuple[float, float, str]] = {
    "temp": (-60.0, 130.0, "°C"),
    "flow": (0.0, 150.0, "L/min"),
    "hz": (0.0, 250.0, "Hz"),
    "power": (-100000.0, 100000.0, "W"),
    "current": (0.0, 100.0, "A"),
    "energy": (0.0, 1.0e8, "kWh"),
    "hours": (0.0, 1.0e6, "h"),
    "count": (0.0, 1.0e8, ""),
    "cop": (0.0, 20.0, ""),
    "binary": (0.0, 1.0, ""),
}


@dataclass(frozen=True)
class Role:
    key: str
    domain: str
    suffixes: tuple[str, ...]          # preferred first
    kind: str
    required: bool = False
    label: str | None = None           # ESPAltherma label when read directly

    @property
    def unit(self) -> str:
        return KINDS[self.kind][2]


ROLES: tuple[Role, ...] = (
    # the 12 attributes of the reference sheet (operation mode = 2 roles)
    Role("op_heating", BINARY, ("mode_climate_heating",), "binary", True),
    Role("op_cooling", BINARY, ("mode_climate_cooling",), "binary"),
    Role("threeway_valve", BINARY, ("dhw_valve_dhw_tank",), "binary", False, ATTR_3WAY_VALVE),
    Role("defrost", BINARY, ("mode_defrost_active",), "binary", True, ATTR_DEFROST_OPERATION),
    Role("leaving_r2t", SENSOR, ("sensors_temperature_r2t_leaving_water",), "temp", True,
         ATTR_LEAVING_WATER_AFTER_BUH),
    Role("inlet_r4t", SENSOR, ("sensors_temperature_r4t_return_water",
                               "sensors_temperature_r9t_return_water"), "temp", True, ATTR_INLET_WATER_R4T),
    Role("outdoor", SENSOR, ("sensors_temperature_outside_unit", "sensors_temperature_outside",
                             "sensors_temperature_outside_param15"), "temp", True, ATTR_OUTDOOR_AIR_R1T),
    Role("flow", SENSOR, ("sensors_flow",), "flow", True, ATTR_FLOW_SENSOR),
    Role("pump", BINARY, ("mode_circulation_pump",), "binary", True, ATTR_WATER_PUMP_OPERATION),
    Role("buh1", BINARY, ("mode_buh",), "binary", True, ATTR_BUH_STEP1),
    Role("buh2", BINARY, ("mode_buh_2",), "binary", True, ATTR_BUH_STEP2),
    Role("lw_setpoint", SENSOR, ("lwt_lwt_setpoint",), "temp", True, ATTR_LW_SETPOINT),
    Role("compressor_hz", SENSOR, ("mode_compressor_rpm",), "hz", True, ATTR_INV_FREQUENCY_RPS),
    # extended
    Role("compressor_on", BINARY, ("mode_compressor",), "binary"),
    Role("leaving_r1t", SENSOR, ("sensors_temperature_r1t_hp2gas_water",), "temp", False,
         ATTR_LEAVING_WATER_BEFORE_BUH),
    Role("dhw_tank", SENSOR, ("dhw_temperature_r5t_dhw_tank",), "temp", False, ATTR_DHW_TANK_TEMP),
    Role("heat_power", SENSOR, ("power_production_heatpump",), "power"),
    Role("hp_power", SENSOR, ("power_consumption_heatpump",), "power"),
    Role("buh_power", SENSOR, ("power_consumption_buh",), "power"),
    Role("inv_current", SENSOR, ("power_inverter_primary_current",), "current", False, INV_PRIMARY_CURRENT_KEY),
    Role("cop_realtime", SENSOR, ("cop_cop_realtime",), "cop"),
    Role("gasboiler_active", BINARY, ("mode_gasboiler_active",), "binary"),
    Role("gas_power", SENSOR, ("power_production_gasboiler",), "power"),
    Role("gas_consumed", SENSOR, ("meters_gas_consumed",), "energy"),
    Role("energy_produced_total", SENSOR, ("meters_energy_produced_compressor_total",), "energy"),
    Role("energy_consumed_total", SENSOR, ("meters_electricity_consumed_total",), "energy"),
    Role("compressor_starts", SENSOR, ("meters_starts_compressor",), "count"),
    Role("compressor_hours_heating", SENSOR, ("meters_hours_compressor_heating",), "hours"),
    Role("gasboiler_hours_heating", SENSOR, ("meters_hours_gasboiler_heating",), "hours"),
    Role("room_temp", SENSOR, ("sensors_temperature_room",), "temp"),
    Role("refrigerant_r3t", SENSOR, ("sensors_temperature_r3t_refrigerant",), "temp"),
    Role("discharge", SENSOR, ("sensors_temperature_refrigerant_discharge",), "temp"),
    Role("water_pressure", SENSOR, ("sensors_water_pressure",), "count"),
    # field settings that change how values are read (PR3)
    Role("dhw_tank_installed", BINARY, ("fieldsettings_e_06_a222_dhw_tank_installed",), "binary"),
    Role("external_backup", SENSOR, ("fieldsettings_c_02_external_backup",), "count"),
)
ROLE_BY_KEY = {r.key: r for r in ROLES}
REQUIRED_ROLES = tuple(r.key for r in ROLES if r.required)

# The bridge has no I/U operation mode: the 3-way valve tells when the tank
# is heated (as for ESPAltherma definitions without it, #454 / #487).
NOT_PUBLISHED = frozenset({ATTR_IU_OPERATION_MODE})


def _object_id(entity_id: str) -> tuple[str, str]:
    domain, _, obj = entity_id.partition(".")
    return domain, obj


def _match(obj: str, suffix: str) -> str | None:
    """The prefix when ``obj`` ends in the role suffix, else None."""
    if obj == suffix:
        return ""
    if obj.endswith("_" + suffix):
        return obj[: len(obj) - len(suffix)]
    return None


@dataclass
class Detection:
    mapping: dict[str, str] = field(default_factory=dict)
    prefixes: dict[str, int] = field(default_factory=dict)   # prefix -> matched roles
    prefix: str | None = None                                 # the most common one
    missing_required: list[str] = field(default_factory=list)


def detect(entity_ids: Iterable[str], prefix: str | None = None) -> Detection:
    """Map every role to an entity by name ending.

    A role's earlier suffix wins over a later one (outdoor unit before the
    external sensor); for the same suffix the given ``prefix`` wins, then
    the prefix most roles share. Several bridges: pass the prefix of the one
    to read.
    """
    found: dict[str, list[tuple[int, str, str]]] = {}
    for eid in entity_ids:
        domain, obj = _object_id(eid)
        for role in ROLES:
            if domain != role.domain:
                continue
            for rank, sfx in enumerate(role.suffixes):
                pre = _match(obj, sfx)
                if pre is not None:
                    found.setdefault(role.key, []).append((rank, pre, eid))
                    break
    counts = Counter(pre for cands in found.values() for _, pre, _ in cands)
    out = Detection(prefixes=dict(counts))
    out.prefix = prefix if prefix is not None else (counts.most_common(1)[0][0] if counts else None)
    want = prefix.split(".", 1)[-1] if prefix else None

    def order(c: tuple[int, str, str]) -> tuple[int, int, int, str]:
        rank, pre, eid = c
        return (0 if want is not None and pre == want else 1, rank, -counts[pre], eid)

    for key, cands in found.items():
        if want is not None and not any(pre == want for _, pre, _ in cands):
            # another bridge's entity is never taken for this one
            if any(p == want for p in counts):
                continue
        out.mapping[key] = sorted(cands, key=order)[0][2]
    out.missing_required = [k for k in REQUIRED_ROLES if k not in out.mapping]
    return out


def _num(raw: Any, kind: str) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        v = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    lo, hi, _ = KINDS[kind]
    return v if math.isfinite(v) and lo <= v <= hi else None


def _onoff(raw: Any) -> str | None:
    s = str(raw).strip().lower() if raw is not None else ""
    return "ON" if s in ("on", "true", "1") else "OFF" if s in ("off", "false", "0") else None


@dataclass
class Resolved:
    attrs: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)       # role -> read value
    rejected: dict[str, str] = field(default_factory=dict)     # role -> why
    missing_required: list[str] = field(default_factory=list)  # ESPAltherma labels
    unmapped: list[str] = field(default_factory=list)          # required roles without entity


def resolve(mapping: Mapping[str, str], get_state: Callable[[str], Any]) -> Resolved:
    """Read the mapped entities and build the ESPAltherma attributes."""
    out = Resolved()
    for key, eid in mapping.items():
        role = ROLE_BY_KEY.get(key)
        if role is None or not eid:
            continue
        raw = get_state(eid)
        val: Any = _onoff(raw) if role.kind == "binary" else _num(raw, role.kind)
        if val is None:
            if raw not in (None, "unavailable", "unknown", ""):
                out.rejected[key] = f"out of range or not a number: {raw!r}"
            continue
        out.values[key] = val
    v = out.values

    # guards (#512)
    if v.get("dhw_tank") is not None and v["dhw_tank"] < R5T_DISCONNECTED_THRESHOLD:
        out.rejected["dhw_tank"] = f"{v.pop('dhw_tank')} °C: no tank connected"
    inlet_eid = mapping.get("inlet_r4t", "")
    if "r9t" in inlet_eid and v.get("inlet_r4t") == 0.0:
        out.rejected["inlet_r4t"] = "R9T reads 0.000: not connected"
        v.pop("inlet_r4t")
    # no tank (R5T about -40 °C, or field setting E-06 off): a 3-way valve on
    # the bus is not a hot-water signal (the hybrid's Intergas makes the
    # hot water itself)
    no_tank = "no tank" in out.rejected.get("dhw_tank", "") or v.get("dhw_tank_installed") == "OFF"
    if no_tank and v.get("threeway_valve") is not None:
        v.pop("threeway_valve")
        out.rejected["threeway_valve"] = "no hot-water tank"
    if "r1t" in mapping.get("outdoor", "") and "outside" not in mapping.get("outdoor", ""):
        out.rejected["outdoor"] = "R1T on the bridge is water, not outdoor air"
        v.pop("outdoor", None)

    for key, val in v.items():
        label = ROLE_BY_KEY[key].label
        if label:
            out.attrs[label] = val
    heating, cooling = v.get("op_heating"), v.get("op_cooling")
    if heating == "ON":
        out.attrs[ATTR_OPERATION_MODE] = OP_MODE_HEATING
    elif cooling == "ON":
        out.attrs[ATTR_OPERATION_MODE] = OP_MODE_COOLING
    elif heating == "OFF" or cooling == "OFF":
        out.attrs[ATTR_OPERATION_MODE] = "Off"
    # The bridge's own heat and electrical power, in kW like ESPAltherma's
    # statistics: the COP chain then uses them (meter > these > estimate).
    if v.get("heat_power") is not None:
        out.attrs[V2_STATS_HEAT_KEY] = round(max(0.0, float(v["heat_power"])) / 1000.0, 3)
    if v.get("hp_power") is not None:
        el = max(0.0, float(v["hp_power"])) + max(0.0, float(v.get("buh_power") or 0.0))
        out.attrs[V2_STATS_KEY] = round(el / 1000.0, 3)
    boiler = v.get("gasboiler_active")
    if boiler is not None:
        # with the valve on the tank, the boiler heats hot water, else space
        dhw = boiler == "ON" and v.get("threeway_valve") == "ON"
        out.attrs[ATTR_BOILER_OPERATION_DEMAND] = "OFF" if dhw else boiler
        out.attrs[ATTR_BOILER_DHW_DEMAND] = "ON" if dhw else "OFF"
        # #288: a non-hybrid unit with an external boiler (C-02 >= 1) is
        # bivalent: its boiler flag then counts like a hybrid's
        if (v.get("external_backup") or 0) >= 1:
            out.attrs[ATTR_BIVALENT_OPERATION] = boiler

    out.missing_required = [a for a in REQUIRED_ATTRIBUTES if a not in out.attrs and a not in NOT_PUBLISHED]
    out.unmapped = [k for k in REQUIRED_ROLES if not mapping.get(k)]
    return out


def expected_units() -> dict[str, str]:
    """Role -> the unit it is read in (shown in the setup, never read)."""
    return {r.key: r.unit for r in ROLES}


# ---------- field settings (the installer's settings, read-only) ----------

_FIELD = re.compile(r"fieldsettings_([0-9a-f])_([0-9a-f]{2})_(.+)$")

# Daikin code -> name used in the summary (diagnostics, model profile hints)
FIELD_SUMMARY: dict[str, str] = {
    "1-00": "curve_heating_low_outdoor", "1-01": "curve_heating_high_outdoor",
    "1-02": "curve_heating_low_outdoor_lwt", "1-03": "curve_heating_high_outdoor_lwt",
    "9-00": "lwt_heating_max", "9-01": "lwt_heating_min", "9-09": "target_dt",
    "9-0B": "emitter_slow", "4-02": "heating_outdoor_max", "5-01": "equilibrium_temp",
    "C-02": "external_backup", "C-03": "bivalent_activation_temp", "C-04": "bivalent_hysteresis",
    "E-00": "unit_type", "E-01": "compressor_type", "E-05": "dhw_operation", "E-06": "dhw_tank_installed",
    "6-0E": "dhw_setpoint_max", "8-0B": "flow_target_heatpump", "8-02": "anti_recycling_time",
}


def field_settings(entities: Mapping[str, Any], prefix: str | None = None) -> dict[str, dict[str, Any]]:
    """Every readable field setting: ``{"9-09": {"name": "delta_t", "value": 5.0}}``.

    ``entities`` maps entity_id -> state. With several bridges only the
    given prefix is read. Unavailable settings (the bridge has not read
    them yet) are left out.
    """
    want = prefix.split(".", 1)[-1] if prefix else None
    out: dict[str, dict[str, Any]] = {}
    for eid, raw in entities.items():
        obj = _object_id(eid)[1]
        m = _FIELD.search(obj)
        if not m or (want is not None and not obj.startswith(want)):
            continue
        if raw in (None, "unavailable", "unknown", ""):
            continue
        code = f"{m.group(1)}-{m.group(2)}".upper()
        val: Any = _onoff(raw) if eid.startswith("binary_sensor.") else _num(raw, "energy")
        if val is None and not eid.startswith("binary_sensor."):
            try:
                val = float(str(raw))
            except ValueError:
                val = str(raw)
        out[code] = {"name": m.group(3), "value": val}
    return dict(sorted(out.items()))


def field_summary(settings: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The settings the integration uses or shows, by readable name."""
    return {name: settings[code]["value"] for code, name in FIELD_SUMMARY.items() if code in settings}
