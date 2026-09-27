# Daikin Cycle ML

Home Assistant integration that detects compressor cycles, classifies
pendulum behaviour, self-learns per mode, and advises on Daikin Altherma
heat pumps. **Local-only ML, no cloud.**

[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](https://github.com/elRadix/daikin_cycle_ml/releases/tag/v1.0.1)
[![Tests](https://img.shields.io/badge/tests-1300%2B-brightgreen.svg)](#16-testing)
[![Coverage](https://img.shields.io/badge/coverage-95.09%25-brightgreen.svg)](#16-testing)
[![Ruff](https://img.shields.io/badge/ruff-clean-brightgreen.svg)](https://github.com/astral-sh/ruff)
[![Pylint](https://img.shields.io/badge/pylint-9.94%2F10-brightgreen.svg)](https://pylint.readthedocs.io/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-blue.svg)](https://www.home-assistant.io/)
[![IQS](https://img.shields.io/badge/IQS-Bronze%20%2B%20Silver-orange.svg)](quality_scale.yaml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**IoT class:** `calculated`

---

## Table of contents

1. [Why](#1-why)
2. [Features](#2-features)
3. [Requirements](#3-requirements)
4. [Installation](#4-installation)
5. [Source sensor & attributes](#5-source-sensor--attributes)
6. [Config flow — step by step](#6-config-flow--step-by-step)
7. [Entities](#7-entities)
8. [Services](#8-services)
9. [Alerts & notifications](#9-alerts--notifications)
10. [ML pipeline](#10-ml-pipeline)
11. [Clustering](#11-clustering)
12. [Scheduled jobs](#12-scheduled-jobs)
13. [Retention & storage](#13-retention--storage)
14. [Database schema](#14-database-schema)
15. [Integration Quality Scale](#15-integration-quality-scale)
16. [Testing](#16-testing)
17. [Troubleshooting](#17-troubleshooting)
18. [Out of scope](#18-out-of-scope)

---

## 1. Why

Pendelen (short-cycling) is the #1 cause of reduced COP and extra wear on
Daikin Altherma heat pumps. Existing HA integrations do not detect it,
because they look at temperature or power — not at the actual compressor
runtime pattern.

Daikin Cycle ML watches the ESPAltherma sensor stream, detects every
compressor cycle (start → run → stop), scores it, learns what "normal"
looks like for **your** installation per mode (Heating / Cooling / DHW),
and warns you when patterns drift.

No cloud. No external API. Everything runs inside your Home Assistant box.

---

## 2. Features

- **Cycle detection** — RPS threshold + optional power-sensor fallback
- **Water pump guard** — skips cycles where the pump is off
- **8 pendulum patterns** — per mode (Heating / Cooling / DHW), hourly + daily
- **Quality score 0-100** per cycle (runtime, dT, off-time, BUH, defrost)
- **thermal_kW per cycle** — computed from flow × 4.18 × dT
- **MultiBaseline** — per-mode EWMA, dim 12, persistent, dim-guarded
- **AdaptiveThresholds** — percentile-based self-learning per mode (opt-in)
- **Weekly k-means clustering** + per-cycle nearest-centroid assignment
- **12-dim feature vector** — duration_s, dT_max, dT_avg, rps_max, rps_avg,
  outdoor_temp, buh_used, defrost_used, cop_avg, lwt_avg, indoor_temp_avg,
  thermal_kw_avg
- **Actionable advice** — priority-ordered, category-tagged, included in alerts
- **Setpoint-oscillation detection** — rolling window, tunable threshold
- **Rich sectioned alerts** — emoji + aligned rows + severity + mode + advice
- **Bilingual notifications** — EN + NL templates, per installation
- **Per-group alert toggles** — 5 groups: pendulum / short-cycle / ML /
  setpoint / COP-stooklijn
- **Test-notification dropdown** — 9 alert kinds (incl. all_alerts button)
- **COP stooklijn analysis** — daily advice + bucket table
- **Custom attribute map** — remap non-standard ESPAltherma firmware keys
- **SQLite persistence** — retention, daily rollups, auto-migration 8→11→12
- **24 entities** — 9 container sensors + 15 binary sensors
- **6 services** — reset, export, label, recompute, maintain, test-notify
- **HA-compliant** — 8-step wizard, OptionsFlowWithReload, 8-screen menu
- **IQS Bronze + Silver** — see quality_scale.yaml

---

## 3. Requirements

- **Home Assistant** 2026.9 or newer
- **Python** 3.13 (HA core 2026 baseline)
- **ESPAltherma** publishing attributes on a sensor
- Recommended: outdoor temp attribute + leaving-water temp attribute
  (needed for dT and COP)

---

## 4. Installation

1. Copy custom_components/daikin_cycle_ml/ into your HA config tree
   (usually /config/custom_components/daikin_cycle_ml/).
2. **Restart Home Assistant** (Settings → System → Restart).
   A config-entry reload is **not** enough when the module code changes.
3. **Settings → Devices & Services → Add Integration → "Daikin Cycle ML"**.
4. Follow the 8-step wizard (see next section).

---

## 5. Source sensor & attributes

Daikin Cycle ML reads from a single HA sensor (typically
sensor.althermasensors published by ESPAltherma). All processing is based
on the sensor's **attributes**.

### Required attributes

Always processed. If any is missing, the missing_attrs repair is raised
and cycle detection may degrade. 13 core attributes:

| Attribute | Purpose |
|---|---|
| INV frequency (rps) | Compressor rotation speed → cycle detection |
| Operation Mode | Fallback mode source |
| I/U operation mode | Primary mode source (Heating / Cooling / DHW) |
| 3way valve | DHW vs heating discrimination |
| Defrost Operation | Defrost flag on cycle record |
| Leaving water temp after BUH (R2T) | LWT — for dT and COP |
| Inlet water temp (R4T) | Inlet — for dT and COP |
| Flow sensor (l/min) | Water flow — for thermal kW |
| Water pump operation | Pump on/off — for cycle validity |
| Outdoor air temp (R1T) | Outdoor temp — for stooklijn bucketing |
| DHW tank temp (R5T) | DHW tank temp — for DHW recognition |
| BUH Step1 | Backup heater step 1 flag |
| BUH Step2 | Backup heater step 2 flag |

### Recommended attributes

Pre-selected in the wizard. Safe to enable. Improve quality and enable
extra features.

| Attribute | Purpose |
|---|---|
| Discharge pipe temp. | Compressor health indicator |
| Suction pipe temp. | Refrigerant-side context |
| INV primary current (A) | Extra power proxy |
| Target Cond. Temp. | Target condensing temp for stooklijn comparison |
| LW setpoint (main) | Required for setpoint_osc alert |
| DHW setpoint | DHW setpoint for DHW cycle context |

### Optional attributes

Default off. Enable only if your installation publishes them.

Heat exchanger mid-temp., Liquid pipe temp.(R6T), Expansion valve (pls),
Crank case heater 1, Pressure equalizing operation, 4 Way Valve 1,
Solenoid Valve 1, Target Evap. Temp., RT setpoint, High Pressure,
Water pressure, Brine inlet temp., Brine outlet temp.

**Note on required attributes:** even if you deselect required attributes
in the wizard, they are **always kept** — cycle detection depends on them.

### Custom attribute map

If your ESPAltherma firmware uses non-standard attribute names, the wizard
(Model = Custom) offers a JSON mapping. Left = standard key, right = your
actual attribute name. The integration renames your attribute to the
standard key before processing.

Rules:
- Valid JSON object (validated at wizard time)
- Empty or missing actual attribute → original is left untouched
- Only affects the keys you list

---

## 6. Config flow — step by step

### Setup wizard (8 steps)

    user → model_custom (opt) → attributes → cycle
         → pendulum → quality → notifications → finalize

#### Step 1 — Source & model

| Field | Type | Default | Notes |
|---|---|---|---|
| Source sensor | entity picker | sensor.althermasensors | Your ESPAltherma sensor |
| Model | dropdown | EPRA12EAV3 | Or Custom for non-standard pumps |

Models: EPRA12EAV3, EPRA08EAV3, EABH16DA6V, EABX16DA6V, Custom.

#### Step 2 — Custom attribute map *(only if Model = Custom)*

JSON textarea. See section 5.

#### Step 3 — Attributes (warning-only)

Shows how many of the 13 core attributes are present. Missing ones are
listed but do **not** block the wizard — you can proceed and fix later.

#### Step 4 — Cycle detection

| Field | Default | Notes |
|---|---|---|
| Compressor RPS threshold | 3 | Compressor "on" when RPS > this |
| Power sensor entity | (none) | Optional fallback |
| Indoor temp sensor | (none) | Enables indoor_temp_avg in ML vector |
| Fallback power threshold (W) | 200 | |

#### Step 5 — Pendulum thresholds

| Field | Default |
|---|---|
| Short run threshold (min) | 20 |
| Short off threshold (min) | 5 |
| Pendulum cycles per hour | 4 |
| Pendulum cycles per day | 40 |
| DHW pendulum cycles per hour | 3 |

#### Step 6 — Quality thresholds

| Field | Default |
|---|---|
| Good run threshold (min) | 45 |
| Good dT threshold (K) | 5.0 |
| Good off threshold (min) | 20 |
| Target cycles per day | 8 |

#### Step 7 — Notifications (wizard-basic)

| Field | Default |
|---|---|
| Persistent notifications | true |
| Notify target | (empty) |
| Quiet hours enabled | false |
| Quiet hours start | 22:00 |
| Quiet hours end | 07:00 |

#### Step 8 — Finalize

Review + Submit. Integration starts polling every 30 s.

---

### Options menu (8 screens)

**Settings → Devices & Services → Daikin Cycle ML → Configure**. Each
screen saves independently.

#### 1. Device

| Field | Default | Range |
|---|---|---|
| Compressor RPS threshold | 3 | 1–100 |
| Power sensor | (none) | — |
| Fallback power threshold (W) | 200 | 10–10000 |
| Indoor temp sensor | (none) | — |
| COP sensor | (none) | — |

#### 2. Pendulum

| Field | Default | Range |
|---|---|---|
| Short run threshold (min) | 20 | 1–240 |
| Short off threshold (min) | 5 | 1–120 |
| Pendulum cycles per hour | 4 | 1–100 |
| Pendulum cycles per day | 40 | 1–200 |
| DHW pendulum cycles per hour | 3 | 1–20 |
| Setpoint oscillation threshold | 6 | 1–100 |
| Setpoint window (min) | 30 | 5–180 |
| Minimum setpoint change (°C) | 0.5 | 0.1–2.0 (step 0.1) |

#### 3. Quality

| Field | Default |
|---|---|
| Good run threshold (min) | 45 |
| Good dT threshold (K) | 5.0 |
| Good off threshold (min) | 20 |
| Target cycles per day | 8 |

#### 4. Notifications (16 fields)

| Field | Default |
|---|---|
| Persistent notifications | true |
| Notify target | (empty) |
| Emoji in notifications | true |
| Include action advice | true |
| Quiet hours | false |
| Quiet hours start / end | 22:00 / 07:00 |
| Alert aggregation (minutes) | 30 (1–1440) |
| Periodic status updates | false |
| Status interval (hours) | 24 (1–168) |
| Notification language | English (or Nederlands) |
| Alert: pendulum | true |
| Alert: short cycle | true |
| Alert: ML anomaly | true |
| Alert: setpoint oscillation | true |
| Alert: COP / heat curve | true |

#### 5. ML

| Field | Default |
|---|---|
| Adaptive thresholds enabled | false |
| Adaptive min samples | 20 |

#### 6. Maintenance

| Field | Default |
|---|---|
| Retention enabled | true |
| Cycle retention (days) | 90 |
| Alert retention (days) | 30 |
| VACUUM enabled | true |

#### 7. Send test notification

Dropdown of 9 alert kinds:

- status_summary
- pendulum_hourly
- pendulum_daily
- short_run
- short_off
- ml_anomaly
- setpoint_osc
- cop_low
- stooklijn_advies

Option: ignore_group_filters (bool). Submits and shows a **preview** of
the rendered message.

#### 8. Send ALL test notifications

Single button. Emits **every** alert kind in one shot — useful for verifying
EN/NL formatting, emoji, severity labels and rich-sectioned layout at once.

---

### Reconfigure

Two paths, via **Settings → Devices & Services → Reconfigure**:

- reconfigure_basic — change source sensor + model only
- reconfigure_full — re-run the full wizard, prefilled

> source_sensor and model live in the config-entry **DATA**, not OPTIONS.
> That's why they can only be changed via Reconfigure.

---

## 7. Entities

### Container sensors (9)

| Entity | Unit | Description |
|---|---|---|
| sensor.daikin_cycle_ml_cycle_state | — | idle / active |
| sensor.daikin_cycle_ml_current_cycle | — | Current cycle mode + duration attribute |
| sensor.daikin_cycle_ml_last_cycle | score | Last cycle quality + cluster attribute |
| sensor.daikin_cycle_ml_today | — | Cycles since midnight |
| sensor.daikin_cycle_ml_quality_today | score | Average quality today |
| sensor.daikin_cycle_ml_source_health | s | Seconds since last source update |
| sensor.daikin_cycle_ml_learned_thresholds | min | Adaptive threshold (if enabled) |
| sensor.daikin_cycle_ml_cop_vandaag | COP | Today's average COP |
| sensor.daikin_cycle_ml_stooklijn_advies | — | verlaag_lwt_2c / verhoog_lwt_2c / behoud / unknown |

Cluster membership: state_attr('sensor.daikin_cycle_ml_last_cycle', 'cluster').

### Binary sensors (15)

| Entity | Device class | Description |
|---|---|---|
| compressor_running | RUNNING | Compressor currently on |
| pendulum_hourly | PROBLEM | Cycles/hour ≥ threshold |
| pendulum_daily | PROBLEM | Cycles/day ≥ threshold |
| short_run | PROBLEM | Last cycle < short-run threshold |
| short_off | PROBLEM | Off-time < short-off threshold |
| defrost_active | RUNNING | Defrost in progress |
| buh_active | HEAT | BUH Step1 or Step2 on (attr: step=1 or 2) |
| dhw_active | — | Currently in DHW mode |
| heating_active | HEAT | Currently in heating mode |
| cooling_active | COLD | Currently in cooling mode |
| source_stale | PROBLEM | Source sensor not fresh |
| missing_attributes | PROBLEM | Required attributes missing |
| setpoint_oscillating | PROBLEM | Setpoint changes ≥ threshold |
| dhw_pendulum | PROBLEM | DHW cycles/h ≥ DHW threshold |
| high_cycle_rate | PROBLEM | Cycles/h > 1.5 × target |

---

## 8. Services

All under daikin_cycle_ml.

### reset_counters

Reset daily counters. No parameters.

### export_cycles

| Field | Type | Default |
|---|---|---|
| days | int | 30 |
| format | string | json (or csv) |
| path | string | /config/daikin_cycles_export.json |

### label_cycle

| Field | Type | Required |
|---|---|---|
| cycle_id | int | yes |
| label | string | yes |

### recompute_baseline

| Field | Type | Default |
|---|---|---|
| days | int | 30 |

### run_maintenance

No parameters. Runs retention prune + optional VACUUM.

### send_test_notification

| Field | Type | Default |
|---|---|---|
| entry_id | string | auto-resolved if 1 entry |
| message | string | Daikin Cycle ML: test notification |
| target | string | from options |

**Response:** {"ok": bool, "target": str, "message": str}.

Example:

    service: daikin_cycle_ml.send_test_notification
    data:
      message: "Hello from Daikin Cycle ML"

---

## 9. Alerts & notifications

Every alert is rendered as a **rich sectioned message** in the selected
language (EN or NL).

### Structure

    🔁 Daikin Cycle ML — Pendulum (hourly)
    🕐 2026-09-26 14:32
    ━━━━━━━━━━━━━━━━━━━━━━
    🔁 Cycli/uur     5
    🎯 Doel          ≤ 4
    🔥 Modus         verwarmen
    🌡️ LWT setpoint  35.0 °C
    ⏱️ Gem. duur     14 min
    🌡️ Buiten        14.7 °C
    ━━━━━━━━━━━━━━━━━━━━━━
    💡 Verhoog de thermostaat-hysterese, of verlaag de stooklijn
       zodat cycli langer duren.

### Alert matrix

| Alert | Trigger | Severity | Group | Dedup |
|---|---|---|---|---|
| pendulum (hourly) | cycles/h ≥ target | warning | pendulum | 30 min |
| pendulum (daily) | cycles today ≥ target | warning | pendulum | 30 min |
| short_run | last cycle < threshold | warning | short_cycle | 30 min |
| short_off | off-time < threshold | warning | short_cycle | 30 min |
| ml_anomaly | z-score ≥ watch (2.0) | warn/crit | ml | 30 min |
| setpoint_osc | N changes in window | warning | setpoint | 30 min |
| cop_low | daily COP < 2.5 | warning | cop_stooklijn | 20 h |
| stooklijn_advies | daily heat-curve advice | warning | cop_stooklijn | 20 h |
| status_update | opt-in periodic | info | — | interval |

### Delivery channels

Two independent channels — a failure in one does not block the other:

1. **Persistent notification** — HA sidebar (if persistent_enabled)
2. **Notify target** — any notify.* entity (entity- or legacy-service)

### Quiet hours

Non-critical alerts suppressed in the window (default 22:00 → 07:00).
Wraparound-aware.

### Per-group toggles

5 independent groups in **Options → Notifications**:
pendulum, short_cycle, ml, setpoint, cop_stooklijn.

### Emoji

Per alert-type, severity as fallback. Disable with **Emoji** = false.

| Alert | Emoji |
|---|---|
| pendulum | 🔁 |
| short_run | ⏱️ |
| short_off | 💤 |
| ml_anomaly | 🧠 |
| setpoint_osc | 🎯 |
| cop_low / stooklijn_advies | 📉 |
| status_update | 📊 |

---

## 10. ML pipeline

Every closed cycle becomes a **12-dimensional feature vector**:

    [0]  duration_s
    [1]  dT_max
    [2]  dT_avg
    [3]  rps_max
    [4]  rps_avg
    [5]  outdoor_temp
    [6]  buh_used
    [7]  defrost_used
    [8]  cop_avg
    [9]  lwt_avg
    [10] indoor_temp_avg
    [11] thermal_kw_avg          (added in v0.7.0)

Missing values → 0.0 (JSON-safe).

Three self-learning layers:

### 1. MultiBaseline

Per-mode **EWMA** with Welford-style variance. Produces z-scores per
dimension for anomaly detection.

- Persisted to model_state['baseline_state']
- Dim-guarded: legacy 8/11-dim baseline resets on load

### 2. AdaptiveThresholds

Per-mode percentile. Learns short_run and good_off from your real cycles.
**Opt-in** via adaptive_thresholds_enabled.

- Requires adaptive_min_samples cycles (default 20)
- Persisted to model_state['adaptive_thresholds']
- Exposed via sensor.learned_thresholds

### 3. K-means clustering

Weekly retrain over last 7 days → 3 centroids. See next section.

---

## 11. Clustering

Weekly k-means over the last 7 days → **3 centroids**.

New cycles get cluster_id via **nearest-centroid**. Labels are
auto-derived:

- **shortest mean duration** → cluster_pendulum
- **highest dT_max** → cluster_dhw_like
- **rest** → cluster_normal

Exposed as attribute on sensor.daikin_cycle_ml_last_cycle.

Persisted to model_state['kmeans_state'].

---

## 12. Scheduled jobs

| When | What |
|---|---|
| Every 30 s | Poll sensor, detect cycle transitions, dispatch alerts |
| Every 10 min | Collect COP sample (if COP sensor configured) |
| Every 1 h | Refresh stooklijn cache + daily COP counters |
| Every 6 h | Persist baseline + adaptive state to model_state |
| Daily 03:00 | Retention rollup + prune + optional VACUUM |
| Daily 04:00 | Stooklijn analysis (force refresh + notify) |
| Sunday 04:00 | K-means retrain over last 7 days |
| Every N h (opt-in) | Status summary via build_status_message |

---

## 13. Retention & storage

- **Storage**: /config/.storage/daikin_cycle_ml.db (SQLite via aiosqlite)
- **Cycle retention**: cycle_retention_days (default **90**) — older cycles
  rolled up into daily_summary before pruning
- **Alert retention**: alert_retention_days (default **30**)
- **Features**: orphan-pruned via FK
- **VACUUM**: optional, runs after prune
- **Migration**: automatic (8 → 11 → 12 dim), idempotent

---

## 14. Database schema

**7 tables**:

### cycles

    id             INTEGER PRIMARY KEY
    start_ts       REAL
    end_ts         REAL
    duration_s     REAL
    mode           TEXT      -- heating / cooling / dhw / unknown
    dT_max         REAL
    dT_avg         REAL
    rps_max        INT
    rps_avg        REAL
    outdoor_temp   REAL
    buh_used       INT
    defrost_used   INT
    quality_score  INT
    cluster_id     INTEGER   -- nullable
    label          TEXT      -- nullable
    thermal_kw_avg REAL      -- nullable (v0.7.0+)

### features

    id          INTEGER PRIMARY KEY
    cycle_id    INTEGER FK -> cycles(id)
    vector_json TEXT         -- JSON array of 12 floats

### alerts

    id         INTEGER PRIMARY KEY
    alert_type TEXT
    severity   TEXT
    message    TEXT
    ts         REAL
    notif_id   TEXT

### daily_summary

    day          TEXT   -- YYYY-MM-DD
    mode         TEXT
    cycles       INTEGER
    quality_avg  REAL
    duration_avg REAL
    PRIMARY KEY (day, mode)

### cop_samples

    id            INTEGER PRIMARY KEY
    ts            REAL
    cop           REAL
    lwt           REAL
    outdoor       REAL
    flow_lmin     REAL
    power_stable  INT

### model_state

    key         TEXT PRIMARY KEY
    value_json  TEXT NOT NULL
    updated_ts  REAL NOT NULL

Keys: baseline_state, adaptive_thresholds, kmeans_state,
last_maintenance_ts.

### sqlite_sequence

SQLite internal.

---

## 15. Integration Quality Scale

Status: **Bronze ✅ + Silver ✅** (Gold partial).

See quality_scale.yaml for the full status.

### Bronze

| Rule | Status |
|---|---|
| config-flow | ✅ |
| config-flow-test-coverage | ✅ |
| test-coverage | ✅ (≥95%) |
| action-setup | ✅ |
| runtime-data | ✅ |
| entity-unique-id | ✅ |
| has-entity-name | ✅ |
| brands | ✅ |
| docs-* (10 rules) | ✅ |

### Silver

| Rule | Status |
|---|---|
| parallel-updates | ✅ (PARALLEL_UPDATES = 0) |
| integration-owner | ✅ (codeowners) |
| test-coverage | ✅ |
| config-entry-unloading | ✅ |
| action-exceptions | ✅ |
| reauthentication-flow | exempt (local source) |
| entity-unavailable | ✅ |

### Gold (partial)

| Rule | Status |
|---|---|
| devices | ✅ |
| diagnostics | ✅ |
| repair-issues | ✅ |
| entity-translations | ✅ (EN + NL) |
| reconfiguration-flow | ✅ |
| entity-device-class | ✅ |
| entity-category | ✅ |
| discovery | exempt (calculated) |
| dynamic-devices | exempt |
| stale-devices | exempt |

### Platinum (todo)

| Rule | Status |
|---|---|
| async-dependency | partial (aiosqlite is async) |
| inject-websession | exempt |
| strict-typing | todo (mypy --strict, backlog) |

---

## 16. Testing

- **~1310 tests**, **95.11% coverage**
- Framework: pytest + pytest_homeassistant_custom_component (phcc)
- **Coverage threshold enforced at 95%** (--cov-fail-under=95)
- **Ruff clean** — HA 2026+ config (line-length 100, py313,
  select E/W/F/I/UP/B/SIM/RET/PIE/C4/RUF)
- **Pylint 9.94/10** — --fail-under=8.0 gate, integration code only
- **Import smoke** — 130 modules via importlib.import_module()
- **SQLite integrity** — PRAGMA integrity_check in CI

Per-module coverage (v1.0.0):

| Module | Coverage |
|---|---|
| const.py | 100% |
| diagnostics.py | 100% |
| repairs.py | 100% |
| entity.py | 100% |
| engine/cop_analyzer.py | 100% |
| engine/quality_scorer.py | 100% |
| engine/model_profiles.py | 100% |
| engine/timer_health.py | 100% |
| ml/features.py | 100% |
| ml/multi_baseline.py | 100% |
| engine/cycle_detector.py | 99% |
| ml/baseline.py | 99% |
| ml/clustering.py | 97% |
| engine/notification_engine.py | 97% |
| services.py | 97% |
| engine/status_report.py | 96% |
| storage/db.py | 96% |
| storage/store.py | 96% |
| config_flow.py | 95% |
| engine/anomaly_engine.py | 95% |
| binary_sensor.py | 94% |
| ml/adaptive_thresholds.py | 94% |
| engine/action_engine.py | 93% |
| engine/attribute_reader.py | 93% |
| sensor.py | 93% |
| coordinator.py | 92% |
| __init__.py | 83% |

Run locally:

    PYTHONPATH=/workspace pytest -q

Run ruff:

    ruff check .

Run pylint:

    FILES=$(git ls-files '*.py' | grep -v '^tests/' | grep -v '^docs/')
    pylint --rcfile=.pylintrc $FILES --fail-under=8.0

---

## 17. Troubleshooting

### Binary sensors stay off (heating_active, cooling_active, dhw_active)

- **Fixed in v0.6.0.** Upgrade if older.
- Still stuck after upgrade → **full HA restart** (not config-entry reload).

### source_stale repair is shown

- ESPAltherma not publishing fresh data.
- Check ESP device and Wi-Fi. Repair resolves automatically.

### missing_attrs repair is shown

- Source sensor missing one or more required attributes.
- Verify ESPAltherma fields, or add a custom attribute map.

### Alerts are noisy

- Increase **Alert aggregation (minutes)**.
- Disable unneeded alert groups.
- Raise **Pendulum cycles per hour** / **per day**.
- Enable **Quiet hours**.

### Notifications are in the wrong language

- **Options → Notifications → Notification language** → EN or NL.

### setpoint_osc alert never fires

- Check source publishes **LW setpoint (main)**.
- Default threshold is **6 changes / 30 min** — most installs never hit it
  (that's the point).

### cop_vandaag sensor stays at 0

- Configure a **COP sensor** in **Options → Device**.
- Samples collected every 10 min.

### Database grows too large

- Lower **Cycle retention (days)** in **Options → Maintenance**.
- Ensure vacuum_enabled = true.
- Manual: daikin_cycle_ml.run_maintenance.

---

## 18. Out of scope

- Cost tracking / € calculations
- Setpoint writes
- HACS publication
- Supervised ML (label-based training)
- Weather forecast integration
- ML feature vector 12 → 14 dims
- Brine circuits (EPRA12 is split air-water)
- Web UI cycle-explorer

---

## License

See [LICENSE](LICENSE).