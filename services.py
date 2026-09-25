"""Services for Daikin Cycle ML (Batch 6b-1)."""
from __future__ import annotations

import csv
import io
import logging
import time
from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_RESET_COUNTERS = "reset_counters"
SERVICE_EXPORT_CYCLES = "export_cycles"
SERVICE_LABEL_CYCLE = "label_cycle"
SERVICE_RECOMPUTE_BASELINE = "recompute_baseline"
SERVICE_RUN_MAINTENANCE = "run_maintenance"
ATTR_CYCLE_RETENTION_DAYS = "cycle_retention_days"
ATTR_ALERT_RETENTION_DAYS = "alert_retention_days"
ATTR_VACUUM = "vacuum"

ATTR_ENTRY_ID = "entry_id"
ATTR_COUNTERS = "counters"
ATTR_DAYS = "days"
ATTR_FORMAT = "format"
ATTR_CYCLE_ID = "cycle_id"
ATTR_LABEL = "label"

SCHEMA_RESET = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_COUNTERS): vol.Any(None, [str]),
})

SCHEMA_EXPORT = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_DAYS, default=30): vol.All(int, vol.Range(min=1, max=3650)),
    vol.Optional(ATTR_FORMAT, default="json"): vol.In(["json", "csv"]),
})

SCHEMA_LABEL = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Required(ATTR_CYCLE_ID): int,
    vol.Required(ATTR_LABEL): str,
})

SCHEMA_BASELINE = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_DAYS, default=7): vol.All(int, vol.Range(min=1, max=365)),
})


SCHEMA_RUN_MAINTENANCE = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_CYCLE_RETENTION_DAYS): int,
    vol.Optional(ATTR_ALERT_RETENTION_DAYS): int,
    vol.Optional(ATTR_VACUUM): bool,
})


def _resolve_coordinator(hass: HomeAssistant, entry_id: str) -> Any:
    entry: ConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise HomeAssistantError(f"Unknown config entry: {entry_id}")
    coord = getattr(entry, "runtime_data", None)
    if coord is None:
        raise HomeAssistantError(f"Coordinator not ready for entry {entry_id}")
    return coord


# ---------- pure do-functions (unit-testable) ----------

def _do_reset_counters(coordinator: Any, counters: list[str] | None) -> dict[str, Any]:
    coordinator.store.reset(counters)
    return {"reset": True, "counters": counters if counters else "all"}


def _do_export_cycles(coordinator: Any, days: int, fmt: str) -> dict[str, Any]:
    cutoff = time.time() - float(days) * 86400.0
    cycles = [
        dict(c) for c in coordinator.store.cycles()
        if isinstance(c.get("start_ts"), (int, float)) and c["start_ts"] >= cutoff
    ]
    if fmt == "csv":
        buf = io.StringIO()
        if cycles:
            writer = csv.DictWriter(buf, fieldnames=list(cycles[0].keys()))
            writer.writeheader()
            writer.writerows(cycles)
        return {"format": "csv", "days": days, "content": buf.getvalue()}
    return {"format": "json", "days": days, "cycles": cycles}


async def _do_label_cycle(coordinator: Any, cycle_id: int, label: str) -> dict[str, Any]:
    db = getattr(coordinator, "db", None)
    if db is None:
        raise HomeAssistantError("Database not available")
    ok = await db.async_label_cycle(cycle_id, label)
    return {"labeled": bool(ok), "cycle_id": cycle_id, "label": label}


async def _do_recompute_baseline(coordinator: Any, days: int) -> dict[str, Any]:
    db = getattr(coordinator, "db", None)
    if db is None:
        return {"computed": False, "reason": "no_db", "days": days}
    mb = getattr(coordinator, "baseline", None)
    if mb is None:
        return {"computed": False, "reason": "no_baseline", "days": days}
    try:
        cycles = await db.async_fetch_cycles(days=days)
    except Exception as err:
        return {
            "computed": False,
            "reason": "fetch_failed",
            "days": days,
            "error": str(err),
        }
    if not cycles:
        return {"computed": False, "reason": "no_data", "days": days, "samples": 0}
    from .ml.features import extract_feature_vector, is_valid_record
    try:
        mb.reset()
    except Exception:
        pass
    fed = 0
    for rec in cycles:
        if not is_valid_record(rec):
            continue
        try:
            vec = extract_feature_vector(rec)
        except Exception:
            continue
        mode = rec.get("mode") or "unknown"
        try:
            mb.update(mode, vec)
            fed += 1
        except Exception:
            continue
    try:
        await db.async_set_model_state("baseline_state", mb.to_dict())
    except Exception:
        pass
    return {"computed": True, "days": days, "samples": fed}


# ---------- HA handlers ----------

async def _handle_reset_counters(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return _do_reset_counters(coord, call.data.get(ATTR_COUNTERS))


async def _handle_export_cycles(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return _do_export_cycles(coord, call.data[ATTR_DAYS], call.data[ATTR_FORMAT])


async def _handle_label_cycle(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return await _do_label_cycle(coord, call.data[ATTR_CYCLE_ID], call.data[ATTR_LABEL])


async def _handle_recompute_baseline(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return await _do_recompute_baseline(coord, call.data[ATTR_DAYS])


async def _handle_run_maintenance(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    runner = getattr(coord, "async_run_maintenance", None)
    if runner is None:
        return {"ok": False, "reason": "not_supported"}
    return await runner(
        cycle_retention_days=call.data.get(ATTR_CYCLE_RETENTION_DAYS),
        alert_retention_days=call.data.get(ATTR_ALERT_RETENTION_DAYS),
        vacuum=call.data.get(ATTR_VACUUM),
        force=True,
    )


async def async_register_services(hass: HomeAssistant) -> None:
    """Idempotent registration at DOMAIN level."""
    if hass.services.has_service(DOMAIN, SERVICE_RUN_MAINTENANCE):
        return
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_COUNTERS,
        partial(_handle_reset_counters, hass), schema=SCHEMA_RESET,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_CYCLES,
        partial(_handle_export_cycles, hass), schema=SCHEMA_EXPORT,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LABEL_CYCLE,
        partial(_handle_label_cycle, hass), schema=SCHEMA_LABEL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RECOMPUTE_BASELINE,
        partial(_handle_recompute_baseline, hass), schema=SCHEMA_BASELINE,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RUN_MAINTENANCE,
        partial(_handle_run_maintenance, hass), schema=SCHEMA_RUN_MAINTENANCE,
    )
    _LOGGER.info("Daikin Cycle ML services registered")
