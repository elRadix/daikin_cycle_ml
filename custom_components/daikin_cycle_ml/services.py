"""Services for Daikin Cycle ML (Batch 6b-1)."""
from __future__ import annotations

import csv
import io
import json
import logging
import shutil
import sqlite3
import time
from functools import partial
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError

from .const import DB_FILENAME, DB_FILENAME_TEMPLATE, DOMAIN
from .engine import model_datasheets as md
from .repairs import (
    clear_datasheet_import_invalid,
    clear_datasheet_schema_unknown,
    clear_legacy_db_multi_entry,
    raise_datasheet_import_invalid,
    raise_datasheet_schema_unknown,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_RESET_COUNTERS = "reset_counters"
SERVICE_EXPORT_CYCLES = "export_cycles"
SERVICE_LABEL_CYCLE = "label_cycle"
SERVICE_RECOMPUTE_BASELINE = "recompute_baseline"
SERVICE_RECOMPUTE_KMEANS = "recompute_kmeans"
SERVICE_RUN_MAINTENANCE = "run_maintenance"
SERVICE_SEND_TEST_NOTIFICATION = "send_test_notification"
SERVICE_EXPORT_COP_HOURLY = "export_cop_hourly"
SERVICE_IMPORT_DATASHEET = "import_datasheet"
SERVICE_REMOVE_USER_DATASHEET = "remove_user_datasheet"
SERVICE_ASSIGN_LEGACY_DB = "assign_legacy_db"
SERVICE_ARCHIVE_LEGACY_DB = "archive_legacy_db"
SERVICE_EXPORT_LEGACY_DB = "export_legacy_db"
ATTR_MESSAGE = "message"
ATTR_TARGET = "target"
ATTR_CYCLE_RETENTION_DAYS = "cycle_retention_days"
ATTR_ALERT_RETENTION_DAYS = "alert_retention_days"
ATTR_VACUUM = "vacuum"

ATTR_ENTRY_ID = "entry_id"
ATTR_COUNTERS = "counters"
ATTR_DAYS = "days"
ATTR_FORMAT = "format"
ATTR_CYCLE_ID = "cycle_id"
ATTR_LABEL = "label"
ATTR_MODE = "mode"
ATTR_PAYLOAD = "payload"
ATTR_SOURCE_URL = "source_url"
ATTR_MODEL_KEY = "model_key"
ATTR_ALERT_KIND = "alert_kind"
ATTR_IGNORE_FILTERS = "ignore_filters"
ATTR_TARGET_ENTRY_ID = "target_entry_id"

SCHEMA_RESET = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_COUNTERS): vol.Any(None, [str]),
})

SCHEMA_EXPORT = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_DAYS, default=30): vol.All(int, vol.Range(min=1, max=3650)),
    vol.Optional(ATTR_FORMAT, default="json"): vol.In(["json", "csv"]),
})

SCHEMA_LABEL = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Required(ATTR_CYCLE_ID): int,
    vol.Required(ATTR_LABEL): str,
})

SCHEMA_BASELINE = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_DAYS, default=7): vol.All(int, vol.Range(min=1, max=365)),
})


SCHEMA_RECOMPUTE_KMEANS = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_DAYS, default=7): vol.All(int, vol.Range(min=1, max=365)),
})

SCHEMA_RUN_MAINTENANCE = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_CYCLE_RETENTION_DAYS): int,
    vol.Optional(ATTR_ALERT_RETENTION_DAYS): int,
    vol.Optional(ATTR_VACUUM): bool,
})


SCHEMA_SEND_TEST = vol.Schema({
    vol.Optional(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_MESSAGE): str,
    vol.Optional(ATTR_TARGET): vol.All(
        str, vol.Match(r"^notify\.[a-z0-9_]+\Z")
    ),
    vol.Optional(ATTR_ALERT_KIND): str,
    vol.Optional(ATTR_IGNORE_FILTERS): bool,
})

SCHEMA_EXPORT_COP_HOURLY = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Optional(ATTR_DAYS, default=30): vol.All(
        int, vol.Range(min=1, max=365)
    ),
    vol.Optional(ATTR_MODE): vol.Any(None, str),
    vol.Optional(ATTR_FORMAT, default="json"): vol.In(["json", "csv"]),
})


SCHEMA_IMPORT_DATASHEET = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Required(ATTR_PAYLOAD): vol.Any(dict, str),
    vol.Optional(ATTR_SOURCE_URL): vol.Any(None, str),
})

SCHEMA_REMOVE_USER_DATASHEET = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Required(ATTR_MODEL_KEY): str,
})

SCHEMA_ASSIGN_LEGACY_DB = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
    vol.Required(ATTR_TARGET_ENTRY_ID): str,
})
SCHEMA_ARCHIVE_LEGACY_DB = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
})
SCHEMA_EXPORT_LEGACY_DB = vol.Schema({
    vol.Required(ATTR_ENTRY_ID): str,
})


def _resolve_coordinator(hass: HomeAssistant, entry_id: str) -> Any:
    entry: ConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise HomeAssistantError(f"Unknown config entry: {entry_id}")
    coord = getattr(entry, "runtime_data", None)
    if coord is None:
        raise HomeAssistantError(f"Coordinator not ready for entry {entry_id}")
    return coord


def _resolve_optional_coordinator(
    hass: HomeAssistant, entry_id: str | None
) -> Any:
    """Resolve coord; auto-pick if only one Daikin entry is loaded."""
    if entry_id:
        return _resolve_coordinator(hass, entry_id)
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("No Daikin Cycle ML config entry loaded")
    if len(entries) > 1:
        raise HomeAssistantError(
            "Multiple config entries; specify entry_id "
            f"({len(entries)} found)"
        )
    return _resolve_coordinator(hass, entries[0].entry_id)


# ---------- pure do-functions (unit-testable) ----------

def _do_reset_counters(coordinator: Any, counters: list[str] | None) -> dict[str, Any]:
    coordinator.store.reset(counters)
    return {"reset": True, "counters": counters if counters else "all"}


def _do_export_cycles(coordinator: Any, days: int, fmt: str) -> dict[str, Any]:
    cutoff = time.time() - float(days) * 86400.0
    cycles = [
        dict(c) for c in coordinator.store.cycles()
        if isinstance(c.get("start_ts"), (int, float)) and c["start_ts"] >= cutoff
    ]
    if fmt == "csv":
        buf = io.StringIO()
        if cycles:
            writer = csv.DictWriter(buf, fieldnames=list(cycles[0].keys()))
            writer.writeheader()
            writer.writerows(cycles)
        return {"format": "csv", "days": days, "content": buf.getvalue()}
    return {"format": "json", "days": days, "cycles": cycles}


async def _do_export_cop_hourly(
    coordinator: Any, days: int, mode: str | None, fmt: str,
) -> dict[str, Any]:
    """Export cop_hourly rows as JSON dict or CSV string."""
    db = getattr(coordinator, "db", None)
    if db is None:
        raise HomeAssistantError("Database not available")
    since_ts = time.time() - float(days) * 86400.0
    rows = await db.async_query_cop_hourly(since_ts=since_ts, mode=mode)
    if fmt == "csv":
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(
                buf, fieldnames=list(rows[0].keys())
            )
            writer.writeheader()
            writer.writerows(rows)
        return {
            "format": "csv", "days": days, "mode": mode,
            "count": len(rows), "content": buf.getvalue(),
        }
    return {
        "format": "json", "days": days, "mode": mode,
        "count": len(rows), "rows": rows,
    }


async def _handle_export_cop_hourly(
    hass: HomeAssistant, call: ServiceCall,
) -> dict[str, Any]:
    entry_id = call.data[ATTR_ENTRY_ID]
    coord = _resolve_coordinator(hass, entry_id)
    days = call.data.get(ATTR_DAYS, 30)
    mode = call.data.get(ATTR_MODE)
    fmt = call.data.get(ATTR_FORMAT, "json")
    return await _do_export_cop_hourly(coord, days, mode, fmt)

async def _do_label_cycle(coordinator: Any, cycle_id: int, label: str) -> dict[str, Any]:
    db = getattr(coordinator, "db", None)
    if db is None:
        raise HomeAssistantError("Database not available")
    ok = await db.async_label_cycle(cycle_id, label)
    return {"labeled": bool(ok), "cycle_id": cycle_id, "label": label}


async def _do_recompute_baseline(coordinator: Any, days: int) -> dict[str, Any]:
    db = getattr(coordinator, "db", None)
    if db is None:
        return {"computed": False, "reason": "no_db", "days": days}
    mb = getattr(coordinator, "baseline", None)
    if mb is None:
        return {"computed": False, "reason": "no_baseline", "days": days}
    try:
        cycles = await db.async_fetch_cycles(days=days)
    except Exception as err:
        return {
            "computed": False,
            "reason": "fetch_failed",
            "days": days,
            "error": str(err),
        }
    if not cycles:
        return {"computed": False, "reason": "no_data", "days": days, "samples": 0}
    from .ml.features import extract_feature_vector, is_valid_record
    try:
        mb.reset()
    except Exception as err:
        _LOGGER.debug("baseline reset failed: %s", err)
    fed = 0
    for rec in cycles:
        if not is_valid_record(rec):
            continue
        try:
            vec = extract_feature_vector(rec)
        except Exception as err:
            _LOGGER.debug(
                "feature extraction failed for cycle %s: %s",
                rec.get("id"), err,
            )
            continue
        mode = rec.get("mode") or "unknown"
        try:
            mb.update(mode, vec)
            fed += 1
        except Exception as err:
            _LOGGER.debug(
                "baseline update failed for mode %s: %s", mode, err,
            )
            continue
    try:
        await db.async_set_model_state("baseline_state", mb.to_dict())
    except Exception as err:
        _LOGGER.warning("Failed to persist baseline state: %s", err)
    return {"computed": True, "days": days, "samples": fed}


# ---------- HA handlers ----------

async def _handle_reset_counters(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return _do_reset_counters(coord, call.data.get(ATTR_COUNTERS))


async def _handle_export_cycles(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return _do_export_cycles(coord, call.data[ATTR_DAYS], call.data[ATTR_FORMAT])


async def _handle_label_cycle(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return await _do_label_cycle(coord, call.data[ATTR_CYCLE_ID], call.data[ATTR_LABEL])


async def _handle_recompute_baseline(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    return await _do_recompute_baseline(coord, call.data[ATTR_DAYS])


async def _handle_recompute_kmeans(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Trigger a kmeans retrain, notify the user, return the result."""
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    days = int(call.data.get(ATTR_DAYS, 7))
    _raw = await coord.async_run_kmeans(days=days)
    result: dict[str, Any] = dict(_raw) if isinstance(_raw, dict) else {"ok": False, "reason": "bad_result"}
    _fire_kmeans_notification(hass, result)
    return result


def _fire_kmeans_notification(
    hass: HomeAssistant, result: dict[str, Any]
) -> None:
    """Emit a persistent notification describing the kmeans retrain outcome."""
    from .engine.status_report import KMEANS_ADVICE_BY_REASON
    try:
        if result.get("ok"):
            n = int(result.get("n", 0) or 0)
            k = int(result.get("k", 0) or 0)
            msg = f"K-means retrain succeeded \u2014 {n} cycles, {k} clusters"
            title = "Daikin Cycle ML \u2014 K-means retrain"
        else:
            reason = str(result.get("reason", "unknown"))
            table = KMEANS_ADVICE_BY_REASON.get(
                "en", KMEANS_ADVICE_BY_REASON["en"]
            )
            advice = table.get(reason) or table.get(None, "")
            msg = f"K-means retrain failed \u2014 {reason}. {advice}"
            title = "Daikin Cycle ML \u2014 K-means retrain failed"
        hass.async_create_task(hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": msg,
                "notification_id": f"daikin_cycle_ml_recompute_kmeans_{int(time.time())}",
            },
            blocking=False,
        ))
    except Exception:
        _LOGGER.exception("recompute_kmeans notification failed")


async def _handle_run_maintenance(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coord = _resolve_coordinator(hass, call.data[ATTR_ENTRY_ID])
    runner = getattr(coord, "async_run_maintenance", None)
    if runner is None:
        return {"ok": False, "reason": "not_supported"}
    result: dict[str, Any] = await runner(
        cycle_retention_days=call.data.get(ATTR_CYCLE_RETENTION_DAYS),
        alert_retention_days=call.data.get(ATTR_ALERT_RETENTION_DAYS),
        vacuum=call.data.get(ATTR_VACUUM),
        force=True,
    )
    return result


async def _handle_send_test_notification(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    coord = _resolve_optional_coordinator(
        hass, call.data.get(ATTR_ENTRY_ID)
    )
    alert_kind = call.data.get(ATTR_ALERT_KIND)
    if alert_kind:
        msg = await coord.async_emit_test_alert(
            str(alert_kind),
            ignore_filters=bool(
                call.data.get(ATTR_IGNORE_FILTERS, False)
            ),
        )
        return {
            "ok": True,
            "alert_kind": str(alert_kind),
            "message": msg,
        }
    from .engine.notification_engine import async_send_notification
    opts = getattr(coord, "options", None) or {}
    target = call.data.get(ATTR_TARGET) or opts.get("notify_service") or ""
    if target and not target.startswith("notify."):
        _LOGGER.warning("Refused non-notify target %s", target)
        return {"ok": False, "target": target, "error": "target must be notify.*"}
    msg = (
        call.data.get(ATTR_MESSAGE)
        or "Daikin Cycle ML: test notification"
    )
    ok = await async_send_notification(hass, target, msg)
    return {"ok": bool(ok), "target": target, "message": msg}

async def _handle_import_datasheet(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    entry_id = call.data[ATTR_ENTRY_ID]
    coord = _resolve_coordinator(hass, entry_id)
    raw = call.data[ATTR_PAYLOAD]

    payload: Any = raw
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors = [f"json parse error: {exc}"]
            raise_datasheet_import_invalid(hass, entry_id, errors)
            return {"imported": [], "errors": errors}

    clean, errors = md.validate_user_payload(payload)
    found = payload.get("schema_version") if isinstance(payload, dict) else None
    if found is not None and found != md.KNOWN_SCHEMA_VERSION:
        raise_datasheet_schema_unknown(hass, entry_id, found)
    elif errors:
        raise_datasheet_import_invalid(hass, entry_id, errors)

    if not clean:
        return {"imported": [], "errors": errors or ["no valid models"]}

    existing = await md.load_user(hass, entry_id)
    merged = {**existing, **clean}
    await md.save_user(hass, entry_id, merged)
    clear_datasheet_import_invalid(hass, entry_id)
    clear_datasheet_schema_unknown(hass, entry_id)

    reload_fn = getattr(coord, "async_reload_user_datasheets", None)
    if reload_fn is not None:
        await reload_fn()
    return {"imported": sorted(clean.keys()), "errors": errors}


async def _handle_remove_user_datasheet(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    entry_id = call.data[ATTR_ENTRY_ID]
    coord = _resolve_coordinator(hass, entry_id)
    model_key = call.data[ATTR_MODEL_KEY]

    removed = await md.remove_user_model(hass, entry_id, model_key)
    if removed:
        reload_fn = getattr(coord, "async_reload_user_datasheets", None)
        if reload_fn is not None:
            await reload_fn()
    return {"removed": removed, "model_key": model_key}



async def _handle_assign_legacy_db(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Move the per-entry DB from one config entry to another.

    Multi-entry correction: legacy data was auto-assigned to the oldest
    entry during migration. This service moves that live per-entry DB to
    a different config entry that does not yet have its own DB. Both
    entries must be reloaded for the change to take effect.
    """
    source_id = str(call.data[ATTR_ENTRY_ID])
    target_id = str(call.data[ATTR_TARGET_ENTRY_ID])

    if source_id == target_id:
        return {"ok": False, "reason": "source_equals_target"}

    target_entry = hass.config_entries.async_get_entry(target_id)
    if target_entry is None:
        return {"ok": False, "reason": "target_entry_not_found"}

    storage = Path(hass.config.config_dir) / ".storage"
    source_db = storage / DB_FILENAME_TEMPLATE.format(entry_id=source_id)
    target_db = storage / DB_FILENAME_TEMPLATE.format(entry_id=target_id)

    if not source_db.exists():
        return {
            "ok": False,
            "reason": "no_source_db",
            "source_path": str(source_db),
        }
    if target_db.exists():
        return {
            "ok": False,
            "reason": "target_already_has_db",
            "target_path": str(target_db),
        }

    try:
        await hass.async_add_executor_job(source_db.replace, target_db)
    except OSError as err:
        _LOGGER.exception(
            "assign_legacy_db: rename %s -> %s failed",
            source_db,
            target_db,
        )
        return {
            "ok": False,
            "reason": "rename_failed",
            "error": str(err),
        }

    clear_legacy_db_multi_entry(hass, source_id)
    clear_legacy_db_multi_entry(hass, target_id)
    _LOGGER.info(
        "assign_legacy_db: %s moved to entry %s", source_db, target_id
    )
    return {
        "ok": True,
        "source_entry_id": source_id,
        "target_entry_id": target_id,
        "new_db_path": str(target_db),
        "reload_required": [source_id, target_id],
    }



EXPORT_TABLES = (
    "cycles",
    "features",
    "cop_samples",
    "cop_hourly",
    "daily_summary",
    "alerts",
    "model_state",
)


def _export_table_csv(
    db_path: Path, table: str, out_dir: Path
) -> int:
    """Write one table to CSV (read-only). Returns row count."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(f"SELECT * FROM {table}")  # noqa: S608
        cols = [d[0] for d in cur.description]
        n = 0
        csv_path = out_dir / f"{table}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in cur:
                w.writerow(row)
                n += 1
        return n
    finally:
        conn.close()


async def _handle_archive_legacy_db(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Archive the current per-entry DB as `.legacy-<ts>`.

    Multi-entry correction: user wants to discard the mixed historical
    data that landed on one entry after migration, keeping a preserved
    copy for audit. Entry reload is required to open a fresh DB. The
    archived file is written to /config/.storage/daikin_cycle_ml.db
    .legacy-<timestamp> - this is the only place `.legacy-*` files are
    created by the integration.
    """
    entry_id = str(call.data[ATTR_ENTRY_ID])
    storage = Path(hass.config.config_dir) / ".storage"
    live_db = storage / DB_FILENAME_TEMPLATE.format(entry_id=entry_id)
    if not live_db.exists():
        return {
            "ok": False,
            "reason": "no_db_file",
            "live_path": str(live_db),
        }
    ts = time.strftime("%Y%m%d-%H%M%S")
    archived = storage / f"{DB_FILENAME}.legacy-{ts}"
    try:
        await hass.async_add_executor_job(live_db.replace, archived)
    except OSError as err:
        _LOGGER.exception(
            "archive_legacy_db: rename %s -> %s failed",
            live_db,
            archived,
        )
        return {
            "ok": False,
            "reason": "rename_failed",
            "error": str(err),
        }
    clear_legacy_db_multi_entry(hass, entry_id)
    _LOGGER.info("archive_legacy_db: %s -> %s", live_db, archived)
    return {
        "ok": True,
        "entry_id": entry_id,
        "archived_path": str(archived),
        "reload_required": [entry_id],
    }



async def _handle_export_legacy_db(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Export the per-entry DB to CSV files + manifest.json.

    Multi-entry correction: user inspects the mixed historical data
    that landed on one entry after migration. Each table is written as
    a separate CSV in /config/daikin_cycle_ml_export_<entry>_<ts>/,
    with manifest.json listing row counts and any per-table errors.
    """
    entry_id = str(call.data[ATTR_ENTRY_ID])
    storage = Path(hass.config.config_dir) / ".storage"
    live_db = storage / DB_FILENAME_TEMPLATE.format(entry_id=entry_id)
    if not live_db.exists():
        return {
            "ok": False,
            "reason": "no_db_file",
            "live_path": str(live_db),
        }
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = (
        Path(hass.config.config_dir)
        / f"daikin_cycle_ml_export_{entry_id}_{ts}"
    )
    try:
        await hass.async_add_executor_job(
            partial(out_dir.mkdir, parents=True, exist_ok=False)
        )
    except OSError as err:
        _LOGGER.exception(
            "export_legacy_db: mkdir %s failed", out_dir
        )
        return {
            "ok": False,
            "reason": "mkdir_failed",
            "error": str(err),
        }
    table_counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    for table in EXPORT_TABLES:
        try:
            n = await hass.async_add_executor_job(
                _export_table_csv, live_db, table, out_dir
            )
            table_counts[table] = n
        except (sqlite3.Error, OSError) as err:
            errors[table] = str(err)
    manifest = {
        "entry_id": entry_id,
        "source_db": str(live_db),
        "export_dir": str(out_dir),
        "timestamp": ts,
        "tables": table_counts,
        "errors": errors,
    }
    try:
        await hass.async_add_executor_job(
            partial(
                (out_dir / "manifest.json").write_text,
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        )
    except OSError as err:
        _LOGGER.exception(
            "export_legacy_db: manifest write failed", exc_info=True
        )
        return {
            "ok": False,
            "reason": "manifest_write_failed",
            "error": str(err),
            "export_dir": str(out_dir),
        }
    _LOGGER.info(
        "export_legacy_db: %s -> %s (%d tables)",
        live_db,
        out_dir,
        len(table_counts),
    )
    return {
        "ok": True,
        "entry_id": entry_id,
        "export_dir": str(out_dir),
        "tables": table_counts,
        "errors": errors,
    }


async def async_register_services(hass: HomeAssistant) -> None:
    """Idempotent registration at DOMAIN level."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_TEST_NOTIFICATION):
        return
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_COUNTERS,
        partial(_handle_reset_counters, hass), schema=SCHEMA_RESET,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_CYCLES,
        partial(_handle_export_cycles, hass), schema=SCHEMA_EXPORT,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LABEL_CYCLE,
        partial(_handle_label_cycle, hass), schema=SCHEMA_LABEL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RECOMPUTE_BASELINE,
        partial(_handle_recompute_baseline, hass), schema=SCHEMA_BASELINE,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RUN_MAINTENANCE,
        partial(_handle_run_maintenance, hass), schema=SCHEMA_RUN_MAINTENANCE,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEND_TEST_NOTIFICATION,
        partial(_handle_send_test_notification, hass),
        schema=SCHEMA_SEND_TEST,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_COP_HOURLY,
        partial(_handle_export_cop_hourly, hass),
        schema=SCHEMA_EXPORT_COP_HOURLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT_DATASHEET,
        partial(_handle_import_datasheet, hass),
        schema=SCHEMA_IMPORT_DATASHEET,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RECOMPUTE_KMEANS,
        partial(_handle_recompute_kmeans, hass),
        schema=SCHEMA_RECOMPUTE_KMEANS,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_USER_DATASHEET,
        partial(_handle_remove_user_datasheet, hass),
        schema=SCHEMA_REMOVE_USER_DATASHEET,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ASSIGN_LEGACY_DB,
        partial(_handle_assign_legacy_db, hass),
        schema=SCHEMA_ASSIGN_LEGACY_DB,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ARCHIVE_LEGACY_DB,
        partial(_handle_archive_legacy_db, hass),
        schema=SCHEMA_ARCHIVE_LEGACY_DB,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT_LEGACY_DB,
        partial(_handle_export_legacy_db, hass),
        schema=SCHEMA_EXPORT_LEGACY_DB,
        supports_response=SupportsResponse.ONLY,
    )
    _LOGGER.info("Daikin Cycle ML services registered")
