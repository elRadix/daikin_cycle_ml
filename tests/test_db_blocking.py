"""Regression: async_initialize must not call blocking read_text in loop."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.daikin_cycle_ml.storage import db as db_mod
from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture
async def open_db(tmp_path):
    d = CycleDB(tmp_path / "blocking.db")
    await d.async_open()
    try:
        yield d
    finally:
        await d.async_close()


async def test_initialize_uses_to_thread(open_db):
    """async_initialize must dispatch schema read via asyncio.to_thread."""
    real_to_thread = db_mod.asyncio.to_thread
    calls: list = []

    async def spy(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", repr(fn)))
        return await real_to_thread(fn, *args, **kwargs)

    with patch.object(db_mod.asyncio, "to_thread", side_effect=spy):
        await open_db.async_initialize()

    # to_thread was called with _SCHEMA_PATH.read_text (bound method)
    assert len(calls) >= 1


async def test_initialize_idempotent_still_works(tmp_path):
    d = CycleDB(tmp_path / "idem.db")
    await d.async_open()
    try:
        await d.async_initialize()
        await d.async_initialize()
        assert await d.async_count("cycles") == 0
    finally:
        await d.async_close()


async def test_initialize_without_explicit_open(tmp_path):
    """async_initialize auto-opens when needed."""
    d = CycleDB(tmp_path / "auto.db")
    try:
        await d.async_initialize()
        assert d.is_open is True
        assert await d.async_count("cycles") == 0
    finally:
        await d.async_close()
