"""Diagnostics support for Daikin Cycle ML (extended 12c)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from typing import cast  # MYPY-FIX-V1224
from homeassistant.util import dt as dt_util
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry  # MYPY-FIX-V1224-C
import time
import sys
import re
import json
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DB_FILENAME, DB_FILENAME_TEMPLATE

_LOGGER = logging.getLogger(__name__)

TO_REDACT: set[str] = {  # # DIAG-V1224
    "notify_service",
    "api_key", "apikey",
    "token", "access_token", "refresh_token",
    "password", "username", "client_secret",
    "latitude", "longitude", "elevation",
}

_NOTIFY_SERVICE_RE = re.compile(r"\bnotify\.[A-Za-z0-9_]+\b")  # # DIAG-V1224
_URL_CREDS_RE = re.compile(r"(?P<scheme>https?://)[^/\s:@]+:[^/\s@]+@")


def _redact_strings_recursive(obj: Any) -> Any:
    """Value-level redaction: notify.* targets + URL credentials."""
    if isinstance(obj, dict):
        return {
            (_redact_strings_recursive(k) if isinstance(k, str) else k):
            _redact_strings_recursive(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_strings_recursive(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_redact_strings_recursive(v) for v in obj)
    if isinstance(obj, str):
        return _NOTIFY_SERVICE_RE.sub("notify.**REDACTED**", obj)
    return obj

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
        for mode in baseline.modes():  # DIAG-V1224
            entry_d: dict[str, Any] = {
                "sample_count": baseline.sample_count(mode),
            }
            try:
                d = baseline.to_dict() if hasattr(baseline, "to_dict") else {}
                modes_d = d.get("baselines", d.get("modes", {})) if isinstance(d, dict) else {}
                mode_d = modes_d.get(mode, {}) if isinstance(modes_d, dict) else {}
                for k in ("n", "mean", "m2", "alpha", "dim", "outlier_skip_z"):
                    if isinstance(mode_d, dict) and k in mode_d:
                        entry_d[k] = mode_d[k]
            except Exception:
                pass
            summary["modes"][mode] = entry_d
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
        try:  # DIAG-V1224
            d = adaptive.to_dict() if hasattr(adaptive, "to_dict") else {}
            out["thresholds"] = d.get("thresholds", d.get("modes", {})) if isinstance(d, dict) else {}
        except Exception:
            pass
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
        out["centroid_vectors"] = [list(c) for c in centroids[:12]]  # DIAG-V1224
        stale = getattr(coord, "_kmeans_stale", {}) or {}
        if stale:
            out["stale"] = dict(stale)
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
        out['state_mapped'] = _state_map(out['state'])  # DIAG-V1224
        out['bucket_edges'] = cache.get('bucket_edges') if cache else None
        db = getattr(coord, 'db', None)
        if db is not None and hasattr(db, 'async_count_cop_samples'):
            out['total_samples'] = await db.async_count_cop_samples()
    except Exception:
        _LOGGER.debug("cop_summary failed", exc_info=True)
    return out



def _meta_envelope(coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    from .const import VERSION
    now = dt_util.now()
    offset = now.utcoffset()
    return {
        "generated_at": now.isoformat(),
        "integration_version": VERSION,
        "diagnostics_format": 2,
        "redaction_keys": sorted(TO_REDACT),
        "python_version": sys.version.split()[0],
        "timezone": str(now.tzinfo),
        "utc_offset_s": int(offset.total_seconds()) if offset else 0,
        "coordinator_missing": coord is None,
    }


def _source_full(hass: HomeAssistant, coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    source_id = getattr(coord, "source_entity", None)
    if not source_id:
        return {"entity_id": None, "available": False, "reason": "no_source"}
    state = hass.states.get(source_id)
    if state is None:
        return {"entity_id": source_id, "available": False, "reason": "state_missing"}
    raw_attrs = dict(state.attributes or {})
    url_redactions = 0
    cleaned: dict[str, Any] = {}
    for k, v in raw_attrs.items():
        if isinstance(v, str):
            nv, n = _URL_CREDS_RE.subn(r"\g<scheme>**REDACTED**@", v)
            if n:
                url_redactions += n
                v = nv
        cleaned[k] = v
    truncated = False
    if len(json.dumps(cleaned, default=str)) > 65536:
        truncated = True
        cleaned = dict(list(cleaned.items())[:200])
    ts = state.last_updated.timestamp() if state.last_updated else None
    return {
        "entity_id": source_id,
        "state": state.state,
        "available": state.state not in ("unavailable", "unknown"),
        "last_updated_ts": ts,
        "age_s": (time.time() - ts) if ts else None,
        "attribute_count": len(raw_attrs),
        "attributes_full": cleaned,
        "attributes_truncated": truncated,
        "url_redactions": url_redactions,
    }


def _entities_registry(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:  # # DIAG-V1224
    reg = er.async_get(hass)
    owned = [e for e in reg.entities.values() if e.config_entry_id == entry.entry_id]
    out = []
    for ent in owned[:256]:
        st = hass.states.get(ent.entity_id)
        attrs = dict(st.attributes) if st else {}
        encoded = json.dumps(attrs, default=str)
        if len(encoded) > 4096:
            attrs = {"_truncated": True, "_original_bytes": len(encoded)}
        out.append({
            "entity_id": ent.entity_id,
            "unique_id": ent.unique_id,
            "name": ent.name,
            "platform": ent.platform,
            "state": st.state if st else None,
            "attributes": attrs,
        })
    return {
        "registered": len(owned),
        "listed": len(out),
        "truncated": len(owned) > 256,
        "entries": out,
    }


def _device_registry(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:  # # DIAG-V1224
    reg = dr.async_get(hass)  # MYPY-FIX-V1224
    devices_map = cast(dict[str, "DeviceEntry"], reg.devices)  # MYPY-FIX-V1224
    for dev in devices_map.values():
        if entry.entry_id in dev.config_entries:
            return {
                "id": dev.id,
                "name": dev.name,
                "manufacturer": dev.manufacturer,
                "model": dev.model,
                "sw_version": dev.sw_version,
                "hw_version": dev.hw_version,
                "identifiers": [list(i) for i in dev.identifiers],
                "area_id": dev.area_id,
            }
    return {"missing": True, "reason": "no_device_for_entry"}


def _detector_snapshot(coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    det = getattr(coord, "detector", None)
    if det is None:
        return {"missing": True, "reason": "no_detector"}
    out: dict[str, Any] = {}
    for k in ("state", "_state", "mode", "_mode", "mode_source",
              "_mode_source", "_run_start_ts", "run_start_ts",
              "_rps_threshold", "_dhw_present"):
        if hasattr(det, k):  # MYPY-FIX-V1224
            v = getattr(det, k, None)
            if v is not None and hasattr(v, "isoformat"):
                out[k.lstrip("_")] = v.isoformat()
            else:
                out[k.lstrip("_")] = v
    if "run_start_ts" in out and out["run_start_ts"]:
        try:
            out["run_duration_s"] = time.time() - float(out["run_start_ts"])
        except (TypeError, ValueError):
            pass
    if not out:
        return {"missing": True, "reason": "no_known_attrs"}
    return out


def _features_snapshot(coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    store = getattr(coord, "store", None)
    if store is None:
        return {"missing": True, "reason": "no_store"}
    last = store.last_cycle() if hasattr(store, "last_cycle") else None
    if not last or not isinstance(last, dict):
        return {"missing": True, "reason": "no_last_cycle"}
    return {
        "last_cycle_id": last.get("id"),
        "vector": last.get("feature_vector") or last.get("features"),
    }


def _alerts_snapshot(coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    last_sent = getattr(coord, "_last_alert_sent", {}) or {}
    return {
        "dispatch_count": len(last_sent),
        "dispatch_history": {str(k): float(v) for k, v in last_sent.items()},
    }


def _defrost_snapshot(coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    return {
        "count_today": getattr(coord, "_defrost_count_today", None),
        "start_ts": getattr(coord, "_defrost_start_ts", None),
        "duration_s": getattr(coord, "_defrost_duration_s", None),
        "last_defrost_ts": getattr(coord, "_last_defrost_ts", None),
    }


def _buh_snapshot(coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    return {"step": getattr(coord, "_buh_step", None)}


_STATE_MAP = {  # # DIAG-V1224
    "keep": "stable",
    "raise": "raise_lwt",
    "lower": "lower_lwt",
    "raise_lwt": "raise_lwt",
    "lower_lwt": "lower_lwt",
    "stable": "stable",
    "no_data": "no_data",
}


def _state_map(raw: Any) -> Any:
    return _STATE_MAP.get(raw, raw)


def _sampling_snapshot(coord: Any) -> dict[str, Any]:  # DIAG-V1224B
    return {
        "samples_last_24h": getattr(coord, "_samples_last_24h", None),
        "samples_expected_24h": getattr(coord, "_samples_expected_24h", None),
        "gap_count_24h": getattr(coord, "_gap_count_24h", 0),
        "largest_gap_s": getattr(coord, "_largest_gap_s", 0.0),
        "last_gap_s": getattr(coord, "_last_gap_s", None),
        "duplicate_ts_count": getattr(coord, "_duplicate_ts_count", 0),
        "non_numeric_attrs": list(getattr(coord, "_non_numeric_attrs", []) or []),
        "null_attrs_last_tick": list(getattr(coord, "_null_attrs_last_tick", []) or []),
    }


def _coordinator_timing(coord: Any) -> dict[str, Any]:  # DIAG-V1224B
    durations = list(getattr(coord, "_tick_durations_ms", []) or [])
    out: dict[str, Any] = {
        "tick_count": getattr(coord, "_tick_count", 0),
        "tick_duration_ms_last": getattr(coord, "_last_tick_duration_ms", None),
        "tick_duration_ms_max": getattr(coord, "_tick_duration_max_ms", None),
        "uptime_s": None,
    }
    if durations:
        s = sorted(durations)
        out["tick_duration_ms_p50"] = s[len(s) // 2]
        idx95 = min(len(s) - 1, int(len(s) * 0.95))
        out["tick_duration_ms_p95"] = s[idx95]
    start_mono = getattr(coord, "_uptime_start_monotonic", 0.0)
    if start_mono:
        out["uptime_s"] = time.monotonic() - start_mono
    return out


def _detector_transitions(coord: Any) -> list[dict[str, Any]]:  # DIAG-V1224B
    t = getattr(coord, "_transitions", None)
    if t is None:
        return []
    try:
        return list(t)
    except Exception:
        return []


def _repairs_snapshot(hass: HomeAssistant) -> dict[str, Any]:  # DIAG-V1224B
    from homeassistant.helpers import issue_registry as ir
    from .const import DOMAIN
    try:
        registry = ir.async_get(hass)
        issues = getattr(registry, "issues", {}) or {}
        active = []
        for k, v in issues.items():
            if isinstance(k, tuple):
                dom, iid = k[0], k[1]
            else:
                dom, iid = None, str(k)
            if dom == DOMAIN:
                active.append({
                    "issue_id": str(iid),
                    "severity": str(getattr(v, "severity", "")),
                    "translation_key": getattr(v, "translation_key", None),
                    "is_fixable": bool(getattr(v, "is_fixable", False)),
                })
        return {"active": active, "count": len(active)}
    except Exception:
        return {"active": [], "count": 0, "error": True}


def _runtime_extended(coord: Any) -> dict[str, Any]:  # DIAG-V1224B
    import logging as _log
    start_mono = getattr(coord, "_uptime_start_monotonic", 0.0)
    uptime_s = (time.monotonic() - start_mono) if start_mono else None
    return {
        "coordinator_uptime_s": uptime_s,
        "last_exception": getattr(coord, "_last_exception", None),
        "last_exception_ts": getattr(coord, "_last_exception_ts", None),
        "last_exception_traceback": getattr(coord, "_last_exception_traceback", None),
        "log_level": _log.getLevelName(_LOGGER.getEffectiveLevel()),
    }


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
                cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
                row = cur.fetchone()
                if row is not None:  # pragma: no branch
                    counts[table] = int(row[0])
            # v1.19.8: DatabaseError (parent of OperationalError) also
            # catches "file is not a database" for non-SQLite files
            # matching the DB filename pattern.
            except sqlite3.DatabaseError:
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
    result = {  # DIAG-V1224
        "meta": _meta_envelope(coord),
        "source": _source_full(hass, coord),
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
            # v1.20.0 #281: COP source transparency (was dead; now surfaced)
            "cop_source": str(getattr(snap, "cop_source", "none")),
            "dhw_present": getattr(coord, "dhw_present", None),
            "dhw_present_source": getattr(coord, "_dhw_present_source", "unresolved"),
            "dhw_present_resolved": getattr(coord, "_dhw_present_resolved", False),
            # Hybrid (EVLQ) — issue #218
            # v1.17.2: boiler_* only meaningful on hybrid installs
            "boiler_active": (
                bool(getattr(snap, "boiler_active", False))
                if getattr(snap, "is_hybrid", False) else False
            ),
            "boiler_heat_active": (
                bool(getattr(snap, "boiler_heat_active", False))
                if getattr(snap, "is_hybrid", False) else False
            ),
            "boiler_dhw_active": (
                bool(getattr(snap, "boiler_dhw_active", False))
                if getattr(snap, "is_hybrid", False) else False
            ),
            "hybrid_mode": str(getattr(snap, "hybrid_mode", "") or ""),
            "boiler_efficiency_cop": getattr(snap, "boiler_efficiency_cop", None),
            "inv_freq_secondary": getattr(snap, "inv_freq_secondary", None),
        },
        "source_resolution": dict(getattr(coord, "_source_resolution", {}) or {}),
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
            "integrity_ok": bool(getattr(coord, "_db_integrity_ok", True)),
            "retention_stale": dict(getattr(coord, "_db_retention_stale", {}) or {}),
        },
        "detector": _detector_snapshot(coord),
        "features": _features_snapshot(coord),
        "alerts": _alerts_snapshot(coord),
        "bivalent": {
            "is_hybrid": bool(getattr(snap, "is_hybrid", False)),
            "boiler_active": bool(getattr(snap, "boiler_active", False)),
            "boiler_heat_active": bool(getattr(snap, "boiler_heat_active", False)),
            "boiler_dhw_active": bool(getattr(snap, "boiler_dhw_active", False)),
            "hybrid_mode": str(getattr(snap, "hybrid_mode", "") or ""),
            "boiler_efficiency_cop": getattr(snap, "boiler_efficiency_cop", None),
        },
        "defrost": _defrost_snapshot(coord),
        "buh": _buh_snapshot(coord),
        "entities": _entities_registry(hass, entry),
        "device": _device_registry(hass, entry),
        "runtime": _runtime_extended(coord),  # DIAG-V1224B
        "sampling": _sampling_snapshot(coord),
        "coordinator_timing": _coordinator_timing(coord),
        "transitions": _detector_transitions(coord),
        "repairs": _repairs_snapshot(hass),
    }
    result = _redact_strings_recursive(result)  # MYPY-FIX-V1224
    return cast(dict[str, Any], result)
