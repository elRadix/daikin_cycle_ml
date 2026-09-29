# Daikin Cycle ML — Technical Reference

**Version:** 1.3.0 · **Updated:** 2026-09-29
**Domain:** `daikin_cycle_ml` · **IoT class:** calculated · **Integration type:** helper
**Repository:** https://github.com/elRadix/daikin_cycle_ml

---

## 1. Overview

Home Assistant custom integration that detects, classifies, self-learns
and advises on Daikin heat pump compressor cycles. Source sensor is any
entity exposing Daikin Altherma operating attributes (typically
`sensor.althermasensors` from an ESPAltherma bridge).

**Problem it solves.** Short-cycling (Dutch: *pendelen*) is the #1 cause
of reduced seasonal COP and accelerated compressor wear. No existing HA
integration detects or classifies it.

**Design principles.**

- Fully local — no cloud, no proprietary RPC.
- Deterministic ML — no training loop, no external dependency.
- HA-native — coordinator pattern, config flow, diagnostics, repairs.
- Self-learning — per-mode baselines and percentile thresholds evolve
  with the installation.

**Data flow at the top level.**

```
source_sensor (ESPAltherma)
      │
      ▼
DaikinCycleMLCoordinator  ──30 s tick──▶  detect · classify · advise
      │
      ├─▶ sensors / binary_sensors / services / repairs / notifications
      ├─▶ SQLite store (/config/.storage/daikin_cycle_ml.db)
      └─▶ scheduled jobs (maintenance, k-means, COP sampling)
```

---

## 2. Architecture

```
config_entry ──▶ DaikinCycleMLCoordinator ──▶ CycleDetector
                     │
                     ├─▶ AttributeReader      (engine/attribute_reader.py)
                     ├─▶ CycleStore           (storage/store.py, in-memory deque)
                     ├─▶ CycleDB              (storage/db.py, aiosqlite)
                     │      7 tables + cluster_id + cop_samples.mode
                     │      migrations: v11, v12, v13
                     ├─▶ MultiBaseline        (ml/multi_baseline.py, per-mode)
                     ├─▶ AdaptiveThresholds   (ml/adaptive_thresholds.py)
                     ├─▶ anomaly_engine       (engine/anomaly_engine.py)
                     ├─▶ action_engine        (engine/action_engine.py)
                     ├─▶ notification_engine  (engine/notification_engine.py, v2)
                     │      AlertSpec + evaluate_alerts
                     ├─▶ cop_analyzer         (engine/cop_analyzer.py, DHW-aware)
                     ├─▶ status_report        (engine/status_report.py)
                     ├─▶ repairs              (repairs.py, 5 issue types)
                     ├─▶ sensor platform      (sensor.py, 10 entities)
                     │      ├─ configured_* attributes        (FEAT-1)
                     │      └─ thermal_power_live sensor      (FEAT-2)
                     └─▶ binary_sensor        (binary_sensor.py, 15 entities)
                            └─ DHW-mode gating for short_run/short_off/pendulum

Scheduled jobs (tracked for unload):
  • async_setup_maintenance      → daily 03:00
  • async_setup_stooklijn        → daily 04:00
  • async_setup_kmeans           → Sunday 04:00
  • async_setup_baseline_save    → every 6 h
  • _maybe_collect_cop_sample    → every 10 min
  • _maybe_refresh_stooklijn     → hourly (DHW-aware)
  • _maybe_refresh_cop_today     → hourly
```

---

## 3. Runtime data flow

### 3.1 Every 30 seconds — `_async_update_data`

```
1.  read_attrs(source_sensor)
2.  normalize (AttributeReader, mixed-type safe)
3.  missing_required(CORE_ATTRIBUTES)  → repairs + binary sensor
4.  source_age check                    → repairs + binary sensor
5.  water-pump guard (skip false-positive compressor-off when pump runs)
6.  CycleDetector.detect_compressor_on(attrs, options, power_w)
7.  if state changed:
        on cycle-close:
            _process_new_cycle(record)
                ├─ _collect_cycle_averages()
                ├─ extract_feature_vector(record)        (12-dim)
                ├─ MultiBaseline.update(mode, vector)
                ├─ AdaptiveThresholds.observe_cycle()
                ├─ MultiBaseline.zscore(mode, vector)
                ├─ evaluate_anomaly(vector, zscore)     → severity
                ├─ generate_advice(record, anomaly, quality)
                ├─ DB insert (cycles + features)
                └─ nearest_centroid(vector, centroids)  → cycles.cluster_id
8.  Alert dispatch  →  _emit_alert(AlertSpec)
        • quiet-hours gate (non-critical only)
        • dedup window (30 min binary / 20 h cop_low / 20 h stooklijn)
        • persistent_notification.create + notify.send_message
9.  async_check_repairs(hass, entry_id, snap, coordinator)
```

### 3.2 FEAT-2 sensor — thermal_power_live (same tick)

```
_read_power_w() ──▶ unit-normalized to Watts
_read_cop()     ──▶ COP or None
_flow_from_attrs() / _dt_from_attrs() / _rps_from_attrs()

_compute_thermal_power_live(power_w, cop, flow_lmin, dt_k, rps):
    1. power_cop       if power_w > 0 AND cop > 0
    2. flow_dt         if flow_lmin > 0 AND dt_k > 0
    3. rps_heuristic   if rps > 0
    4. idle            otherwise       →  state = None / "unknown"
```

Attributes exposed: `input_power_w`, `input_cop`, `input_flow_lmin`,
`input_dt_k`, `input_rps`, `calculation_source` ∈
{`power_cop`, `flow_dt`, `rps_heuristic`, `idle`}.

---

## 4. Module inventory

| Path | Purpose |
|---|---|
| `__init__.py` | `async_setup`, `setup_entry`, `unload_entry`, `CONFIG_SCHEMA` |
| `const.py` | `DOMAIN`, `VERSION`, `CORE_ATTRIBUTES` (13), emoji maps, FEAT-2 constants |
| `coordinator.py` | 30 s `DataUpdateCoordinator`, power/COP readers, all schedulers |
| `config_flow.py` | 8-step setup wizard + 8-screen OptionsFlow + reconfigure |
| `sensor.py` | 10 sensors, `_attrs_cycle_state` (FEAT-1), FEAT-2 cascade |
| `binary_sensor.py` | 15 binary sensors, DHW-mode gating |
| `services.py` | 6 HA services |
| `repairs.py` | 5 repair issue types |
| `diagnostics.py` | Redacted config + DB counts + snapshot export |
| `entity.py` | Base entity class |
| `manifest.json` | HA manifest, `version = "1.2.1"` |
| `strings.json` + `translations/{en,nl}.json` | Full EN/NL mirror |
| `quality_scale.yaml` | IQS manifest (Bronze + Silver + Gold) |
| `py.typed` | PEP 561 marker |
| `engine/attribute_reader.py` | Attrs → normalized dict, `missing_required` |
| `engine/cycle_detector.py` | RPS threshold + power fallback + water-pump guard |
| `engine/quality_scorer.py` | 5-penalty 0–100 score |
| `engine/anomaly_engine.py` | Z-score → severity classifier |
| `engine/action_engine.py` | Advice generation from record + anomaly |
| `engine/notification_engine.py` | `AlertSpec` + `evaluate_alerts` (v2) |
| `engine/cop_analyzer.py` | DHW-aware COP bucketing + stooklijn advice |
| `engine/status_report.py` | Human-readable reports + rich alerts |
| `engine/model_profiles.py` | 5 model profiles (attribute maps) |
| `engine/timer_health.py` | Scheduler health: clamp / is_stale / reconcile |
| `ml/features.py` | `VECTOR_LEN = 12`, `extract_feature_vector` |
| `ml/baseline.py` | Welford `Baseline` + EWMA `AdaptiveBaseline` |
| `ml/multi_baseline.py` | Per-mode dispatch to `AdaptiveBaseline` |
| `ml/clustering.py` | k-means (k=4), `nearest_centroid`, `classify_clusters` |
| `ml/adaptive_thresholds.py` | Per-mode percentile self-learning |
| `storage/store.py` | In-memory cycle deque |
| `storage/db.py` | aiosqlite, migrations, retention, VACUUM |
| `storage/schema.sql` | Canonical schema (7 tables) |
| `dashboard/cards/simple-card/` | Lovelace card + `preview.png` |

---

## 5. Cycle detection

Detection is deliberately layered because ESPAltherma sometimes reports
`rps = 0` while the compressor is still running (damped transition),
and sometimes reports `rps > 0` when only the water pump is active.

```
1. rps_threshold gate
       compressor_rps_threshold  (default 3)
       → if rps ≥ threshold:               COMPRESSOR ON
2. power fallback
       power_w ≥ fallback_power_threshold_w (default 200 W)
       → if crossed:                       COMPRESSOR ON
3. water-pump guard
       if water pump active AND rps == 0 AND power < threshold:
       → treat as OFF (avoid false cycle from circulation only)
```

`classify_mode(attrs)` returns `heating` / `dhw` / `cooling` /
`defrost` / `unknown` and drives everything downstream (baseline
routing, alert gating, thresholds).

---

## 6. Quality score

```
score = 100
  −30  if duration_s   < good_run_threshold_min
  −20  if dT_max       < good_dt_threshold_k
  −20  if off_time_s   < good_off_threshold_min
  −20  if short_cycle_ratio > 50
  −10  if buh_used
result = max(0, score)
```

Thresholds come from options; the penalty matrix is fixed
(`engine/quality_scorer.py`).

---

## 7. ML pipeline

### 7.1 Feature vector — 12 dimensions

`ml/features.py` → `VECTOR_LEN = 12`.

```
dim 0  duration_s
dim 1  dT_max
dim 2  dT_avg
dim 3  rps_max
dim 4  rps_avg
dim 5  outdoor_temp
dim 6  buh_used          (0/1)
dim 7  defrost_used      (0/1)
dim 8  cop_avg           (0.0 if unavailable)
dim 9  lwt_avg           (0.0 if unavailable)
dim 10 indoor_temp_avg   (0.0 if unavailable)
dim 11 extended slot     (see ml/features.py for the current consumer)
```

`is_valid_record()` rejects NaN / Inf. `extract_many()` bulk-extracts
for the k-means weekly retrain.

### 7.2 MultiBaseline (per-mode dispatch)

`ml/multi_baseline.py` holds one `AdaptiveBaseline` per mode. This
prevents a mode switch (Heating → DHW) from polluting the statistics
of the mode that just ended.

```python
update(mode, vector)
zscore(mode, vector)            # per-dim z-scores
is_anomaly(mode, vector, threshold=3.0)
to_dict() / from_dict(data)     # model_state persistence
```

Persistence key: `model_state['baseline_state']`, written every 6 h.

### 7.3 AdaptiveBaseline (EWMA)

`ml/baseline.py`. Online mean / variance with exponential weighting.

```
mean_t = (1 − α) · mean_(t−1) + α · x_t
var_t  = (1 − α) · ( var_(t−1) + α · (x_t − mean_(t−1))² )
```

| Param | Default | Meaning |
|---|---|---|
| `alpha` | 0.05 | ~14-day half-life at 30 s sampling |
| `outlier_skip_z` | 5.0 | Skip update if z exceeds this (post warm-up) |
| `min_samples_before_skip` | 20 | Warm-up gate for outlier skipping |

`Baseline` (Welford) is retained for backward-compat tests only.
`baseline_from_dict()` dispatches on `type`: `welford` → `Baseline`,
`ewma` → `AdaptiveBaseline`.

### 7.4 Anomaly severity

```
z = (x − mean) / std
z < 2.0            → normal
2.0 ≤ z < 3.0      → watch
3.0 ≤ z < 4.5      → warn
z ≥ 4.5            → critical
zero-variance dim  → z = 0 → never alerts
```

Constants: `SEV_NORMAL`, `SEV_WATCH`, `SEV_WARN`, `SEV_CRITICAL`,
`DEFAULT_WATCH_Z = 2.0`, `DEFAULT_WARN_Z = 3.0`,
`DEFAULT_CRITICAL_Z = 4.5` (tunable — backlog item).

### 7.5 AdaptiveThresholds

`ml/adaptive_thresholds.py`. Per-mode percentile self-learning.

| Learned value | Formula | Clamp |
|---|---|---|
| `learn_short_run_min(mode)` | p20 of run durations | 2 – 240 min |
| `learn_good_off_min(mode)` | p50 of off durations | 0 – 240 min |
| `learn_target_cycles_per_day()` | p50 of daily counts | 1 – 100 |

Enabled via `adaptive_thresholds_enabled` (default **off** — opt-in
after real-data validation). `adaptive_min_samples = 20` gate.

`_effective_threshold(key, default)` in the coordinator overrides
static `short_run`, `good_off`, `target_cycles_per_day` in
`_alert_binary_states` when enabled. Below `min_samples` the learned
value is `None` (falls back to static).

Persistence key: `model_state['adaptive_thresholds']`, written on the
same 6 h hook as the baseline.

### 7.6 K-means (weekly)

Runs Sunday 04:00 via `async_run_kmeans()`.

```
1. Query last 7 days cycles from DB
2. extract_many → filter is_valid_record
3. kmeans(vectors, k=4, max_iter=100, tolerance=1e-4, seed=42)
4. Save model_state['kmeans_state'] = {centroids, labels, inertia, ts}
```

- Deterministic (seed = 42).
- k-means++ init.
- `DEFAULT_K = 4`, `DEFAULT_MAX_ITER = 100`, `DEFAULT_TOLERANCE = 1e-4`.

### 7.7 Per-cycle cluster assignment

After each DB insert the coordinator calls
`nearest_centroid(vector, centroids)` and writes the result to
`cycles.cluster_id` (lazy `ALTER TABLE` on legacy DBs).

`classify_clusters(centroids)` auto-labels by feature geometry:

```
sorted by mean duration (dim 0), shortest first:
    → "pendulum"
highest dT_max (dim 1) among the rest:
    → "dhw_like"
remaining:
    → "normal"
```

Centroids are loaded at startup from
`model_state['kmeans_state']`.

### 7.8 recompute_baseline service

No longer a stub.

```
1. db.async_export_cycles(days)
2. extract_feature_vector per record → filter is_valid
3. baseline = MultiBaseline(); update per record mode
4. async_save_baseline_state()
return {"computed": int, "samples": int, "days": int}
```

---

## 8. COP analysis and stooklijn advice

`engine/cop_analyzer.py`. DHW-aware and recency-limited.

- Samples parsed from `sensor.altherma_global_cop` attributes
  (string → float, unit stripped).
- Bucketed by 2 °C outdoor temperature.
- `STOOKLIJN_RECENT_WINDOW_S = 48 · 3600` (48 h recency gate).
- DHW / `unknown` mode samples are skipped (v13 migration added
  `cop_samples.mode`).

**Advice states.**

| State | Condition |
|---|---|
| `verlaag_lwt_2c` | Current LWT above bucket average, comfort-safe |
| `verhoog_lwt_2c` | Current LWT below bucket average |
| `behoud` | Within ±1.5 °C, or comfort guard triggered |

**Sampling cadence:** every 10 min while `cop > 0`, quality = Good,
`power_stable`, no defrost. Retention: 365 days (~2 MB / year).
Analysis window: last 30 days, min 5 samples / bucket.

**Exposed.**

- `sensor.daikin_cycle_ml_stooklijn_advies` — state + bucket table attrs
- `sensor.daikin_cycle_ml_cop_vandaag` — state + samples/min/max attrs

**Daily 04:00 alert scheduling.**

- `cop_low`: day COP < 2.5 with ≥ 3 samples (20 h dedup)
- `stooklijn_advies`: saving ≥ 5 % COP, confidence ≥ 0.7 (20 h dedup)

---

## 9. Notification engine (v2)

`engine/notification_engine.py`.

```python
AlertSpec(
    alert_type: str,
    severity: str,          # info | watch | warning | critical | ok
    message: str,
    notif_id: str,
    dedupe_key: str,
    persistent: bool = True,
    context: dict | None = None,   # alert-specific extras
)
```

`evaluate_alerts(binary_states, options)` returns a list of specs.

**Severity → emoji fallback:** critical 🔴 / warning 🟠 / watch 🟡 /
info 🔵 / ok 🟢. Per-alert emoji map in `const.py`.

**Quiet hours.** Non-critical only. Window is wraparound-aware
(`22:00 → 07:00` handled correctly).

**Deduplication windows.**

| Alert family | Window |
|---|---|
| Binary (pendulum, short_run, short_off, ml_anomaly, setpoint_osc) | `alert_aggregation_minutes` (30) |
| `cop_low` | 20 h |
| `stooklijn_advies` | 20 h |
| `status_update` | `status_update_interval_hours` |

**Delivery.**

1. `persistent_notification.create({title, message, notification_id})`
2. `notify.send_message` (entity path) or legacy `notify` service
3. `_notify_fail_streak += 1` on exception → repair `notify_failed` at ≥ 3

**Test paths.** OptionsFlow screen `test_notification` accepts an
`alert_kind` (10 options) + `ignore_group_filters` flag.
`test_all_notifications` iterates `BINARY_ALERT_MAP` and additionally
emits `cop_low` + `stooklijn`.

---

## 10. Entities

### 10.1 Sensors (10)

| Entity | State | Unit | Device class |
|---|---|---|---|
| `sensor.daikin_cycle_ml_thermal_power_live` | float \| unknown | kW | `power` |
| `sensor.daikin_cycle_ml_cycle_state` | idle / active | — | — |
| `sensor.daikin_cycle_ml_current_cycle` | mode / idle | — | — |
| `sensor.daikin_cycle_ml_last_cycle` | quality score | — | — |
| `sensor.daikin_cycle_ml_today` | cycles_today | — | — |
| `sensor.daikin_cycle_ml_quality_today` | avg quality | — | — |
| `sensor.daikin_cycle_ml_source_health` | source_age_s | s | `duration` |
| `sensor.daikin_cycle_ml_learned_thresholds` | short_run_min | min | `duration` |
| `sensor.daikin_cycle_ml_cop_vandaag` | COP | — | — |
| `sensor.daikin_cycle_ml_stooklijn_advies` | state | — | — |

### 10.2 Binary sensors (15)

| # | Entity suffix | Device class | Notes |
|---|---|---|---|
| 1 | `compressor_running` | RUNNING | — |
| 2 | `pendulum_hourly` | PROBLEM | DHW-excluded |
| 3 | `pendulum_daily` | PROBLEM | — |
| 4 | `short_run` | PROBLEM | DHW-skip |
| 5 | `short_off` | PROBLEM | DHW-skip |
| 6 | `defrost_active` | RUNNING | — |
| 7 | `buh_active` | HEAT | attr `step = 1/2` |
| 8 | `dhw_active` | — | requires compressor or BUH |
| 9 | `heating_active` | HEAT | — |
| 10 | `cooling_active` | COLD | — |
| 11 | `source_stale` | PROBLEM | — |
| 12 | `missing_attributes` | PROBLEM | — |
| 13 | `setpoint_oscillating` | PROBLEM | — |
| 14 | `dhw_pendulum` | PROBLEM | — |
| 15 | `high_cycle_rate` | PROBLEM | — |

`PARALLEL_UPDATES = 0` on both platforms.

### 10.3 FEAT-1 — configured_* attributes

Exposed on `sensor.daikin_cycle_ml_cycle_state` so dashboards and
automations can discover the configured sources without reading the
config entry directly.

| Attribute | Source |
|---|---|
| `configured_source_sensor` | `entry.data["source_sensor"]` |
| `configured_power_sensor` | `entry.options["power_sensor_entity"]` |
| `configured_cop_sensor` | `entry.options["cop_sensor_entity"]` |
| `configured_indoor_sensor` | `entry.options["indoor_temp_sensor"]` |
| `configured_model` | `entry.data["model"]` |
| `configured_language` | `entry.options["notification_language"]` (default `"en"`) |
| `configured_entry_id` | `entry.entry_id` |

`notify_service` is **intentionally not exposed** (PII / no automation
value).

### 10.4 FEAT-2 — thermal_power_live cascade

`sensor.daikin_cycle_ml_thermal_power_live`. Four-step cascade, first
match wins:

| Step | Formula | Gate |
|---|---|---|
| 1. `power_cop` | `power_w · cop / 1000` | `power_w > 0 AND cop > 0` |
| 2. `flow_dt` | `flow_lmin · ρ · cp · ΔT / 60` | `flow_lmin > 0 AND ΔT > 0` |
| 3. `rps_heuristic` | `rps · RPS_KW_FACTOR` | `rps > 0` |
| 4. `idle` | — | fallback → state = unknown |

Constants (`const.py`):

```
RPS_KW_FACTOR        = 0.20   ← empirical, EPRA12 air-water, verify in heating season
WATER_SPECIFIC_HEAT  = 4.186  kJ/(kg·K)
WATER_DENSITY        = 1.0    kg/L
```

`_normalize_power_w(raw, unit)` scales to Watts if `unit_of_measurement`
is `kW`. `ΔT = abs(LWT − inlet)`.

### 10.5 Device registry

27 entities total in `core.entity_registry` — 25 integration + 2
HACS-managed companions.

---

## 11. Services

| Service | Purpose | Params |
|---|---|---|
| `reset_counters` | Reset daily counters | — |
| `export_cycles` | JSON/CSV export | `days`, `format`, `path` |
| `label_cycle` | Manual label override | `cycle_id`, `label` |
| `recompute_baseline` | Rebuild ML baseline | `days` |
| `run_maintenance` | Retention + VACUUM on demand | — |
| `send_test_notification` | Fire a test alert | `entry_id?`, `message?`, `target?` |

`send_test_notification` response: `{"ok": bool, "target": str, "message": str}`.

---

## 12. Config flow

### 12.1 Setup wizard (8 steps)

```
user → model_custom? → attributes → cycle → pendulum → quality → notifications → finalize
```

| Step | Fields |
|---|---|
| `user` | `source_sensor` (entity), `model` (dropdown, default `epra12eav3`) |
| `model_custom` | `custom_attribute_map` (JSON textarea) |
| `attributes` | Warning-only — lists missing CORE_ATTRIBUTES |
| `cycle` | `compressor_rps_threshold = 3`, `power_sensor_entity = None`, `indoor_temp_sensor = None`, `fallback_power_threshold_w = 200` |
| `pendulum` | `short_run_threshold_min = 20`, `short_off_threshold_min = 5`, `pendulum_cycles_per_day = 40`, `dhw_pendulum_cycles_per_hour = 3` |
| `quality` | `good_run_threshold_min = 45`, `good_dt_threshold_k = 5.0`, `good_off_threshold_min = 20`, `target_cycles_per_day = 8` |
| `notifications` | `persistent_enabled`, `notify_service`, `quiet_hours_enabled = false`, `quiet_hours_start = "22:00"`, `quiet_hours_end = "07:00"` |
| `finalize` | Confirmation |

### 12.2 OptionsFlow — 8-screen menu

```
init (menu)
  ├─ device              (5 fields)
  ├─ pendulum            (8 fields)
  ├─ quality             (4 fields)
  ├─ notifications       (16 fields)
  ├─ ml                  (2 fields)
  ├─ maintenance         (4 fields)
  ├─ test_notification   (alert_kind + ignore_group_filters)
  └─ test_all_notifications  (submit → emits every alert)
```

Key option fields per screen:

- **device**: `compressor_rps_threshold`, `power_sensor_entity`,
  `fallback_power_threshold_w`, `indoor_temp_sensor`,
  `cop_sensor_entity`
- **pendulum**: `short_run_threshold_min`, `short_off_threshold_min`,
  `pendulum_cycles_per_hour`, `pendulum_cycles_per_day`,
  `dhw_pendulum_cycles_per_hour`, `setpoint_oscillation_threshold`,
  `setpoint_osc_window_min`, `setpoint_osc_min_delta`
- **quality**: `good_run_threshold_min`, `good_dt_threshold_k`,
  `good_off_threshold_min`, `target_cycles_per_day`
- **notifications**: `persistent_enabled`, `notify_service`,
  `notify_emoji_enabled`, `action_advice_enabled`,
  `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`,
  `alert_aggregation_minutes`, `status_update_enabled`,
  `status_update_interval_hours`, `notification_language`,
  `alert_group_pendulum`, `alert_group_short_cycle`, `alert_group_ml`,
  `alert_group_setpoint`, `alert_group_cop_stooklijn`
- **ml**: `adaptive_thresholds_enabled`, `adaptive_min_samples`
- **maintenance**: `retention_enabled`, `cycle_retention_days`,
  `alert_retention_days`, `vacuum_enabled`

Reconfigure paths: `reconfigure_basic` (source + model) and
`reconfigure_full` (full wizard, prefilled).

---

## 13. Repairs

| Issue ID | Trigger | Title | Resolution |
|---|---|---|---|
| `source_stale` | `source_age > 2 × UPDATE_INTERVAL` | Source sensor is stale | auto-clears |
| `missing_attrs` | CORE_ATTRIBUTES incomplete | Missing required attributes | auto-clears |
| `db_corrupt` | `_db_integrity_ok == False` | Database integrity check failed | auto-clears |
| `notify_failed` | `_notify_fail_streak ≥ 3` | Notify service failing | auto-clears |
| `migration_failed` | `_migration_error` set | Migration error | auto-clears |

---

## 14. Database

### 14.1 Location

`/config/.storage/daikin_cycle_ml.db` (SQLite, via `aiosqlite`).

### 14.2 Tables (7)

**`cycles`** — one row per closed cycle.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `start_ts` | REAL | — |
| `end_ts` | REAL | — |
| `duration_s` | INTEGER | — |
| `mode` | TEXT | heating / dhw / cooling / defrost / unknown |
| `dT_max` | REAL | — |
| `dT_avg` | REAL | — |
| `rps_max` | INTEGER | — |
| `rps_avg` | REAL | — |
| `outdoor_temp` | REAL | — |
| `buh_used` | INTEGER | 0/1 |
| `defrost_used` | INTEGER | 0/1 |
| `quality_score` | INTEGER | 0–100 |
| `cluster_id` | INTEGER | lazy ALTER on legacy DBs |
| `label` | TEXT | user override |
| `thermal_kw_avg` | REAL | **in-memory CycleRecord only** — not persisted |

> **Schema-drift warning (R156).** Production DBs created before v1.2.0
> may lack `thermal_kw_avg` and `UNIQUE(start_ts)`. Always
> `PRAGMA table_info(cycles)` before assuming a column exists.
> `storage/schema.sql` is the canonical source.

**`features`**

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `cycle_id` | INTEGER FK → `cycles.id` | — |
| `vector_json` | TEXT | 12-dim vector, JSON-encoded |
| `v11` | REAL | legacy 11-dim storage |

**`alerts`**

`id` PK · `alert_type` · `severity` · `message` · `ts` · `notif_id`

**`daily_summary`** — PK `(day, mode)`.

`day` · `mode` · `cycles` · `total_duration_s` · `duration_min` ·
`duration_max` · `quality_sum` · `dt_max_sum` · `rps_sum` ·
`buh_count` · `defrost_count` · `updated_ts`.
*Only* `async_run_maintenance` writes this table.

**`cop_samples`** (v13)

`id` PK · `ts` · `cop` · `lwt` · `outdoor` · `flow_lmin` ·
`power_stable` · `mode`

**`model_state`**

`key` PK · `value_json` · `updated_ts`.
Known keys:

- `baseline_state`
- `adaptive_thresholds`
- `kmeans_state`
- `last_maintenance_ts`

**`sqlite_sequence`** — internal.

### 14.3 Migrations

| Version | Method | Scope |
|---|---|---|
| v11 | `async_migrate_features_to_v11` | 8 → 11 dim |
| v12 | `async_migrate_features_to_v12` | 11 → 12 dim |
| v13 | `async_migrate_cop_samples_to_v13` | `ALTER TABLE cop_samples ADD COLUMN mode` |

### 14.4 Retention

`async_run_maintenance(cycle_retention_days, alert_retention_days, vacuum)`:

```
1. Rollup cycles → daily_summary   (atomic, before prune)
2. Prune features                  (children first)
3. Prune cycles
4. Delete orphan features
5. Prune alerts
6. VACUUM                          (fresh connection, isolation_level=None)
```

Default windows: `cycle_retention_days = 90`,
`alert_retention_days = 30`, `vacuum_enabled = true`.

---

## 15. Scheduler

| Job | Cadence | Method | Effect |
|---|---|---|---|
| Poll | 30 s | `_async_update_data` | Read → detect → dispatch |
| COP sample | 10 min | `_maybe_collect_cop_sample` | Insert `cop_samples` if gates pass |
| Stooklijn refresh | 1 h | `_maybe_refresh_stooklijn` | DHW check before cache check |
| Baseline + adaptive save | 6 h | `async_save_baseline_state` + `async_save_adaptive_state` | `model_state` write |
| Maintenance | 03:00 daily | `async_run_maintenance` | Rollup + prune + VACUUM |
| Stooklijn analysis | 04:00 daily | `_async_stooklijn_callback` | Advice + daily alerts |
| K-means retrain | Sunday 04:00 | `async_run_kmeans` | `model_state['kmeans_state']` |
| Status update | opt-in | `async_emit_status_update` | Persistent + notify |

All subscriptions tracked (`_baseline_save_unsub`, `_kmeans_unsub`,
etc.) and cancelled on `async_unload_entry`.

---

## 16. Diagnostics

`diagnostics.py` exposes (with sensitive fields redacted):

- Config entry DATA + OPTIONS
- DB counts per table
- `MultiBaseline` snapshot
- `AdaptiveThresholds` snapshot
- Cluster summary + centroid table
- `cop_analysis` block
- Sensor states
- Coordinator stats (ticks, errors, last update)

---

## 17. Translations

Three sources, kept in lockstep:

- `strings.json`
- `translations/en.json`
- `translations/nl.json`

Required sections:

- `config.step.*` — setup wizard, reconfigure paths
- `config.error.*`, `config.abort.*`
- `options.step.*` — `init` + 8 sub-steps
- `entity.sensor.*` — 10 entries
- `entity.binary_sensor.*` — 15 entries
- `issues.*` — 5 entries
- `selector.alert_kind.options.*` — 10 entries

Hassfest rules observed: no `data_description` without a matching
`data` block; JSON examples escape `{` as `{{`; menu / info steps carry
title + description only. EN and NL are fully mirrored.

---

## 18. Testing

**Framework.**

| Tool | Version |
|---|---|
| Python | 3.14.6 (container) / 3.13 (CI) |
| pytest | 9.0.3 |
| pluggy | 1.6.0 |
| pytest-asyncio | 1.4.0 |
| pytest-homeassistant-custom-component | 0.13.366 |
| coverage.py | 7.1.0 |
| Hypothesis | 6.168.2 |
| ruff | 0.16.9 |
| pylint | 4.0.9 |
| mypy | 2.3.1 |

**Current results (v1.2.1, commit `2b9063e`).**

```
1615 passed, 4 skipped
branch coverage:  100.00 %
statements:       4092 / 4092
branches:         1166 / 1166
ruff:             clean
pylint:           10.00 / 10
mypy --strict:    0 errors
wall time:        ~58 s
```

CI: 6 / 6 green (Coverage, Pylint, Ruff, Mypy, HACS Validation,
Hassfest).

**Local run.**

```bash
export PYTHONPATH=/workspace
cd /workspace/daikin_cycle_ml
pytest -q
```

**Subset runs.** Always use `pytest tests/ -k <filter>` — never a
single absolute file path (conftest load-order trap).

---

## 19. Known limitations (v1.2.1)

- `RPS_KW_FACTOR = 0.20` is empirical for EPRA12 air-water — verify in
  heating season against real data.
- 13 `# pragma: no cover` / `no branch` markers on defensive guards
  that are runtime-unreachable. Accepted as documented guards.
- CI coverage gate is 100 % — every new uncovered line breaks CI.
- CI runs on Python 3.13, dev container on 3.14.6. Divergence accepted
  while green.
- `thermal_kw_avg` is **not persisted** to `cycles` (in-memory only).
- COP and cost analysis beyond stooklijn advice is out of scope.
- Adaptive thresholds default **off** (opt-in after real-data
  validation).
- K-means and cluster sensors require ≥ 7 days of cycles before they
  produce meaningful output.
- Weather-compensation advisor is not implemented.
- Brine circuits (EPRA12 is split air-water) are not supported.
- No MQTT publish path (confirmed not needed).
- No web UI cycle explorer.

---

## 20. Version history

| Version | Date | Key changes |
|---|---|---|
| v0.5.0 | 2026-09-26 | ML 8 → 11 dims, i18n basis, menu OptionsFlow |
| v0.6.0 | 2026-09-26 | `setpoint_osc`, EN/NL i18n, alert groups |
| v0.7.0 | 2026-09-26 | Core attrs, sensor restructure, water-pump guard, `VECTOR_LEN = 12` |
| v0.8.0 | 2026-09-26 | `OptionsFlowWithReload`, HA compliance, test-notification dropdown |
| v0.9.0 | 2026-09-26 | Rich alerts EN/NL, all-alerts test, import smoke, ruff, manifest validator |
| v1.0.0 | 2026-09-26 | HA compliance release — ruff + pylint clean, IQS Bronze + Silver |
| v1.0.1 | 2026-09-27 | DHW gating, stooklijn mode, `AlertSpec` context, IQS Gold |
| v1.0.2 | 2026-09-27 | mypy `--strict` 219 → 0, `py.typed`, CI Mypy |
| v1.1.0 | 2026-09-27 | HACS-compliant layout. Breaking: integration moved to `custom_components/daikin_cycle_ml/` |
| v1.1.1 | 2026-09-28 | Docs-only: `dashboard/` folder + showcase + HANDOFF_SOP |
| v1.2.0 | 2026-09-28 | C+F2 + COV-0/1/2 + FEAT-1 + FEAT-2 + mypy fix. ⚠️ Tagged with stale version strings (`1.1.1`). Marked pre-release after the fact |
| v1.2.1 | 2026-09-28 | Fix: bump version strings to `1.2.1`, close `[Unreleased]`, refresh README badges. Commit `2b9063e` |

---

## Appendix A — SSH quick checks

```bash
# Disk version strings
docker exec homeassistant bash -lc '
  grep "^VERSION" /config/custom_components/daikin_cycle_ml/const.py
  grep "\"version\"" /config/custom_components/daikin_cycle_ml/manifest.json
'

# Feature anchors (rollback / update verification)
docker exec homeassistant bash -lc '
  grep -c thermal_power_live      /config/custom_components/daikin_cycle_ml/sensor.py
  grep -c configured_source_sensor /config/custom_components/daikin_cycle_ml/sensor.py
'
```

## Appendix B — DB quick checks

```bash
docker exec homeassistant bash -lc "python3 - <<'PYEOF'
import sqlite3
c = sqlite3.connect('/config/.storage/daikin_cycle_ml.db')
print('cycles     :', c.execute('SELECT COUNT(*) FROM cycles').fetchone()[0])
print('cop_samples:', c.execute('SELECT COUNT(*) FROM cop_samples').fetchone()[0])
print('modes      :', dict(c.execute('SELECT mode, COUNT(*) FROM cop_samples GROUP BY mode')))
print('model_state:', [r[0] for r in c.execute('SELECT key FROM model_state')])
PYEOF
"
```

## Appendix C — Rollback verification

Rollback is **not** complete until both checks pass:

1. Version strings back to the previous release.
2. Feature anchors gone (`grep -c thermal_power_live` = 0 for a v1.1.1
   rollback).

Checking only (1) is a known failure mode — see Rule R177 in the
handoff.
---

## COP hourly pipeline (v1.3.0)

New in v1.3.0: hourly aggregation of cop_samples into cop_hourly,
plus query, sensor, REST, and export surfaces.

### Writer

CycleDB.async_rollup_cop_hourly(window_hours=6):

- Reads cop_samples for the trailing window.
- Buckets by (CAST(ts/3600 AS INT), mode).
- Computes per bucket: n_samples, cop_mean, cop_p10, cop_p50,
  cop_p90, cop_std, lwt_mean, outdoor_mean/min/max, flow_mean.
- Idempotent INSERT ... ON CONFLICT(ts_hour, mode) DO UPDATE.

Hook: _async_baseline_save_callback (every 6h) calls
_maybe_rollup_cop_hourly() in an isolated try/except so a rollup
failure cannot break baseline persistence.

### Query layer

Three methods on CycleDB:

- async_query_cop_hourly(since_ts, until_ts=None, mode=None, limit=None)
- async_cop_hourly_stats(since_ts, mode=None) - bucket-weighted mean
  (weight = n_samples), p10 = min(bucket p10), p90 = max(bucket p90),
  min/max of bucket means
- async_cop_hourly_by_mode(since_ts) - {mode: stats}

Coordinator: _maybe_refresh_cop_hourly(now) throttled to 300s;
populates _cop_hourly_cache with day (1d), week (7d), month (30d),
and curve_recent (48h, capped to 96 points). Curve refresh lives in
a second try/except so its failure cannot poison the KPI cache or
the throttle timestamp.

### Sensors

| Entity | Unit | State | Attributes |
|---|---|---|---|
| sensor.cop_mean_day | COP | heating weighted mean last 24h | per-period + by_mode |
| sensor.cop_mean_week | COP | heating weighted mean last 7d | same |
| sensor.cop_mean_month | COP | heating weighted mean last 30d | same |
| sensor.cop_curve_recent | count | n_points | points[] 48h x mode |

sensor.cop_curve_recent payload is bounded to ~8 KB (48h x 2 modes),
safely under HA's 16 KB recorder attribute cap.

### REST endpoint

GET /api/daikin_cycle_ml/cop_hourly?days=N&mode=X

- Auth required (requires_auth = True).
- days 1..365, default 30; mode optional.
- 200 -> {days, mode, count, rows}; 400 invalid days; 503 no
  entry/db; 500 query failure.
- Registered once per HA lifecycle in async_setup via
  hass.data["daikin_cycle_ml_view_registered"] flag.
- manifest.json declares dependencies ["http"].

### Export service

daikin_cycle_ml.export_cop_hourly (6th service):

| Field | Type | Default | Notes |
|---|---|---|---|
| entry_id | str | required | config entry |
| days | int | 30 | 1..365 |
| mode | str | none | heating/dhw/defrost/unknown |
| format | enum | json | json or csv |

Returns in-memory (mirrors export_cycles):
{format, days, mode, count, rows} for json,
{format, days, mode, count, content} for csv.

### Dashboard cards

See dashboard/README.md for two ready-made ApexCharts cards:
scatter (COP vs outdoor, 90d via REST) and time series
(COP last 48h via sensor attrs).
