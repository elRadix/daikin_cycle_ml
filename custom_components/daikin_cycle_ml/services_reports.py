"""Period-report services (#508): get_report, export_reports, rebuild_reports.

The Reports card reads through ``get_report`` (a response-only service), so
the reports never sit in large state attributes (R401).
"""
from __future__ import annotations

from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .engine import period_reports as pr
from .storage import report_query as rq
from .storage.report_query import HISTORY_DEFAULT

SERVICE_GET_REPORT = "get_report"
SERVICE_EXPORT_REPORTS = "export_reports"
SERVICE_REBUILD_REPORTS = "rebuild_reports"
REPORT_SERVICES = (SERVICE_GET_REPORT, SERVICE_EXPORT_REPORTS, SERVICE_REBUILD_REPORTS)

_MODES = [pr.ALL, *pr.MODES]
_DAY = vol.Match(r"^\d{4}-\d{2}-\d{2}\Z")

SCHEMA_GET_REPORT = vol.Schema({
    vol.Optional("entry_id"): str,
    vol.Optional("period_type", default="month"): vol.In(list(pr.PERIOD_TYPES)),
    vol.Optional("period"): vol.Match(r"^\d{4}(-W\d{2}|-\d{2}|/\d{2})?\Z"),
    vol.Optional("mode", default=pr.ALL): vol.In(_MODES),
    vol.Optional("compare", default="previous"): vol.In(["previous", "last_year", "none"]),
    vol.Optional("history", default=HISTORY_DEFAULT): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
    vol.Optional("include_days", default=False): bool,
})

SCHEMA_EXPORT_REPORTS = vol.Schema({
    vol.Optional("entry_id"): str,
    vol.Optional("table", default="periods"): vol.In(["periods", "days"]),
    vol.Optional("period_type"): vol.In(list(pr.PERIOD_TYPES)),
    vol.Optional("mode"): vol.In(_MODES),
    vol.Optional("first_day"): _DAY,
    vol.Optional("last_day"): _DAY,
    vol.Optional("format", default="json"): vol.In(["json", "csv"]),
})

SCHEMA_REBUILD_REPORTS = vol.Schema({
    vol.Optional("entry_id"): str,
    vol.Optional("full", default=False): bool,
})


def _conn(coord: Any) -> Any:
    db = getattr(coord, "db", None)
    if db is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="database_unavailable")
    return db._require()


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> Any:
    from .services import _resolve_optional_coordinator  # pylint: disable=import-outside-toplevel
    return _resolve_optional_coordinator(hass, call.data.get("entry_id"))


async def _handle_get_report(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _coordinator(hass, call)
    return await rq.get_report(
        _conn(coord),
        period_type=call.data.get("period_type", "month"),
        key=call.data.get("period"),
        mode=call.data.get("mode", pr.ALL),
        against=call.data.get("compare", "previous"),
        history=call.data.get("history", HISTORY_DEFAULT),
        include_days=call.data.get("include_days", False),
        scheme=coord.degree_day_scheme,
        season_start_month=pr.season_start_month(getattr(coord, "options", None)),
    )


async def _handle_export_reports(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _coordinator(hass, call)
    return await rq.export(
        _conn(coord), table=call.data.get("table", "periods"),
        period_type=call.data.get("period_type"), mode=call.data.get("mode"),
        first_day=call.data.get("first_day"), last_day=call.data.get("last_day"),
        fmt=call.data.get("format", "json"),
    )


async def _handle_rebuild_reports(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _coordinator(hass, call)
    _conn(coord)
    full = bool(call.data.get("full", False))
    stats = await coord.async_build_reports(full=full)
    if stats is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="reports_build_failed")
    return {"full": full, **stats}


def async_register_report_services(hass: HomeAssistant) -> None:
    for name, handler, schema in (
        (SERVICE_GET_REPORT, _handle_get_report, SCHEMA_GET_REPORT),
        (SERVICE_EXPORT_REPORTS, _handle_export_reports, SCHEMA_EXPORT_REPORTS),
        (SERVICE_REBUILD_REPORTS, _handle_rebuild_reports, SCHEMA_REBUILD_REPORTS),
    ):
        hass.services.async_register(
            DOMAIN, name, partial(handler, hass), schema=schema,
            supports_response=(SupportsResponse.ONLY if name != SERVICE_REBUILD_REPORTS
                               else SupportsResponse.OPTIONAL),
        )
