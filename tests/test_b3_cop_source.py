"""B3: cop_samples.source round-trip + interval 300s.

Marker: B3_COP_SOURCE_INTERVAL_300_v1
"""
from __future__ import annotations

from pathlib import Path

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_and_read_source(
    tmp_path: Path, sample: dict, ts: float
) -> str:
    db = CycleDB(tmp_path / "b3.db")
    await db.async_initialize()
    try:
        ok = await db.async_insert_cop_sample(sample)
        assert ok is True
        conn = db._require()
        async with conn.execute(
            "SELECT source FROM cop_samples WHERE ts = ?", (ts,)
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        return row[0]
    finally:
        await db.async_close()


async def test_b3_insert_source_explicit_interval(tmp_path: Path) -> None:
    sample = {
        "ts": 1000.0,
        "cop": 3.5,
        "lwt": 35.0,
        "outdoor": 5.0,
        "flow_lmin": 15.0,
        "power_stable": True,
        "mode": "heating",
        "source": "interval",
    }
    src = await _insert_and_read_source(tmp_path, sample, 1000.0)
    assert src == "interval"


async def test_b3_insert_source_missing_defaults_interval(tmp_path: Path) -> None:
    sample = {
        "ts": 2000.0,
        "cop": 2.0,
        "lwt": 30.0,
        "outdoor": 10.0,
        "flow_lmin": 12.0,
        "power_stable": False,
        "mode": "dhw",
    }
    src = await _insert_and_read_source(tmp_path, sample, 2000.0)
    assert src == "interval"


async def test_b3_insert_source_explicit_tick(tmp_path: Path) -> None:
    sample = {
        "ts": 3000.0,
        "cop": 4.0,
        "lwt": 40.0,
        "outdoor": 2.0,
        "flow_lmin": 14.0,
        "power_stable": True,
        "mode": "heating",
        "source": "tick",
    }
    src = await _insert_and_read_source(tmp_path, sample, 3000.0)
    assert src == "tick"

