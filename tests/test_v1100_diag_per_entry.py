"""v1.10.0 #75 - diagnostics per-entry DB enumeration tests."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from custom_components.daikin_cycle_ml.const import (
    DB_FILENAME,
    DB_FILENAME_TEMPLATE,
)
from custom_components.daikin_cycle_ml.diagnostics import (
    DB_TABLES,
    _count_tables_sync,
    _enum_db_files,
)


def _make_db(path: Path, tables=()) -> None:
    conn = sqlite3.connect(path)
    try:
        for t in tables:
            conn.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()


def test_count_tables_sync_missing_path(tmp_path):
    result = _count_tables_sync(tmp_path / "missing.db")
    assert result == {}


def test_count_tables_sync_no_tables(tmp_path):
    db = tmp_path / "empty.db"
    _make_db(db)
    result = _count_tables_sync(db)
    assert result == {}


def test_count_tables_sync_happy(tmp_path):
    db = tmp_path / "full.db"
    _make_db(db, tables=DB_TABLES)
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT INTO cycles (id) VALUES (1)")
        conn.execute("INSERT INTO cycles (id) VALUES (2)")
        conn.commit()
    finally:
        conn.close()
    result = _count_tables_sync(db)
    assert result["cycles"] == 2
    assert result["alerts"] == 0


async def test_enum_db_files_empty(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    (tmp_path / ".storage").mkdir()
    result = await _enum_db_files(hass)
    assert result == {"per_entry": {}, "legacy": None}


async def test_enum_db_files_multiple(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    storage = tmp_path / ".storage"
    storage.mkdir()
    a = storage / DB_FILENAME_TEMPLATE.format(entry_id="aaa")
    b = storage / DB_FILENAME_TEMPLATE.format(entry_id="bbb")
    _make_db(a, ["cycles"])
    _make_db(b, ["cycles"])
    legacy = storage / DB_FILENAME
    _make_db(legacy, ["cycles"])
    result = await _enum_db_files(hass)
    assert set(result["per_entry"].keys()) == {"aaa", "bbb"}
    assert result["per_entry"]["aaa"]["path"] == str(a)
    assert result["per_entry"]["aaa"]["size_bytes"] > 0
    assert result["per_entry"]["aaa"]["counts"]["cycles"] == 0
    assert result["legacy"] is not None
    assert result["legacy"]["path"] == str(legacy)
    assert result["legacy"]["counts"]["cycles"] == 0


async def test_enum_db_files_executor_oserror(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    (tmp_path / ".storage").mkdir()

    async def boom(_fn, *args, **kwargs):
        raise OSError("executor fail")

    hass.async_add_executor_job = boom
    result = await _enum_db_files(hass)
    assert result == {"per_entry": {}, "legacy": None}
