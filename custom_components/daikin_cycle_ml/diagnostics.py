"""Diagnostics support for Daikin Cycle ML (extended 12c)."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import (
    Any,
    cast,  # MYPY-FIX-V1224
)

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BUH_STEP1, ATTR_BUH_STEP2, DB_FILENAME, DB_FILENAME_TEMPLATE, REPORTS_BACKFILL_MARKER,
)
from .coordinator import DaikinCycleMLConfigEntry
from .engine.model_catalog import model_check
from .engine.thermal import _flow_dt_kw, dt_from_attrs, flow_from_attrs
from .ml.features import FEATURE_NAMES
from .storage import reports as _report_store
from .storage.report_builder import REPORTS_STATE_KEY
from .engine.thermal import boiler_signals_trusted as _boiler_signals_trusted

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


async def _db_extra(db: Any) -> dict[str, Any]:
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


_BUILDING_KEYS = ("outdoor_mean", "indoor_mean", "indoor_source", "indoor_drift",
                  "heat_sh_signed_kwh", "heat_sh_s", "sun_h", "coverage", "degree_days")


async def _building_last7(conn: Any) -> list[dict[str, Any]]:
    """#495: the building's day values of the last seven days (all modes)."""
    today = time.strftime("%Y-%m-%d")
    first = time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400))
    rows = await _report_store.fetch_days(conn, first, today, mode="all")
    return [{"day": r["day"], **{k: (r.get("data") or {}).get(k) for k in _BUILDING_KEYS}}
            for r in rows]


async def _reports_summary(coord: Any) -> dict[str, Any]:
    """#508: period-report counts, the last build and the last month."""
    db = getattr(coord, "db", None)
    out: dict[str, Any] = {
        "degree_day_scheme": getattr(coord, "degree_day_scheme", None),
        "last_month": getattr(coord, "last_month_report", None),
    }
    if db is None or not getattr(db, "is_open", False):
        return out
    try:
        out["state"] = await db.async_get_model_state(REPORTS_STATE_KEY)
        out["backfill"] = await db.async_get_model_state(REPORTS_BACKFILL_MARKER)
        out["counts"] = await _report_store.counts(db._require())
        out["building_day_last7"] = await _building_last7(db._require())  # #495
    except Exception:
        _LOGGER.debug("diagnostics: period reports failed")
    return out


def _baseline_summary(coord: Any) -> dict[str, Any]:
    baseline = getattr(coord, "baseline", None)
    if baseline is None:
        return {}
    summary: dict[str, Any] = {"total_samples": 0, "modes": {}}
    if hasattr(baseline, "summary"):  # #443: ML v2 behaviour baseline
        try:
            summary.update(baseline.summary())
            summary["total_samples"] = baseline.total_samples()
        except Exception:
            _LOGGER.debug("diagnostics: baseline summary failed")
        return summary
    try:  # a baseline without summary(): only its sample count
        summary["total_samples"] = baseline.total_samples()
    except Exception:
        _LOGGER.debug("diagnostics: baseline summary failed")
    return summary


def _adaptive_summary(coord: Any) -> dict[str, Any]:
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
        # #339 A1: what is learned per mode, with the sample counts behind it
        # (to_dict() holds raw samples, never per-mode thresholds)
        out["thresholds"] = {
            m: {**adaptive.suggest(m), "samples": adaptive.sample_count(m)}
            for m in out["modes"]
        }
    except Exception:
        _LOGGER.debug("diagnostics: adaptive summary failed")
    return out


async def _cluster_summary(coord: Any) -> dict[str, Any]:
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


def _bucket_edges(buckets: Any) -> list[float | None] | None:
    """#339 A5: outdoor-band edges from the bucket keys ("-2-0", "20+",
    "-10-" below -10); None marks an open end."""
    if not isinstance(buckets, dict) or not buckets:
        return None
    edges: set[float] = set()
    low = high = False
    for key in buckets:
        k = str(key)
        m = re.fullmatch(r"(-?\d+)-(-?\d+)", k)
        if m:
            edges.update((float(m.group(1)), float(m.group(2))))
        elif re.fullmatch(r"-?\d+\+", k):
            edges.add(float(k[:-1]))
            high = True
        elif re.fullmatch(r"-?\d+-", k):
            edges.add(float(k[:-1]))
            low = True
    if not edges:
        return None
    out: list[float | None] = [None] if low else []
    out.extend(sorted(edges))
    return out + ([None] if high else [])


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
        out['bucket_edges'] = _bucket_edges(out['buckets'])
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
    # v1.22.10: modern device registry API. Old code relied on the
    # dictionary-style mapping access and the plural-fields attribute
    # that HA removes in 2027.9 and 2027.10 respectively.
    reg = dr.async_get(hass)
    for dev in dr.async_entries_for_config_entry(reg, entry.entry_id):
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
    # #339 A3: the detector's real fields (start_ts, pending mode switch,
    # continued run, defrost hold) and the rps threshold from its options
    for k in ("state", "_state", "mode", "_mode", "_start_ts", "_pending_mode",
              "_pending_mode_since", "_continued", "_defrost_hold_s",
              "_pump_off_count", "_dhw_present"):
        if hasattr(det, k):  # MYPY-FIX-V1224
            v = getattr(det, k, None)
            if v is not None and hasattr(v, "isoformat"):
                out[k.lstrip("_")] = v.isoformat()
            else:
                out[k.lstrip("_")] = v
    opts = getattr(det, "_options", None)
    if isinstance(opts, dict) and "compressor_rps_threshold" in opts:
        out["rps_threshold"] = opts["compressor_rps_threshold"]
    if isinstance(out.get("start_ts"), (int, float)) and out["start_ts"]:
        out["run_duration_s"] = round(time.time() - float(out["start_ts"]), 1)
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


async def _features_db(coord: Any) -> dict[str, Any]:
    """#339 A2: the feature vector of the last closed cycle lives in the
    database (features table), not in the cycle store; store as fallback."""
    db = getattr(coord, "db", None)
    if db is not None and getattr(db, "is_open", False):
        try:
            row = await db.async_get_latest_feature_vector()
        except Exception:
            _LOGGER.debug("diagnostics: latest feature vector failed", exc_info=True)
            row = None
        if row:
            return {"last_cycle_id": row["cycle_id"], "vector": row["vector"], "names": list(FEATURE_NAMES)}
    return _features_snapshot(coord)


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
        # #463: events, running hours and the weather-aware limit (7 days)
        "limit_7d": getattr(coord, "_defrost_7d", None),
    }


def _on(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().upper() in ("ON", "1", "TRUE")
    if isinstance(v, (int, float)):
        return v > 0
    return False


def _buh_snapshot(coord: Any) -> dict[str, Any]:  # # DIAG-V1224
    """#339 A4: the backup heater's current step from the source (0 off,
    1 step 1, 2 step 2) and today's seconds per step."""
    attrs = getattr(coord, "last_attrs", None)
    attrs = attrs if isinstance(attrs, dict) else {}
    s1, s2 = attrs.get(ATTR_BUH_STEP1), attrs.get(ATTR_BUH_STEP2)
    step: int | None = None
    if s1 is not None or s2 is not None:
        step = 2 if _on(s2) else 1 if _on(s1) else 0
    return {"step": step, "step1_s": getattr(coord, "_buh_step1_s", None),
            "step2_s": getattr(coord, "_buh_step2_s", None)}

def _notify_health_snapshot(coord: Any) -> dict[str, Any]:
    """#384: notify-dispatch health (fail-streak counters)."""
    if coord is None:
        return {}
    h = getattr(coord, "notify_health", None)
    if isinstance(h, dict):
        return {str(k): v for k, v in h.items()}
    return {}


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


def _sampling_snapshot(coord: Any) -> dict[str, Any]:  # DIAG-V1224B / A3a
    primed = bool(getattr(coord, "_samples_window_primed", False))
    last = getattr(coord, "_samples_last_24h", None)
    expected_since = getattr(coord, "_samples_expected_since_start", 0)
    # #515: past a day the rate is the last 24 h against what 24 h expects
    expected = getattr(coord, "_samples_expected_24h", None) if primed else expected_since
    rate_pct = (
        round(min(100.0, last / expected * 100.0), 1)
        if isinstance(expected, int) and expected > 0 and isinstance(last, int)
        else None
    )
    return {
        "samples_window": "24h" if primed else "since_start",
        "samples_last_24h": last,
        "samples_since_start": last if not primed else None,
        "samples_expected_since_start": expected_since if not primed else None,
        "sample_rate_pct": rate_pct,
        "samples_expected_24h": getattr(coord, "_samples_expected_24h", None),
        "gap_count_24h": getattr(coord, "_gap_count_24h", 0),
        "largest_gap_s": getattr(coord, "_largest_gap_s", 0.0),
        "last_gap_s": getattr(coord, "_last_gap_s", None),
        "duplicate_ts_count": getattr(coord, "_duplicate_ts_count", 0),
        "non_numeric_attrs": list(getattr(coord, "_non_numeric_attrs", []) or []),
        "null_attrs_last_tick": list(getattr(coord, "_null_attrs_last_tick", []) or []),
    }


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _power_meter(coord: Any) -> dict[str, Any] | None:
    """#435: is the configured power meter used, its unit, why not."""
    pm = getattr(coord, "power_meter_status", None)
    return pm if isinstance(pm, dict) else None


def _cop_cross_check(coord: Any, snap: Any) -> dict[str, Any]:
    """#408 D: COP used vs measured (flow x dT / power) vs ESPAltherma.

    An external ``cop_sensor_entity`` below MAX_COP is used as-is; this
    makes a disagreeing sensor visible (prod-1: sensor 7.59, measured
    6.1, ESPAltherma 5.61).
    """
    attrs = getattr(snap, "attrs", None) or {}
    used = _num(getattr(snap, "cop", None))
    measured: float | None = None
    try:
        flow, dt = flow_from_attrs(attrs), dt_from_attrs(attrs)
        reader = getattr(coord, "_read_power_w", None)
        power_w = _num(reader()) if callable(reader) else None
        if flow and dt and dt > 0 and power_w and power_w > 0:
            measured = round(_flow_dt_kw(flow, dt) * 1000.0 / power_w, 2)
    except Exception:
        measured = None
    esp = attrs.get("Stats: COP estimated")
    esp_cop = _num(esp)
    dev = (
        round((used - measured) / measured * 100.0, 1)
        if used is not None and measured else None
    )
    return {
        "cop_used": used,
        "cop_source": str(getattr(snap, "cop_source", "none")),
        "cop_measured_flow_dt_power": measured,
        "cop_espaltherma_estimate": esp_cop,
        "used_vs_measured_pct": dev,
    }


def _runtime_check(coord: Any, snap: Any, now: float | None = None) -> dict[str, Any]:
    """#419: today's runtime from the cycles vs ESPAltherma's own counter.

    Cycles = closed cycles' portions since local midnight + the open
    cycle's portion. A heat pump running 24/7 should show close to 100 %
    of the native ``Stats: Compressor run today (min)``; a shortfall
    means runs were not captured (prod-1 before #417: lost on restart).
    """
    t = time.time() if now is None else float(now)
    lt = time.localtime(t)
    midnight = time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
    )
    closed = 0.0
    try:
        for cy in coord.store.cycles_intersecting(midnight, t) or ():
            st, en = _num(cy.get("start_ts")), _num(cy.get("end_ts"))
            if st is not None and en is not None:
                closed += max(0.0, min(en, t) - max(st, midnight))
    except Exception:
        closed = 0.0
    open_s = 0.0
    try:
        det = coord.detector.snapshot()
        start = _num(det.get("start_ts"))
        if det.get("state") == "running" and start is not None:
            open_s = max(0.0, t - max(start, midnight))
    except Exception:
        open_s = 0.0
    attrs = getattr(snap, "attrs", None) or {}
    native = _num(attrs.get("Stats: Compressor run today (min)"))
    cycles_min = round((closed + open_s) / 60.0, 1)
    return {
        "elapsed_min": round((t - midnight) / 60.0, 1),
        "cycles_min": cycles_min,
        "closed_min": round(closed / 60.0, 1),
        "open_cycle_min": round(open_s / 60.0, 1),
        "native_min": native,
        # #466: False when the ESP's today counters do not reset at midnight
        "native_daily": native is None or native <= round((t - midnight) / 60.0, 1) + 5.0,
        "diff_min": round(cycles_min - native, 1) if native is not None else None,
        "coverage_pct": (
            round(cycles_min / native * 100.0, 1) if native else None
        ),
    }


def _int_or_zero(v: Any) -> int:
    """#353: tolerate mocks / missing attributes in diagnostics."""
    return int(v) if isinstance(v, int) and not isinstance(v, bool) else 0


def _coordinator_timing(coord: Any) -> dict[str, Any]:  # DIAG-V1224B
    durations = list(getattr(coord, "_tick_durations_ms", []) or [])
    out: dict[str, Any] = {
        "tick_count": getattr(coord, "_tick_count", 0),
        "tick_duration_ms_last": getattr(coord, "_last_tick_duration_ms", None),
        "tick_duration_ms_max": getattr(coord, "_tick_duration_max_ms", None),
        # #353 A3c: when + where the slowest tick happened. tick 1 is the
        # startup refresh; slowest_phases_ms names the top-3 steps.
        "tick_duration_max_ts": getattr(coord, "_tick_duration_max_ts", None),
        "tick_duration_max_tick": getattr(coord, "_tick_duration_max_tick", None),
        "tick_duration_max_phases_ms": dict(
            getattr(coord, "_tick_duration_max_phases", {}) or {}
        ),
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
    except OSError:
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
    hass: HomeAssistant, entry: DaikinCycleMLConfigEntry
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
            "cop_cross_check": _cop_cross_check(coord, snap),
            "power_meter": _power_meter(coord),
            "runtime_check": _runtime_check(coord, snap),
            "dhw_present": getattr(coord, "dhw_present", None),
            "dhw_present_source": getattr(coord, "_dhw_present_source", "unresolved"),
            "dhw_present_resolved": getattr(coord, "_dhw_present_resolved", False),
            # Hybrid (EVLQ) — issue #218
            # v1.17.2 / #288: boiler_* only meaningful when trusted
            # (hybrid install or bivalent opt-in)
            "boiler_active": (
                bool(getattr(snap, "boiler_active", False))
                if _boiler_signals_trusted(snap) else False
            ),
            "boiler_heat_active": (
                bool(getattr(snap, "boiler_heat_active", False))
                if _boiler_signals_trusted(snap) else False
            ),
            "boiler_dhw_active": (
                bool(getattr(snap, "boiler_dhw_active", False))
                if _boiler_signals_trusted(snap) else False
            ),
            "hybrid_mode": str(getattr(snap, "hybrid_mode", "") or ""),
            "boiler_efficiency_cop": getattr(snap, "boiler_efficiency_cop", None),
            "inv_freq_secondary": getattr(snap, "inv_freq_secondary", None),
        },
        "source_resolution": dict(getattr(coord, "_source_resolution", {}) or {}),
        # #522: the configured model against the unit code ESPAltherma reports
        "model_check": model_check(hass, dict(entry.data or {}).get("model")),
        "store": {
            "cycle_count": store.count(),
            "counters": counters,
            "last_cycle": store.last_cycle(),
        },
        "baseline": _baseline_summary(coord),
        "adaptive": _adaptive_summary(coord),
        "clusters": await _cluster_summary(coord),
        "cop_analysis": await _cop_summary(coord),
        "period_reports": await _reports_summary(coord),
        "database": {
            "path": getattr(db, "path", None),
            "is_open": bool(getattr(db, "is_open", False)),
            "counts": await _db_counts(db),
            "extra": await _db_extra(db),
            "per_entry": db_files["per_entry"],
            "legacy": db_files["legacy"],
            "integrity_ok": bool(getattr(coord, "_db_integrity_ok", True)),
            "retention_stale": dict(getattr(coord, "_db_retention_stale", {}) or {}),
            # #353 A3c: cop samples waiting after a lock + last VACUUM.
            "pending_cop_samples": _int_or_zero(getattr(db, "pending_cop_samples", 0)),
            "last_vacuum": dict(getattr(db, "last_vacuum", {}) or {}),
        },
        "detector": _detector_snapshot(coord),
        "features": await _features_db(coord),
        "alerts": _alerts_snapshot(coord),
        "bivalent": {
            "is_hybrid": bool(getattr(snap, "is_hybrid", False)),
            "is_bivalent": getattr(snap, "is_bivalent", False) is True,
            "boiler_signals_trusted": _boiler_signals_trusted(snap),
            "boiler_active": bool(getattr(snap, "boiler_active", False)),
            "boiler_heat_active": bool(getattr(snap, "boiler_heat_active", False)),
            "boiler_dhw_active": bool(getattr(snap, "boiler_dhw_active", False)),
            "hybrid_mode": str(getattr(snap, "hybrid_mode", "") or ""),
            "boiler_efficiency_cop": getattr(snap, "boiler_efficiency_cop", None),
        },
        "defrost": _defrost_snapshot(coord),
        # #467: the user's model profile and the learned compressor range
        "model_profile": {
            "stored": getattr(coord, "model_profile", None),
            "rps_learned": getattr(coord, "rps_learned", None),
            "hmax_learned": getattr(coord, "hmax_learned", None),
        },
        "buh": _buh_snapshot(coord),
        "entities": _entities_registry(hass, entry),
        "device": _device_registry(hass, entry),
        "runtime": _runtime_extended(coord),  # DIAG-V1224B
        "sampling": _sampling_snapshot(coord),
        "notify_health": _notify_health_snapshot(coord),
        "coordinator_timing": _coordinator_timing(coord),
        "transitions": _detector_transitions(coord),
        "repairs": _repairs_snapshot(hass),
    }
    result = _redact_strings_recursive(result)  # MYPY-FIX-V1224
    return cast(dict[str, Any], result)
