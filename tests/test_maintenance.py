"""Batch 11b-2 tests: maintenance hook + service + retention options."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
import voluptuous as vol

from custom_components.daikin_cycle_ml.const import (
    DEFAULT_ALERT_RETENTION_DAYS,
    DEFAULT_CYCLE_RETENTION_DAYS,
    DEFAULT_RETENTION_ENABLED,
    DEFAULT_VACUUM_ENABLED,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.services import (
    SCHEMA_RUN_MAINTENANCE,
    SERVICE_RUN_MAINTENANCE,
    async_register_services,
)


class _Entry:
    def __init__(self, entry_id="e1", data=None, options=None):
        self.entry_id = entry_id
        self.data = data or {
            "source_sensor": "sensor.x",
            "model": "basisprofiel",
        }
        self.options = options or {}


class FakeDB:
    def __init__(self, last_ts=None):
        self.last_ts = last_ts
        self.set_calls = []
        self.run_calls = []
        self.raise_on_run = False

    async def async_get_model_state(self, key, default=None):
        return self.last_ts

    async def async_set_model_state(self, key, value):
        self.set_calls.append((key, value))

    async def async_run_maintenance(self, **kw):
        if self.raise_on_run:
            raise RuntimeError("boom")
        self.run_calls.append(kw)
        return {"cycles_deleted": 5, "alerts_deleted": 2}


def _coord(hass, options=None, db=None):
    c = DaikinCycleMLCoordinator(hass, _Entry(options=options))
    c.db = db
    return c


async def test_setup_maintenance_schedules_3am(hass):
    c = _coord(hass)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_change"
    ) as m:
        await c.async_setup_maintenance()
        assert m.call_count == 1
        _a, kwargs = m.call_args
        assert kwargs.get("hour") == 3
        assert kwargs.get("minute") == 0
        assert kwargs.get("second") == 0


async def test_setup_maintenance_idempotent(hass):
    c = _coord(hass)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_change"
    ) as m:
        await c.async_setup_maintenance()
        await c.async_setup_maintenance()
        assert m.call_count == 1


async def test_run_maintenance_skips_recent(hass):
    db = FakeDB(last_ts=time.time() - 3600)
    c = _coord(hass, db=db)
    res = await c.async_run_maintenance()
    assert res["ok"] is False
    assert res["reason"] == "too_soon"
    assert db.run_calls == []


async def test_run_maintenance_runs_when_stale(hass):
    db = FakeDB(last_ts=time.time() - 30 * 3600)
    c = _coord(hass, db=db)
    res = await c.async_run_maintenance()
    assert res["ok"] is True
    assert db.run_calls
    assert any(k == "last_maintenance_ts" for k, _ in db.set_calls)


async def test_run_maintenance_first_run_no_ts(hass):
    db = FakeDB(last_ts=None)
    c = _coord(hass, db=db)
    res = await c.async_run_maintenance()
    assert res["ok"] is True


async def test_run_maintenance_disabled_skips(hass):
    db = FakeDB(last_ts=None)
    c = _coord(hass, options={"retention_enabled": False}, db=db)
    res = await c.async_run_maintenance()
    assert res["ok"] is False
    assert res["reason"] == "retention_disabled"


async def test_run_maintenance_no_db(hass):
    c = _coord(hass, db=None)
    res = await c.async_run_maintenance()
    assert res["ok"] is False
    assert res["reason"] == "no_db"


async def test_run_maintenance_exception_caught(hass):
    db = FakeDB(last_ts=None)
    db.raise_on_run = True
    c = _coord(hass, db=db)
    res = await c.async_run_maintenance()
    assert res["ok"] is False
    assert res["reason"] == "exception"


async def test_force_bypasses_guard(hass):
    db = FakeDB(last_ts=time.time() - 60)
    c = _coord(hass, db=db)
    res = await c.async_run_maintenance(force=True)
    assert res["ok"] is True


async def test_params_override_options(hass):
    db = FakeDB(last_ts=None)
    c = _coord(hass, options={"cycle_retention_days": 30}, db=db)
    await c.async_run_maintenance(
        cycle_retention_days=7, alert_retention_days=3, vacuum=False
    )
    kw = db.run_calls[0]
    assert kw["cycle_retention_days"] == 7
    assert kw["alert_retention_days"] == 3
    assert kw["vacuum"] is False


async def test_options_used_when_no_override(hass):
    db = FakeDB(last_ts=None)
    c = _coord(
        hass,
        options={
            "cycle_retention_days": 45,
            "alert_retention_days": 15,
            "vacuum_enabled": False,
        },
        db=db,
    )
    await c.async_run_maintenance()
    kw = db.run_calls[0]
    assert kw["cycle_retention_days"] == 45
    assert kw["alert_retention_days"] == 15
    assert kw["vacuum"] is False


async def test_service_registration_idempotent(hass):
    await async_register_services(hass)
    await async_register_services(hass)
    assert hass.services.has_service("daikin_cycle_ml", SERVICE_RUN_MAINTENANCE)


def test_schema_requires_entry_id():
    SCHEMA_RUN_MAINTENANCE({"entry_id": "x"})


def test_schema_optional_absent_by_default():
    data = SCHEMA_RUN_MAINTENANCE({"entry_id": "x"})
    assert "cycle_retention_days" not in data
    assert "alert_retention_days" not in data
    assert "vacuum" not in data


def test_schema_rejects_missing_entry_id():
    with pytest.raises(vol.Invalid):
        SCHEMA_RUN_MAINTENANCE({})


def test_schema_override():
    data = SCHEMA_RUN_MAINTENANCE(
        {
            "entry_id": "x",
            "cycle_retention_days": 30,
            "alert_retention_days": 7,
            "vacuum": False,
        }
    )
    assert data["cycle_retention_days"] == 30
    assert data["alert_retention_days"] == 7
    assert data["vacuum"] is False


def test_new_defaults_defined():
    assert DEFAULT_RETENTION_ENABLED is True
    assert DEFAULT_CYCLE_RETENTION_DAYS == 90
    assert DEFAULT_ALERT_RETENTION_DAYS == 30
    assert DEFAULT_VACUUM_ENABLED is True


def test_options_flow_source_contains_new_fields():
    src = (Path(__file__).parent.parent / "config_flow.py").read_text()
    for key in (
        "retention_enabled",
        "cycle_retention_days",
        "alert_retention_days",
        "vacuum_enabled",
    ):
        assert (chr(34) + key + chr(34)) in src, key

