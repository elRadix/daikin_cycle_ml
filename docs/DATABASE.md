# Database

Where the integration keeps its data, what every table holds, how it is
maintained and migrated, and how to back it up or query it. The schema
is `custom_components/daikin_cycle_ml/storage/schema.sql`.

## Contents

- [1. Files](#1-files)
- [2. Tables](#2-tables)
- [3. model_state keys](#3-model_state-keys)
- [4. Retention and maintenance](#4-retention-and-maintenance)
- [5. Migrations](#5-migrations)
- [6. Several heat pumps and the old shared file](#6-several-heat-pumps-and-the-old-shared-file)
- [7. Backup, recovery and reset](#7-backup-recovery-and-reset)
- [8. Inspecting the data](#8-inspecting-the-data)
- [9. Size and performance](#9-size-and-performance)

## 1. Files

All under `/config/.storage/`:

| File | Contents |
|---|---|
| `daikin_cycle_ml_<entry_id>.db` | SQLite database of one heat pump (one per config entry) |
| `daikin_cycle_ml.alerts` | Home Assistant store: when each alert was last sent (repeat windows) |
| `daikin_cycle_ml.user_datasheets` | Home Assistant store: datasheets imported with `import_datasheet` |
| `daikin_cycle_ml.model_profile.<entry_id>` | Home Assistant store: your model profile (Configure → Model profile, `set_model_profile`) |

The database uses `aiosqlite` in WAL mode; tables and columns are created
or added on start.

## 2. Tables

### 2.1 `cycles`

One row per compressor run (or run segment).

| Column | Meaning |
|---|---|
| `id`, `start_ts`, `end_ts`, `duration_s`, `mode` | Identity, times (Unix), length and mode (`heating`, `dhw`, `cooling`, `unknown`) |
| `dT_max`, `dT_avg` | Water ΔT (R1T − R4T) |
| `rps_max`, `rps_avg` | Compressor speed |
| `outdoor_temp` | Mean outdoor temperature |
| `buh_used`, `buh_s`, `defrost_used`, `defrost_s` | Backup heater and defrost flags and seconds |
| `quality_score` | 0-100 ([ML §2](ML.md#2-quality-score)) |
| `cop_avg`, `cop_sample_count`, `cop_sample_stdev`, `cop_confidence` | COP of the run |
| `thermal_kw_avg` | Mean heat output |
| `cluster_id`, `label` | Cluster and user label |
| `is_transient` | Very short run, kept out of statistics |
| `mode_original`, `parent_cycle_id`, `is_dhw_tail` | Mode corrections and hot-water tails |
| `is_reconstructed` | Rebuilt from COP samples after a lost restart (v32) |
| `boiler_contribution_samples`, `boiler_heat_samples`, `boiler_dhw_samples` | Hybrid / bivalent co-fire counts |
| `dhw_tank_temp` | Tank temperature at the end of a hot-water run |

### 2.2 `features`

`cycle_id` and `vector_json`: the 12-value feature vector of each cycle
(`ml/features.py`).

### 2.3 `cop_samples`

One row per COP sample, every 10 minutes while the compressor runs.

| Column | Meaning |
|---|---|
| `ts`, `cop`, `mode`, `source` | Time, COP, mode and how it was obtained |
| `lwt`, `outdoor`, `r1t`, `r4t`, `flow_lmin` | Water and outdoor temperatures, flow |
| `thermal_kw`, `power_w`, `rps` | Heat, electrical input and compressor speed |
| `power_stable` | Power was steady |
| `is_transition_artifact` | Flagged by the physics checks or start-up (below 1.0); kept, never counted |
| `boiler_active`, `boiler_mode` | Boiler firing (hybrid / bivalent) |
| `buh_active` | Backup heater on; left out of the curve advice |
| `mode_original`, `is_reconstructed` | Corrections |

Samples above 1.5 × the Carnot limit are not stored at all.

### 2.4 `cop_hourly`

Hourly COP per mode, rolled up from `cop_samples`: `ts_hour`, `mode`,
`n_samples`, `cop_mean`, `cop_p10` / `p50` / `p90`, `cop_std`, `lwt_mean`,
`outdoor_mean` / `min` / `max`, `flow_mean`. Feeds `cop_curve_recent`, the
cards and `export_cop_hourly`.

### 2.5 `daily_summary`

Per local day and mode: `cycles` (started that day), `runs` (runs touching
the day), `total_duration_s` (runtime within the day, split at midnight),
`duration_min` / `max`, `quality_sum`, `dt_max_sum`, `rps_sum`,
`buh_count`, `defrost_count`, `transient_count`. Feeds
`daily_summary_recent` and the Daily summary card.

### 2.6 `alerts`

`ts`, `alert_type`, `severity`, `message`, `aggregated_count`: every alert
sent, pruned after `alert_retention_days`.

### 2.7 `model_state`

`key`, `value_json`, `updated_ts`: learned models, accumulators and
migration markers ([§3](#3-model_state-keys)).

## 3. model_state keys

| Key | Contents |
|---|---|
| `baseline_state` | Behaviour baseline ([ML §3](ML.md#3-behaviour-baseline-and-ml_anomaly)) |
| `adaptive_thresholds` | Run and pause samples per mode ([ML §4](ML.md#4-adaptive-thresholds)) |
| `kmeans_state` | Clusters per mode and retrain status |
| `ml_version` | ML version the models were built with |
| `thermal_daily_baseline` | Energy-anomaly baseline per mode |
| `cycle_detector_state` | The run in progress, restored on start |
| `runtime_acc.<day>` | Today's runtime, starts, backup-heater minutes, defrosts |
| `energy_acc.<day>` | Today's electrical and thermal energy per mode |
| `spf_state` | Season / year SPF cache |
| `rps_learned`, `hmax_learned` | Learned compressor range and maximum heat |
| `last_maintenance_ts` | Last maintenance run |
| `data_migration_*` | One marker per data migration ([§5](#5-migrations)) |

## 4. Retention and maintenance

Daily at 03:00 (when `retention_enabled` is on, Configure → Advanced):

1. cycles older than `cycle_retention_days` (90) are rolled up into
   `daily_summary` and removed, with their features;
2. alerts older than `alert_retention_days` (30) are removed;
3. old `runtime_acc` / `energy_acc` days are pruned;
4. VACUUM when `vacuum_enabled` is on.

`daikin_cycle_ml.run_maintenance` runs it now. `db_retention_warning` fires
when more than 100 rows are past their retention (maintenance not running).

## 5. Migrations

On start, the integration adds missing columns (self-healing, every
start) and runs each data migration once, recording a
`data_migration_*` marker. A failure raises the `migration_failed` repair
and leaves the data untouched for the next attempt.

| Marker | What it did |
|---|---|
| `v19` | Rebuilt `cop_hourly` from `cop_samples` |
| `v20` | Signed ΔT from R1T / R4T |
| `v21`-`v24` | Hybrid boiler columns and counts |
| `v25` | Merged runs cut by the old 4 h cap |
| `v26` | Cleared heat output of runs under 90 s |
| `v27` | Fixed overlapping run pairs, rebuilt summaries |
| `v28` | Re-classified COP samples with the 0.65 Carnot factor |
| `v29` | Rebuilt `daily_summary` (runtime split at midnight) |
| `v30` | Flagged old COP outliers, rebuilt affected hours and days |
| `v31` | Rebuilt `cop_hourly` rows that no longer matched their samples |
| `v32` | Rebuilt runs lost on a restart from the COP samples |
| `v33` | Filled `daily_summary.runs` |
| `v34` | Back-filled heat, power and speed of older samples |
| `quality_v2` | Rescored every cycle with the proportional penalties |
| `off_s_relearn` | Relearned pauses from the cycle order |
| `ml_v2` | Replayed every cycle into the ML v2 models |

## 6. Several heat pumps and the old shared file

Since v1.10.0 every heat pump has its own database. An install upgraded
from before that had one shared `daikin_cycle_ml.db`:

- one heat pump: the file was renamed to its per-entry name (a backup is
  in `/config/.daikin_backups/`);
- several: the file went to the oldest entry and the
  `legacy_db_multi_entry` repair says so. `assign_legacy_db` moves it,
  `archive_legacy_db` starts fresh (the old file is kept as
  `.legacy-<time>`), `export_legacy_db` writes every table to CSV.

## 7. Backup, recovery and reset

- **Home Assistant backups** include `/config/.storage`, so the database
  and stores are in every full backup.
- **Manual copy:** stop Home Assistant (or accept a copy taken during
  WAL writes), then copy `daikin_cycle_ml_<entry>.db` and its `-wal` file.
- **Restore:** stop Home Assistant, put the files back, start.
- **Corrupt file** (`db_corrupt`): check with
  `sqlite3 <file> "PRAGMA integrity_check"`; if it fails, delete the file
  and restart. History is lost, the integration starts a new one.
- **Start the ML over, keep the cycles:** `daikin_cycle_ml.recompute_baseline`.
- **Start everything over:** remove the integration, delete the
  `daikin_cycle_ml_<entry>.db` files and the stores, restart, add it
  again.

## 8. Inspecting the data

The diagnostics file shows counts, recent daily summaries, migrations and
integrity ([Diagnostics](DIAGNOSTICS.md)). For SQL, open the file
read-only, for example from the Advanced SSH add-on:

```bash
sqlite3 -readonly /config/.storage/daikin_cycle_ml_<entry>.db
```

```sql
-- runtime and cycles per day
SELECT day, mode, cycles, runs, round(total_duration_s / 3600.0, 1) AS hours
FROM daily_summary ORDER BY day DESC, mode LIMIT 20;

-- the last 10 cycles
SELECT datetime(start_ts, 'unixepoch', 'localtime') AS start, mode,
       duration_s / 60 AS min, quality_score, cop_avg
FROM cycles ORDER BY start_ts DESC LIMIT 10;

-- COP per hour today
SELECT datetime(ts_hour, 'unixepoch', 'localtime') AS hour, mode, n_samples, round(cop_mean, 2)
FROM cop_hourly WHERE ts_hour >= strftime('%s', 'now', 'start of day') ORDER BY ts_hour;
```

## 9. Size and performance

- **Size:** typically 10-40 MB after a year with the default retention;
  `cop_samples` is the largest table.
- **Writes:** a COP sample every 10 minutes while running, a cycle row on
  close, the accumulators every 15 minutes and on change of day.
- **Reads:** the cards and sensors read cached values; heavy queries run
  on a schedule, not every tick.
- The coordinator's slowest tick and its phases are in the diagnostics
  (`coordinator_timing`).
