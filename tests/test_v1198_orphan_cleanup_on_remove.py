"""v1.19.8 #236: 0-byte orphan DB cleanup on entry removal."""
from __future__ import annotations

from pathlib import Path

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import async_remove_entry
from custom_components.daikin_cycle_ml.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState


def _make_entry(hass, entry_id):
    entry = MockConfigEntry(domain=DOMAIN, entry_id=entry_id)
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    return entry


async def test_remove_entry_cleans_0byte_orphan(hass):
    """#236: 0-byte orphan DB removed during entry removal."""
    storage = Path(hass.config.config_dir) / ".storage"
    storage.mkdir(exist_ok=True)
    orphan = storage / "daikin_cycle_ml_orphan0byte.db"
    orphan.touch()
    assert orphan.stat().st_size == 0

    entry = _make_entry(hass, "test_236_a")
    await async_remove_entry(hass, entry)

    assert not orphan.exists(), "0-byte orphan must be cleaned on remove"


async def test_remove_entry_preserves_nonzero_db(hass):
    """#236: non-zero DB files preserved (only 0-byte cleaned)."""
    storage = Path(hass.config.config_dir) / ".storage"
    storage.mkdir(exist_ok=True)
    real_db = storage / "daikin_cycle_ml_other999.db"
    real_db.write_bytes(b"sqlite db content")

    entry = _make_entry(hass, "test_236_b")
    await async_remove_entry(hass, entry)

    assert real_db.exists(), "non-zero DB must be preserved"
    assert real_db.read_bytes() == b"sqlite db content"


async def test_remove_entry_still_removes_own_db(hass):
    """#236: existing per-entry DB removal preserved."""
    storage = Path(hass.config.config_dir) / ".storage"
    storage.mkdir(exist_ok=True)
    entry = _make_entry(hass, "test_236_c")
    own_db = storage / f"daikin_cycle_ml_{entry.entry_id}.db"
    own_db.write_bytes(b"own db")

    await async_remove_entry(hass, entry)

    assert not own_db.exists(), "per-entry DB must still be removed"


async def test_cleanup_skips_active_wal(hass):
    """v1.19.8: 0-byte .db with non-empty .db-wal is NOT deleted."""
    storage = Path(hass.config.config_dir) / ".storage"
    storage.mkdir(exist_ok=True)
    db = storage / "daikin_cycle_ml_activewal.db"
    db.touch()
    wal = storage / "daikin_cycle_ml_activewal.db-wal"
    wal.write_bytes(b"pending transaction data")

    entry = _make_entry(hass, "test_236_wal")
    await async_remove_entry(hass, entry)

    assert db.exists(), "0-byte .db with active .db-wal must be preserved"
    assert wal.exists()


async def test_cleanup_skips_active_shm(hass):
    """v1.19.8: 0-byte .db with .db-shm (active connection) is NOT deleted."""
    storage = Path(hass.config.config_dir) / ".storage"
    storage.mkdir(exist_ok=True)
    db = storage / "daikin_cycle_ml_activeshm.db"
    db.touch()
    shm = storage / "daikin_cycle_ml_activeshm.db-shm"
    shm.write_bytes(b"shared memory index")

    entry = _make_entry(hass, "test_236_shm")
    await async_remove_entry(hass, entry)

    assert db.exists(), "0-byte .db with .db-shm must be preserved"
