"""v1.19.8: _count_tables_sync must never raise on non-SQLite files."""
from __future__ import annotations

import pytest_freezer  # noqa: F401  (keeps plugin registration parity)

from custom_components.daikin_cycle_ml.diagnostics import _count_tables_sync


def test_count_tables_sync_non_sqlite_file(tmp_path):
    """Non-SQLite content must not raise; returns empty dict (v1.19.8)."""
    f = tmp_path / "daikin_cycle_ml_bogus.db"
    f.write_bytes(b"not a sqlite file at all")
    assert _count_tables_sync(f) == {}


def test_count_tables_sync_empty_file(tmp_path):
    """0-byte file must not raise; returns empty dict (v1.19.8)."""
    f = tmp_path / "daikin_cycle_ml_empty.db"
    f.touch()
    assert _count_tables_sync(f) == {}
