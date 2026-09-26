"""Batch 51b-fix: coverage for _async_setup_database paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml import _async_setup_database
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _mock_db(**kw):
    inst = MagicMock()
    inst.async_open = AsyncMock()
    inst.async_initialize = AsyncMock()
    inst.async_migrate_features_to_v11 = AsyncMock(return_value=0)
    inst.async_migrate_features_to_v12 = AsyncMock(return_value=0)
    inst.async_integrity_check = AsyncMock(return_value=True)
    for k, v in kw.items():
        setattr(inst, k, v)
    return inst


async def test_setup_database_happy(hass):
    coord = MagicMock()
    inst = _mock_db()
    with patch("custom_components.daikin_cycle_ml.CycleDB", return_value=inst):
        await _async_setup_database(hass, coord)
    assert coord.db is inst
    assert coord._migration_error is None
    assert coord._db_integrity_ok is True


async def test_setup_database_v11_raises(hass):
    coord = MagicMock()
    inst = _mock_db()
    inst.async_migrate_features_to_v11 = AsyncMock(side_effect=RuntimeError("v11 boom"))
    with patch("custom_components.daikin_cycle_ml.CycleDB", return_value=inst):
        await _async_setup_database(hass, coord)
    assert coord._migration_error == "v11 boom"


async def test_setup_database_v12_raises(hass):
    coord = MagicMock()
    inst = _mock_db()
    inst.async_migrate_features_to_v12 = AsyncMock(side_effect=RuntimeError("v12 boom"))
    with patch("custom_components.daikin_cycle_ml.CycleDB", return_value=inst):
        await _async_setup_database(hass, coord)
    assert coord._migration_error == "v12 boom"


async def test_setup_database_integrity_raises(hass):
    coord = MagicMock()
    inst = _mock_db()
    inst.async_integrity_check = AsyncMock(side_effect=RuntimeError("int boom"))
    with patch("custom_components.daikin_cycle_ml.CycleDB", return_value=inst):
        await _async_setup_database(hass, coord)
    assert coord._db_integrity_ok is False


async def test_setup_database_outer_fail(hass):
    coord = MagicMock()
    with patch("custom_components.daikin_cycle_ml.CycleDB",
               side_effect=RuntimeError("open boom")):
        await _async_setup_database(hass, coord)
    assert coord.db is None


async def test_integrity_check_real(tmp_path):
    db = CycleDB(tmp_path / "t.db")
    await db.async_open()
    await db.async_initialize()
    ok = await db.async_integrity_check()
    assert ok is True
    await db.async_close()


async def test_integrity_check_broken(tmp_path):
    db = CycleDB(tmp_path / "t2.db")
    await db.async_open()
    await db.async_initialize()
    db._require = lambda: (_ for _ in ()).throw(RuntimeError("closed"))
    ok = await db.async_integrity_check()
    assert ok is False
    await db.async_close()
