# Daikin Cycle ML

Home Assistant integration that detects compressor cycles, classifies
pendulum behaviour, self-learns per mode, and advises on Daikin Altherma
heat pumps. **Local-only ML, no cloud.**

[![Version](https://img.shields.io/badge/version-0.6.0-blue.svg)](https://github.com/elRadix/daikin_cycle_ml/releases/tag/v0.6.0)
[![Tests](https://img.shields.io/badge/tests-987-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-95.65%25-brightgreen.svg)](#testing)

**IoT class:** `calculated`

---

## Table of contents

1. [Why](#1-why)
2. [Features](#2-features)
3. [Requirements](#3-requirements)
4. [Installation](#4-installation)
5. [Source sensor & attributes](#5-source-sensor--attributes)
   - [Required attributes](#required-attributes)
   - [Recommended attributes](#recommended-attributes)
   - [Optional attributes](#optional-attributes)
   - [Custom attribute map](#custom-attribute-map)
6. [Config flow — step by step](#6-config-flow--step-by-step)
   - [Setup wizard (8 steps)](#setup-wizard-8-steps)
   - [Options menu (6 screens)](#options-menu-6-screens)
7. [Entities](#7-entities)
   - [Sensors (31)](#sensors-31)
   - [Binary sensors (19)](#binary-sensors-19)
8. [Services](#8-services)
9. [Alerts & notifications](#9-alerts--notifications)
10. [ML pipeline](#10-ml-pipeline)
11. [Clustering](#11-clustering)
12. [Scheduled jobs](#12-scheduled-jobs)
13. [Retention & storage](#13-retention--storage)
14. [Database schema](#14-database-schema)
15. [Troubleshooting](#15-troubleshooting)
16. [Testing](#16-testing)
17. [Out of scope](#17-out-of-scope)

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
- **8 pendulum patterns** — per mode (Heating / Cooling / DHW), hourly + daily
- **Quality score 0-100** per cycle (runtime, dT, off-time, BUH, defrost)
- **MultiBaseline** — per-mode EWMA, persistent, dim-guarded
- **AdaptiveThresholds** — percentile-based self-learning per mode (opt-in)
- **Weekly k-means clustering** + per-cycle nearest-centroid assignment
- **11-dim feature vector** — `duration_s`, `dT_max`, `dT_avg`, `rps_max`,
  `rps_avg`, `outdoor_temp`, `buh_used`, `defrost_used`, `cop_avg`,
  `lwt_avg`, `indoor_temp_avg`
- **Actionable advice** — priority-ordered, category-tagged, included in alerts
- **Setpoint-oscillation detection** — rolling window, change counter against
  a tunable threshold (default 6 changes / 30 min)
- **Bilingual notifications** — EN + NL templates with clear situation +
  advice, selectable per installation
- **Per-group alert toggles** — 5 groups: pendulum / short-cycle / ML /
  setpoint / COP-stooklijn
- **COP stooklijn analysis** — daily advice + bucket table
- **Custom attribute map** — remap non-standard ESPAltherma firmware keys
- **Selected attributes** — restrict processing to opt-in attributes
- **SQLite persistence** — retention, daily rollups, auto-migration 8→11 dim
- **50 entities** — 31 sensors + 19 binary sensors
- **6 services** — reset, export, label, recompute, maintain, test-notify

---

## 3. Requirements

- **Home Assistant** 2026.9 or newer
- **ESPAltherma** publishing attributes on a sensor
- Recommended: outdoor temp attribute + leaving-water temp attribute
  (needed for dT and COP)

---

## 4. Installation

1. Copy `custom_components/daikin_cycle_ml/` into your HA config tree
   (usually `/config/custom_components/daikin_cycle_ml/`).
2. **Restart Home Assistant** (Settings → System → Restart).
   A config-entry reload is **not** enough when the module code changes.
3. **Settings → Devices & Services → Add Integration → "Daikin Cycle ML"**.
4. Follow the 8-step wizard (see next section).

---

## 5. Source sensor & attributes

Daikin Cycle ML reads from a single HA sensor (typically
`sensor.althermasensors` published by ESPAltherma). All processing is based
on the sensor's **attributes**.

Attributes are grouped in three buckets:

### Required attributes

These are always processed. If any is missing, the `missing_attrs` repair
is raised and cycle detection may fail.

| Attribute | Purpose |
|---|---|
| `INV frequency (rps)` | Compressor rotation speed → cycle detection |
| `Operation Mode` | Fallback mode source (when `I/U operation mode` absent) |
| `I/U operation mode` | Primary mode source (Heating / Cooling / DHW / Fan Only) |
| `3way valve` | DHW vs heating discrimination |
| `Defrost Operation` | Defrost flag on cycle record |
| `Leaving water temp after BUH (R2T)` | LWT — for dT computation and COP |
| `Inlet water temp (R4T)` | Inlet — for dT computation and COP |
| `Flow sensor (l/min)` | Water flow — for thermal kW computation |
| `Water pump operation` | Pump on/off — for cycle validity |
| `Outdoor air temp (R1T)` | Outdoor temp — for stooklijn bucketing |
| `DHW tank temp (R5T)` | DHW tank temp — for DHW recognition |
| `BUH Step1` | Backup heater step 1 flag |
| `BUH Step2` | Backup heater step 2 flag |

### Recommended attributes

Pre-selected in the wizard. Safe to enable. Improve quality and enable
extra features.

| Attribute | Purpose |
|---|---|
| `Discharge pipe temp.` | Compressor health indicator |
| `Suction pipe temp.` | Refrigerant-side context |
| `INV primary current (A)` | Extra power proxy |
| `Target Cond. Temp.` | Target condensing temp for stooklijn comparison |
| `LW setpoint (main)` | **Required for `setpoint_osc` alert** |
| `DHW setpoint` | DHW setpoint for DHW cycle context |

### Optional attributes

Default off. Enable only if your installation publishes them. Useful for
diagnostics and future features, not required for core detection.

| Attribute | Purpose |
|---|---|
| `Heat exchanger mid-temp.` | Refrigerant mid-stage temp |
| `Liquid pipe temp.(R6T)` | Refrigerant liquid temp |
| `Expansion valve (pls)` | Valve position |
| `Crank case heater 1` | Crank case heater status |
| `Pressure equalizing operation` | Pressure equalisation flag |
| `4 Way Valve 1` | Reversing valve state |
| `Solenoid Valve 1` | Solenoid valve state |
| `Target Evap. Temp.` | Target evaporating temp |
| `RT setpoint` | Room thermostat setpoint |
| `High Pressure` | Refrigerant high-side pressure |
| `Water pressure` | System water pressure |
| `Brine inlet temp.` | Brine-inlet (geothermal only) |
| `Brine outlet temp.` | Brine-outlet (geothermal only) |

**Note on required attributes:** even if you deselect required attributes
in the wizard, they are **always kept** — cycle detection depends on them.
The `selected_attributes` filter only restricts the *optional* set.

### Custom attribute map

If your ESPAltherma firmware uses non-standard attribute names, the wizard
(Model = Custom) offers a JSON mapping:

```json
{
  "INV frequency (rps)": "my_inv_rps",
  "I/U operation mode": "my_iu_mode",
  "Leaving water temp after BUH (R2T)": "my_lwt"
}
```

Left side = standard key, right side = your actual attribute name. The
integration renames your attribute to the standard key before processing,
so all downstream logic sees the canonical names.

**Rules:**
- Must be a valid JSON object (validated at wizard time)
- Empty or missing actual attribute → original is left untouched
- Only affects the keys you list — everything else is untouched

---

## 6. Config flow — step by step

### Setup wizard (8 steps)

After clicking **Add Integration → Daikin Cycle ML**, the wizard walks you
through 8 steps.

#### Step 1 — Source & model

| Field | Type | Default | Notes |
|---|---|---|---|
| **Source sensor** | entity picker | `sensor.althermasensors` | Your ESPAltherma sensor. Must publish the attributes above. |
| **Model** | dropdown | `EPRA12EAV3` | Picks a model profile (defaults for thresholds). Choose **Custom** if your pump is not in the list. |

Available models: `EPRA12EAV3`, `EPRA08EAV3`, `EABH16DA6V`, `EABX16DA6V`, `Custom`.

#### Step 2 — Custom attribute map *(only if Model = Custom)*

Optional JSON textarea. See [Custom attribute map](#custom-attribute-map).

Validation:
- Invalid JSON → error `invalid_json`
- Non-object JSON (e.g. array, number) → same error
- Empty string → accepted, treated as "no map"

#### Step 3 — Selected attributes

Multi-select list. See [Source sensor & attributes](#5-source-sensor--attributes)
for the full list.

- **Recommended** attributes are pre-selected (6 items)
- **Optional** attributes can be added by checking them
- **Required** attributes are always kept regardless of your selection

#### Step 4 — Cycle detection

| Field | Type | Default | Notes |
|---|---|---|---|
| **Compressor RPS threshold** | number | `3` | Compressor is "on" when RPS > this. |
| **Power sensor** | entity picker | *(none)* | Optional. If set, used as fallback when RPS is missing. |
| **Fallback power threshold (W)** | number | `200` | Power above this counts as compressor on. |
| **Indoor temp sensor** | entity picker | *(none)* | Optional. Enables `indoor_temp_avg` in the ML vector. |

#### Step 5 — Pendulum thresholds

| Field | Type | Default | Notes |
|---|---|---|---|
| **Short run threshold (min)** | number | `20` | Cycles shorter than this are flagged. |
| **Short off threshold (min)** | number | `5` | Off-times shorter than this are flagged. |
| **Pendulum cycles per hour** | number | `4` | Triggers hourly pendulum alert. |
| **DHW pendulum cycles per hour** | number | `3` | Triggers DHW-specific pendulum alert. |

#### Step 6 — Quality thresholds

| Field | Type | Default | Notes |
|---|---|---|---|
| **Good run threshold (min)** | number | `45` | Below = quality penalty −30. |
| **Good dT threshold (K)** | number | `5.0` | Below = quality penalty −20. |
| **Good off threshold (min)** | number | `20` | Below = quality penalty −20. |
| **Target cycles per day** | number | `8` | Used in daily rollup advice. |

#### Step 7 — Notifications

| Field | Type | Default | Notes |
|---|---|---|---|
| **Persistent notifications** | boolean | `true` | Show alerts in HA sidebar. |
| **Notify target** | dropdown | *(empty)* | Pick a `notify.*` entity. Empty = no push. |
| **Quiet hours** | boolean | `false` | |
| **Quiet hours start** | time | `22:00` | |
| **Quiet hours end** | time | `07:00` | |

After the wizard, all other notification settings (language, emoji,
action advice, alert groups, status updates) are configured via the
Options menu.

#### Step 8 — Finalize

Review and click **Submit**. The integration starts polling every 30 s.

---

### Options menu (6 screens)

Go to **Settings → Devices & Services → Daikin Cycle ML → Configure**.
A menu with 6 screens opens. Each screen saves **independently** — you
can change one field and go back without losing the rest.

#### 1. Device

Runtime detection parameters.

| Field | Default | Range | Notes |
|---|---|---|---|
| **Compressor RPS threshold** | `3` | 1–100 | Compressor is "on" when RPS > this. |
| **Power sensor** | *(none)* | — | Optional fallback. |
| **Fallback power threshold (W)** | `200` | 10–10000 | |
| **Indoor temp sensor** | *(none)* | — | Enables `indoor_temp_avg` ML dim. |
| **COP sensor** | *(none)* | — | If set, daily COP samples are collected every 10 min. |

#### 2. Pendulum

Thresholds that decide what counts as a "bad" cycle.

| Field | Default | Range | Notes |
|---|---|---|---|
| **Short run threshold (min)** | `20` | 1–240 | |
| **Short off threshold (min)** | `5` | 1–120 | |
| **Pendulum cycles per hour** | `4` | 1–100 | Hourly alert trigger. |
| **Pendulum cycles per day** | `40` | 1–200 | Daily alert trigger. |
| **DHW pendulum cycles per hour** | `3` | 1–20 | |
| **Setpoint oscillation threshold** | `6` | 1–100 | Setpoint changes in window before alert. Default 6 filters normal thermostat tuning. |
| **Setpoint window (min)** | `30` | 5–180 | Rolling window. |
| **Minimum setpoint change (°C)** | `0.5` | 0.1–2.0 (step 0.1) | Filters floating-point noise. |

#### 3. Quality

| Field | Default | Range | Notes |
|---|---|---|---|
| **Good run threshold (min)** | `45` | 1–240 | |
| **Good dT threshold (K)** | `5.0` | 0.5–20 (step 0.5) | |
| **Good off threshold (min)** | `20` | 1–240 | |
| **Target cycles per day** | `8` | 1–100 | |

#### 4. Notifications

| Field | Default | Notes |
|---|---|---|
| **Persistent notifications** | `true` | |
| **Notify target** | *(empty)* | Dropdown of `notify.*` entities from your registry. |
| **Emoji in notifications** | `true` | Prefix with emoji for quick scanning. |
| **Include action advice** | `true` | Append the top advice line to alerts. |
| **Quiet hours** | `false` | |
| **Quiet hours start / end** | `22:00` / `07:00` | Non-critical alerts suppressed. |
| **Alert aggregation (minutes)** | `30` | 1–1440. Dedup window per alert type. |
| **Periodic status updates** | `false` | Opt-in summary. |
| **Status interval (hours)** | `24` | 1–168. |
| **Notification language** | `English` | Dropdown: **English** or **Nederlands**. |
| **Alert: pendulum** | `true` | Hourly + daily pendulum alerts. |
| **Alert: short cycle** | `true` | Short-run + short-off alerts. |
| **Alert: ML anomaly** | `true` | ML anomaly alerts (z-score). |
| **Alert: setpoint oscillation** | `true` | LWT setpoint oscillation alerts. |
| **Alert: COP / heat curve** | `true` | Daily COP + heat-curve advice alerts. |

#### 5. ML

| Field | Default | Notes |
|---|---|---|
| **Adaptive thresholds enabled** | `false` | Opt-in percentile self-learning. |
| **Adaptive min samples** | `20` | Samples before learned thresholds activate. |

#### 6. Maintenance

| Field | Default | Notes |
|---|---|---|
| **Retention enabled** | `true` | |
| **Cycle retention (days)** | `90` | Older cycles rolled into daily_summary. |
| **Alert retention (days)** | `30` | |
| **VACUUM enabled** | `true` | Runs after prune. |

#### Reconfigure

Two paths, accessed via **Settings → Devices & Services → Daikin Cycle ML → Reconfigure**:

- **reconfigure_basic** — change source sensor + model only
- **reconfigure_full** — re-run the full wizard, prefilled with current values

> **Important:** `source_sensor` and `model` live in the config-entry **DATA**
> section, not in OPTIONS. That's why they can only be changed via
> Reconfigure, not via the Options menu.

---

## 7. Entities

### Sensors (31)

| Entity | Unit | Description |
|---|---|---|
| `sensor.daikin_cycle_ml_cycle_state` | — | `idle` / `active` |
| `sensor.daikin_cycle_ml_current_cycle_duration` | min | Current cycle duration |
| `sensor.daikin_cycle_ml_current_cycle_mode` | — | `heating` / `cooling` / `dhw` / `unknown` |
| `sensor.daikin_cycle_ml_current_dt` | K | Live dT (LWT − inlet) |
| `sensor.daikin_cycle_ml_current_rps` | rps | Live compressor speed |
| `sensor.daikin_cycle_ml_last_cycle_duration` | min | Last cycle duration |
| `sensor.daikin_cycle_ml_last_cycle_mode` | — | Last cycle mode |
| `sensor.daikin_cycle_ml_last_cycle_dt_max` | K | Last cycle max dT |
| `sensor.daikin_cycle_ml_last_cycle_quality` | 0–100 | Last cycle quality score |
| `sensor.daikin_cycle_ml_cycles_today` | — | Cycles since midnight |
| `sensor.daikin_cycle_ml_cycles_last_hour` | — | Cycles in the last 60 min |
| `sensor.daikin_cycle_ml_short_runs_today` | — | Cycles below short-run threshold |
| `sensor.daikin_cycle_ml_short_offs_today` | — | Off-times below short-off threshold |
| `sensor.daikin_cycle_ml_short_cycle_ratio` | % | Short cycles / total |
| `sensor.daikin_cycle_ml_avg_cycle_duration_today` | min | Daily average runtime |
| `sensor.daikin_cycle_ml_avg_off_time_today` | min | Daily average off-time |
| `sensor.daikin_cycle_ml_longest_cycle_today` | min | |
| `sensor.daikin_cycle_ml_shortest_cycle_today` | min | |
| `sensor.daikin_cycle_ml_avg_quality_today` | 0–100 | |
| `sensor.daikin_cycle_ml_good_cycles_today` | — | Cycles with quality ≥ 70 |
| `sensor.daikin_cycle_ml_bad_cycles_today` | — | Cycles with quality < 70 |
| `sensor.daikin_cycle_ml_good_cycle_ratio` | % | Good / total |
| `sensor.daikin_cycle_ml_source_age` | s | Seconds since last source update |
| `sensor.daikin_cycle_ml_missing_attrs_count` | — | Required attributes missing |
| `sensor.daikin_cycle_ml_last_sample_age` | s | Seconds since last coordinator tick |
| `sensor.daikin_cycle_ml_coordinator_errors` | — | Cumulative errors |
| `sensor.daikin_cycle_ml_learned_short_run_min` | min | Adaptive threshold (if enabled) |
| `sensor.daikin_cycle_ml_learned_good_off_min` | min | Adaptive threshold (if enabled) |
| `sensor.daikin_cycle_ml_learned_target_cycles_per_day` | — | Adaptive target (if enabled) |
| `sensor.daikin_cycle_ml_stooklijn_advies` | — | `verlaag_lwt_2c` / `verhoog_lwt_2c` / `behoud` / `unknown` |
| `sensor.daikin_cycle_ml_cop_vandaag` | — | Today's average COP |

### Binary sensors (19)

| Entity | Description |
|---|---|
| `binary_sensor.daikin_cycle_ml_compressor_running` | Compressor currently on |
| `binary_sensor.daikin_cycle_ml_pendulum_hourly` | Cycles in last hour ≥ threshold |
| `binary_sensor.daikin_cycle_ml_pendulum_daily` | Cycles today ≥ threshold |
| `binary_sensor.daikin_cycle_ml_short_run` | Last cycle below short-run threshold |
| `binary_sensor.daikin_cycle_ml_short_off` | Off-time below short-off threshold |
| `binary_sensor.daikin_cycle_ml_defrost_active` | Defrost cycle in progress |
| `binary_sensor.daikin_cycle_ml_buh_step1_active` | Backup heater step 1 on |
| `binary_sensor.daikin_cycle_ml_buh_step2_active` | Backup heater step 2 on |
| `binary_sensor.daikin_cycle_ml_dhw_active` | Currently in DHW mode |
| `binary_sensor.daikin_cycle_ml_heating_active` | Currently in heating mode |
| `binary_sensor.daikin_cycle_ml_cooling_active` | Currently in cooling mode |
| `binary_sensor.daikin_cycle_ml_source_stale` | Source sensor not producing fresh data |
| `binary_sensor.daikin_cycle_ml_missing_attrs` | Required attributes missing |
| `binary_sensor.daikin_cycle_ml_setpoint_oscillating` | Setpoint changes ≥ threshold in window |
| `binary_sensor.daikin_cycle_ml_dhw_pendulum` | DHW cycles/h ≥ DHW threshold |
| `binary_sensor.daikin_cycle_ml_high_cycle_rate` | Cycles today above target |
| `binary_sensor.daikin_cycle_ml_cluster_pendulum` | Latest cycle in pendulum cluster |
| `binary_sensor.daikin_cycle_ml_cluster_normal` | Latest cycle in normal cluster |
| `binary_sensor.daikin_cycle_ml_cluster_dhw_like` | Latest cycle in DHW-like cluster |

> **v0.6.0 note:** `heating_active`, `cooling_active` and `dhw_active` were
> permanently `off` in every earlier release due to a case-sensitivity bug
> between `classify_mode()` (lowercase) and `OP_MODE_*` constants
> (capitalized). Fixed in v0.6.0.

---

## 8. Services

All services live under the `daikin_cycle_ml.` domain.

### `daikin_cycle_ml.reset_counters`

Reset daily counters (cycles_today, short_runs_today, etc).

| Field | Type | Required | Description |
|---|---|---|---|
| — | — | — | No parameters. |

### `daikin_cycle_ml.export_cycles`

Export cycle history as JSON or CSV.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `days` | int | no | `30` | Number of days to export |
| `format` | string | no | `json` | `json` or `csv` |
| `path` | string | no | `/config/daikin_cycles_export.json` | Output path |

### `daikin_cycle_ml.label_cycle`

Attach a user label to a cycle (analytics).

| Field | Type | Required | Description |
|---|---|---|---|
| `cycle_id` | int | yes | Cycle row ID from the DB |
| `label` | string | yes | Free-form label |

### `daikin_cycle_ml.recompute_baseline`

Rebuild the MultiBaseline from stored cycle history. Useful after a
migration or a big config change.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `days` | int | no | `30` | Lookback window |

### `daikin_cycle_ml.run_maintenance`

Run retention prune + optional VACUUM immediately (scheduled at 03:00
otherwise).

| Field | Type | Required | Description |
|---|---|---|---|
| — | — | — | No parameters. |

### `daikin_cycle_ml.send_test_notification`

Send a test notification to the configured target. Useful for verifying
that your `notify.*` entity works.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entry_id` | string | no | auto-resolved if 1 entry | Config entry ID |
| `message` | string | no | `Daikin Cycle ML: test notification` | Message body |
| `target` | string | no | from options | Override notify target |

**Response:** `{"ok": bool, "target": str, "message": str}`.

Example:

```yaml
service: daikin_cycle_ml.send_test_notification
data:
  message: "Hello from Daikin Cycle ML"
```

---

## 9. Alerts & notifications

Alerts are dispatched on cycle-close (or on a schedule for daily/weekly
ones). Each alert has:

- a **severity** (`info` / `watch` / `warning` / `critical`)
- a **group** (`pendulum` / `short_cycle` / `ml` / `setpoint` / `cop_stooklijn`)
- a **dedup key** (aggregation window, default 30 min)
- a **language** (EN or NL, set via Options)

The message body is a **full sentence**: what happened → why → what to do.

### Alert matrix

| Alert | Trigger | Severity | Group | Dedup |
|---|---|---|---|---|
| `pendulum` (hourly) | cycles/h ≥ target | warning | pendulum | 30 min |
| `pendulum` (daily) | cycles today ≥ target | warning | pendulum | 30 min |
| `short_run` | last cycle < threshold | warning | short_cycle | 30 min |
| `short_off` | off-time < threshold | warning | short_cycle | 30 min |
| `ml_anomaly` | z-score ≥ watch (2.0) | warning | ml | 30 min |
| `setpoint_osc` | N changes in window | warning | setpoint | 30 min |
| `cop_low` | daily COP < 2.5 | warning | cop_stooklijn | 20 h |
| `stooklijn_advies` | daily heat-curve advice | warning | cop_stooklijn | 20 h |
| `status_update` | opt-in periodic | info | — | interval |

### Message format (EN example)

```
🔁 Pendulum detected (hourly)
5 cycles in the last hour (target ≤ 4).
💡 Widen thermostat hysteresis, or lower the heat curve so cycles run longer.
```

```
🎯 LWT setpoint oscillating
Changed 7× in the last 30 min (threshold 6).
💡 Lock the LWT setpoint, or increase thermostat hysteresis so the heat pump can settle.
```

### Message format (NL example)

```
🔁 Pendelen gedetecteerd (per uur)
5 cycli in het laatste uur (doel ≤ 4).
💡 Verhoog de thermostaat-hysterese, of verlaag de stooklijn zodat cycli langer duren.
```

### Delivery channels

Each alert is delivered through **two independent channels**:

1. **Persistent notification** — always shown in the HA sidebar (if enabled
   via `persistent_enabled`)
2. **Notify target** — configurable `notify.*` entity or legacy service

Both channels are attempted independently. A failure in one does not block
the other.

### Quiet hours

Non-critical alerts are suppressed during the quiet-hours window (default
`22:00` → `07:00`). The window is **wraparound-aware** — `22:00 → 07:00`
correctly covers the entire night.

### Per-group toggles

Five groups can be silenced independently in **Options → Notifications**:

- `alert_group_pendulum`
- `alert_group_short_cycle`
- `alert_group_ml`
- `alert_group_setpoint`
- `alert_group_cop_stooklijn`

All default to `true` (enabled).

### Emoji

Emoji are added per alert-type (falling back to severity). Disable with
**Emoji in notifications** = `false`.

| Alert type | Emoji |
|---|---|
| `pendulum` | 🔁 |
| `short_run` | ⏱ |
| `short_off` | 💤 |
| `ml_anomaly` | 🧠 |
| `setpoint_osc` | 🎯 |
| `cop_low` / `stooklijn_advies` | 📉 |
| `status_update` | 📊 |

---

## 10. ML pipeline

Every closed cycle becomes an **11-dimensional feature vector**:

```
[0] duration_s
[1] dT_max
[2] dT_avg
[3] rps_max
[4] rps_avg
[5] outdoor_temp
[6] buh_used
[7] defrost_used
[8] cop_avg              ← added in v0.5.0 (batch 14c)
[9] lwt_avg              ← added in v0.5.0
[10] indoor_temp_avg     ← added in v0.5.0
```

Missing values are filled with `0.0` (JSON-safe, no NaN).

The vector feeds three self-learning layers:

### 1. MultiBaseline

Per-mode **Exponentially Weighted Moving Average** with Welford-style
variance. Produces z-scores per dimension for anomaly detection.

- Persisted to `model_state['baseline_state']`
- Updated on every cycle close
- **Dim-guarded**: if a legacy 8-dim baseline is loaded, it is reset to
  avoid mismatched vectors

### 2. AdaptiveThresholds

Per-mode percentile. Learns `short_run` and `good_off` thresholds from your
real cycles. **Opt-in** via `adaptive_thresholds_enabled`.

- Requires `adaptive_min_samples` cycles (default 20) before activating
- Persisted to `model_state['adaptive_thresholds']`
- Exposed via `sensor.learned_*`

### 3. K-means clustering

Weekly retrain over the last 7 days → 3 centroids. See next section.

No labels. No supervised training. Everything is self-learning.

---

## 11. Clustering

Weekly k-means over the last 7 days produces **3 centroids**.

New cycles are assigned via **nearest-centroid** and stored as `cluster_id`.

Cluster labels are auto-derived from centroid properties:

- **shortest mean duration** → `cluster_pendulum`
- **highest `dT_max`** → `cluster_dhw_like`
- **rest** → `cluster_normal`

Three binary sensors expose membership for the **latest** cycle:

- `binary_sensor.daikin_cycle_ml_cluster_pendulum`
- `binary_sensor.daikin_cycle_ml_cluster_normal`
- `binary_sensor.daikin_cycle_ml_cluster_dhw_like`

Persisted to `model_state['kmeans_state']`.

---

## 12. Scheduled jobs

| When | What |
|---|---|
| Every 30 s | Poll sensor, detect cycle transitions, dispatch alerts |
| Every 10 min | Collect COP sample (if COP sensor configured) |
| Every 1 h | Refresh stooklijn cache + daily COP counters |
| Every 6 h | Persist baseline + adaptive state to `model_state` |
| Daily 03:00 | Retention rollup + prune + optional VACUUM |
| Daily 04:00 | Stooklijn analysis (force refresh + notify) |
| Sunday 04:00 | K-means retrain over last 7 days |
| Every N h (opt-in) | Send status summary via `build_status_message` |

---

## 13. Retention & storage

- **Storage**: `/config/.storage/daikin_cycle_ml.db` (SQLite)
- **Cycle retention**: `cycle_retention_days` (default **90**)
  — older cycles are rolled up into `daily_summary` before pruning
- **Alert retention**: `alert_retention_days` (default **30**)
- **Features**: orphan-pruned via FK
- **VACUUM**: optional, runs after prune
- **Migration**: automatic (8 → 11 dim feature vectors)

---

## 14. Database schema

**7 tables**:

### `cycles` — main table

```
id            INTEGER PRIMARY KEY
start_ts      REAL
end_ts        REAL
duration_s    REAL
mode          TEXT      -- heating / cooling / dhw / unknown
dT_max        REAL
dT_avg        REAL
rps_max       INT
rps_avg       REAL
outdoor_temp  REAL
buh_used      INT
defrost_used  INT
quality_score INT
cluster_id    INTEGER   -- nullable
label         TEXT      -- user-attached
```

### `features` — ML vectors

```
id        INTEGER PRIMARY KEY
cycle_id  INTEGER FK -> cycles(id)
v0..v10   REAL      -- 11 dims
```

### `alerts`

```
id         INTEGER PRIMARY KEY
alert_type TEXT
severity   TEXT
message    TEXT
ts         REAL
notif_id   TEXT
```

### `daily_summary`

```
day            TEXT   -- YYYY-MM-DD
mode           TEXT
cycles         INTEGER
quality_avg    REAL
duration_avg   REAL
PRIMARY KEY (day, mode)
```

### `cop_samples`

```
id            INTEGER PRIMARY KEY
ts            REAL
cop           REAL
lwt           REAL
outdoor       REAL
flow_lmin     REAL
power_stable  INT
```

### `model_state` — key-value persistence

```
key         TEXT PRIMARY KEY
value       TEXT (JSON)
updated_ts  REAL
```

Keys: `baseline_state`, `adaptive_thresholds`, `kmeans_state`,
`last_maintenance_ts`.

### `sqlite_sequence`

SQLite internal.

---

## 15. Troubleshooting

### Binary sensors stay off (`heating_active`, `cooling_active`, `dhw_active`)

- **Fixed in v0.6.0.** If you are on an older version, upgrade.
- If you still see stuck sensors after upgrade, do a **full HA restart**
  (Settings → System → Restart). A config-entry reload is not enough.

### `source_stale` repair is shown

- ESPAltherma is not publishing fresh data.
- Check the ESP device and Wi-Fi.
- The repair resolves automatically when data resumes.

### `missing_attrs` repair is shown

- The source sensor is missing one or more required attributes.
- Verify that ESPAltherma is publishing all fields.
- Or add a custom attribute map in **Options → Device**.

### Alerts are noisy

- Increase **Alert aggregation (minutes)** in **Options → Notifications**.
- Disable one or more alert groups you do not care about.
- Raise **Pendulum cycles per hour** or **per day**.
- Enable **Quiet hours** for overnight suppression.

### Notifications are in the wrong language

- **Options → Notifications → Notification language** → pick EN or NL.

### `setpoint_osc` alert never fires

- Check that the source sensor actually publishes **LW setpoint (main)**.
- Default threshold is **6 changes in 30 minutes** — most installations
  never hit that (which is correct; it means you do not have the problem).

### `cop_vandaag` sensor stays at 0

- You must configure a **COP sensor** in **Options → Device**.
- COP samples are collected every 10 min.

### Database grows too large

- Lower **Cycle retention (days)** in **Options → Maintenance**.
- Ensure `vacuum_enabled` = `true`.
- Manually trigger `daikin_cycle_ml.run_maintenance` once.

---

## 16. Testing

- **987 tests**, **95.65% coverage** (as of v0.6.0)
- Framework: `pytest` + `pytest_homeassistant_custom_component`
- Coverage threshold enforced at **95%** in `pyproject.toml`

Per-module coverage (v0.6.0):

| Module | Coverage |
|---|---|
| `const.py` | 100% |
| `binary_sensor.py` | 100% |
| `diagnostics.py` | 100% |
| `repairs.py` | 100% |
| `entity.py` | 100% |
| `engine/cop_analyzer.py` | 100% |
| `engine/quality_scorer.py` | 100% |
| `engine/model_profiles.py` | 100% |
| `engine/timer_health.py` | 100% |
| `ml/features.py` | 100% |
| `ml/multi_baseline.py` | 100% |
| `engine/attribute_reader.py` | 99% |
| `engine/cycle_detector.py` | 99% |
| `ml/baseline.py` | 99% |
| `ml/clustering.py` | 99% |
| `storage/store.py` | 98% |
| `engine/attribute_reader.py` | 99% |
| `ml/adaptive_thresholds.py` | 97% |
| `config_flow.py` | 96% |
| `storage/db.py` | 95% |
| `coordinator.py` | 94% |
| `engine/action_engine.py` | 93% |
| `sensor.py` | 93% |
| `services.py` | 92% |
| `engine/notification_engine.py` | 89% |
| `__init__.py` | 82% |

Run locally:

```bash
PYTHONPATH=/workspace pytest -q
```

---

## 17. Out of scope

- Cost tracking / € calculations
- Setpoint writes
- HACS publication
- Supervised ML (label-based training)
- Weather forecast integration
- ML feature vector 14 dims (planned for v0.7.0)
- Brine circuits (EPRA12 is split air-water)

---

## License

See [LICENSE](LICENSE).