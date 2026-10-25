"""v1.12.5 #133: _sample_aggregates mode + exclude_artifacts params."""
import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _seed(db, rows):
    conn = db._require()
    for ts, cop, mode, artifact in rows:
        await conn.execute(
            "INSERT INTO cop_samples (ts, cop, mode, is_transition_artifact) "
            "VALUES (?, ?, ?, ?)",
            (ts, cop, mode, artifact),
        )
    await conn.commit()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_no_mode_no_exclude_backward_compat(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed(db, [
        (10.0, 3.0, "heating", 0),
        (20.0, 4.0, "dhw", 0),
        (30.0, 5.0, "heating", 1),
    ])
    avg, count = await db._sample_aggregates(0.0, 100.0)
    assert count == 3
    assert avg == pytest.approx(4.0)
    await db.async_close()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_mode_filter(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed(db, [
        (10.0, 3.0, "heating", 0),
        (20.0, 4.0, "dhw", 0),
        (30.0, 5.0, "heating", 0),
    ])
    avg, count = await db._sample_aggregates(0.0, 100.0, mode="heating")
    assert count == 2
    assert avg == pytest.approx(4.0)
    await db.async_close()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_exclude_artifacts(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed(db, [
        (10.0, 3.0, "heating", 0),
        (20.0, 4.0, "heating", 1),
        (30.0, 5.0, "heating", 0),
    ])
    avg, count = await db._sample_aggregates(0.0, 100.0, exclude_artifacts=True)
    assert count == 2
    assert avg == pytest.approx(4.0)
    await db.async_close()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_mode_and_exclude(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed(db, [
        (10.0, 3.0, "heating", 0),
        (20.0, 4.0, "dhw", 0),
        (30.0, 5.0, "heating", 1),
        (40.0, 6.0, "heating", 0),
    ])
    avg, count = await db._sample_aggregates(
        0.0, 100.0, mode="heating", exclude_artifacts=True
    )
    assert count == 2
    assert avg == pytest.approx(4.5)
    await db.async_close()
