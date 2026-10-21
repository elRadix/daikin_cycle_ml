"""v1.12.0: model_state retention tests (issue #106)."""
from __future__ import annotations

import time
from pathlib import Path

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _open(p: Path) -> CycleDB:
    db = CycleDB(str(p))
    await db.async_initialize()
    return db


def _day_offset(days: int) -> str:
    return time.strftime(
        "%Y-%m-%d", time.localtime(time.time() - days * 86400)
    )


async def test_prune_deletes_old_energy(tmp_path: Path) -> None:
    db = await _open(tmp_path / "db.db")
    try:
        old = _day_offset(500)
        await db.async_set_model_state(
            f"energy_acc.{old}", {"day": old},
        )
        n = await db.async_prune_model_state(retention_days=400)
        assert n == 1
        assert await db.async_get_model_state(f"energy_acc.{old}") is None
    finally:
        await db.async_close()


async def test_prune_deletes_old_runtime(tmp_path: Path) -> None:
    db = await _open(tmp_path / "db.db")
    try:
        old = _day_offset(500)
        await db.async_set_model_state(
            f"runtime_acc.{old}", {"day": old},
        )
        n = await db.async_prune_model_state(retention_days=400)
        assert n == 1
        assert await db.async_get_model_state(f"runtime_acc.{old}") is None
    finally:
        await db.async_close()


async def test_prune_keeps_recent(tmp_path: Path) -> None:
    db = await _open(tmp_path / "db.db")
    try:
        recent = _day_offset(10)
        await db.async_set_model_state(
            f"energy_acc.{recent}", {"day": recent},
        )
        await db.async_set_model_state(
            f"runtime_acc.{recent}", {"day": recent},
        )
        n = await db.async_prune_model_state(retention_days=400)
        assert n == 0
        assert await db.async_get_model_state(
            f"energy_acc.{recent}"
        ) is not None
        assert await db.async_get_model_state(
            f"runtime_acc.{recent}"
        ) is not None
    finally:
        await db.async_close()


async def test_prune_ignores_unrelated_keys(tmp_path: Path) -> None:
    """kmeans_state, baseline_state, last_maintenance_ts must not be touched."""
    db = await _open(tmp_path / "db.db")
    try:
        await db.async_set_model_state("kmeans_state", {"k": 3})
        await db.async_set_model_state("baseline_state", {"n": 100})
        await db.async_set_model_state("last_maintenance_ts", 12345.0)
        n = await db.async_prune_model_state(retention_days=1)
        assert n == 0
        assert await db.async_get_model_state("kmeans_state") is not None
        assert await db.async_get_model_state("baseline_state") is not None
        assert await db.async_get_model_state("last_maintenance_ts") == 12345.0
    finally:
        await db.async_close()


async def test_prune_empty_db(tmp_path: Path) -> None:
    db = await _open(tmp_path / "db.db")
    try:
        n = await db.async_prune_model_state(retention_days=400)
        assert n == 0
    finally:
        await db.async_close()


async def test_prune_idempotent(tmp_path: Path) -> None:
    db = await _open(tmp_path / "db.db")
    try:
        old = _day_offset(500)
        await db.async_set_model_state(
            f"energy_acc.{old}", {"day": old},
        )
        n1 = await db.async_prune_model_state(retention_days=400)
        n2 = await db.async_prune_model_state(retention_days=400)
        assert n1 == 1
        assert n2 == 0
    finally:
        await db.async_close()


async def test_maintenance_returns_model_state_deleted(
    tmp_path: Path,
) -> None:
    db = await _open(tmp_path / "db.db")
    try:
        old = _day_offset(500)
        await db.async_set_model_state(
            f"energy_acc.{old}", {"day": old},
        )
        result = await db.async_run_maintenance(
            cycle_retention_days=90,
            alert_retention_days=90,
            cop_retention_days=365,
            model_state_retention_days=400,
            vacuum=False,
        )
        assert "model_state_deleted" in result
        assert result["model_state_deleted"] >= 1
    finally:
        await db.async_close()


async def test_maintenance_handles_prune_exception(tmp_path: Path) -> None:
    """v1.12.0 (#106): prune raise must not abort maintenance."""
    from unittest.mock import AsyncMock, patch
    db = await _open(tmp_path / "db.db")
    try:
        with patch.object(
            db, "async_prune_model_state",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await db.async_run_maintenance(
                cycle_retention_days=90,
                alert_retention_days=90,
                cop_retention_days=365,
                model_state_retention_days=400,
                vacuum=False,
            )
        # Handler caught the exception; model_state_deleted stays 0
        assert result["model_state_deleted"] == 0
        # Other prune counts still present -> maintenance completed
        for k in ("cycles_deleted", "features_deleted",
                  "alerts_deleted", "cop_deleted"):
            assert k in result
    finally:
        await db.async_close()
