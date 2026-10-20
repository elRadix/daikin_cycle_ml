"""v1.10.0 #75 - per-entry DB migration tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.const import (
    DB_FILENAME,
    DB_FILENAME_TEMPLATE,
    DB_LEGACY_MARKER_FILENAME,
)
from custom_components.daikin_cycle_ml.repairs import (
    clear_legacy_db_multi_entry,
    raise_legacy_db_multi_entry,
)
from custom_components.daikin_cycle_ml.storage import migration


def _make_entry(entry_id: str, title: str = "") -> MagicMock:
    e = MagicMock()
    e.entry_id = entry_id
    e.title = title or entry_id
    return e


@pytest.fixture
def mig_env(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    (tmp_path / ".storage").mkdir()
    return hass, tmp_path


def _storage(tmp_path: Path) -> Path:
    return tmp_path / ".storage"


def _legacy(tmp_path: Path) -> Path:
    return _storage(tmp_path) / DB_FILENAME


def _marker(tmp_path: Path) -> Path:
    return _storage(tmp_path) / DB_LEGACY_MARKER_FILENAME


def _per_entry(tmp_path: Path, entry_id: str) -> Path:
    return _storage(tmp_path) / DB_FILENAME_TEMPLATE.format(entry_id=entry_id)


async def test_migrate_skipped_when_no_legacy(mig_env):
    hass, tmp_path = mig_env
    hass.config_entries.async_entries = MagicMock(
        return_value=[_make_entry("a")]
    )
    result = await migration.async_migrate_legacy_db(
        hass, _make_entry("a")
    )
    assert result.status == "skipped"
    assert _marker(tmp_path).exists()


async def test_migrate_already_when_marker_present(mig_env):
    hass, tmp_path = mig_env
    _marker(tmp_path).write_text("v1100:single\nentry=a\n")
    result = await migration.async_migrate_legacy_db(
        hass, _make_entry("a")
    )
    assert result.status == "already"


async def test_migrate_recovered_when_per_entry_exists(mig_env):
    hass, tmp_path = mig_env
    _per_entry(tmp_path, "a").write_bytes(b"x")
    result = await migration.async_migrate_legacy_db(
        hass, _make_entry("a")
    )
    assert result.status == "already"
    assert "recovered" in _marker(tmp_path).read_text()


async def test_migrate_backup_fails(mig_env):
    hass, tmp_path = mig_env
    _legacy(tmp_path).write_bytes(b"legacy")
    hass.config_entries.async_entries = MagicMock(
        return_value=[_make_entry("a")]
    )
    with patch.object(migration, "_backup_legacy_file", return_value=None):
        result = await migration.async_migrate_legacy_db(
            hass, _make_entry("a")
        )
    assert result.status == "error"
    assert result.error == "backup_failed"


async def test_migrate_single_success(mig_env):
    hass, tmp_path = mig_env
    _legacy(tmp_path).write_bytes(b"legacy-content-123")
    entry = _make_entry("a")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    result = await migration.async_migrate_legacy_db(hass, entry)
    assert result.status == "single"
    assert result.assigned_entry_id == "a"
    assert _per_entry(tmp_path, "a").exists()
    assert not _legacy(tmp_path).exists()
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert _marker(tmp_path).exists()


async def test_migrate_single_target_exists(mig_env):
    hass, tmp_path = mig_env
    _legacy(tmp_path).write_bytes(b"legacy")
    _per_entry(tmp_path, "a").write_bytes(b"existing")
    entry = _make_entry("a")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    result = await migration.async_migrate_legacy_db(hass, entry)
    assert result.status == "error"
    assert result.error == "target_exists"
    assert "single-skip" in _marker(tmp_path).read_text()


async def test_migrate_multi_success(mig_env):
    hass, tmp_path = mig_env
    _legacy(tmp_path).write_bytes(b"legacy-content")
    a = _make_entry("a", title="First")
    b = _make_entry("b", title="Second")
    hass.config_entries.async_entries = MagicMock(return_value=[a, b])
    with patch.object(
        migration, "raise_legacy_db_multi_entry"
    ) as raise_mock:
        result = await migration.async_migrate_legacy_db(hass, b)
    assert result.status == "multi"
    assert result.assigned_entry_id == "a"
    raise_mock.assert_called_once()


async def test_migrate_multi_target_exists(mig_env):
    hass, tmp_path = mig_env
    _legacy(tmp_path).write_bytes(b"legacy")
    _per_entry(tmp_path, "a").write_bytes(b"existing")
    a = _make_entry("a")
    b = _make_entry("b")
    hass.config_entries.async_entries = MagicMock(return_value=[a, b])
    with patch.object(
        migration, "raise_legacy_db_multi_entry"
    ) as raise_mock:
        result = await migration.async_migrate_legacy_db(hass, b)
    assert result.status == "error"
    assert result.error == "target_exists"
    raise_mock.assert_called_once()
    assert "multi-skip" in _marker(tmp_path).read_text()


def test_migrate_multi_no_entries_direct(mig_env):
    hass, tmp_path = mig_env
    _legacy(tmp_path).write_bytes(b"legacy")
    result = migration._migrate_multi(
        hass,
        _make_entry("a"),
        [],
        _legacy(tmp_path),
        Path("/tmp/bk"),
        0,
    )
    assert result.status == "error"
    assert result.error == "no_entries"


def test_do_rename_oserror(mig_env):
    hass, tmp_path = mig_env
    legacy = _legacy(tmp_path)  # does NOT exist
    target = _per_entry(tmp_path, "a")
    result = migration._do_rename(
        hass, legacy, target, Path("/tmp/bk"), 1, "a", single=True
    )
    assert result.status == "error"
    assert result.error


def test_do_rename_size_mismatch_rollback(mig_env, monkeypatch):
    hass, tmp_path = mig_env
    legacy = _legacy(tmp_path)
    legacy.write_bytes(b"legacy")
    target = _per_entry(tmp_path, "a")

    def fake_replace(self, dst):
        dst.write_bytes(b"Y" * 100)
        self.unlink()

    monkeypatch.setattr(Path, "replace", fake_replace)
    result = migration._do_rename(
        hass, legacy, target, Path("/tmp/bk"), 1, "a", single=True
    )
    assert result.status == "error"
    assert result.error == "size_mismatch"


def test_do_rename_size_mismatch_rollback_fails(mig_env, monkeypatch):
    hass, tmp_path = mig_env
    legacy = _legacy(tmp_path)
    legacy.write_bytes(b"legacy")
    target = _per_entry(tmp_path, "a")
    calls = {"n": 0}

    def fake_replace(self, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            dst.write_bytes(b"Y" * 100)
            self.unlink()
        else:
            raise OSError("rollback boom")

    monkeypatch.setattr(Path, "replace", fake_replace)
    result = migration._do_rename(
        hass, legacy, target, Path("/tmp/bk"), 1, "a", single=True
    )
    assert result.status == "error"
    assert result.error == "size_mismatch"


async def test_migrate_wraps_exception(mig_env):
    hass, _ = mig_env
    with patch.object(
        migration,
        "_async_migrate_impl",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        result = await migration.async_migrate_legacy_db(
            hass, _make_entry("a")
        )
    assert result.status == "error"
    assert "boom" in (result.error or "")


def test_write_marker_oserror(mig_env, monkeypatch):
    hass, _ = mig_env

    def boom(*_a, **_k):
        raise OSError("no write")

    monkeypatch.setattr(Path, "write_text", boom)
    migration._write_marker(hass, "x")


def test_raise_clear_legacy_db_multi_entry(hass):
    raise_legacy_db_multi_entry(
        hass,
        "e1",
        assigned_title="First",
        legacy_path="/x/y.db",
        n_entries=3,
    )
    clear_legacy_db_multi_entry(hass, "e1")


def test_backup_legacy_file_oserror(mig_env, monkeypatch):
    """Cover lines 84-86: _backup_legacy_file OSError path."""
    hass, tmp_path = mig_env
    legacy = _legacy(tmp_path)
    legacy.write_bytes(b"legacy")

    def boom(*_a, **_k):
        raise OSError("copy fail")

    monkeypatch.setattr(migration.shutil, "copy2", boom)
    result = migration._backup_legacy_file(hass, legacy)
    assert result is None


def test_migrate_multi_rename_error_branch(mig_env):
    """Cover branch 216->229: _do_rename error in multi mode."""
    hass, tmp_path = mig_env
    _legacy(tmp_path).write_bytes(b"legacy")
    a = _make_entry("a")
    b = _make_entry("b")
    fake_err = migration.MigrationResult(status="error", error="fake")
    with patch.object(migration, "_do_rename", return_value=fake_err):
        result = migration._migrate_multi(
            hass,
            b,
            [a, b],
            _legacy(tmp_path),
            Path("/tmp/bk"),
            2,
        )
    assert result.status == "error"
    assert result.error == "fake"


async def test_setup_database_migration_error_logs(hass, tmp_path):
    """Cover __init__.py L59: migration error log (entry not None)."""
    from custom_components.daikin_cycle_ml import _async_setup_database
    from custom_components.daikin_cycle_ml.storage.migration import (
        MigrationResult,
    )
    hass.config.config_dir = str(tmp_path)
    (tmp_path / ".storage").mkdir()
    coord = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    inst = AsyncMock()
    inst.async_migrate_features_to_v11 = AsyncMock(return_value=0)
    inst.async_integrity_check = AsyncMock(return_value=True)
    with patch(
        "custom_components.daikin_cycle_ml.async_migrate_legacy_db",
        new_callable=AsyncMock,
        return_value=MigrationResult(status="error", error="boom"),
    ), patch(
        "custom_components.daikin_cycle_ml.CycleDB", return_value=inst
    ):
        await _async_setup_database(hass, coord, entry)
    assert coord.db is inst


async def test_setup_database_migration_multi_logs(hass, tmp_path):
    """Cover __init__.py L63: migration multi log (entry not None)."""
    from custom_components.daikin_cycle_ml import _async_setup_database
    from custom_components.daikin_cycle_ml.storage.migration import (
        MigrationResult,
    )
    hass.config.config_dir = str(tmp_path)
    (tmp_path / ".storage").mkdir()
    coord = MagicMock()
    entry = MagicMock()
    entry.entry_id = "e2"
    inst = AsyncMock()
    inst.async_migrate_features_to_v11 = AsyncMock(return_value=0)
    inst.async_integrity_check = AsyncMock(return_value=True)
    with patch(
        "custom_components.daikin_cycle_ml.async_migrate_legacy_db",
        new_callable=AsyncMock,
        return_value=MigrationResult(
            status="multi", assigned_entry_id="oldest"
        ),
    ), patch(
        "custom_components.daikin_cycle_ml.CycleDB", return_value=inst
    ):
        await _async_setup_database(hass, coord, entry)
    assert coord.db is inst



async def test_remove_entry_deletes_db(mig_env):
    """v1.10.0 #75: per-entry DB deleted on entry removal."""
    from custom_components.daikin_cycle_ml import async_remove_entry
    hass, tmp_path = mig_env
    entry = _make_entry("a")
    db_file = _per_entry(tmp_path, "a")
    db_file.write_bytes(b"db-content")
    await async_remove_entry(hass, entry)
    assert not db_file.exists()


async def test_remove_entry_missing_db_no_error(mig_env):
    """Missing DB: silent no-op, no exception."""
    from custom_components.daikin_cycle_ml import async_remove_entry
    hass, tmp_path = mig_env
    entry = _make_entry("a")
    await async_remove_entry(hass, entry)


async def test_remove_entry_unlink_fails_logs(mig_env, monkeypatch):
    """OSError on unlink is logged, not raised (R366)."""
    from custom_components.daikin_cycle_ml import async_remove_entry
    hass, tmp_path = mig_env
    entry = _make_entry("a")
    db_file = _per_entry(tmp_path, "a")
    db_file.write_bytes(b"db-content")

    async def boom(fn):
        raise OSError("unlink fail")

    monkeypatch.setattr(hass, "async_add_executor_job", boom)
    await async_remove_entry(hass, entry)
    assert db_file.exists()


async def test_remove_entry_preserves_legacy_and_backups(mig_env):
    """Legacy and backup files survive removal."""
    from custom_components.daikin_cycle_ml import async_remove_entry
    hass, tmp_path = mig_env
    entry = _make_entry("a")
    db_file = _per_entry(tmp_path, "a")
    db_file.write_bytes(b"db")
    legacy_file = (
        _storage(tmp_path) / "daikin_cycle_ml.db.legacy-20260101-120000"
    )
    legacy_file.write_bytes(b"legacy")
    backup_dir = tmp_path / ".daikin_backups"
    backup_dir.mkdir()
    backup_file = backup_dir / "daikin_cycle_ml.db.backup-20260101-120000"
    backup_file.write_bytes(b"backup")

    await async_remove_entry(hass, entry)

    assert not db_file.exists()
    assert legacy_file.exists()
    assert backup_file.exists()
