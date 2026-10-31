import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.mark.asyncio
async def test_v25_migration_idempotent(tmp_path):
    db = CycleDB(str(tmp_path / "test.db"))
    await db.async_open()
    await db.async_initialize()
    # Draai de migratie 2x, mag niet falen
    res1 = await db.async_migrate_to_v25()
    res2 = await db.async_migrate_to_v25()
    assert res1 is not None
    assert res2 is not None
    await db.async_close()
