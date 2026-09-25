"""Diagnostics support for Daikin Cycle ML (extended 12c)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
        except Exception:  # noqa: BLE001
            _LOGGER.debug("diagnostics: count(%s) failed", table)
    return counts


async def _db_extra(db: Any) -> dict[str, Any]:  # pragma: no cover
    out: dict[str, Any] = {}
    if db is None or not getattr(db, "is_open", False):
        return out
    try:
        out["daily_summary"] = await db.async_daily_summary(days=7)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("diagnostics: daily_summary failed")
    for key in ("last_maintenance_ts", "kmeans_state", "baseline_state"):
        try:
            out[key] = await db.async_get_model_state(key)
        except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        pass
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
    except Exception:  # noqa: BLE001
        pass
    return out


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
    if hasattr(store, "counters_snapshot"):
        counters = store.counters_snapshot()

    attrs = getattr(snap, "attrs", {}) or {}
    attrs_sample = dict(list(attrs.items())[:ATTRS_SAMPLE_CAP])

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
        },
    }

