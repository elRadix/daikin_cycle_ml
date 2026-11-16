"""Reproduction + regression for #381 (HA deprecations) and #382 (Recorder 16KB).

#381: device_registry.devices mapping + DeviceEntry.config_entries deprecated
      in diagnostics.py:265-266. Deadlines HA 2027.9 / 2027.10.
#382: alerts_today attrs exceed 16384-byte Recorder limit -> HA drops all
      attributes from history. Prod-1: 24310 bytes / 27 alerts (2026-11-16).
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import diagnostics
from custom_components.daikin_cycle_ml.diagnostics import _device_registry
from custom_components.daikin_cycle_ml.sensor import (
    _ALERTS_ATTR_BYTE_LIMIT,
    _ALERTS_ATTR_MAX_ITEMS,
    _attrs_alerts_today,
)

DOMAIN = "daikin_cycle_ml"


def _alerts(n: int, msg_chars: int) -> list[dict]:
    msg = "x" * msg_chars
    return [
        {
            "ts": 1794864283.64 + i * 60,
            "alert_type": "test_alert",
            "severity": "warning",
            "message": msg,
            "aggregated_count": 1,
        }
        for i in range(n)
    ]


def _snap(alerts: list[dict], total: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        alerts_today={
            "since": 1794780000.0,
            "total": total if total is not None else len(alerts),
            "by_type": {"test_alert": len(alerts)},
            "by_severity": {"warning": len(alerts)},
            "alerts": alerts,
            "truncated": False,
        }
    )


def _size(attrs: dict) -> int:
    return len(json.dumps(attrs, separators=(",", ":")))


# ---------- Issue #382: Recorder 16KB (3 branches) ----------

def test_alerts_today_branch1_small_fits_no_truncation():
    """Small list <14KB: full list returned, no truncated_reason."""
    snap = _snap(_alerts(3, 200))
    attrs = _attrs_alerts_today(snap, None)
    assert _size(attrs) <= _ALERTS_ATTR_BYTE_LIMIT
    assert attrs["alerts_shown"] == 3
    assert attrs["alerts_total"] == 3
    assert "truncated_reason" not in attrs
    assert attrs["truncated"] is False


def test_alerts_today_branch2_prod_27_alerts_capped():
    """Prod-1: 27 alerts * 800B = 22KB > 14KB -> cap to 10, fits."""
    snap = _snap(_alerts(27, 800))
    attrs = _attrs_alerts_today(snap, None)
    assert _size(attrs) <= _ALERTS_ATTR_BYTE_LIMIT
    assert attrs["alerts_shown"] == _ALERTS_ATTR_MAX_ITEMS
    assert attrs["alerts_total"] == 27
    assert attrs["truncated"] is True
    assert attrs["truncated_reason"] == "attr_size_limit"


def test_alerts_today_branch3_even_capped_too_big_drops_list():
    """10 alerts * 3KB = 30KB > 14KB even after cap -> empty list."""
    snap = _snap(_alerts(_ALERTS_ATTR_MAX_ITEMS, 3000))
    attrs = _attrs_alerts_today(snap, None)
    assert _size(attrs) <= _ALERTS_ATTR_BYTE_LIMIT
    assert attrs["alerts"] == []
    assert attrs["alerts_shown"] == 0
    assert attrs["alerts_total"] == _ALERTS_ATTR_MAX_ITEMS
    assert attrs["truncated"] is True
    assert attrs["truncated_reason"] == "attr_size_limit"


def test_alerts_today_empty_alerts_happy_path():
    """Empty alerts -> branch 1, no truncation."""
    snap = _snap([])
    attrs = _attrs_alerts_today(snap, None)
    assert attrs["alerts"] == []
    assert attrs["alerts_shown"] == 0
    assert attrs["alerts_total"] == 0
    assert "truncated_reason" not in attrs


def test_alerts_today_aggregates_preserved_in_branch2():
    """by_type / by_severity survive the cap."""
    snap = _snap(_alerts(27, 800))
    attrs = _attrs_alerts_today(snap, None)
    assert attrs["by_type"] == {"test_alert": 27}
    assert attrs["by_severity"] == {"warning": 27}
    assert attrs["total"] == 27


def test_alerts_today_aggregates_preserved_in_branch3():
    """by_type / by_severity survive the drop."""
    snap = _snap(_alerts(_ALERTS_ATTR_MAX_ITEMS, 3000))
    attrs = _attrs_alerts_today(snap, None)
    assert attrs["by_type"] == {"test_alert": _ALERTS_ATTR_MAX_ITEMS}
    assert attrs["by_severity"] == {"warning": _ALERTS_ATTR_MAX_ITEMS}
    assert attrs["total"] == _ALERTS_ATTR_MAX_ITEMS


# ---------- Issue #381: HA deprecations ----------

def test_device_registry_no_deprecated_mapping():
    """Static: _device_registry must not use reg.devices mapping."""
    src = inspect.getsource(diagnostics._device_registry)
    assert "reg.devices" not in src, (
        "Uses reg.devices (deprecated HA 2027.9). Issue #381."
    )


def test_device_registry_no_deprecated_config_entries():
    """Static: _device_registry must not use dev.config_entries."""
    src = inspect.getsource(diagnostics._device_registry)
    assert ".config_entries" not in src, (
        "Uses dev.config_entries (deprecated HA 2027.10). Issue #381."
    )


def test_device_registry_uses_modern_api():
    """Static: _device_registry uses async_entries_for_config_entry."""
    src = inspect.getsource(diagnostics._device_registry)
    assert "async_entries_for_config_entry" in src, (
        "Must use reg.async_entries_for_config_entry(entry.entry_id). "
        "Issue #381."
    )


@pytest.mark.asyncio
async def test_device_registry_returns_device_when_found(hass):
    """Branch 1: device registered -> returns device info."""
    from homeassistant.helpers import device_registry as dr

    entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry", data={})
    entry.add_to_hass(hass)

    reg = dr.async_get(hass)
    dev = reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "test_device")},
        name="Test device",
        model="epra12eav3",
    )

    result = _device_registry(hass, entry)
    assert not result.get("missing")
    assert result["id"] == dev.id
    assert result["model"] == "epra12eav3"


@pytest.mark.asyncio
async def test_device_registry_returns_missing_when_no_device(hass):
    """Branch 2: no device registered -> missing sentinel."""
    entry = MockConfigEntry(
        domain=DOMAIN, entry_id="orphan_entry", data={},
    )
    entry.add_to_hass(hass)

    result = _device_registry(hass, entry)
    assert result == {"missing": True, "reason": "no_device_for_entry"}
