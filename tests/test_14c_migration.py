"""Tests voor 14c-3: DB-migratie + MultiBaseline/kmeans dim-guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.ml.features import (
    VECTOR_LEN,
    VECTOR_LEN_LEGACY,
)
from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def test_feature_len_constants():
    assert VECTOR_LEN == 12
    assert VECTOR_LEN_LEGACY == 8


@pytest.mark.asyncio
async def test_migrate_empty_db(tmp_path):
    db = CycleDB(str(tmp_path / 'test.db'))
    await db.async_initialize()
    try:
        n = await db.async_migrate_features_to_v11()
        assert n == 0
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_migrate_legacy_8dim(tmp_path):
    db = CycleDB(str(tmp_path / 'test.db'))
    await db.async_initialize()
    try:
        row = {
            'start_ts': 100.0, 'end_ts': 200.0, 'duration_s': 100,
            'mode': 'heating', 'dT_max': 5.0, 'dT_avg': 3.0,
            'rps_max': 40, 'rps_avg': 30.0, 'outdoor_temp': 7.0,
            'buh_used': 0, 'defrost_used': 0,
        }
        cid = await db.async_insert_cycle(row)
        assert cid is not None
        # Simuleer legacy 8-dim vector
        conn = db._require()
        legacy = json.dumps([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        await conn.execute(
            'INSERT OR REPLACE INTO features (cycle_id, vector_json) VALUES (?,?)',
            (cid, legacy),
        )
        await conn.commit()
        n = await db.async_migrate_features_to_v11()
        assert n == 1
        # Check gepad
        async with conn.execute(
            'SELECT vector_json FROM features WHERE cycle_id=?', (cid,)
        ) as cur:
            r = await cur.fetchone()
        vec = json.loads(r[0])
        assert len(vec) == 12
        assert vec[8] == 0.0 and vec[9] == 0.0 and vec[10] == 0.0
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_migrate_idempotent(tmp_path):
    db = CycleDB(str(tmp_path / 'test.db'))
    await db.async_initialize()
    try:
        row = {
            'start_ts': 100.0, 'end_ts': 200.0, 'duration_s': 100,
            'mode': 'heating', 'dT_max': 5.0, 'dT_avg': 3.0,
            'rps_max': 40, 'rps_avg': 30.0, 'outdoor_temp': 7.0,
            'buh_used': 0, 'defrost_used': 0,
        }
        cid = await db.async_insert_cycle(row)
        conn = db._require()
        legacy = json.dumps([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        await conn.execute(
            'INSERT OR REPLACE INTO features (cycle_id, vector_json) VALUES (?,?)',
            (cid, legacy),
        )
        await conn.commit()
        n1 = await db.async_migrate_features_to_v11()
        n2 = await db.async_migrate_features_to_v11()
        assert n1 == 1
        assert n2 == 0
    finally:
        await db.async_close()


def test_multibaseline_resets_on_legacy_dim():
    # Simuleer 8-dim legacy state
    legacy_state = {
        'dim': 8,
        'alpha': 0.1,
        'outlier_skip_z': 3.0,
        'min_samples_before_skip': 5,
        'baselines': {},
    }
    mb = MultiBaseline.from_dict(legacy_state)
    assert mb.dim == 12


def test_multibaseline_accepts_current_dim():
    state = {
        'dim': 11,
        'alpha': 0.1,
        'outlier_skip_z': 3.0,
        'min_samples_before_skip': 5,
        'baselines': {},
    }
    mb = MultiBaseline.from_dict(state)
    assert mb.dim == 12


def test_multibaseline_new_instance_is_12dim():
    mb = MultiBaseline(VECTOR_LEN)
    assert mb.dim == 12


def test_dummy_prod_db_migration_path():
    """Verifieer dat de migratie-call in __init__.py staat."""
    init_path = Path(__file__).parent.parent / '__init__.py'
    src = init_path.read_text()
    assert 'async_migrate_features_to_v11' in src


def test_multibaseline_source_has_legacy_import():
    mb_path = Path(__file__).parent.parent / 'ml' / 'multi_baseline.py'
    src = mb_path.read_text()
    assert 'VECTOR_LEN_LEGACY' in src


def test_coordinator_has_kmeans_guard():
    co_path = Path(__file__).parent.parent / 'coordinator.py'
    src = co_path.read_text()
    assert 'kmeans_state is legacy' in src
