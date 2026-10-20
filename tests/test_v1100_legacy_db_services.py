"""v1.10.0 #75 - legacy DB correction service tests."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    DB_FILENAME,
    DB_FILENAME_TEMPLATE,
)
from custom_components.daikin_cycle_ml.services import (
    _handle_archive_legacy_db,
    _handle_assign_legacy_db,
    _handle_export_legacy_db,
)


def _make_call(entry_id: str, target: str | None = None) -> MagicMock:
    call = MagicMock()
    call.data = {"entry_id": entry_id}
    if target is not None:
        call.data["target_entry_id"] = target
    return call


@pytest.fixture
def svc_env(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    (tmp_path / ".storage").mkdir()
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    return hass, tmp_path


def _db(tmp_path: Path, entry_id: str) -> Path:
    return tmp_path / ".storage" / DB_FILENAME_TEMPLATE.format(
        entry_id=entry_id
    )


def _create_full_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE cycles (id INTEGER PRIMARY KEY, start_ts REAL)"
        )
        conn.execute(
            "CREATE TABLE features (id INTEGER PRIMARY KEY, cycle_id INTEGER)"
        )
        conn.execute(
            "CREATE TABLE cop_samples (id INTEGER PRIMARY KEY, ts REAL)"
        )
        conn.execute("CREATE TABLE cop_hourly (ts_hour INTEGER, mode TEXT)")
        conn.execute("CREATE TABLE daily_summary (day TEXT, mode TEXT)")
        conn.execute(
            "CREATE TABLE alerts (id INTEGER PRIMARY KEY, ts REAL)"
        )
        conn.execute(
            "CREATE TABLE model_state (key TEXT PRIMARY KEY, value_json TEXT)"
        )
        conn.execute("INSERT INTO cycles (start_ts) VALUES (1.0)")
        conn.execute("INSERT INTO cycles (start_ts) VALUES (2.0)")
        conn.commit()
    finally:
        conn.close()


async def test_assign_source_equals_target(svc_env):
    hass, _ = svc_env
    call = _make_call("a", target="a")
    result = await _handle_assign_legacy_db(hass, call)
    assert result == {"ok": False, "reason": "source_equals_target"}


async def test_assign_target_not_found(svc_env):
    hass, _ = svc_env
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    call = _make_call("a", target="b")
    result = await _handle_assign_legacy_db(hass, call)
    assert result == {"ok": False, "reason": "target_entry_not_found"}


async def test_assign_no_source_db(svc_env):
    hass, _ = svc_env
    hass.config_entries.async_get_entry = MagicMock(return_value=MagicMock())
    call = _make_call("a", target="b")
    result = await _handle_assign_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "no_source_db"
    assert "source_path" in result


async def test_assign_target_already_has_db(svc_env):
    hass, tmp_path = svc_env
    hass.config_entries.async_get_entry = MagicMock(return_value=MagicMock())
    _db(tmp_path, "a").write_bytes(b"source")
    _db(tmp_path, "b").write_bytes(b"target")
    call = _make_call("a", target="b")
    result = await _handle_assign_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "target_already_has_db"
    assert "target_path" in result
    assert _db(tmp_path, "a").exists()
    assert _db(tmp_path, "b").exists()


async def test_assign_rename_failed(svc_env, monkeypatch):
    hass, tmp_path = svc_env
    hass.config_entries.async_get_entry = MagicMock(return_value=MagicMock())
    _db(tmp_path, "a").write_bytes(b"source")

    async def boom(_fn, *_args, **_kwargs):
        raise OSError("rename fail")

    monkeypatch.setattr(hass, "async_add_executor_job", boom)
    call = _make_call("a", target="b")
    result = await _handle_assign_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "rename_failed"
    assert "error" in result


async def test_assign_happy_path(svc_env, monkeypatch):
    from custom_components.daikin_cycle_ml import services
    hass, tmp_path = svc_env
    hass.config_entries.async_get_entry = MagicMock(return_value=MagicMock())
    _db(tmp_path, "a").write_bytes(b"db-content")
    clear_mock = MagicMock()
    monkeypatch.setattr(
        services, "clear_legacy_db_multi_entry", clear_mock
    )
    call = _make_call("a", target="b")
    result = await _handle_assign_legacy_db(hass, call)
    assert result["ok"] is True
    assert result["source_entry_id"] == "a"
    assert result["target_entry_id"] == "b"
    assert "new_db_path" in result
    assert result["reload_required"] == ["a", "b"]
    assert not _db(tmp_path, "a").exists()
    assert _db(tmp_path, "b").exists()
    assert _db(tmp_path, "b").read_bytes() == b"db-content"
    assert clear_mock.call_count == 2


async def test_archive_no_db_file(svc_env):
    hass, _ = svc_env
    call = _make_call("a")
    result = await _handle_archive_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "no_db_file"
    assert "live_path" in result


async def test_archive_rename_failed(svc_env, monkeypatch):
    hass, tmp_path = svc_env
    _db(tmp_path, "a").write_bytes(b"db-content")

    async def boom(_fn, *_args, **_kwargs):
        raise OSError("rename fail")

    monkeypatch.setattr(hass, "async_add_executor_job", boom)
    call = _make_call("a")
    result = await _handle_archive_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "rename_failed"
    assert "error" in result
    assert _db(tmp_path, "a").exists()


async def test_archive_happy_path(svc_env, monkeypatch):
    from custom_components.daikin_cycle_ml import services
    hass, tmp_path = svc_env
    _db(tmp_path, "a").write_bytes(b"db-content")
    clear_mock = MagicMock()
    monkeypatch.setattr(
        services, "clear_legacy_db_multi_entry", clear_mock
    )
    call = _make_call("a")
    result = await _handle_archive_legacy_db(hass, call)
    assert result["ok"] is True
    assert result["entry_id"] == "a"
    assert "archived_path" in result
    assert result["reload_required"] == ["a"]
    archived = Path(result["archived_path"])
    assert archived.exists()
    assert archived.read_bytes() == b"db-content"
    assert archived.name.startswith(DB_FILENAME + ".legacy-")
    assert not _db(tmp_path, "a").exists()
    clear_mock.assert_called_once_with(hass, "a")


async def test_export_no_db_file(svc_env):
    hass, _ = svc_env
    call = _make_call("a")
    result = await _handle_export_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "no_db_file"
    assert "live_path" in result


async def test_export_mkdir_failed(svc_env, monkeypatch):
    hass, tmp_path = svc_env
    _db(tmp_path, "a").write_bytes(b"db")

    async def boom(_fn, *_args, **_kwargs):
        raise OSError("mkdir fail")

    monkeypatch.setattr(hass, "async_add_executor_job", boom)
    call = _make_call("a")
    result = await _handle_export_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "mkdir_failed"
    assert "error" in result


async def test_export_table_error_populates_errors(svc_env):
    hass, tmp_path = svc_env
    db_path = _db(tmp_path, "a")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE cycles (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO cycles (id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()
    call = _make_call("a")
    result = await _handle_export_legacy_db(hass, call)
    assert result["ok"] is True
    assert result["tables"]["cycles"] == 1
    assert "features" in result["errors"]
    assert "cop_hourly" in result["errors"]


async def test_export_happy_path(svc_env):
    hass, tmp_path = svc_env
    db_path = _db(tmp_path, "a")
    _create_full_db(db_path)
    call = _make_call("a")
    result = await _handle_export_legacy_db(hass, call)
    assert result["ok"] is True
    assert result["entry_id"] == "a"
    out_dir = Path(result["export_dir"])
    assert out_dir.exists()
    assert out_dir.name.startswith("daikin_cycle_ml_export_a_")
    # All 7 tables exported
    assert set(result["tables"].keys()) == {
        "cycles", "features", "cop_samples", "cop_hourly",
        "daily_summary", "alerts", "model_state",
    }
    assert result["tables"]["cycles"] == 2
    # CSVs + manifest present
    assert (out_dir / "cycles.csv").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["entry_id"] == "a"
    assert manifest["tables"]["cycles"] == 2
    assert manifest["errors"] == {}


async def test_export_manifest_write_failed(svc_env, monkeypatch):
    hass, tmp_path = svc_env
    db_path = _db(tmp_path, "a")
    _create_full_db(db_path)

    # First call (mkdir) succeeds via real executor.
    # Second call (CSV per table) succeeds.
    # Only manifest write should fail -> patch Path.write_text
    from pathlib import Path as _Path
    real_write_text = _Path.write_text

    def selective_boom(self, *args, **kwargs):
        if self.name == "manifest.json":
            raise OSError("manifest fail")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(_Path, "write_text", selective_boom)
    call = _make_call("a")
    result = await _handle_export_legacy_db(hass, call)
    assert result["ok"] is False
    assert result["reason"] == "manifest_write_failed"
    assert "export_dir" in result


async def test_legacy_services_registered(hass):
    from custom_components.daikin_cycle_ml import services as svc
    await svc.async_register_services(hass)
    for name in (
        "assign_legacy_db",
        "archive_legacy_db",
        "export_legacy_db",
    ):
        assert hass.services.has_service("daikin_cycle_ml", name), name
