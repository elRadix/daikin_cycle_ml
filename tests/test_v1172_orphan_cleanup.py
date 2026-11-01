"""v1.17.2: orphan DB cleanup tests."""

from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml import _async_cleanup_orphan_dbs


@pytest.mark.asyncio
async def test_cleanup_removes_zero_byte_dbs(hass, tmp_path, monkeypatch):
    """Empty daikin_cycle_ml_*.db files are removed, others preserved."""
    monkeypatch.setattr(hass.config, "config_dir", str(tmp_path))
    storage = tmp_path / ".storage"
    storage.mkdir()

    empty1 = storage / "daikin_cycle_ml_empty1.db"
    empty2 = storage / "daikin_cycle_ml_empty2.db"
    nonempty = storage / "daikin_cycle_ml_real.db"
    other = storage / "other_file.db"

    empty1.touch()
    empty2.touch()
    nonempty.write_bytes(b"x" * 100)
    other.touch()

    await _async_cleanup_orphan_dbs(hass)

    assert not empty1.exists()
    assert not empty2.exists()
    assert nonempty.exists()
    assert other.exists()


@pytest.mark.asyncio
async def test_cleanup_no_zero_byte_files(hass, tmp_path, monkeypatch):
    """No empty DB files -> no crash, no removal, no log."""
    monkeypatch.setattr(hass.config, "config_dir", str(tmp_path))
    storage = tmp_path / ".storage"
    storage.mkdir()

    real = storage / "daikin_cycle_ml_real.db"
    real.write_bytes(b"x" * 100)

    await _async_cleanup_orphan_dbs(hass)

    assert real.exists()
