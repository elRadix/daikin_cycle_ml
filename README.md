# Daikin Cycle ML

Home Assistant integration that detects compressor cycles, classifies
pendulum behaviour, self-learns per mode, and advises on Daikin Altherma
heat pumps. **Local-only ML, no cloud.**

[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)](https://github.com/elRadix/daikin_cycle_ml/releases/tag/v1.5.0)
[![Tests](https://img.shields.io/badge/tests-1740-brightgreen.svg)](#19-testing)
[![Coverage](https://img.shields.io/badge/coverage-100.00%25-brightgreen.svg)](#19-testing)
[![Ruff](https://img.shields.io/badge/ruff-clean-brightgreen.svg)](https://github.com/astral-sh/ruff)
[![Pylint](https://img.shields.io/badge/pylint-10.00%2F10-brightgreen.svg)](https://pylint.readthedocs.io/)
[![mypy](https://img.shields.io/badge/mypy-strict%200%20errors-brightgreen.svg)](https://mypy-lang.org/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-blue.svg)](https://www.home-assistant.io/)
[![IQS](https://img.shields.io/badge/IQS-Bronze%20%2B%20Silver%20%2B%20Gold-orange.svg)](quality_scale.yaml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=elRadix&repository=daikin_cycle_ml&category=integration)

**IoT class:** `calculated` — **Integration type:** `helper`

---

## Showcase

| Simple Card | Heating Curve |
|:---:|:---:|
| [![Daikin Cycle ML - Simple Card](https://raw.githubusercontent.com/elRadix/daikin_cycle_ml/main/dashboard/cards/simple-card/preview.png)](dashboard/cards/simple-card/) | [![Daikin Cycle ML - Heating Curve](https://raw.githubusercontent.com/elRadix/daikin_cycle_ml/main/dashboard/cards/heating-curve/preview.png)](dashboard/cards/heating-curve/) |
| *one-glance overview* | *LWT vs outdoor* |

*One-glance dashboard cards - see [dashboard/](dashboard/) for installation.*

---

## Table of contents

1. [Why](#1-why)
2. [What's new](#2-whats-new)
3. [Version history](#3-version-history)
4. [Features](#4-features)
5. [Requirements](#5-requirements)
6. [Installation](#6-installation)
7. [Source sensor & attributes](#7-source-sensor--attributes)
8. [Config flow — step by step](#8-config-flow--step-by-step)
9. [Entities](#9-entities)
10. [Services](#10-services)
11. [Automations & recipes](#11-automations--recipes)
12. [Alerts & notifications](#12-alerts--notifications)
13. [ML pipeline](#13-ml-pipeline)
14. [Clustering](#14-clustering)
15. [Scheduled jobs](#15-scheduled-jobs)
16. [Retention & storage](#16-retention--storage)
17. [Database schema](#17-database-schema)
18. [Integration Quality Scale](#18-integration-quality-scale)
19. [Testing](#19-testing)
20. [Continuous integration](#20-continuous-integration)
21. [Troubleshooting](#21-troubleshooting)
22. [Out of scope](#22-out-of-scope)

---

## 1. Why

Pendelen (short-cycling) is the #1 cause of reduced COP and extra wear on
Daikin Altherma heat pumps. Existing HA integrations do not detect it,
because they look at temperature or power — not at the actual compressor
runtime pattern.

Daikin Cycle ML watches the ESPAltherma sensor stream, detects every
compressor cycle (start → run → stop), scores it, learns what "normal"
looks like for **your** installation per mode (Heating / Cooling / DHW),
and warns you when patterns drift. Since v1.5.0 it also **advises a
dynamic Leaving-Water-Temperature step (1–3 °C)** versus the current LWT
setpoint, with comfort guardrails.

No cloud. No external API. Everything runs inside your Home Assistant box.

---

## 2. What's new

### v1.5.0 — Dynamic LWT step

- **Dynamic LWT step 1–3 °C** — advice is no longer hardcoded at "2 °C".
  The `heating_curve_advice` sensor now emits a `step_c` attribute between
  `LWT_STEP_MIN` (1.0) and `LWT_STEP_MAX` (3.0), scaled to the delta
  between measured LWT and target.
- **Setpoint comparison** — advice is computed against
  `LW setpoint (main)` (`ATTR_LW_SETPOINT`) instead of the last bucket
  sample, closing the "advice ignores what the unit was told to do" gap.
- **Comfort dual-loop (min + max)** — a min (comfort floor) and max
  (comfort ceiling) slider drive a two-sided guard: never advise lowering
  below the floor, never advise raising above the ceiling.
- **Tracking-error dampening** — when the unit is measurably behind the
  setpoint (`LWT_TRACKING_TOLERANCE = 1.5 °C`), the suggested step is
  reduced to avoid over-correction.
- **8 new attributes** on `heating_curve_advice`: `state_label`, `step_c`,
  `delta_c`, `huidige_setpoint`, `doel_setpoint`, `tracking_error`,
  `comfort_cap`, plus extended `reason` codes.
- **Canonical EN states** — `no_data` / `keep` / `lower_lwt` / `raise_lwt` /
  `unknown`.
- **Two new OptionsFlow sliders** — `comfort_min_c` (15–22 °C, default 20)
  and `comfort_max_c` (22–28 °C, default 24).
- **New constants** — `K_EMIT_DEFAULT`, `LWT_STEP_MIN`, `LWT_STEP_MAX`,
  `LWT_TRACKING_TOLERANCE`, `COMFORT_TOLERANCE`, `DEFAULT_COMFORT_MIN_C`,
  `DEFAULT_COMFORT_MAX_C`.
- **Banker's-rounding fix** — `round(2.5) = 2` corrected to `int(x + 0.5)`
  for integer step labels.

### v1.4.x — Hardening

- **v1.4.0** — canonical entity-ID slug renames (`sensor.daikin_cycle_ml_<key>`).
- **v1.4.1** — bug fixes to cycle detector, quality scorer, notification
  engine.
- **v1.4.2** — startup hydrate + quality backfill + `cop_hourly` rollup
  extended to 720 h.
- **v1.4.3** — order-swap hotfix in the maintenance scheduler.
- **v1.4.4** — `_day_key` fix in the hydrate path.
- **v1.4.5** — dashboard card refresh + i18n for cards.

### v1.3.0 — COP analytics

- COP hourly rollup (`cop_hourly`, per-hour per-mode aggregates).
- COP KPI sensors `cop_mean_day` / `cop_mean_week` / `cop_mean_month`.
- REST endpoint `GET /api/daikin_cycle_ml/cop_hourly`.
- `sensor.cop_curve_recent` (48 h window, recorder-safe).
- `daikin_cycle_ml.export_cop_hourly` service.

---

## 3. Version history

| Version | Date | Highlights |
|---|---|---|
| **v1.5.0** | 2026-10-03 | Dynamic LWT step + comfort dual-loop + setpoint comparison |
| v1.4.5 | 2026-10-03 | Dashboard cards refresh + card i18n |
| v1.4.4 | 2026-10-02 | `_day_key` hydrate fix |
| v1.4.3 | 2026-10-02 | Order-swap hotfix |
| v1.4.2 | 2026-10-02 | Hydrate + backfill + rollup 720 h |
| v1.4.1 | 2026-10-02 | Cycle/quality/notify fixes |
| v1.4.0 | 2026-09-29 | Entity slug renames + all core features |
| v1.3.0 | 2026-09-26 | COP hourly rollup + KPI sensors + REST endpoint |
| v1.2.x | 2026-09-20 | IQS Silver + Gold |
| v1.1.0 | 2026-09-15 | HACS-compliant layout |
| v1.0.x | 2026-09-10 | Initial release |

---

## 4. Features

- **Cycle detection** — RPS threshold + optional power-sensor fallback
- **Water pump guard** — skips cycles where the pump is off
- **8 pendulum patterns** — per mode (Heating / Cooling / DHW), hourly + daily
- **Quality score 0–100** per cycle (runtime, dT, off-time, BUH, defrost)
- **thermal_kW per cycle** — computed from flow × 4.18 × dT
- **COP hourly rollup** — 6 h scheduler aggregates `cop_samples` into
  `cop_hourly` (per-hour per-mode: mean/p10/p50/p90/std, lwt_mean,
  outdoor mean/min/max, flow_mean)
- **COP KPI sensors** — `cop_today`, `cop_mean_day`, `cop_mean_week`,
  `cop_mean_month` (heating-weighted mean, all-mode breakdown as attribute)
- **COP curve REST endpoint** —
  `GET /api/daikin_cycle_ml/cop_hourly?days=N&mode=X` (auth required,
  1–365 days)
- **COP curve sensor** — `cop_curve_recent` (48 h window, ~8 KB attrs,
  recorder-safe for ApexCharts)
- **Export COP hourly** — `daikin_cycle_ml.export_cop_hourly` service
  (json/csv, up to 365 days)
- **Dynamic LWT step 1–3 °C** — see §2
- **Comfort dual-loop (floor + ceiling)** — see §2
- **MultiBaseline** — per-mode EWMA, dim 12, persistent, dim-guarded
- **AdaptiveThresholds** — percentile-based self-learning per mode (opt-in)
- **Weekly k-means clustering** + per-cycle nearest-centroid assignment
- **12-dim feature vector** — see §13
- **Actionable advice** — priority-ordered, category-tagged, included in alerts
- **Setpoint-oscillation detection** — rolling window, tunable threshold
- **Rich sectioned alerts** — aligned rows + severity + mode + advice
- **Bilingual notifications** — EN + NL templates, per installation
- **Per-group alert toggles** — 5 groups: pendulum / short-cycle / ML /
  setpoint / COP-stooklijn
- **Test-notification dropdown** — 10 alert kinds + "all alerts" button
- **COP stooklijn analysis** — daily advice + bucket table, DHW-aware,
  48-hour recency window
- **Custom attribute map** — remap non-standard ESPAltherma firmware keys
- **SQLite persistence** — retention, daily rollups, schema v14
- **30 entities** — 14 sensors + 15 binary sensors + 1 HA-managed update
  entity
- **7 services** — reset, export, label, recompute, maintain, test-notify,
  export-cop-hourly
- **5 repair issues** — source stale, missing attrs, DB corrupt,
  notify fail, migration fail
- **HA-compliant** — 8-step wizard, `OptionsFlowWithReload`, 8-screen menu
- **HACS-installable** — Custom repository, no workarounds
- **IQS Bronze + Silver + Gold**
- **6 CI workflows** — Ruff, Pylint, Coverage, Mypy (strict),
  HACS Validation, Hassfest

---

## 5. Requirements

- **Home Assistant** 2026.9.0 or newer
- **Python** 3.14 (matches HA 2026.9 baseline)
- **ESPAltherma** publishing attributes on a sensor
- Recommended: outdoor temp attribute + leaving-water temp attribute
  (needed for dT and COP)

---

## 6. Installation

### 6.1 Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=elRadix&repository=daikin_cycle_ml&category=integration)

1. Install [HACS](https://hacs.xyz/docs/setup/download) if you haven't already.
2. In Home Assistant, go to **HACS → Integrations → (three dots, top right)
   → Custom repositories**.
3. Add repository URL `https://github.com/elRadix/daikin_cycle_ml` with
   category **Integration**.
4. Click **Add** → find **Daikin Cycle ML** in the list → **Download**.
5. **Restart Home Assistant** (Settings → System → Restart).
6. **Settings → Devices & Services → Add Integration → "Daikin Cycle ML"**.
7. Follow the 8-step wizard (§8).

### 6.2 Manual installation

1. Copy `custom_components/daikin_cycle_ml/` into your HA config tree
   (usually `/config/custom_components/daikin_cycle_ml/`).
2. **Restart Home Assistant** (Settings → System → Restart).
   A config-entry reload is **not** enough when the module code changes.
3. **Settings → Devices & Services → Add Integration → "Daikin Cycle ML"**.
4. Follow the 8-step wizard (§8).

> **Upgrading from v1.0.x?** v1.1.0 restructured the repository to the
> HACS-compliant layout. If you installed manually before, replace your
> existing `/config/custom_components/daikin_cycle_ml/` with the new
> contents. Your configuration, entities and database are preserved.

---

## 7. Source sensor & attributes

Daikin Cycle ML reads from a single HA sensor (typically
`sensor.althermasensors` published by ESPAltherma). All processing is
based on the sensor's **attributes**.

### Required attributes (13)

Always processed. If any is missing, the `missing_attrs` repair is raised
and cycle detection may degrade.

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
| **LW setpoint (main)** | **Required for v1.5.0 LWT-advice + setpoint_osc alert** |
| DHW setpoint | DHW setpoint for DHW cycle context |

> **LW setpoint (main) is strongly recommended.** Without it, the
> `heating_curve_advice` sensor falls back to legacy sample-vs-bucket
> comparison and cannot emit `huidige_setpoint` / `doel_setpoint`.

### Optional attributes

Default off. Enable only if your installation publishes them.

Heat exchanger mid-temp., Liquid pipe temp. (R6T), Expansion valve (pls),
Crank case heater 1, Pressure equalizing operation, 4 Way Valve 1,
Solenoid Valve 1, Target Evap. Temp., RT setpoint, High Pressure,
Water pressure, Brine inlet temp., Brine outlet temp.

> **Note on required attributes:** even if you deselect required attributes
> in the wizard, they are **always kept** — cycle detection depends on them.

### Custom attribute map

If your ESPAltherma firmware uses non-standard attribute names, the wizard
(Model = **Custom**) offers a JSON mapping. Left = standard key, right =
your actual attribute name. The integration renames your attribute to the
standard key before processing.

Rules:

- Valid JSON object (validated at wizard time)
- Empty or missing actual attribute → original is left untouched
- Only affects the keys you list

Example:

```json
{
  "INV frequency (rps)": "my_rps",
  "Leaving water temp after BUH (R2T)": "my_lwt"
}
```

---

## 8. Config flow — step by step

### 8.1 Setup wizard (8 steps)

Flow:

```
user → model_custom (conditional) → attributes (check)
     → cycle → pendulum → quality → notifications → finalize
```

#### Step 1 — `user` (Source & model)

| Field | Type | Default | Notes |
|---|---|---|---|
| `source_sensor` | entity picker | `sensor.althermasensors` | Your ESPAltherma sensor |
| `model` | dropdown | `EPRA12EAV3` | Or `Custom` for non-standard pumps |

Available models: `EPRA12EAV3`, `EPRA08EAV3`, `EABH16DA6V`,
`EABX16DA6V`, `Custom`.

#### Step 2 — `model_custom` *(only shown when Model = Custom)*

| Field | Type | Notes |
|---|---|---|
| `custom_attribute_map` | JSON textarea | See §7 |

Validated at wizard time. Invalid JSON → inline error, wizard does not
advance.

#### Step 3 — `attributes` (warning-only)

Shows how many of the 13 core attributes are present on the selected
source sensor. Missing ones are listed but do **not** block the wizard.
You can proceed and fix later.

#### Step 4 — `cycle` (Cycle detection)

| Field | Default | Range | Notes |
|---|---|---|---|
| `compressor_rps_threshold` | 3 | 1–100 | Compressor considered "on" when RPS > this |
| `power_sensor_entity` | (none) | entity | Optional power-based fallback |
| `fallback_power_threshold_w` | 200 | 10–10000 | Used when RPS missing |
| `indoor_temp_sensor` | (none) | entity | Enables `indoor_temp_avg` in ML vector |

#### Step 5 — `pendulum` (Pendulum thresholds)

| Field | Default | Range |
|---|---|---|
| `short_run_threshold_min` | 20 | 1–240 |
| `short_off_threshold_min` | 5 | 1–120 |
| `pendulum_cycles_per_day` | 40 | 1–200 |
| `dhw_pendulum_cycles_per_hour` | 3 | 1–20 |

#### Step 6 — `quality` (Quality thresholds)

| Field | Default | Range |
|---|---|---|
| `good_run_threshold_min` | 45 | 1–240 |
| `good_dt_threshold_k` | 5.0 | 0.1–20.0 (step 0.1) |
| `good_off_threshold_min` | 20 | 1–240 |
| `target_cycles_per_day` | 8 | 1–100 |

#### Step 7 — `notifications` (Wizard-basic notifications)

| Field | Default |
|---|---|
| `persistent_enabled` | `true` |
| `notify_service` | (empty) |
| `quiet_hours_enabled` | `false` |
| `quiet_hours_start` | `22:00` |
| `quiet_hours_end` | `07:00` |

> Full notification configuration (alert groups, language, emoji, action
> advice, status updates, aggregation window) is available in the Options
> menu, screen 5 — see §8.2.

#### Step 8 — `finalize`

Review screen. Submit → integration starts polling every 30 seconds.

---

### 8.2 Options menu (8 screens)

Open via **Settings → Devices & Services → Daikin Cycle ML → Configure**.
Each screen saves independently. All number fields have sensible min / max
validators enforced by the UI.

#### Screen 1 — `init` (menu)

Menu options:

```
device
pendulum
quality
notifications
ml
maintenance
test_notification
test_all_notifications
```

#### Screen 2 — `device`

| Field | Default | Range |
|---|---|---|
| `compressor_rps_threshold` | 3 | 1–100 |
| `power_sensor_entity` | (none) | entity |
| `fallback_power_threshold_w` | 200 | 10–10000 |
| `indoor_temp_sensor` | (none) | entity |
| `cop_sensor_entity` | (none) | entity — required for `cop_samples` |
| `comfort_min_c` | 20.0 | 15.0–22.0 (step 0.5) |
| `comfort_max_c` | 24.0 | 22.0–28.0 (step 0.5) |

> `comfort_min_c` is the comfort **floor** (never advise lowering LWT below
> this projected indoor temp). `comfort_max_c` is the comfort **ceiling**
> (never advise raising above). They are independent; the advice engine
> enforces both.

#### Screen 3 — `pendulum`

| Field | Default | Range |
|---|---|---|
| `short_run_threshold_min` | 20 | 1–240 |
| `short_off_threshold_min` | 5 | 1–120 |
| `pendulum_cycles_per_hour` | 4 | 1–100 |
| `pendulum_cycles_per_day` | 40 | 1–200 |
| `dhw_pendulum_cycles_per_hour` | 3 | 1–20 |
| `setpoint_oscillation_threshold` | 6 | 1–100 |
| `setpoint_osc_window_min` | 30 | 5–180 |
| `setpoint_osc_min_delta` | 0.5 | 0.1–2.0 (step 0.1) |

#### Screen 4 — `quality`

| Field | Default | Range |
|---|---|---|
| `good_run_threshold_min` | 45 | 1–240 |
| `good_dt_threshold_k` | 5.0 | 0.1–20.0 (step 0.1) |
| `good_off_threshold_min` | 20 | 1–240 |
| `target_cycles_per_day` | 8 | 1–100 |

#### Screen 5 — `notifications` (16 fields)

| Field | Default | Range / Options |
|---|---|---|
| `persistent_enabled` | `true` | bool |
| `notify_service` | (empty) | dropdown (loaded at runtime) |
| `notify_emoji_enabled` | `true` | bool |
| `action_advice_enabled` | `true` | bool |
| `quiet_hours_enabled` | `false` | bool |
| `quiet_hours_start` | `22:00` | time |
| `quiet_hours_end` | `07:00` | time |
| `alert_aggregation_minutes` | 30 | 1–1440 |
| `status_update_enabled` | `false` | bool |
| `status_update_interval_hours` | 24 | 1–168 |
| `notification_language` | `en` | dropdown: `en`, `nl` |
| `alert_group_pendulum` | `true` | bool |
| `alert_group_short_cycle` | `true` | bool |
| `alert_group_ml` | `true` | bool |
| `alert_group_setpoint` | `true` | bool |
| `alert_group_cop_stooklijn` | `true` | bool |

#### Screen 6 — `ml` (Machine learning)

| Field | Default | Range |
|---|---|---|
| `adaptive_thresholds_enabled` | `false` | bool |
| `adaptive_min_samples` | 20 | 5–500 |

#### Screen 7 — `maintenance`

| Field | Default | Range |
|---|---|---|
| `retention_enabled` | `true` | bool |
| `cycle_retention_days` | 90 | 7–3650 |
| `alert_retention_days` | 30 | 7–3650 |
| `vacuum_enabled` | `true` | bool |

#### Screen 8a — `test_notification`

| Field | Default | Notes |
|---|---|---|
| `alert_kind` | `status_summary` | dropdown — 10 options, see below |
| `ignore_group_filters` | `false` | bool |

Available `alert_kind` options:

```
status_summary
pendulum_hourly
pendulum_daily
short_run
short_off
ml_anomaly
setpoint_osc
cop_low
stooklijn_advies
all_alerts
```

Submits and shows a **preview** of the rendered message. The preview
respects the currently configured language and emoji setting.

#### Screen 8b — `test_all_notifications`

Single submit button. Emits **every** alert kind in one shot — useful for
verifying EN/NL formatting, severity labels and the rich sectioned layout
at once. Ignores per-group filters (uses `ignore_filters=True`
internally).

---

### 8.3 Reconfigure

Two reconfigure paths, available via **Settings → Devices & Services →
Daikin Cycle ML → Reconfigure**:

- `reconfigure_basic` — change `source_sensor` and `model` only.
  Prefilled with current values. Saves to config-entry DATA.
- `reconfigure_full` — re-run the full wizard, all steps prefilled. Use
  this if you want to re-apply default thresholds across the board.

> `source_sensor` and `model` live in the config-entry **DATA**, not
> OPTIONS. That's why they can only be changed via Reconfigure and not via
> the Options menu.

---

## 9. Entities

### 9.1 Sensors (14)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_cycle_state` | — | — | `idle` / `running` / `cooldown` |
| `sensor.daikin_cycle_ml_current_cycle` | — | — | Current cycle mode + duration attribute |
| `sensor.daikin_cycle_ml_last_cycle` | score | — | Last cycle quality + cluster attribute |
| `sensor.daikin_cycle_ml_cycles_today` | — | — | Cycles since midnight |
| `sensor.daikin_cycle_ml_quality_today` | score | — | Average quality today |
| `sensor.daikin_cycle_ml_source_health` | s | DURATION | Seconds since last source update |
| `sensor.daikin_cycle_ml_learned_thresholds` | min | DURATION | Adaptive threshold (if enabled) |
| `sensor.daikin_cycle_ml_thermal_power_live` | kW | POWER | Live thermal power (flow × 4.18 × dT / 60) |
| `sensor.daikin_cycle_ml_heating_curve_advice` | — | — | LWT advice with dynamic step (see §9.3) |
| `sensor.daikin_cycle_ml_cop_today` | COP | — | Today's simple KPI + baseline loss % |
| `sensor.daikin_cycle_ml_cop_mean_day` | COP | — | Today's heating-weighted mean COP |
| `sensor.daikin_cycle_ml_cop_mean_week` | COP | — | Rolling 7-day mean COP |
| `sensor.daikin_cycle_ml_cop_mean_month` | COP | — | Rolling 30-day mean COP |
| `sensor.daikin_cycle_ml_cop_curve_recent` | COP | — | 48 h window; recorder-safe (~8 KB attrs) |

Cluster membership: `state_attr('sensor.daikin_cycle_ml_last_cycle', 'cluster')`.

### 9.2 Binary sensors (15)

| Entity | Device class | Description |
|---|---|---|
| `compressor_running` | RUNNING | Compressor currently on |
| `pendulum_hourly` | PROBLEM | Cycles/h ≥ threshold |
| `pendulum_daily` | PROBLEM | Cycles/day ≥ threshold |
| `short_run` | PROBLEM | Last cycle < short-run threshold |
| `short_off` | PROBLEM | Off-time < short-off threshold |
| `defrost_active` | RUNNING | Defrost in progress |
| `buh_active` | HEAT | BUH active (attr: `step` = `0` / `1` / `2`) |
| `dhw_active` | — | Currently in DHW mode |
| `heating_active` | HEAT | Currently in heating mode |
| `cooling_active` | COLD | Currently in cooling mode |
| `source_stale` | PROBLEM | Source sensor not fresh |
| `missing_attributes` | PROBLEM | Required attributes missing |
| `setpoint_oscillating` | PROBLEM | Setpoint changes ≥ threshold |
| `dhw_pendulum` | PROBLEM | DHW cycles/h ≥ DHW threshold |
| `high_cycle_rate` | PROBLEM | Cycles/h > 1.5 × target |

### 9.3 `heating_curve_advice` — state & attributes

**States (canonical EN):**

| State | Meaning |
|---|---|
| `no_data` | No recent heating samples, or DHW active |
| `keep` | Advice is "no change" — delta within deadband |
| `lower_lwt` | Lower LWT setpoint by `step_c` °C |
| `raise_lwt` | Raise LWT setpoint by `step_c` °C |
| `unknown` | Insufficient confidence / sensor unavailable |

**Attributes:**

| Attribute | Type | Meaning |
|---|---|---|
| `huidige_lwt` | float | Current measured LWT (°C) |
| `optimale_lwt` | float | Best-COP LWT for the current bucket (°C) |
| `besparing_cop_pct` | float | Estimated COP saving if applied (%) |
| `comfort_impact` | float | Projected indoor-temp impact (°C) |
| `betrouwbaarheid` | float | 0.0–1.0 confidence |
| `bucket` | str | Outdoor bucket (`-10-`, `-10--8`, ..., `18-20`, `20+`) |
| `samples` | int | Samples in the current bucket only |
| `buckets` | dict | Full bucket summary table |
| `state_label` | str | Localized label (EN or NL) with step substituted |
| `step_c` | float | Recommended step (1.0–3.0) |
| `delta_c` | float | `huidige_lwt − optimale_lwt` |
| `huidige_setpoint` | float | Current LWT setpoint from source sensor |
| `doel_setpoint` | float | Suggested new LWT setpoint (`huidige_setpoint ± step_c`) |
| `tracking_error` | float | LWT − setpoint (positive = unit ahead) |
| `comfort_cap` | str | `floor` / `ceiling` / `ok` / `unavailable` |
| `reason` | str | Machine-readable reason code (see below) |

**Reason codes (EN):**

```
no_recent_heating
dhw_active
within_deadband
comfort_floor_reached
comfort_ceiling_reached
unit_tracking_behind
low_confidence
no_indoor_sensor
```

### 9.4 Auto-generated entities (1)

| Entity | Purpose |
|---|---|
| `update.daikin_cycle_ml_update` | HA-managed update entity for the HACS-tracked repo. Not part of the integration's own sensor surface. |

---

## 10. Services

All under `daikin_cycle_ml`.

### 10.1 `reset_counters`

Reset daily counters. No parameters.

### 10.2 `export_cycles`

| Field | Type | Default |
|---|---|---|
| `days` | int | 30 |
| `format` | string | `json` (or `csv`) |
| `path` | string | `/config/daikin_cycles_export.json` |

### 10.3 `label_cycle`

| Field | Type | Required |
|---|---|---|
| `cycle_id` | int | yes |
| `label` | string | yes |

### 10.4 `recompute_baseline`

| Field | Type | Default |
|---|---|---|
| `days` | int | 30 |

### 10.5 `run_maintenance`

No parameters. Runs retention prune + optional VACUUM.

### 10.6 `export_cop_hourly`

| Field | Type | Default |
|---|---|---|
| `days` | int | 30 |
| `format` | string | `json` (or `csv`) |
| `path` | string | `/config/daikin_cop_hourly_export.json` |

### 10.7 `send_test_notification`

| Field | Type | Default |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `message` | string | `Daikin Cycle ML: test notification` |
| `target` | string | from options |

**Response:** `{"ok": bool, "target": str, "message": str}`.

Example:

```yaml
service: daikin_cycle_ml.send_test_notification
data:
  message: "Hello from Daikin Cycle ML"
```

---

## 11. Automations & recipes

> **Scope note.** Daikin Cycle ML is **read-only** toward your heat pump.
> It never writes setpoints. All recipes below are user-side automations
> that consume the integration's sensors. Use at your own risk; test
> thoroughly. `climate.set_temperature` targets are examples — replace
> with your actual thermostat entity.

### 11.1 Notify on LWT advice change

Fires whenever `heating_curve_advice` transitions **into** a lower/raise
state. Uses the localized `state_label` for the message body.

```yaml
alias: "Daikin: LWT advice → notify"
mode: single
trigger:
  - platform: state
    entity_id: sensor.daikin_cycle_ml_heating_curve_advice
    to:
      - "lower_lwt"
      - "raise_lwt"
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                    'betrouwbaarheid') | float(0) >= 0.6 }}
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Daikin LWT advice"
      message: >-
        {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                      'state_label') }}
        — setpoint {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                                 'huidige_setpoint') }}
        → {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                        'doel_setpoint') }} °C
        (reason: {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                               'reason') }})
```

### 11.2 Log every step change to the Logbook

Useful for tracking advice convergence across days.

```yaml
alias: "Daikin: log LWT step changes"
mode: queued
trigger:
  - platform: state
    entity_id: sensor.daikin_cycle_ml_heating_curve_advice
    attribute: step_c
action:
  - service: logbook.log
    data:
      name: "Daikin LWT"
      message: >-
        {{ trigger.to_state.state }}
        | step {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                             'step_c') }} °C
        | tracking {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                                 'tracking_error') }} °C
        | cap {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                            'comfort_cap') }}
```

### 11.3 Daily LWT advice summary

Delivers a compact daily digest at 20:00 local time.

```yaml
alias: "Daikin: daily LWT summary"
mode: single
trigger:
  - platform: time
    at: "20:00:00"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Daikin daily"
      message: >-
        LWT: {{ states('sensor.daikin_cycle_ml_heating_curve_advice') }}
        ({{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                       'state_label') }})
        · step {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                             'step_c') }} °C
        · bucket {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                               'bucket') }}
        · samples {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                                'samples') }}
        · cycles today {{ states('sensor.daikin_cycle_ml_cycles_today') }}
```

### 11.4 Advisory auto-apply (advanced, opt-in)

**Read the disclaimer above before enabling.** This automation *writes* to
your thermostat. Gate it on high confidence and skip during quiet hours.

```yaml
alias: "Daikin: apply LWT advice (opt-in)"
mode: single
max_exceeded: silent
trigger:
  - platform: state
    entity_id: sensor.daikin_cycle_ml_heating_curve_advice
    to:
      - "lower_lwt"
      - "raise_lwt"
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                    'betrouwbaarheid') | float(0) >= 0.75 }}
  - condition: template
    value_template: >
      {{ not (now().hour >= 22 or now().hour < 7) }}
  - condition: template
    value_template: >
      {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                    'comfort_cap') in ['ok'] }}
action:
  - variables:
      advice: "{{ trigger.to_state.state }}"
      step: "{{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                           'step_c') | float(0) }}"
      current: "{{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                              'huidige_setpoint') | float(0) }}"
      target: >-
        {{ (current - step) if advice == 'lower_lwt'
           else (current + step) if advice == 'raise_lwt'
           else current }}
  - service: climate.set_temperature
    target:
      entity_id: climate.your_daikin_thermostat
    data:
      temperature: "{{ target | round(1) }}"
  - service: logbook.log
    data:
      name: "Daikin auto-apply"
      message: >-
        {{ advice }} step {{ step }} °C
        · {{ current }} → {{ target | round(1) }} °C
```

### 11.5 Comfort ceiling guard

Independent safety net: if the indoor temp rises above your ceiling while
the pump is still heating, notify.

```yaml
alias: "Daikin: comfort ceiling guard"
mode: single
trigger:
  - platform: numeric_state
    entity_id: sensor.your_indoor_temperature
    above: 23.5
    for: "00:30:00"
condition:
  - condition: state
    entity_id: binary_sensor.daikin_cycle_ml_heating_active
    state: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Comfort ceiling reached"
      message: >-
        Indoor > 23.5 °C while heating still active.
        LWT cap: {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                               'comfort_cap') }}
        · advice: {{ states('sensor.daikin_cycle_ml_heating_curve_advice') }}
```

### 11.6 Dashboard template card (LWT advice)

Paste into a Lovelace `markdown` card. Reads only v1.5.0 attributes.

```yaml
type: markdown
title: Daikin LWT advice
content: >-
  **{{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                  'state_label') }}**

  Step: {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                      'step_c') }} °C

  Setpoint: {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                          'huidige_setpoint') }}
  → {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                  'doel_setpoint') }} °C

  Tracking: {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                          'tracking_error') }} °C

  Bucket: {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                        'bucket') }}
  · Samples: {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice',
                           'samples') }}
```

### 11.7 Cycle-event driven: tag DHW cycles in the Logbook

Useful for cross-referencing DHW activity against LWT advice.

```yaml
alias: "Daikin: tag DHW cycles"
mode: queued
max_exceeded: silent
trigger:
  - platform: state
    entity_id: sensor.daikin_cycle_ml_last_cycle
action:
  - condition: template
    value_template: >
      {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'mode') == 'dhw' }}
  - service: logbook.log
    data:
      name: "Daikin DHW cycle"
      message: >-
        duration {{ state_attr('sensor.daikin_cycle_ml_last_cycle',
                               'duration_min') }} min
        · quality {{ states('sensor.daikin_cycle_ml_last_cycle') }}
        · dT {{ state_attr('sensor.daikin_cycle_ml_last_cycle',
                           'dt_avg_k') }} K
```

---

## 12. Alerts & notifications

Every alert is rendered as a **rich sectioned message** in the selected
language (EN or NL).

### 12.1 Structure

```
Daikin Cycle ML — Pendulum (hourly)
2026-09-26 14:32
----------------------
Cycles/hour     5
Target          <= 4
Mode            heating
LWT setpoint    35.0 °C
Avg duration    14 min
Outdoor         14.7 °C
----------------------
Advice: increase thermostat hysteresis, or lower the heat curve
so cycles run longer.
```

### 12.2 Alert matrix

| Alert | Trigger | Severity | Group | Dedup |
|---|---|---|---|---|
| `pendulum` (hourly) | cycles/h ≥ target | warning | pendulum | 30 min |
| `pendulum` (daily) | cycles today ≥ target | warning | pendulum | 30 min |
| `short_run` | last cycle < threshold | warning | short_cycle | 30 min |
| `short_off` | off-time < threshold | warning | short_cycle | 30 min |
| `ml_anomaly` | z-score ≥ watch (2.0) | warn / crit | ml | 30 min |
| `setpoint_osc` | N changes in window | warning | setpoint | 30 min |
| `cop_low` | daily COP < 2.5 | warning | cop_stooklijn | 20 h |
| `stooklijn_advies` | daily heat-curve advice | warning | cop_stooklijn | 20 h |
| `status_update` | opt-in periodic | info | — | interval |

### 12.3 Delivery channels

Two independent channels — a failure in one does not block the other:

1. **Persistent notification** — HA sidebar (if `persistent_enabled`)
2. **Notify target** — any `notify.*` entity (entity- or legacy-service)

The `AlertSpec.context` dictionary is passed to `notify.*` payloads but
**not** to `persistent_notification` (HA does not support extra keys
there).

### 12.4 Quiet hours

Non-critical alerts are suppressed inside the window (default
22:00 → 07:00). Wraparound-aware: 22:00 → 07:00 spans midnight
correctly.

### 12.5 Per-group toggles

5 independent groups, configurable in **Options → Notifications**:

```
pendulum
short_cycle
ml
setpoint
cop_stooklijn
```

### 12.6 Emoji

Per alert type, severity as fallback. Disable with **Emoji** = `false`.

| Alert | Emoji prefix |
|---|---|
| pendulum | bell |
| short_run | hourglass |
| short_off | zzz |
| ml_anomaly | brain |
| setpoint_osc | target |
| cop_low / stooklijn_advies | chart-down |
| status_update | chart |

Emoji are only added when `notify_emoji_enabled = true`. Persistent
notifications never receive emoji.

---

## 13. ML pipeline

Every closed cycle becomes a **12-dimensional feature vector**:

```
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
[11] thermal_kw_avg
```

Missing values → `0.0` (JSON-safe).

Three self-learning layers:

### 13.1 MultiBaseline

Per-mode **EWMA** with Welford-style variance. Produces z-scores per
dimension for anomaly detection.

- Persisted to `model_state['baseline_state']`
- Dim-guarded: legacy 8-dim or 11-dim baseline resets on load

### 13.2 AdaptiveThresholds

Per-mode percentile. Learns `short_run` and `good_off` from your real
cycles. **Opt-in** via `adaptive_thresholds_enabled`.

- Requires `adaptive_min_samples` cycles (default 20)
- Persisted to `model_state['adaptive_thresholds']`
- Exposed via `sensor.learned_thresholds`

### 13.3 K-means clustering

Weekly retrain over last 7 days → 3 centroids. See §14.

---

## 14. Clustering

Weekly k-means over the last 7 days → **3 centroids**.

New cycles get `cluster_id` via **nearest-centroid**. Labels are
auto-derived:

- **shortest mean duration** → `cluster_pendulum`
- **highest dT_max** → `cluster_dhw_like`
- **rest** → `cluster_normal`

Exposed as attribute on `sensor.daikin_cycle_ml_last_cycle`.

Persisted to `model_state['kmeans_state']`.

---

## 15. Scheduled jobs

| When | What |
|---|---|
| Every 30 s | Poll sensor, detect cycle transitions, dispatch alerts |
| Every 5 min | Collect COP sample (if COP sensor configured) |
| Every 300 s | Refresh `cop_hourly` (720 h window) |
| Every 1 h | Refresh stooklijn cache + daily COP counters |
| Every 6 h | Persist baseline + adaptive state to `model_state` |
| Daily 03:00 | Retention rollup + prune + optional VACUUM |
| Daily 04:00 | Stooklijn analysis (force refresh + notify) |
| Sunday 04:00 | K-means retrain over last 7 days |
| Every N h (opt-in) | Status summary via `build_status_message` |

---

## 16. Retention & storage

- **Storage**: `/config/.storage/daikin_cycle_ml.db` (SQLite via `aiosqlite`)
- **Cycle retention**: `cycle_retention_days` (default **180**)
- **COP samples retention**: 365 days
- **COP hourly retention**: 365 days
- **Daily rollup retention**: ∞
- **Alert retention**: `alert_retention_days` (default **90**)
- **Features**: orphan-pruned via FK (follows cycles)
- **VACUUM**: optional, runs after prune
- **Migration**: automatic through schema v14

---

## 17. Database schema

**Schema version: 14.** Tables:

### 17.1 `cycles`

```
id              INTEGER PRIMARY KEY
start_ts        REAL UNIQUE
end_ts          REAL
duration_s      REAL
mode            TEXT      -- heating / cooling / dhw / unknown
dT_max          REAL
dT_avg          REAL
rps_max         INT
rps_avg         REAL
outdoor_temp    REAL
buh_used        INT
defrost_used    INT
quality_score   INT       -- 0..100
label           TEXT      -- nullable
cluster_id      INTEGER   -- nullable
cop_avg         REAL      -- nullable
cop_sample_count INTEGER  -- nullable
cop_sample_stdev REAL     -- nullable
cop_confidence  REAL      -- nullable
```

### 17.2 `features`

```
id          INTEGER PRIMARY KEY
cycle_id    INTEGER FK -> cycles(id) UNIQUE
v0..v11     REAL          -- 12-dim vector, one column per dimension
```

### 17.3 `cop_samples`

```
id            INTEGER PRIMARY KEY
ts            REAL
cop           REAL
lwt           REAL
outdoor       REAL
flow_lmin     REAL
power_w       REAL
power_stable  INT
mode          TEXT       -- NULL / dhw / heating / cooling / unknown
data_quality  TEXT
source        TEXT
```

### 17.4 `cop_hourly`

```
ts_hour       REAL
mode          TEXT
n_samples     INT
cop_mean      REAL
cop_p10       REAL
cop_p50       REAL
cop_p90       REAL
cop_std       REAL
lwt_mean      REAL
outdoor_mean  REAL
outdoor_min   REAL
outdoor_max   REAL
flow_mean     REAL
updated_ts    REAL
PRIMARY KEY (ts_hour, mode)
```

### 17.5 `daily_rollup`

```
day           TEXT   -- YYYY-MM-DD
cycles        INTEGER
short_cycles  INTEGER
mean_cop      REAL
mean_quality  REAL
PRIMARY KEY (day)
```

### 17.6 `alerts`

```
id          INTEGER PRIMARY KEY
alert_type  TEXT
severity    TEXT
message     TEXT
ts          REAL
notif_id    TEXT
```

### 17.7 `model_state`

```
key         TEXT PRIMARY KEY
value       TEXT NOT NULL   -- JSON
updated_ts  REAL NOT NULL
```

Keys: `baseline_state`, `adaptive_thresholds`, `kmeans_state`,
`last_maintenance_ts`.

---

## 18. Integration Quality Scale

Status: **Bronze + Silver + Gold**.

See `quality_scale.yaml` for the full status.

### 18.1 Bronze

| Rule | Status |
|---|---|
| config-flow | pass |
| config-flow-test-coverage | pass |
| test-coverage | pass (100%) |
| action-setup | pass |
| runtime-data | pass |
| entity-unique-id | pass |
| has-entity-name | pass |
| brands | pass |
| docs-* (10 rules) | pass |

### 18.2 Silver

| Rule | Status |
|---|---|
| parallel-updates | pass (`PARALLEL_UPDATES = 0`) |
| integration-owner | pass (codeowners) |
| test-coverage | pass |
| config-entry-unloading | pass |
| action-exceptions | pass |
| reauthentication-flow | exempt (local source) |
| entity-unavailable | pass |

### 18.3 Gold

| Rule | Status |
|---|---|
| devices | pass |
| diagnostics | pass |
| repair-issues | pass |
| entity-translations | pass (EN + NL) |
| reconfiguration-flow | pass |
| entity-device-class | pass |
| entity-category | pass |
| discovery | exempt (calculated) |
| dynamic-devices | exempt |
| stale-devices | exempt |

### 18.4 Platinum (not targeted)

| Rule | Status |
|---|---|
| strict-typing | **pass** (`mypy --strict`, 0 errors, 30 modules) |
| py.typed | pass |
| async-dependency | partial (`aiosqlite` is async) |
| inject-websession | exempt |

---

## 19. Testing

- **1737 tests, 0 skipped** — **100.00% coverage** (4676 stmts / 1312 branches)
- Framework: `pytest` + `pytest_homeassistant_custom_component` (phcc)
- **Coverage threshold enforced at 100%** (`--cov-fail-under=100`)
- **Ruff clean** — HA 2026+ config (line-length 100, py314,
  select E/W/F/I/UP/B/SIM/RET/PIE/C4/RUF)
- **Pylint 10.00/10** — `--fail-under=8.0` gate, integration code only
- **`mypy --strict`** — 0 errors, 30 source files, directory-based
- **Import smoke** — 130 modules via `importlib.import_module()`
- **SQLite integrity** — `PRAGMA integrity_check` in CI

Notable test files:

| File | Purpose |
|---|---|
| `test_b13_dynamic_step.py` | 32 cases — LWT step, comfort dual-loop, tracking dampening |
| `test_b13_config_flow.py` | 5 cases — comfort sliders + i18n parity |
| `test_entity_registry_integration.py` | entity_id / unique_id migration on rename |
| `test_v1_4_*_improvements.py` | regression guards for v1.4.x fixes |

Run locally:

```bash
PYTHONPATH=/workspace pytest -q
```

Run ruff:

```bash
ruff check --no-fix --select E,F,W \
  --ignore E501,E402,F401 --exclude tests
```

Run pylint:

```bash
FILES=$(git ls-files '*.py' | grep -v '^tests/' | grep -v '^docs/')
pylint --rcfile=.pylintrc $FILES --fail-under=8.0
```

Run mypy strict (directory-based):

```bash
python3 -m mypy --strict --python-version 3.14 \
  --follow-imports=silent --ignore-missing-imports \
  custom_components/daikin_cycle_ml
```

---

## 20. Continuous integration

Six GitHub Actions workflows run on every push and PR to `main`:

| Workflow | What it checks | Typical duration | File |
|---|---|---|---|
| **Ruff** | Lint (`E,F,W` minus `E501,E402,F401`, excludes tests) | ~5 s | `.github/workflows/ruff.yml` |
| **Pylint** | `--fail-under=8.0` on integration code | ~20 s | `.github/workflows/pylint.yml` |
| **Hassfest** | Official HA integration validator | ~25 s | `.github/workflows/hassfest.yml` |
| **HACS Validation** | `hacs/action@main`, category `integration` | ~40 s | `.github/workflows/hacs.yml` |
| **Mypy** | `mypy --strict`, Python 3.14, HA 2026.9 stubs | ~65 s | `.github/workflows/mypy.yml` |
| **Coverage** | Full suite + `--cov-fail-under=100` | ~135 s | `.github/workflows/coverage.yml` |

All six must pass before a release is tagged.

---

## 21. Troubleshooting

### Binary sensors stay off (`heating_active`, `cooling_active`, `dhw_active`)

- Fixed in v0.6.0. Upgrade if older.
- Still stuck after upgrade → **full HA restart** (not config-entry reload).

### `source_stale` repair is shown

- ESPAltherma not publishing fresh data.
- Check ESP device and Wi-Fi. Repair resolves automatically.

### `missing_attrs` repair is shown

- Source sensor missing one or more required attributes.
- Verify ESPAltherma fields, or add a custom attribute map.

### Alerts are noisy

- Increase **Alert aggregation (minutes)**.
- Disable unneeded alert groups.
- Raise **Pendulum cycles per hour** / **per day**.
- Enable **Quiet hours**.

### Notifications are in the wrong language

- **Options → Notifications → Notification language** → `en` or `nl`.

### `setpoint_osc` alert never fires

- Check source publishes **LW setpoint (main)**.
- Default threshold is **6 changes / 30 min** — most installs never hit it
  (that's the point).

### `heating_curve_advice` stays at `unknown` or `no_data`

- Ensure **LW setpoint (main)** is published by the source sensor — this
  is required for v1.5.0 setpoint-based advice.
- Ensure `indoor_temp_sensor` is configured (used for comfort guards).
- In summer (outdoor > 18 °C) there are no heating samples → `no_data` is
  expected.
- When DHW is active, `no_data` with `reason: dhw_active` is by design —
  DHW cycles are excluded from the LWT advice path.
- Check `reason` attribute — `dhw_active`, `within_deadband`,
  `comfort_floor_reached`, `comfort_ceiling_reached`,
  `unit_tracking_behind`, `low_confidence`, `no_indoor_sensor`.

### `step_c` seems too small

- `tracking_error` dampening reduces the step when the unit is measurably
  behind the setpoint (`LWT_TRACKING_TOLERANCE = 1.5 °C`).
- Low `betrouwbaarheid` also reduces the effective step.
- This is by design — the goal is convergence, not over-correction.

### `cop_mean_day` / `cop_mean_week` / `cop_mean_month` return 0 or unknown

- Configure a **COP sensor** in **Options → Device**.
- Samples collected every 5 min.
- DHW-only days may leave heating-weighted means empty. `cop_today`
  continues to report the simple daily KPI in that case.

### `thermal_power_live` is `unknown` when idle

- Expected. The sensor only produces a value when the compressor is
  running and flow/dT are both valid.

### Database grows too large

- Lower **Cycle retention (days)** in **Options → Maintenance**.
- Ensure `vacuum_enabled = true`.
- Manual: `daikin_cycle_ml.run_maintenance`.

### HACS does not show the integration after adding the custom repository

- Confirm category = **Integration** (not Dashboard, not Template).
- Confirm the repository URL ends with `daikin_cycle_ml` (no `.git`).
- Refresh HACS: **HACS → Integrations → three dots → Reload**.

### `hassfest` CI workflow fails with `KeyError: 'data'`

- Only relevant if you are contributing to the code. Fixed in v1.1.0.
  If you fork: any step with `data_description` must also have a `data`
  block (and vice versa for menu / info-only steps).

### `hassfest` CI workflow fails on manifest key order

- Only relevant if you are contributing. `manifest.json` keys must be
  `domain`, `name`, then **alphabetical**. Verify with:

```bash
python3 -c "import json; k=list(json.load(open('custom_components/daikin_cycle_ml/manifest.json')).keys()); assert k[:2]==['domain','name']; assert k[2:]==sorted(k[2:]); print('OK')"
```

### `hassfest` CI workflow fails on translation placeholders

- Only relevant if you are contributing. Any `{...}` in a translation
  string must be escaped as `{{...}}` unless it is a valid placeholder
  identifier matching `[a-zA-Z_][a-zA-Z0-9_]*`.

---

## 22. Out of scope

- Cost tracking / € calculations
- Setpoint writes (integration is read-only; user automations may write)
- Supervised ML (label-based training)
- Weather forecast integration
- Brine circuits (EPRA12 is split air-water)
- Web UI cycle-explorer
- InfluxDB export (use HA's built-in recorder / InfluxDB integration)
- Webhook push (use HA notify targets)

---

## Support

Daikin Cycle ML is free and open-source, built and maintained in my own
time. No cloud, no accounts, no telemetry — your heat pump data stays on
your Home Assistant instance.

If this integration has helped you cut down pendelen, understand your
cycles, or improve your COP, a coffee is always appreciated and helps
keep the project going.

[![Buy me a coffee](assets/buy-me-a-coffee.png)](https://buymeacoffee.com/elradix)

## License

See [LICENSE](LICENSE).