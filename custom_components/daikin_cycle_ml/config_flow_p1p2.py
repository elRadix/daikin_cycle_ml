"""Setup step for the P1/P2 MQTT bridge (#512): one entity picker per role,
filled in from the detection, with the live value and the expected unit.

The unit shown is fixed per role (engine/p1p2.py), never the entity's own
``unit_of_measurement``: the bridge leaves it empty on most entities.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .engine import p1p2

# Roles shown in the setup, in this order. The rest are detected and used
# when present (meters, refrigerant, room) but not asked for.
FORM_ROLES: tuple[str, ...] = (
    "op_heating", "op_cooling", "threeway_valve", "defrost", "compressor_hz",
    "leaving_r2t", "leaving_r1t", "inlet_r4t", "outdoor", "flow", "pump",
    "buh1", "buh2", "lw_setpoint", "dhw_tank", "heat_power", "hp_power",
    "buh_power", "gasboiler_active",
)
# Without these the heat pump's runs cannot be followed.
CRITICAL_ROLES: tuple[str, ...] = (
    "op_heating", "defrost", "compressor_hz", "leaving_r2t", "inlet_r4t", "outdoor", "flow",
)


def schema(current: Mapping[str, str]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for key in FORM_ROLES:
        role = p1p2.ROLE_BY_KEY[key]
        sel = selector.EntitySelector(selector.EntitySelectorConfig(domain=role.domain))
        default = current.get(key)
        marker = vol.Optional(key, description={"suggested_value": default}) if default else vol.Optional(key)
        fields[marker] = sel
    return vol.Schema(fields)


def preview(hass: HomeAssistant, mapping: Mapping[str, str]) -> str:
    """One line per mapped role: entity, value read, expected unit."""
    res = p1p2.resolve(mapping, lambda eid: getattr(hass.states.get(eid), "state", None))
    lines = []
    for key in FORM_ROLES:
        eid = mapping.get(key)
        if not eid:
            continue
        role = p1p2.ROLE_BY_KEY[key]
        if key in res.values:
            mark, val = "✓", f"{res.values[key]} {role.unit}".strip()
        else:
            mark, val = "⚠", res.rejected.get(key, "no value")
        lines.append(f"{mark} `{eid}`: {val}")
    return "\n".join(lines) or "—"


def validate(hass: HomeAssistant, user_input: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """The map to save and the errors per field."""
    mapping = {k: str(v) for k, v in user_input.items() if k in p1p2.ROLE_BY_KEY and v}
    errors: dict[str, str] = {}
    for key in CRITICAL_ROLES:
        if not mapping.get(key):
            errors[key] = "p1p2_role_required"
    for key, eid in mapping.items():
        if hass.states.get(eid) is None:
            errors[key] = "entity_not_found"
    if "r1t" in mapping.get("outdoor", "") and "outside" not in mapping.get("outdoor", ""):
        errors["outdoor"] = "p1p2_r1t_is_water"
    return mapping, errors


def detect(hass: HomeAssistant, prefix: str | None = None) -> p1p2.Detection:
    return p1p2.detect(hass.states.async_entity_ids(), prefix)
