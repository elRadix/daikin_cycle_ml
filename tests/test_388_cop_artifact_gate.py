"""#388: COP sensor gate + flagged-sample exclusion (prod-1 regression).

Prod-1 config: cop_sensor_entity=sensor.altherma_global_cop (user COP
sensor wins the COP cascade, cop_source="cop_sensor"),
power_sensor_entity=sensor.warmtepomp_power, model=epra12eav3.

Observed on prod-1 (v1.22.10):
  * cop_today.cop_max = 14.0 while MAX_COP = 11.0
  * thermal_power_live.input_cop = 9.829 (2026-11-17, LWT 28.6 / T_out 8)
  * cop_physically_impossible = off
  * cop_normalized_a7w35 = null with cop_measured 6.169, LWT 31.3, T_out 11.4

Each test asserts the CORRECT behaviour; a failing test reproduces a bug.
"""
from __future__ import annotations

import math
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import MAX_COP
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.engine.physics import classify_cop_sample
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _coord_with_cop_sensor(value: str) -> DaikinCycleMLCoordinator:
    c = object.__new__(DaikinCycleMLCoordinator)
    c.cop_sensor_entity = "sensor.altherma_global_cop"
    c.hass = MagicMock()
    c.hass.states.get.return_value = SimpleNamespace(state=value)
    return c


# --- R1: user COP sensor bypasses the MAX_COP / finite gate -----------------

@pytest.mark.parametrize("raw", ["14.0", "16.486", "inf"])
def test_r1_cop_sensor_value_is_gated(raw):
    """snap.cop must never exceed MAX_COP or be non-finite."""
    c = _coord_with_cop_sensor(raw)
    cop, _src = c._read_cop_effective(time.time(), {})
    assert cop is None or (math.isfinite(cop) and cop <= MAX_COP), (cop, _src)


# --- R2: flagged (suspect) samples still feed cop_today ---------------------

async def test_r2_cop_today_excludes_flagged_samples(tmp_path):
    db = CycleDB(str(tmp_path / "prod1.db"))
    await db.async_open()
    now = time.time()
    # prod-1 2026-11-18 heating, LWT 30.0, T_out 11.4
    base = {"lwt": 30.0, "outdoor": 11.4, "mode": "heating", "power_stable": True}
    for i, cop in enumerate((6.1, 6.2, 6.3)):
        await db.async_insert_cop_sample({**base, "ts": now - 300 + i, "cop": cop})
    assert classify_cop_sample("heating", 30.0, 11.4, 14.0) == "flag"
    await db.async_insert_cop_sample(
        {**base, "ts": now - 10, "cop": 14.0, "is_transition_artifact": 1}
    )
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c._is_hybrid_install = lambda: False
    await c._refresh_cop_today(now)
    await db.async_close()
    assert c._cop_today_cache["cop_max"] < 14.0, c._cop_today_cache


# --- R3: classifier verdicts at the exact prod-1 operating points -----------

@pytest.mark.parametrize(
    "lwt,t_out,cop,expected",
    [
        (28.6, 8.0, 9.83, "accept"),   # 2026-11-17 memo point: 0.671 x Carnot
        (30.0, 5.0, 9.83, "flag"),     # issue body point: 0.81 x Carnot
        (30.0, 11.4, 14.0, "flag"),    # 2026-11-18 cop_today.cop_max
        (30.0, 11.4, 6.169, "accept"), # 2026-11-18 live COP
    ],
)
def test_r3_classifier_at_prod_points(lwt, t_out, cop, expected):
    """Documents current classifier verdicts (design, not a bug)."""
    assert classify_cop_sample("heating", lwt, t_out, cop) == expected


# --- R4: A7/W35 normalisation with prod-1 2026-11-18 inputs -----------------

async def test_r4_normalized_a7w35_with_prod_inputs():
    from custom_components.daikin_cycle_ml.engine.model_datasheets import (
        load_bundled,
    )
    c = object.__new__(DaikinCycleMLCoordinator)
    c.entry = MagicMock()
    c.entry.data = {"model": "epra12eav3"}
    c._datasheet_user_loaded = True
    c._datasheet_defaults = None
    c._datasheet_cache = {}
    c._datasheet_user = {}
    c._datasheet_merged = load_bundled()
    c._stooklijn_cache = {"huidige_lwt": 31.3}
    snap = SimpleNamespace(
        cop=6.169,
        attrs={"R1T-Outdoor air temp.": 11.4, "Stats: COP estimated": 6.88},
        last_record={"outdoor_temp": 11.3},
    )
    await c._refresh_datasheet_state(
        time.time(),
        c._resolve_lwt_for_datasheet(snap),
        c._resolve_outdoor_temp(snap),
        c._resolve_cop_for_datasheet(snap),
    )
    assert c._datasheet_cache.get("cop_normalized_a7w35") is not None, c._datasheet_cache


# --- Fix coverage: valid sensor value still wins ---------------------------

def test_cop_sensor_valid_value_still_used():
    c = _coord_with_cop_sensor("6.169")
    assert c._read_cop_effective(time.time(), {}) == (6.169, "cop_sensor")


def test_cop_sensor_at_max_cop_boundary_kept():
    c = _coord_with_cop_sensor(str(MAX_COP))
    assert c._read_cop_effective(time.time(), {}) == (MAX_COP, "cop_sensor")


# --- Fix coverage: DB filters ------------------------------------------------

async def _db_with_flagged(tmp_path):
    db = CycleDB(str(tmp_path / "gate.db"))
    await db.async_open()
    now = time.time()
    base = {"lwt": 30.0, "outdoor": 11.4, "mode": "heating", "power_stable": True}
    await db.async_insert_cop_sample({**base, "ts": now - 120, "cop": 6.2})
    await db.async_insert_cop_sample(
        {**base, "ts": now - 60, "cop": 14.0, "is_transition_artifact": 1}
    )
    return db, now


async def test_fetch_cop_samples_include_artifacts_flag(tmp_path):
    db, _now = await _db_with_flagged(tmp_path)
    try:
        assert len(await db.async_fetch_cop_samples(days=1)) == 2  # default: unchanged
        clean = await db.async_fetch_cop_samples(days=1, include_artifacts=False)
        assert [r["cop"] for r in clean] == [6.2]
    finally:
        await db.async_close()


async def test_fetch_cop_samples_between_include_artifacts_flag(tmp_path):
    db, now = await _db_with_flagged(tmp_path)
    try:
        assert len(await db.async_fetch_cop_samples_between(now - 600, now)) == 2
        clean = await db.async_fetch_cop_samples_between(
            now - 600, now, include_artifacts=False,
        )
        assert [r["cop"] for r in clean] == [6.2]
    finally:
        await db.async_close()


async def test_rollup_cop_hourly_excludes_flagged(tmp_path):
    db, _now = await _db_with_flagged(tmp_path)
    try:
        await db.async_rollup_cop_hourly(window_hours=1)
        conn = db._require()
        async with conn.execute(
            "SELECT SUM(n_samples) AS n, MAX(cop_p90) AS p90 FROM cop_hourly"
        ) as cur:
            row = await cur.fetchone()
        assert row["n"] == 1 and row["p90"] == pytest.approx(6.2)
    finally:
        await db.async_close()
