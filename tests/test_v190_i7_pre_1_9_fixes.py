"""v1.9.0 I7 — pre-release cleanup (4.15a, 4.16, 4.17) tests."""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.storage.db import CycleDB


# ---------- helpers ----------

def _coord() -> DaikinCycleMLCoordinator:
    return object.__new__(DaikinCycleMLCoordinator)


def _snap() -> Any:
    n = SimpleNamespace()
    for f in (
        "lwt_setpoint", "lwt_actual", "indoor_temp", "flow_lmin", "outdoor_temp",
        "cop_degradation_week_pct", "cop_trend_30d",
    ):
        setattr(n, f, None)
    return n


def _coord_for_ctx() -> Any:
    c = object.__new__(DaikinCycleMLCoordinator)
    c._avg_duration_7d_min = 42
    c.store = MagicMock()
    c.store.last_cycle.return_value = {"duration_s": 1800}
    c.store.cycles_in_window.return_value = 0
    c.store.cycles_in_window_mode.return_value = 0
    c.store.cycles_today.return_value = []
    c.options = {}
    c._setpoint_history = []
    c._kmeans_stale = {}
    c._energy_daily_anomaly = {}
    c._defrost_7d_sum = 0
    c._buh_7d_ratio = 0.0
    c.config_entry = None
    return c


# ---------- 4.16: defrost duration (DB) ----------

@pytest.mark.asyncio
async def test_defrost_duration_none_when_conn_absent() -> None:
    c = CycleDB.__new__(CycleDB)
    c._conn = None
    assert await c.async_defrost_duration_since(0.0) is None


@pytest.mark.asyncio
async def test_defrost_duration_returns_sum() -> None:
    c = CycleDB.__new__(CycleDB)
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=(300.0,))
    cur.close = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    c._conn = conn
    assert await c.async_defrost_duration_since(0.0) == 300.0


@pytest.mark.asyncio
async def test_defrost_duration_none_when_no_rows() -> None:
    c = CycleDB.__new__(CycleDB)
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=(None,))
    cur.close = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    c._conn = conn
    assert await c.async_defrost_duration_since(0.0) is None


@pytest.mark.asyncio
async def test_defrost_duration_none_on_exception() -> None:
    c = CycleDB.__new__(CycleDB)
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("x"))
    c._conn = conn
    assert await c.async_defrost_duration_since(0.0) is None


# ---------- 4.16: defrost duration (ctx) ----------

def test_defrost_ctx_duration_10min() -> None:
    c = _coord_for_ctx()
    c._defrost_7d_duration_s = 600.0
    ctx = c._build_alert_context(_snap())
    assert ctx["defrost_excessive"]["duration_7d_min"] == 10


def test_defrost_ctx_duration_absent_falls_back_to_zero() -> None:
    c = _coord_for_ctx()
    ctx = c._build_alert_context(_snap())
    assert ctx["defrost_excessive"]["duration_7d_min"] == 0


# ---------- 4.15a: retention defaults ----------

def test_db_alert_retention_default_is_90() -> None:
    sig = inspect.signature(CycleDB.async_run_maintenance)
    assert sig.parameters["alert_retention_days"].default == 90


def test_coordinator_retention_fallback_uses_const() -> None:
    import custom_components.daikin_cycle_ml.coordinator as co
    src = open(co.__file__).read()
    assert "opts.get('alert_retention_days', DEFAULT_ALERT_RETENTION_DAYS)" in src
    assert "opts.get('cycle_retention_days', DEFAULT_CYCLE_RETENTION_DAYS)" in src


# ---------- 4.17: energy sigma/z/mean None semantics ----------

def _energy_bare(db: Any) -> Any:
    c = _coord()
    c.db = db
    return c


@pytest.mark.asyncio
async def test_energy_sigma_none_when_n_lt_2() -> None:
    baseline = {"heating": {"n": 1, "mean": 2.5, "m2": 0.0}}
    today = {"heating_el_kwh": 5.0}
    db = SimpleNamespace()
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    r = await _energy_bare(db)._compute_energy_daily_anomaly()
    assert r["baseline_el_sigma"] is None
    assert r["z_score"] is None
    assert r["baseline_el_mean"] == 2.5
    assert r["samples"] == 1


@pytest.mark.asyncio
async def test_energy_sigma_present_when_n_gte_2() -> None:
    baseline = {"heating": {"n": 3, "mean": 2.0, "m2": 3.0}}
    today = {"heating_el_kwh": 5.0}
    db = SimpleNamespace()
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    r = await _energy_bare(db)._compute_energy_daily_anomaly()
    assert r["baseline_el_sigma"] == 1.0
    assert r["z_score"] == 3.0


@pytest.mark.asyncio
async def test_energy_all_corrupt_mean_sigma_z_none() -> None:
    baseline = {"heating": {"n": 10, "mean": 3.0, "m2": 40.0}}
    today = {"heating_el_kwh": "bad"}
    db = SimpleNamespace()
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    r = await _energy_bare(db)._compute_energy_daily_anomaly()
    assert r["baseline_el_mean"] is None
    assert r["baseline_el_sigma"] is None
    assert r["z_score"] is None
    assert r["samples"] == 0


# ---------- 4.17: schema + labels ----------

def test_energy_schema_has_samples_row() -> None:
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_SCHEMA
    fields = [f[1] for f in ALERT_SCHEMA["energy_daily_anomaly"]]
    assert "samples" in fields
    assert len(fields) == 6


def test_energy_labels_have_samples_both_langs() -> None:
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_LABELS
    assert ALERT_LABELS["en"]["samples"] == "Samples"
    assert ALERT_LABELS["nl"]["samples"] == "Monsters"
