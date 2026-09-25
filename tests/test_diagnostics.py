"""Tests for diagnostics (Batch 6b-2)."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.diagnostics import (
    ATTRS_SAMPLE_CAP,
    TO_REDACT,
    async_get_config_entry_diagnostics,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _entry(coord=None, data=None, options=None):
    e = MagicMock()
    e.entry_id = "test_entry"
    e.version = 1
    e.title = "Daikin Cycle ML"
    e.data = data or {
        "source_sensor": "sensor.althermasensors",
        "model": "epra12eav3",
    }
    e.options = options or {
        "notify_service": "notify.telegram_rachid",
        "short_run_threshold_min": 20,
    }
    e.runtime_data = coord
    return e


def _coord(snap=None, store=None, db=None):
    c = MagicMock()
    c.data = snap if snap is not None else DataSnapshot()
    c.store = store if store is not None else CycleStore()
    c.db = db
    return c


async def test_diagnostics_without_coordinator():
    out = await async_get_config_entry_diagnostics(MagicMock(), _entry(coord=None))
    assert out == {"error": "coordinator_not_ready"}


async def test_diagnostics_top_level_shape():
    out = await async_get_config_entry_diagnostics(MagicMock(), _entry(coord=_coord()))
    assert set(out.keys()) >= {"entry", "coordinator", "store", "database", "baseline"}


async def test_diagnostics_entry_redacts_notify_service():
    out = await async_get_config_entry_diagnostics(MagicMock(), _entry(coord=_coord()))
    assert out["entry"]["options"]["notify_service"] == "**REDACTED**"
    assert out["entry"]["options"]["short_run_threshold_min"] == 20


async def test_diagnostics_coordinator_state():
    snap = DataSnapshot(state="running", mode="Heating", missing_attrs=["x"])
    out = await async_get_config_entry_diagnostics(
        MagicMock(), _entry(coord=_coord(snap=snap))
    )
    assert out["coordinator"]["state"] == "running"
    assert out["coordinator"]["mode"] == "Heating"
    assert out["coordinator"]["missing_attrs"] == ["x"]


async def test_diagnostics_attrs_sample_capped():
    snap = DataSnapshot(attrs={f"k{i}": i for i in range(50)})
    out = await async_get_config_entry_diagnostics(
        MagicMock(), _entry(coord=_coord(snap=snap))
    )
    assert len(out["coordinator"]["attrs_sample"]) == ATTRS_SAMPLE_CAP


async def test_diagnostics_store_counts():
    st = CycleStore()
    st.add_cycle({"start_ts": 1, "duration_s": 100})
    st.increment("x", 5)
    out = await async_get_config_entry_diagnostics(
        MagicMock(), _entry(coord=_coord(store=st))
    )
    assert out["store"]["cycle_count"] == 1
    assert out["store"]["counters"]["x"] == 5


async def test_diagnostics_db_none():
    out = await async_get_config_entry_diagnostics(
        MagicMock(), _entry(coord=_coord(db=None))
    )
    assert out["database"]["path"] is None
    assert out["database"]["is_open"] is False
    assert out["database"]["counts"] == {}


async def test_diagnostics_db_counts():
    db = MagicMock()
    db.is_open = True
    db.path = "/tmp/x.db"
    mapping = {"cycles": 3, "features": 2, "model_state": 1, "alerts": 0}

    async def fake_count(table):
        return mapping[table]

    db.async_count = fake_count
    out = await async_get_config_entry_diagnostics(
        MagicMock(), _entry(coord=_coord(db=db))
    )
    assert out["database"]["counts"] == mapping
    assert out["database"]["path"] == "/tmp/x.db"


async def test_diagnostics_db_closed_no_counts():
    db = MagicMock()
    db.is_open = False
    db.path = "/tmp/y.db"
    out = await async_get_config_entry_diagnostics(
        MagicMock(), _entry(coord=_coord(db=db))
    )
    assert out["database"]["counts"] == {}
    assert out["database"]["is_open"] is False


def test_redact_set_contains_notify_service():
    assert "notify_service" in TO_REDACT
