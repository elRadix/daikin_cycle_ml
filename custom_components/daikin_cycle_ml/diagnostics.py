"""Diagnostics support for Daikin Cycle ML (extended 12c)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DB_FILENAME, DB_FILENAME_TEMPLATE

_LOGGER = logging.getLogger(__name__)

TO_REDACT: set[str] = {"notify_service"}
ATTRS_SAMPLE_CAP = 20
DB_TABLES = ("cycles", "features", "model_state", "alerts", "daily_summary", "cop_samples")


async def _db_counts(db: Any) -> dict[str, int]:
    if db is None or not getattr(db, "is_open", False):
        return {}
    counts: dict[str, int] = {}
    for table in DB_TABLES:
        try:
            counts[table] = await db.async_count(table)
        except Exception:
            _LOGGER.debug("diagnostics: count(%s) failed", table)
    return counts


async def _db_extra(db: Any) -> dict[str, Any]:  # pragma: no cover
    out: dict[str, Any] = {}
    if db is None or not getattr(db, "is_open", False):
        return out
    try:
        out["daily_summary"] = await db.async_daily_summary(days=7)
    except Exception:
        _LOGGER.debug("diagnostics: daily_summary failed")
    for key in ("last_maintenance_ts", "kmeans_state", "baseline_state"):
        try:
            out[key] = await db.async_get_model_state(key)
        except Exception:
            _LOGGER.debug("diagnostics: get_model_state(%s) failed", key)
    return out


def _baseline_summary(coord: Any) -> dict[str, Any]:  # pragma: no cover
    baseline = getattr(coord, "baseline", None)
    if baseline is None:
        return {}
    summary: dict[str, Any] = {"total_samples": 0, "modes": {}}
    try:
        summary["total_samples"] = baseline.total_samples()
        for mode in baseline.modes():
            summary["modes"][mode] = {
                "sample_count": baseline.sample_count(mode),
            }
    except Exception:
        _LOGGER.debug("diagnostics: baseline summary failed")
    return summary


def _adaptive_summary(coord: Any) -> dict[str, Any]:  # pragma: no cover
    adaptive = getattr(coord, "adaptive", None)
    if adaptive is None:
        return {}
    out: dict[str, Any] = {"total_samples": 0, "modes": []}
    try:
        out["total_samples"] = adaptive.total_samples()
        out["modes"] = adaptive.modes()
        out["enabled"] = bool(
            (getattr(coord, "options", {}) or {}).get(
                "adaptive_thresholds_enabled", False
            )
        )
    except Exception:
        _LOGGER.debug("diagnostics: adaptive summary failed")
    return out


async def _cluster_summary(coord: Any) -> dict[str, Any]:  # pragma: no cover
    out: dict[str, Any] = {"centroids": 0, "labels": {}, "counts": {}}
    try:
        centroids = getattr(coord, "_kmeans_centroids", []) or []
        out["centroids"] = len(centroids)
        labels = getattr(coord, "_cluster_labels", {}) or {}
        out["labels"] = {str(k): v for k, v in labels.items()}
        db = getattr(coord, "db", None)
        if db is not None and hasattr(db, "async_count_by_cluster"):
            counts = await db.async_count_by_cluster()
            out["counts"] = {str(k): int(v) for k, v in counts.items()}
    except Exception:
        _LOGGER.debug("cluster_summary failed", exc_info=True)
    return out


async def _cop_summary(coord: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        'state': 'unknown',
        'betrouwbaarheid': 0.0,
        'bucket_current': None,
        'buckets': {},
        'cop_today': {},
        'total_samples': 0,
    }
    try:
        cache = getattr(coord, '_stooklijn_cache', {}) or {}
        if cache:
            out['state'] = cache.get('state') or 'unknown'
            out['betrouwbaarheid'] = cache.get('betrouwbaarheid') or 0.0
            out['bucket_current'] = cache.get('bucket')
            out['buckets'] = cache.get('buckets') or {}
        out['cop_today'] = getattr(coord, '_cop_today_cache', {}) or {}
        db = getattr(coord, 'db', None)
        if db is not None and hasattr(db, 'async_count_cop_samples'):
            out['total_samples'] = await db.async_count_cop_samples()
    except Exception:
        _LOGGER.debug("cop_summary failed", exc_info=True)
    return out



def _count_tables_sync(db_path: Path) -> dict[str, int]:
    """Read-only table counts for one DB file. Never raises."""
    counts: dict[str, int] = {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return counts
    try:
        for table in DB_TABLES:
            try:
                cur = conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                row = cur.fetchone()
                if row is not None:  # pragma: no branch
                    counts[table] = int(row[0])
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()
    return counts


def _safe_size(path: Path) -> int:
    """Return file size or 0 if stat() fails (e.g. file just vanished)."""
    try:
        return path.stat().st_size
    except OSError:  # pragma: no cover
        return 0


async def _enum_db_files(hass: HomeAssistant) -> dict[str, Any]:
    """Enumerate per-entry DB files + legacy DB in .storage/. Never raises."""
    storage = Path(hass.config.config_dir) / ".storage"
    pattern = DB_FILENAME_TEMPLATE.format(entry_id="*")

    def _scan() -> dict[str, Any]:
        per_entry: dict[str, Any] = {}
        for f in storage.glob(pattern):
            entry_id = f.stem.removeprefix("daikin_cycle_ml_")
            size = _safe_size(f)
            per_entry[entry_id] = {
                "path": str(f),
                "size_bytes": size,
                "counts": _count_tables_sync(f),
            }
        legacy_path = storage / DB_FILENAME
        legacy: dict[str, Any] | None = None
        if legacy_path.exists():
            size = _safe_size(legacy_path)
            legacy = {
                "path": str(legacy_path),
                "size_bytes": size,
                "counts": _count_tables_sync(legacy_path),
            }
        return {"per_entry": per_entry, "legacy": legacy}

    try:
        return await hass.async_add_executor_job(_scan)
    except (OSError, TypeError):
        # TypeError: MagicMock test env (async_add_executor_job not awaitable)
        _LOGGER.debug("diagnostics: enum_db_files failed", exc_info=True)
        return {"per_entry": {}, "legacy": None}



async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coord = getattr(entry, "runtime_data", None)
    if coord is None:
        return {"error": "coordinator_not_ready"}

    snap = coord.data
    store = coord.store
    db = getattr(coord, "db", None)

    counters: dict[str, int] = {}
    if hasattr(store, "counters_snapshot"):  # pragma: no branch
        counters = store.counters_snapshot()

    attrs = getattr(snap, "attrs", {}) or {}
    attrs_sample = dict(list(attrs.items())[:ATTRS_SAMPLE_CAP])

    db_files = await _enum_db_files(hass)
    return {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data or {}), TO_REDACT),
            "options": async_redact_data(dict(entry.options or {}), TO_REDACT),
        },
        "coordinator": {
            "state": getattr(snap, "state", None),
            "mode": getattr(snap, "mode", None),
            "missing_attrs": list(getattr(snap, "missing_attrs", []) or []),
            "last_sample_ts": getattr(snap, "last_sample_ts", 0.0),
            "last_success_ts": getattr(snap, "last_success_ts", 0.0),
            "cycle_start_ts": getattr(snap, "cycle_start_ts", 0.0),
            "errors": getattr(snap, "errors", 0),
            "errors_total": getattr(snap, "errors_total", 0),
            "attrs_sample": attrs_sample,
            # Hybrid (EVLQ) — issue #218
            "boiler_active": bool(getattr(snap, "boiler_active", False)),
            "boiler_dhw_active": bool(getattr(snap, "boiler_dhw_active", False)),
            "hybrid_mode": str(getattr(snap, "hybrid_mode", "") or ""),
            "boiler_efficiency_cop": getattr(snap, "boiler_efficiency_cop", None),
            "inv_freq_secondary": getattr(snap, "inv_freq_secondary", None),
        },
        "store": {
            "cycle_count": store.count(),
            "counters": counters,
            "last_cycle": store.last_cycle(),
        },
        "baseline": _baseline_summary(coord),
        "adaptive": _adaptive_summary(coord),
        "clusters": await _cluster_summary(coord),
        "cop_analysis": await _cop_summary(coord),
        "database": {
            "path": getattr(db, "path", None),
            "is_open": bool(getattr(db, "is_open", False)),
            "counts": await _db_counts(db),
            "extra": await _db_extra(db),
            "per_entry": db_files["per_entry"],
            "legacy": db_files["legacy"],
        },
    }
