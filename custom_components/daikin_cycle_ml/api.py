"""B6: REST view exposing cop_hourly via /api/daikin_cycle_ml/cop_hourly."""
from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp.web import Request, Response
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import (
    COP_HOURLY_API_DEFAULT_DAYS,
    COP_HOURLY_API_MAX_DAYS,
    COP_HOURLY_API_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _parse_days(raw: str | None) -> int | None:
    """Parse days query param. Returns None on invalid."""
    if raw is None:
        return COP_HOURLY_API_DEFAULT_DAYS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 1 or value > COP_HOURLY_API_MAX_DAYS:
        return None
    return value


class CopHourlyView(HomeAssistantView):
    """GET /api/daikin_cycle_ml/cop_hourly."""

    url = COP_HOURLY_API_URL
    name = "api:daikin_cycle_ml:cop_hourly"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: Request) -> Response:
        days = _parse_days(request.query.get("days"))
        if days is None:
            return self.json_message(
                "days must be int in [1, "
                f"{COP_HOURLY_API_MAX_DAYS}]",
                status_code=400,
            )
        mode_raw = request.query.get("mode")
        mode: str | None
        if mode_raw is None or not str(mode_raw).strip():
            mode = None
        else:
            mode = str(mode_raw)
        entries = self._hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return self.json_message("no config entry", status_code=503)
        coord: Any = getattr(entries[0], "runtime_data", None)
        if coord is None or getattr(coord, "db", None) is None:
            return self.json_message(
                "coordinator unavailable", status_code=503
            )
        since_ts = time.time() - float(days) * 86400.0
        try:
            rows = await coord.db.async_query_cop_hourly(
                since_ts=since_ts, mode=mode
            )
        except Exception:
            _LOGGER.exception("cop_hourly query failed")
            return self.json_message("query failed", status_code=500)
        return self.json({
            "days": days,
            "mode": mode,
            "count": len(rows),
            "rows": rows,
        })
