# Database

Storage architecture, schema reference, and maintenance for Daikin Cycle ML.

- **Covers:** SQLite database layout, all tables, model_state keys, retention policy, migrations, HA Store alerts
- **For:** end users managing storage, admins running maintenance, developers reading the persistence layer
- **Version:** v1.14.0

Cross-references: [CONFIGURATION.md](CONFIGURATION.md) (retention options), [ENTITIES.md](ENTITIES.md) (services that touch the DB), [ML.md](ML.md) (baseline persistence), [ALERTS.md](ALERTS.md) (alert store).

---

## Per-entry DB files (v1.10.0+)

As of v1.10.0, each config entry has its own SQLite file. Schema is
identical for every file; only the filename scoping changed.

### File layout

    /config/.storage/
        daikin_cycle_ml_<entry_id>.db   per-entry live DB (v1.10.0+)
        daikin_cycle_ml.db              legacy shared DB (pre-v1.10.0)
        daikin_cycle_ml.db.legacy-<ts>  archived copy (archive_legacy_db)
        .daikin_cycle_ml_v1100_migrated migration marker
    /config/.daikin_backups/
        daikin_cycle_ml.db.backup-<ts>  pre-migration backup

### How migration works

First async_setup_entry after upgrade calls
storage.migration.async_migrate_legacy_db(hass, entry):

1. Marker file exists -> already (idempotent)
2. No legacy, but per-entry files exist -> already (recovery)
3. No legacy, nothing else -> skipped
4. Backup legacy to /config/.daikin_backups/
5. Single-entry: rename daikin_cycle_ml.db -> daikin_cycle_ml_<id>.db
6. Multi-entry: rename to oldest entry's per-entry file, raise
   legacy_db_multi_entry repair issue for the other entries
7. Verify file size unchanged after rename; rollback on mismatch
8. Write marker file

Migration never raises. All failures return MigrationResult with
status="error" and a human-readable error field.

### Diagnostics

async_get_config_entry_diagnostics includes database.per_entry
(per-entry file paths, sizes, table counts) and database.legacy
(the legacy file if still present). Both use read-only sqlite3
connections (?mode=ro), so diagnostics never trigger a schema
migration on a file it is inspecting.

### Manual operations

- Inspect counts: sqlite3 /config/.storage/daikin_cycle_ml_<id>.db "SELECT COUNT(*) FROM cycles"
- Export all tables: service daikin_cycle_ml.export_legacy_db
- Archive: service daikin_cycle_ml.archive_legacy_db
- Reassign: service daikin_cycle_ml.assign_legacy_db

---

## Contents

- [1. Storage overview](#1-storage-overview)
- [2. Database location and init](#2-database-location-and-init)
- [3. Schema reference](#3-schema-reference)
- [4. model_state keys](#4-model_state-keys)
- [5. HA Store (alerts)](#5-ha-store-alerts)
- [6. Retention and maintenance](#6-retention-and-maintenance)
- [7. Migrations](#7-migrations)
- [8. Backup and recovery](#8-backup-and-recovery)
- [9. Diagnostics and inspection](#9-diagnostics-and-inspection)
- [10. Performance characteristics](#10-performance-characteristics)

---

## 1. Storage overview

Daikin Cycle ML uses three persistence mechanisms:

| Mechanism | Location | Purpose |
|---|---|---|
| SQLite database | `/config/.storage/daikin_cycle_ml.db` | Cycles, features, COP samples, alerts, daily summaries, model state |
| HA Store (alerts) | `/config/.storage/daikin_cycle_ml.alerts` | Dedup timestamps for all 19 alert types |
| HA Store (user datasheets) | `/config/.storage/daikin_cycle_ml.user_datasheets` | User-imported model specs |

Each mechanism has a separate lifecycle. Deleting one does not affect the others.

### 1.1 What goes where

| Data | Stored in | Persists across restart |
|---|---|---|
| Completed cycles | SQLite `cycles` | Yes |
| Feature vectors | SQLite `features` | Yes |
| COP samples (5 min cadence) | SQLite `cop_samples` | Yes |
| COP hourly aggregates | SQLite `cop_hourly` | Yes |
| Daily per-mode rollups | SQLite `daily_summary` | Yes |
| Fired alert records (for audit) | SQLite `alerts` | Yes |
| Baseline EWMA state | SQLite `model_state` | Yes |
| Adaptive thresholds | SQLite `model_state` | Yes |
| K-means state | SQLite `model_state` | Yes |
| Runtime/energy accumulators | SQLite `model_state` | Yes |
| Thermal daily baseline | SQLite `model_state` | Yes |
| Dedup timestamps | HA Store `daikin_cycle_ml.alerts` | Yes |
| User datasheet imports | HA Store `daikin_cycle_ml.user_datasheets` | Yes |
| Live cycle (in-progress) | Coordinator memory | No (rebuilt on restart) |
| Last alert fired timestamp | HA Store (part of alerts) | Yes |

---

## 2. Database location and init

### 2.1 Path

```python
DB_RELATIVE = Path(".storage") / "daikin_cycle_ml.db"
```

Resolved to `/config/.storage/daikin_cycle_ml.db` at runtime.

### 2.2 Driver

`aiosqlite` — async wrapper around the standard Python `sqlite3`. All DB calls are awaited, never blocking the event loop.

### 2.3 Initialization sequence

On integration setup:

1. Ensure `.storage/` directory exists
2. Open `daikin_cycle_ml.db` (creates if missing)
3. Run schema migrations (see §7)
4. Run `PRAGMA integrity_check` — raises `db_corrupt` repair on failure
5. Enable foreign keys: `PRAGMA foreign_keys = ON`
6. Load `model_state` into memory caches

### 2.4 Current schema version

**v15**. Tracked in `model_state` under key `schema_version` (internal, not exposed).

When the integration loads an older DB, migrations run in sequence. Every migration is atomic — either it succeeds and the version is bumped, or it fails and the DB stays at the previous version.

---

## 3. Schema reference

### 3.1 `cycles`

One row per completed compressor cycle.

```sql
CREATE TABLE cycles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts         REAL NOT NULL UNIQUE,
    end_ts           REAL NOT NULL,
    duration_s       REAL NOT NULL,
    mode             TEXT NOT NULL,
    quality_score    INTEGER,
    cluster_id       INTEGER,
    dT_max           REAL,
    dT_avg           REAL,
    rps_max          INTEGER,
    rps_avg          REAL,
    buh_used         INTEGER NOT NULL DEFAULT 0,
    defrost_used     INTEGER NOT NULL DEFAULT 0,
    thermal_kw_avg   REAL,
    outdoor_temp     REAL,
    label            TEXT,
    cop_avg          REAL,
    cop_sample_count INTEGER,
    cop_sample_stdev REAL,
    cop_confidence   TEXT
);
```

| Column | Type | Purpose |
|---|---|---|
| `id` | int PK | Internal ID, used by `label_cycle` |
| `start_ts` | float | Unix timestamp (unique constraint prevents duplicates) |
| `end_ts` | float | Unix timestamp |
| `duration_s` | float | Duration in seconds |
| `mode` | str | `heating` / `cooling` / `dhw` / `unknown` |
| `quality_score` | int | 0–100, computed by `score_cycle()` |
| `cluster_id` | int | Assigned by nearest-centroid (0/1/2) |
| `dT_max` / `dT_avg` | float | Water-side delta-T |
| `rps_max` / `rps_avg` | int / float | Compressor rotation |
| `buh_used` | int | 0/1 |
| `defrost_used` | int | 0/1 |
| `thermal_kw_avg` | float | Average thermal power during cycle |
| `outdoor_temp` | float | Outdoor temperature at cycle time |
| `label` | str | User label (via `label_cycle` service), nullable |
| `cop_avg` | float | Average COP during cycle (if COP sensor configured) |
| `cop_sample_count` | int | Number of COP samples averaged |
| `cop_sample_stdev` | float | Standard deviation of COP samples |
| `cop_confidence` | str | `none` (0-2) / `low` (3-5) / `medium` (6-11) / `high` (12+) real sample count (v1.12.5 #133) |

**Indexes:**
- `idx_cycles_start_ts` on `start_ts` — used by retention and history queries
- `idx_cycles_end_ts` on `end_ts` — used by `async_avg_duration_since` and `async_defrost_duration_since` (I7)

### 3.2 `features`

12-dimensional feature vectors, one per cycle.

```sql
CREATE TABLE features (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id  INTEGER NOT NULL UNIQUE,
    v0        REAL, v1 REAL, v2 REAL, v3 REAL, v4 REAL, v5 REAL,
    v6        REAL, v7 REAL, v8 REAL, v9 REAL, v10 REAL, v11 REAL,
    FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE
);
```

| Column | Dimension |
|---|---|
| `v0` | duration_s |
| `v1` | dT_max |
| `v2` | dT_avg |
| `v3` | rps_max |
| `v4` | rps_avg |
| `v5` | outdoor_temp |
| `v6` | buh_used |
| `v7` | defrost_used |
| `v8` | cop_avg |
| `v9` | lwt_avg |
| `v10` | indoor_temp_avg |
| `v11` | thermal_kw_avg |

**Cascade delete:** when a cycle is deleted (retention or manual), its feature row is deleted automatically. This is why maintenance deletes features before cycles — or relies on the cascade.

### 3.3 `cop_samples`

Raw COP samples, one per 5-minute tick (when COP sensor configured).

```sql
CREATE TABLE cop_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL NOT NULL,
    cop           REAL NOT NULL,
    lwt           REAL,
    outdoor       REAL,
    flow_lmin     REAL,
    power_w       REAL,
    power_stable  INTEGER DEFAULT 0,
    mode          TEXT,
    data_quality  TEXT,
    source        TEXT DEFAULT 'sensor'
);
```

| Column | Purpose |
|---|---|
| `ts` | Unix timestamp |
| `cop` | COP value at sample time |
| `lwt` | Leaving water temp at sample time |
| `outdoor` | Outdoor temp at sample time |
| `flow_lmin` | Water flow at sample time |
| `power_w` | Electrical power (W) at sample time |
| `power_stable` | 1 if power readings stable for ≥ 5 min, else 0 |
| `mode` | `heating` / `cooling` / `dhw` / `unknown` |
| `data_quality` | `good` / `suspect` / `bad` — set by COP analyzer |
| `source` | `sensor` (from COP sensor) or `computed` (from thermal/electrical ratio) |

**Indexes:** `idx_cop_samples_ts`, `idx_cop_samples_outdoor`

### 3.4 `cop_hourly`

Aggregated COP per hour per mode.

```sql
CREATE TABLE cop_hourly (
    ts_hour       INTEGER NOT NULL,
    mode          TEXT NOT NULL,
    n_samples     INTEGER NOT NULL,
    cop_mean      REAL NOT NULL,
    cop_p10       REAL,
    cop_p50       REAL,
    cop_p90       REAL,
    cop_std       REAL,
    lwt_mean      REAL,
    outdoor_mean  REAL,
    outdoor_min   REAL,
    outdoor_max   REAL,
    flow_mean     REAL,
    updated_ts    REAL NOT NULL,
    PRIMARY KEY (ts_hour, mode)
);
```

`ts_hour` is Unix timestamp truncated to hour boundary.

7-day window maintained by coordinator — older rows rolled into daily_summary then pruned.

### 3.5 `daily_summary`

Per-day per-mode aggregates. One row per `(day, mode)`.

```sql
CREATE TABLE daily_summary (
    day              TEXT NOT NULL,
    mode             TEXT NOT NULL,
    cycles           INTEGER DEFAULT 0,
    total_duration_s INTEGER DEFAULT 0,
    duration_min     INTEGER,
    duration_max     INTEGER,
    quality_sum      INTEGER DEFAULT 0,
    dt_max_sum       REAL DEFAULT 0,
    rps_sum          REAL DEFAULT 0,
    buh_count        INTEGER DEFAULT 0,
    defrost_count    INTEGER DEFAULT 0,
    updated_ts       REAL NOT NULL,
    PRIMARY KEY (day, mode)
);
```

| Column | Purpose |
|---|---|
| `day` | `YYYY-MM-DD` local date |
| `mode` | `heating` / `cooling` / `dhw` / `unknown` |
| `cycles` | Cycle count for that day+mode |
| `total_duration_s` | Total compressor runtime |
| `duration_min` / `duration_max` | Shortest / longest cycle |
| `quality_sum` | Sum of quality scores (average = quality_sum / cycles) |
| `dt_max_sum` | Sum of dT_max (average = dt_max_sum / cycles) |
| `rps_sum` | Sum of rps_avg |
| `buh_count` | Cycles with BUH active |
| `defrost_count` | Cycles with defrost active |

**Index:** `idx_daily_summary_day` on `day`

No thermal kWh columns — those live in `model_state.thermal_daily_baseline` since v1.9 (I6 design decision to avoid a migration).

### 3.6 `alerts`

Historical record of every alert that fired (for audit).

```sql
CREATE TABLE alerts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL NOT NULL,
    alert_type        TEXT NOT NULL,
    severity          TEXT NOT NULL,
    message           TEXT NOT NULL,
    aggregated_count  INTEGER DEFAULT 1,
    UNIQUE(ts, alert_type)
);
```

Different from HA Store alerts (§5): this is a permanent record, not just dedup state. Used to answer "what alerts fired in the last 30 days".

**Retention:** pruned by `async_run_maintenance` per `alert_retention_days` (default 90).

### 3.7 `model_state`

Key-value store for ML state and accumulated counters.

```sql
CREATE TABLE model_state (
    key         TEXT PRIMARY KEY,
    value_json  TEXT NOT NULL,
    updated_ts  REAL NOT NULL
);
```

See §4 for all keys.

---

## 4. model_state keys

Every key in `model_state`, what stores it, and how it's used.

### 4.1 `schema_version` (internal)

- **Stored by:** migration runner
- **Value:** `{"version": 15}`
- **Used by:** migration runner on startup

### 4.2 `baseline_state`

- **Stored by:** `_persist_baseline_state` (every 6 h tick)
- **Value:** MultiBaseline serialization — per-mode EWMA mean/m2, dimension count, sample count
- **Used by:** anomaly detection, `ml_anomaly` alert

### 4.3 `adaptive_thresholds`

- **Stored by:** `_persist_adaptive_thresholds` (every 6 h tick)
- **Value:** per-mode learned percentile thresholds
- **Used by:** cycle detection when `adaptive_thresholds_enabled = true`

### 4.4 `kmeans_state`

- **Stored by:** `_persist_kmeans_state` (every k-means retrain, Sunday 04:00)
- **Value:** k, n, iterations, inertia, labels, centroids, cluster_sizes, ts, last_attempt_ts, last_ok_ts, consecutive_failures, last_failure_reason
- **Used by:** cluster assignment, `kmeans_retrain_stale` alert

### 4.5 `runtime_acc.<YYYY-MM-DD>`

- **Stored by:** `_persist_runtime_acc` (every 5 min when runtime changes)
- **Value:**
  ```json
  {
    "day": "2026-10-19",
    "buh_step1_s": 0.0,
    "buh_step2_s": 0.0,
    "defrost_count": 3,
    "defrost_duration_s": 180.0,
    "last_defrost_ts": 1792425600.0
  }
  ```
- **Used by:** `sensor.runtime_compressor_today`, `sensor.runtime_buh_today`, `sensor.defrost_count_today`, `sensor.defrost_duration_today`

### 4.6 `energy_acc.<YYYY-MM-DD>`

- **Stored by:** `_persist_energy_acc` (every 5 min when energy changes)
- **Value:**
  ```json
  {
    "day": "2026-10-19",
    "heating_th_kwh": 3.61,
    "heating_el_kwh": 0.53,
    "dhw_th_kwh": 0.0,
    "dhw_el_kwh": 0.0,
    "cooling_th_kwh": 0.0,
    "cooling_el_kwh": 0.0
  }
  ```
- **Used by:** `sensor.electrical_energy_*_today`, `sensor.thermal_energy_*_today`

**I8 fix (v1.9):** runtime and energy accumulators use **independent day-key gates**. A runtime restore failure cannot wipe energy_acc, and vice versa. Before I8, both shared one gate — a bug that silently lost a day's energy data on some restarts.

### 4.7 `thermal_daily_baseline`

- **Stored by:** `_persist_energy_baseline` (every 1 h tick, processes yesterday's energy_acc)
- **Value:**
  ```json
  {
    "heating": {"mean": 2.51, "m2": 0.0, "n": 1, "last_day": "2026-10-18"},
    "dhw":     {"mean": 0.0,  "m2": 0.0, "n": 0, "last_day": "2026-10-18"},
    "cooling": {"mean": 0.0,  "m2": 0.0, "n": 0, "last_day": "2026-10-18"}
  }
  ```
- **Used by:** `energy_daily_anomaly` alert (needs n ≥ 7 per mode before firing)

Welford update: each new day adds to mean/m2/n. No old data is deleted — the baseline grows slowly and is robust to outliers.

### 4.8 `last_maintenance_ts`

- **Stored by:** `_run_maintenance` after every prune
- **Value:** Unix timestamp of last maintenance run
- **Used by:** diagnostics display, verifying maintenance is running

### 4.9 `spf_state`

- **Stored by:** `_persist_spf_state` (per SPF sensor update)
- **Value:** cumulative thermal kWh, electrical kWh, season start timestamp
- **Used by:** `sensor.spf_season`, `sensor.spf_ytd`, `sensor.scop_running_365d`

### 4.10 `adaptive_thresholds` (same as 4.3)

Yes, mentioned twice — it is stored under this exact key, no namespace prefix.

---

## 5. HA Store (alerts)

**File:** `/config/.storage/daikin_cycle_ml.alerts`
**Schema version:** 1
**Save delay:** 5 seconds (debounced)

```json
{
  "version": 1,
  "key": "daikin_cycle_ml.alerts",
  "data": {
    "last_sent": {
      "pendulum_hourly": 1792432800.5,
      "short_run": 1792425600.0,
      "source_stale": 1792432800.0
    }
  }
}
```

Full schema in [ALERTS.md Appendix D](ALERTS.md#appendix-d-store-file-format).

**Purpose:** dedup timestamps only. Deleting this file resets dedup state — every alert type can fire immediately once per day after restart.

**Separate from SQLite `alerts` table:** the table records events for audit, the store tracks dedup state. Two different purposes, two different files.

### 5.1 User datasheets store

**File:** `/config/.storage/daikin_cycle_ml.user_datasheets`
**Schema version:** 1

```json
{
  "version": 1,
  "key": "daikin_cycle_ml.user_datasheets",
  "data": {
    "models": {
      "my_custom_model": {
        "family": "Custom Altherma",
        "kw": 12.0,
        "lwt_min": 25,
        "lwt_max": 55,
        "nom_cop": 4.2,
        "schema_version": 1,
        "imported_ts": 1792432800.0,
        "source_url": "https://example.com/datasheet.pdf"
      }
    }
  }
}
```

Managed by `import_datasheet` and `remove_user_datasheet` services.

---

## 6. Retention and maintenance

---

## 6A. Scheduled database operations

All operations run inside the coordinator, not the DB layer. Times are local timezone.

| When | Operation | Table(s) affected |
|---|---|---|
| Every 30 s | Poll + in-memory cycle detection | none (DB) |
| Every 5 min | `INSERT INTO cop_samples` | `cop_samples` |
| Every 300 s | `UPDATE model_state` for runtime/energy accumulators | `model_state` |
| Every 1 h | `INSERT/UPDATE daily_summary`, `UPDATE cop_hourly` | `daily_summary`, `cop_hourly` |
| Every 6 h | `UPDATE model_state` for baseline + adaptive | `model_state` |
| Daily 03:00 | Prune `cop_samples`, `cop_hourly`, `alerts`, `cycles` + optional `VACUUM` | all tables |
| Sunday 04:00 | K-means retrain → `UPDATE model_state.kmeans_state` | `model_state` |

### 6A.1 Manual operations

| Operation | Service | Affects |
|---|---|---|
| Prune now | `daikin_cycle_ml.run_maintenance` | all tables |
| K-means retrain | `daikin_cycle_ml.recompute_kmeans` | `model_state` |
| Baseline recompute | `daikin_cycle_ml.recompute_baseline` | `model_state` |
| Export cycles | `daikin_cycle_ml.export_cycles` | read-only |
| Export COP hourly | `daikin_cycle_ml.export_cop_hourly` | read-only |

### 6A.2 What can break the schedule

| Symptom | Cause | Fix |
|---|---|---|
| 03:00 prune never runs | HA restarted at 03:00 | Run manually via service |
| Weekly retrain never succeeds | < 30 cycles in 7-day window | Wait for more data, or `recompute_kmeans` |
| `last_maintenance_ts` stale > 48 h | Scheduler disabled, or DB error | Check HA logs, run maintenance manually |
| `db_retention_warning` alert | Retention not running | See §8.4 in TROUBLESHOOTING.md |

### 6.1 Default retention

| Data | Default retention | Configurable via |
|---|---|---|
| `cycles` | 90 days | `cycle_retention_days` |
| `features` | Cascade-deleted with cycles | (via cycles retention) |
| `alerts` | 90 days | `alert_retention_days` |
| `cop_samples` | 365 days | Fixed (not exposed) |
| `cop_hourly` | 365 days | Fixed |
| `daily_summary` | ∞ (never pruned) | N/A |
| `model_state` | ∞ | N/A |

### 6.2 Maintenance schedule

Runs **daily at 03:00 local** via the coordinator scheduler.

Sequence:

1. Prune `cop_samples` older than retention
2. Prune `cop_hourly` older than retention
3. Prune `alerts` older than `alert_retention_days`
4. Prune `features` where `cycle_id` no longer exists in `cycles` (orphan cleanup)
5. Prune `cycles` older than `cycle_retention_days`
6. Optionally `VACUUM` (if `vacuum_enabled = true`)
7. Update `last_maintenance_ts` in `model_state`

### 6.3 Manual maintenance

**Service:** `daikin_cycle_ml.run_maintenance`

```yaml
service: daikin_cycle_ml.run_maintenance
data:
  entry_id: <your_entry_id>
  cycle_retention_days: 180
  alert_retention_days: 60
  vacuum: true
```

Response: `{"ok": true, "pruned_cycles": N, "pruned_alerts": M, "vacuumed": bool}`.

### 6.4 VACUUM

SQLite VACUUM rebuilds the database file, reclaiming space from deleted rows. It is **slow** (rewrites the entire file) and **blocks all other DB operations** during its run.

- Enabled by default
- On a 10 MB DB, VACUUM takes ~1 second
- On a 100 MB DB, VACUUM takes ~10 seconds
- On a > 500 MB DB, VACUUM takes > 1 minute — consider disabling it if you have a very long retention

If HA is restarted during VACUUM, the operation is aborted and the DB is left intact (SQLite journal handles this).

### 6.5 Retention health check

The `db_retention_warning` alert fires when:
- Alerts table has > 100 rows past retention, OR
- Cycles table has > 100 rows past retention

This means maintenance is not running. Common causes:
- HA restarted during the 03:00 window
- `retention_enabled = false`
- DB permissions issue

Fix: run `daikin_cycle_ml.run_maintenance` manually, then check the alert clears on the next 1 h tick.

---

## 7. Migrations

### 7.1 Migration mechanism

Each migration is a Python function in `storage/db.py` named `async_migrate_*_to_vNN`, where NN is the target schema version. Migration runner:

1. Reads current `schema_version` from `model_state`
2. If current < target, runs each migration in sequence
3. Each migration is wrapped in a transaction
4. On success, bumps `schema_version`
5. On failure, rolls back — no partial state

### 7.2 Migration history

| Version | Migration | Purpose |
|---|---|---|
| v11 | `async_migrate_features_to_v11` | Restructure feature vector storage |
| v12 | `async_migrate_features_to_v12` | Add `indoor_temp_avg` dimension |
| v13 | `async_migrate_cop_samples_to_v13` | Add `data_quality` column |
| v14 | `async_migrate_cycles_to_v14` | Add COP metadata columns to cycles |
| v14 | `async_migrate_cop_samples_source_v14` | Add `source` column |
| v14 | `async_create_cop_hourly_v14` | Create `cop_hourly` table |
| v15 | `async_migrate_cop_samples_mode_default_v15` | Set `mode` default for old rows |

### 7.3 Recovery from failed migration

If `migration_failed` repair is raised:

1. Check HA logs for the specific migration name
2. Back up `/config/.storage/daikin_cycle_ml.db`
3. Try `daikin_cycle_ml.run_maintenance` with `vacuum: true` — sometimes SQLite journal corruption is fixable
4. If still failing, delete the DB and restart HA (all historical data is lost, but the integration works)

**Data is not recoverable** once the DB is deleted. If the historical data matters, back up the DB *before* deleting.

### 7.4 Downgrading

**Not supported.** If you roll back to an older integration version, the DB schema is newer than expected. The integration may fail to load or silently ignore unknown columns.

To downgrade safely:
1. Export cycles via `daikin_cycle_ml.export_cycles`
2. Delete DB
3. Install older version
4. Let it create a fresh vN-schema DB
5. Historical cycles are lost (only new ones tracked)

---

### v21 — cycles.boiler_contribution_samples (v1.15.0)

Adds `boiler_contribution_samples INTEGER DEFAULT 0` to `cycles`. Records
how many samples within each cycle were taken during boiler co-fire (HP +
boiler both active). Non-hybrid cycles always show 0.

**Idempotent:** marker `data_migration_v21_completed` with `completed` flag.
Fresh installs get the column from `schema.sql` and the ALTER is a no-op.

### v22 — cop_samples.boiler_active (v1.15.0)

Adds `boiler_active INTEGER DEFAULT 0` to `cop_samples`. Flags individual
COP samples taken during boiler co-fire.

**Self-healing.** `async_ensure_cop_samples_table()` runs
`PRAGMA table_info` on every call and issues the ALTER if the column is
missing. Called at `async_initialize()` and before every
`async_insert_cop_sample` / `async_fetch_cop_samples*` / `async_rollup_cop_hourly`.
Legacy DBs (pre-v22) upgrade automatically on next coordinator tick.

**Query behavior:**

- `async_fetch_cop_samples(include_boiler=True)` (default) — all samples
- `async_fetch_cop_samples(include_boiler=False)` — only pure HP (boiler_active = 0)
- `async_rollup_cop_hourly` — always excludes boiler_active = 1
- `_refresh_cop_today` and heating curve — filter boiler_active = 1

**Idempotent:** marker `data_migration_v22_completed`.

## 8. Backup and recovery

### 8.1 Automatic HA backup

HA's built-in backup (Settings → System → Backups) includes `.storage/` by default. This means the DB is automatically backed up.

**Recommendation:** enable daily automatic backups. Two weeks of backups is enough to recover from any data corruption.

### 8.2 Manual backup

```bash
cp /config/.storage/daikin_cycle_ml.db /backup/daikin_cycle_ml_$(date +%Y%m%d).db
cp /config/.storage/daikin_cycle_ml.alerts /backup/
cp /config/.storage/daikin_cycle_ml.user_datasheets /backup/
```

Do this **before** any of:
- Restarting HA during a suspected DB issue
- Upgrading the integration (migration runs on first load)
- Running VACUUM manually

### 8.3 Recovery

**Restore from backup:**

1. Stop HA (or the integration)
2. Copy `daikin_cycle_ml.db` from backup to `.storage/`
3. Same for `.alerts` and `.user_datasheets`
4. Restart HA

The integration will load the DB at whatever schema version it was backed up at, then re-run migrations if needed.

**Query the DB directly:**

```bash
sqlite3 /config/.storage/daikin_cycle_ml.db "SELECT COUNT(*) FROM cycles"
sqlite3 /config/.storage/daikin_cycle_ml.db "SELECT * FROM daily_summary ORDER BY day DESC LIMIT 5"
sqlite3 /config/.storage/daikin_cycle_ml.db "SELECT key FROM model_state"
```

**Export to CSV:**

```bash
sqlite3 -header -csv /config/.storage/daikin_cycle_ml.db \
    "SELECT * FROM cycles ORDER BY start_ts" > /backup/cycles.csv
```

### 8.4 Full reset

To completely reset all data (nuclear option):

1. Note your options: Settings → Devices & Services → Daikin Cycle ML → Configure
2. Delete `/config/.storage/daikin_cycle_ml.db`
3. Delete `/config/.storage/daikin_cycle_ml.alerts`
4. Delete `/config/.storage/daikin_cycle_ml.user_datasheets`
5. Restart HA

The integration will start with a fresh DB. All historical cycles, alerts, and ML state are lost. Options are preserved in the config entry.

---

## 9. Diagnostics and inspection

### 9.1 Diagnostics download

Settings → Devices & Services → Daikin Cycle ML → menu → **Download diagnostics**.

Contains a JSON snapshot with these database fields:

```json
"database": {
  "path": "/config/.storage/daikin_cycle_ml.db",
  "is_open": true,
  "counts": {
    "cycles": 101,
    "features": 101,
    "model_state": 36,
    "alerts": 0,
    "daily_summary": 29,
    "cop_samples": 1698
  },
  "extra": {
    "daily_summary": [...],
    "last_maintenance_ts": 1792371600.06,
    "kmeans_state": {...},
    "baseline_state": {...}
  }
}
```

Use this to:
- Verify row counts are growing as expected
- Check `last_maintenance_ts` is recent (retention running)
- Inspect baseline and kmeans state without querying SQLite

### 9.2 Key queries

**Row counts:**

```sql
SELECT 'cycles' AS tbl, COUNT(*) FROM cycles
UNION ALL SELECT 'features', COUNT(*) FROM features
UNION ALL SELECT 'alerts', COUNT(*) FROM alerts
UNION ALL SELECT 'daily_summary', COUNT(*) FROM daily_summary
UNION ALL SELECT 'cop_samples', COUNT(*) FROM cop_samples
UNION ALL SELECT 'model_state', COUNT(*) FROM model_state;
```

**Recent cycles:**

```sql
SELECT start_ts, duration_s, mode, quality_score, cluster_id
FROM cycles
ORDER BY start_ts DESC
LIMIT 10;
```

**Model state keys:**

```sql
SELECT key, updated_ts FROM model_state ORDER BY key;
```

**Database size:**

```bash
ls -lh /config/.storage/daikin_cycle_ml.db
```

**Integrity check:**

```bash
sqlite3 /config/.storage/daikin_cycle_ml.db "PRAGMA integrity_check"
```

Expected output: `ok`.

### 9.3 Verify maintenance is running

```sql
SELECT value_json FROM model_state WHERE key = 'last_maintenance_ts';
```

Convert Unix timestamp to human-readable:

```bash
sqlite3 /config/.storage/daikin_cycle_ml.db \
    "SELECT datetime(value_json / 1000, 'unixepoch', 'localtime') FROM model_state WHERE key='last_maintenance_ts'"
```

Should be within 24-48 hours of now. If older, maintenance is not running.

---

## 10. Performance characteristics

### 10.1 Writes

| Operation | Frequency | Rows written |
|---|---|---|
| Cycle complete | Per cycle (10-100/day) | 2 (`cycles`, `features`) |
| COP sample | Every 5 min | 1 (`cop_samples`) |
| COP hourly aggregation | Every hour | 1–3 (per mode) |
| Daily summary | Every hour (updates today's row) | 1–3 |
| Runtime accumulator | Every 5 min (if changing) | `model_state` update |
| Energy accumulator | Every 5 min (if changing) | `model_state` update |
| Alert fired | Per alert (rare) | 1 (`alerts`) |
| Maintenance prune | Daily at 03:00 | Many (deletion) |
| Baseline persist | Every 6 h | `model_state` update |

**Total daily writes:** ~50–500 small inserts/updates plus one prune. SQLite handles this easily; typical write latency is < 5 ms.

### 10.2 Reads

| Operation | Frequency | Query complexity |
|---|---|---|
| Cycle detection | Every 30 s (in-memory, no DB) | N/A |
| COP analysis | Every 10 min | Aggregate over 30 days (`cop_samples`) |
| 7d rollups | Every 1 h | Aggregate over 7 days (`cycles`) |
| Diagnostics | On demand | All tables (single call) |
| Entity updates | Per state change | In-memory caches mostly |

**Total daily reads:** ~2500 queries. All indexed; typical read latency < 2 ms.

### 10.3 Disk usage

Rough estimate per row:

| Table | Row size | Rows/day | Disk/day |
|---|---|---|---|
| `cycles` | ~200 bytes | 20 | ~4 KB |
| `features` | ~100 bytes | 20 | ~2 KB |
| `cop_samples` | ~100 bytes | 288 | ~30 KB |
| `cop_hourly` | ~100 bytes | 24 | ~2.4 KB |
| `daily_summary` | ~100 bytes | 3 | ~300 B |
| `alerts` | ~500 bytes (message text) | ~5 | ~2.5 KB |
| `model_state` | ~2 KB (baseline is large) | (updates only) | (fixed ~40 KB) |

**Typical usage:** 40 KB/day steady-state → **~15 MB/year** with 90-day cycle retention, 365-day COP retention.

With 180-day retention and 500 cycles/day (unusual), could reach 100+ MB. Enable VACUUM in that case.

### 10.4 Query that might slow down

**`async_avg_duration_since`** — averages cycle durations over a time window. Uses `idx_cycles_end_ts`. Fast for 7-day windows; on a 365-day retention with 100+ cycles/day, may take ~50 ms.

**Mitigation:** the 7-day average is cached in the coordinator (`_avg_duration_7d_min`), refreshed hourly. Individual sensor reads use the cache, not the DB.

### 10.5 WAL mode

SQLite is running in **WAL mode** (Write-Ahead Logging), which is standard for aiosqlite. Benefits:
- Readers don't block writers
- Crash recovery is fast
- Concurrent access is safe

Trade-off: creates `.db-wal` and `.db-shm` sidecar files during operation. These are normal — HA backup includes them.

**Never delete `.db-wal` or `.db-shm` while HA is running.** Always stop HA first if you need to clean up.

---

## Appendix A — Complete SQL schema dump

```sql
-- cycles
CREATE TABLE cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts REAL NOT NULL UNIQUE,
    end_ts REAL NOT NULL,
    duration_s REAL NOT NULL,
    mode TEXT NOT NULL,
    quality_score INTEGER,
    cluster_id INTEGER,
    dT_max REAL, dT_avg REAL,
    rps_max INTEGER, rps_avg REAL,
    buh_used INTEGER NOT NULL DEFAULT 0,
    defrost_used INTEGER NOT NULL DEFAULT 0,
    thermal_kw_avg REAL, outdoor_temp REAL,
    label TEXT,
    cop_avg REAL, cop_sample_count INTEGER, cop_sample_stdev REAL, cop_confidence TEXT
);
CREATE INDEX idx_cycles_start_ts ON cycles(start_ts);
CREATE INDEX idx_cycles_end_ts ON cycles(end_ts);

-- features
CREATE TABLE features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL UNIQUE,
    v0 REAL, v1 REAL, v2 REAL, v3 REAL, v4 REAL, v5 REAL,
    v6 REAL, v7 REAL, v8 REAL, v9 REAL, v10 REAL, v11 REAL,
    FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE
);

-- cop_samples
CREATE TABLE cop_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, cop REAL NOT NULL,
    lwt REAL, outdoor REAL, flow_lmin REAL, power_w REAL,
    power_stable INTEGER DEFAULT 0,
    mode TEXT, data_quality TEXT, source TEXT DEFAULT 'sensor'
);
CREATE INDEX idx_cop_samples_ts ON cop_samples(ts);
CREATE INDEX idx_cop_samples_outdoor ON cop_samples(outdoor);

-- cop_hourly
CREATE TABLE cop_hourly (
    ts_hour INTEGER NOT NULL, mode TEXT NOT NULL,
    n_samples INTEGER NOT NULL, cop_mean REAL NOT NULL,
    cop_p10 REAL, cop_p50 REAL, cop_p90 REAL, cop_std REAL,
    lwt_mean REAL, outdoor_mean REAL, outdoor_min REAL, outdoor_max REAL, flow_mean REAL,
    updated_ts REAL NOT NULL,
    PRIMARY KEY (ts_hour, mode)
);

-- daily_summary
CREATE TABLE daily_summary (
    day TEXT NOT NULL, mode TEXT NOT NULL,
    cycles INTEGER DEFAULT 0, total_duration_s INTEGER DEFAULT 0,
    duration_min INTEGER, duration_max INTEGER,
    quality_sum INTEGER DEFAULT 0, dt_max_sum REAL DEFAULT 0, rps_sum REAL DEFAULT 0,
    buh_count INTEGER DEFAULT 0, defrost_count INTEGER DEFAULT 0,
    updated_ts REAL NOT NULL,
    PRIMARY KEY (day, mode)
);
CREATE INDEX idx_daily_summary_day ON daily_summary(day);

-- alerts
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, alert_type TEXT NOT NULL,
    severity TEXT NOT NULL, message TEXT NOT NULL,
    aggregated_count INTEGER DEFAULT 1,
    UNIQUE(ts, alert_type)
);

-- model_state
CREATE TABLE model_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_ts REAL NOT NULL
);
```

## Appendix B — Related files

| File | Purpose |
|---|---|
| `storage/schema.sql` | Canonical schema source (used by tests) |
| `storage/db.py` | CycleDB class, all 46 async methods, migrations |
| `storage/store.py` | In-memory cycle store (recent cycles cache) |
| `coordinator.py` | Calls DB methods from the tick scheduler |
| `services.py` | `export_cycles`, `run_maintenance`, `label_cycle` handlers |

## Appendix C — Version history of schema

| Version | Date | Change |
|---|---|---|
| v11 | 2026-09 | Restructured features table |
| v12 | 2026-09 | Added `indoor_temp_avg` dimension (v10) |
| v13 | 2026-10 | Added `data_quality` to cop_samples |
| v14 | 2026-10 | Added COP metadata to cycles, `source` to cop_samples, created cop_hourly |
| v15 | 2026-10 | Set `mode` default for old cop_samples rows |

## Historical synthesis limitation (v1.12.4 R446)

Cycles synthesized by the v1.12.4 v18 migration (is_reconstructed = 1)
carry thermal_kw_avg = NULL. The cop_samples table stores only
cop, lwt, outdoor, flow_lmin, mode - the cold-side temperature required
by the thermal formula was not persisted at sample time (R4T for heating,
R5T for DHW).

Full thermal recompute requires v1.13.0 issue #129 (features rewrite),
which will persist R4T and R5T in cop_samples.

All other cycle fields (cop_avg, cop_sample_count, duration_s) are
computed accurately from the sample window.

## Amend 7 NULL-aggregate cycles (Option B, v1.12.9)

Amend 7 of the v1.12.4 v18 migration backfills cop_avg and
cop_sample_count for NULL/0 cycles where samples exist. Cycles with
zero samples in the window are skipped by design.

In all three production installs, 109 cycles remain NULL after v18
(prod 1: 28, prod 2: 14, prod 3: 67). These are all pre-v1.12.0 cycles
whose sample window fell entirely outside cop_samples retention (or
predates the 300s collection cadence). There is no data to backfill.

Decision (Option B, v1.12.9, PR B): document the state, do not
fabricate. The NULLs are correct. Amend 7 behaviour stays as-is.

Consequences:

- get_cycle_avg_cop() returns None for these cycles, not 0.0
- Dashboards show "-" for their COP, not a misleading average
- ML features skip NULL-cop cycles in training (features.vector_json
  is computed without cop_avg for those cycle_ids)

If you observe NEW NULL cycles post-v1.12.4 (i.e. after Amend 7 shipped),
that is a different signal: verify _collect_cycle_averages() ran with
the real sample count via the 4-tier confidence path (see #133a).
The #136 close condition is that pre-v1.12.0 NULLs are accepted, not
that future NULLs go unnoticed.
