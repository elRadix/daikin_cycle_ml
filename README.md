# Daikin Cycle ML

Home Assistant integration for Daikin Altherma heat pumps that detects
compressor cycles, scores quality, learns per-mode behaviour, and delivers
**HVAC-grade performance intelligence**: per-mode COP, seasonal SPF/SCOP,
weather-normalized degradation trends, runtime + energy accounting, and
Daikin installer-language curve advice (slope / offset). **Local-only ML,
no cloud.**

[![Version](https://img.shields.io/badge/version-1.7.1-orange.svg)](https://github.com/elRadix/daikin_cycle_ml/releases/tag/v1.7.1)
[![Tests](https://img.shields.io/badge/tests-2231-brightgreen.svg)](#19-testing)
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

| Simple Card | Heating Curve | Daily Summary |
|:---:|:---:|:---:|
| [![Daikin Cycle ML - Simple Card](https://raw.githubusercontent.com/elRadix/daikin_cycle_ml/main/dashboard/cards/simple-card/showcase.png)](dashboard/cards/simple-card/) | [![Daikin Cycle ML - Heating Curve](https://raw.githubusercontent.com/elRadix/daikin_cycle_ml/main/dashboard/cards/heating-curve/preview.png)](dashboard/cards/heating-curve/) | [![Daikin Cycle ML - Daily Summary](https://raw.githubusercontent.com/elRadix/daikin_cycle_ml/main/dashboard/cards/daily-summary/showcase.png)](dashboard/cards/daily-summary/) |
| *one-glance overview* | *LWT vs outdoor* | *8-day cycle history* |

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
23. [Upgrade from 1.5.x](#23-upgrade-from-15x)
24. [Known limitations](#24-known-limitations)

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

### v1.6.2 — Onboarding modes

Patch release that unblocks onboarding for units whose ESPAltherma firmware
does not expose every canonical attribute (issue #25).

**Two attribute modes** (screen 1 of the wizard):

- **Automatic** — canonical ESPAltherma names (previous behaviour).
- **Manual** — map each required attribute to whatever your sensor exposes.

The required set shrinks from 13 to 12: `INV frequency (rps)` is now
optional. Units without a compressor-frequency attribute can onboard in
Automatic mode as long as the remaining 12 keys exist, or in Manual mode
when even those use non-canonical names.

**Manual mapping step** — one text field per required (12) and optional (1)
attribute. Leave a field empty if the canonical name already exists on the
sensor; the wizard auto-fills it. Fields with a name that is not present on
the sensor fail fast with `attribute_not_found`.

**Coordinator fallback** — the custom map is resolved in order:
`options["custom_attribute_map"]` → `data["custom_attribute_map"]` →
`data["attribute_map"]`. Existing entries keep working unchanged.

### v1.6.0 — HVAC Parity

The v1.6.0 release turns the integration from a cycle-detector into a
full HVAC performance platform. Three headline additions:

**1. COP intelligence**

- **Per-mode COP** — 9 new sensors: `cop_heating_day` / `_week` / `_month`,
  plus DHW and cooling variants. `cop_today` now reports **heating-only**
  COP (BREAKING; the previous blended value is preserved on the new
  `cop_combined_today` sensor).
- **SPF / SCOP** — `spf_season`, `spf_ytd`, `scop_running_365d` with a
  configurable `season_start_month` option (default October).
- **Weather-normalized degradation** — `cop_degradation_status`,
  `cop_degradation_week_pct`, `cop_trend_30d`. Outdoor-binning + BUH/defrost
  exclusion isolates hardware wear from weather variation.
- **30-day regression trend** — `analyze_trend()` fits
  `COP ~ a + b * T_outdoor` over 30 days and reports the residual mean as
  %-of-predicted.

**2. Daikin datasheet integration**

- **15 bundled models** (8 EPRA + 7 ERLA) — full EN 14511 reference data in
  `data/datasheets.json`.
- **`hp_specs`** sensor exposes the full datasheet as attributes.
- **`cop_normalized_a7w35`** — live COP normalized to A7/W35 reference.
- **`cop_vs_datasheet_pct`** — live deviation vs spec with on_spec /
  below / critical bands.
- **User datasheet import** — `import_datasheet` and
  `remove_user_datasheet` services, per-entry Store, 3 new Repairs
  (invalid / schema unknown / load failed).
- **MODEL_CHOICES** expanded 5 -> 17.

**3. Runtime + energy observability**

- **Runtime** — `runtime_compressor_today`, `runtime_buh_today`,
  `compressor_starts_today`, `defrost_count_today`,
  `defrost_duration_today`, `duty_cycle_today`.
- **Energy (kWh)** — 6 sensors feeding the HA Energy Dashboard:
  `electrical_energy_{heating,dhw,cooling,total}_today` and
  `thermal_energy_{heating,cooling}_today`.
- **Accumulator persistence** — runtime + energy accumulators survive HA
  restart; persisted 300s-throttled, with an old-day flush before reset.

**Plus:**

- **Daikin installer advice** — `heating_curve_advice` now exposes
  `offset_delta_c` and `slope_delta` alongside `delta_c` / `step_c`,
  matching the Altherma installer menu terminology.
- **OptionsFlow overhaul** — every FORM step is now grouped into
  `section()` blocks, and the notifications step is split into a sub-menu
  with 4 dedicated sub-pages. Top-level menu is now 7 items (was 8).
- **Complete service translations** — all 9 services now have full EN + NL
  translations (previously only 3).

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
| **v1.6.1** | 2026-10-06 | Energy tick fix - standby power no longer booked as heating - unknown-mode fallback removed - 16 new tests |
| **v1.6.2** | 2026-10-06 | Onboarding fix - Automatic/Manual attribute mode - Manual mapping step (issue #25) - 3-way custom_map fallback - REQUIRED split (13->12) + OPTIONAL |
| **v1.6.0** | 2026-10-06 | Per-mode COP + SPF/SCOP - Daikin datasheets + user import - Weather-normalized degradation + 30d trend - Runtime + energy (kWh) - Slope/offset advice - OptionsFlow sections + notifications sub-menu - 45 sensors / 9 services / 8 repairs |
| v1.5.0 | 2026-10-03 | Dynamic LWT step + comfort dual-loop + setpoint comparison |
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

### Cycle detection & quality

- **Cycle detection** — RPS threshold + optional power-sensor fallback
- **Water pump guard** — skips cycles where the pump is off
- **8 pendulum patterns** — per mode (Heating / Cooling / DHW), hourly + daily
- **Quality score 0–100** per cycle (runtime, dT, off-time, BUH, defrost)
- **thermal_kW per cycle** — computed from flow x 4.18 x dT
- **Setpoint-oscillation detection** — rolling window, tunable threshold
- **Actionable advice** — priority-ordered, category-tagged, included in alerts

### COP intelligence

- **Per-mode COP** — 9 sensors: `cop_{heating,dhw,cooling}_{day,week,month}`
- **`cop_today`** — heating-only (v1.6.0 BREAKING; old blended value on
  `cop_combined_today`)
- **COP hourly rollup** — `cop_hourly` table, per-hour per-mode aggregates
  (mean / p10 / p50 / p90 / std, lwt_mean, outdoor mean / min / max, flow_mean)
- **COP KPI sensors** — `cop_mean_day` / `_week` / `_month`, `cop_combined_today`
- **COP curve sensor** — `cop_curve_recent` (48 h window, recorder-safe)
- **REST endpoint** — `GET /api/daikin_cycle_ml/cop_hourly?days=N&mode=X`
- **Export service** — `export_cop_hourly` (json / csv, up to 365 days)

### SPF / SCOP

- **`spf_season`** — seasonal performance factor (configurable start month)
- **`spf_ytd`** — year-to-date
- **`scop_running_365d`** — rolling 365-day SCOP

### Daikin datasheets

- **15 bundled models** — 8 EPRA + 7 ERLA, EN 14511 reference data
- **`hp_specs`** — datasheet attributes + per-model provenance
  (`bundled` / `user`)
- **`cop_normalized_a7w35`** — Carnot-corrected live COP
- **`cop_vs_datasheet_pct`** — deviation vs spec with on_spec / below /
  critical band
- **User import** — `import_datasheet` + `remove_user_datasheet` services,
  per-entry `Store`, 3 Repairs (invalid / schema unknown / load failed)

### Degradation analysis

- **Weather-normalized 7d-vs-7d** — outdoor-binned, BUH/defrost excluded,
  LWT-shift aware
- **30-day regression trend** — `analyze_trend()` on `cop_hourly`
- **3 sensors** — `cop_degradation_status`, `cop_degradation_week_pct`,
  `cop_trend_30d`

### Runtime & energy

- **Compressor runtime** — `runtime_compressor_today` (s)
- **BUH runtime** — `runtime_buh_today` (s), model-based step power
  (`BUH_STEP_KW_BY_MODEL`, 14 models + fallback)
- **Compressor starts** — `compressor_starts_today`
- **Defrost** — `defrost_count_today`, `defrost_duration_today`
- **Duty cycle** — `duty_cycle_today` (%)
- **Electrical energy** — heating / DHW / cooling / total (kWh)
- **Thermal energy** — heating / cooling (kWh)
- **HA Energy Dashboard compatible** — `state_class=total_increasing`,
  `device_class=ENERGY`

### Advice & automation

- **Dynamic LWT step 1–3 °C** — scaled to delta vs setpoint
- **Comfort dual-loop (floor + ceiling)** — see §8.2
- **Slope / offset in Daikin installer language** — `offset_delta_c` and
  `slope_delta` attributes on `heating_curve_advice`
- **Tracking-error dampening** — reduces step when unit lags setpoint

### ML pipeline

- **MultiBaseline** — per-mode EWMA, dim 12, persistent, dim-guarded
- **AdaptiveThresholds** — percentile-based self-learning per mode (opt-in)
- **Weekly k-means clustering** — per-cycle nearest-centroid assignment
- **12-dim feature vector** — see §13
- **Anomaly detection** — z-score vs MultiBaseline

### Configuration & UX

- **Custom attribute map** — remap non-standard ESPAltherma firmware keys
- **8-step setup wizard**
- **OptionsFlow (v1.6.0 overhaul):**
  - Top-level menu: **7 items** (device / pendulum / quality_ml /
    notifications / advanced / test_notification / test_all_notifications)
  - Every FORM step is grouped into `section()` blocks
  - **notifications sub-menu** with 4 dedicated sub-pages:
    Delivery / Quiet hours / Content / Test
  - One-level flatten in `_save()` keeps the stored options schema
    backwards compatible
- **Bilingual notifications** — EN + NL templates
- **Per-group alert toggles** — pendulum / short-cycle / ML / setpoint /
  COP-stooklijn
- **Test-notification dropdown** — 10 alert kinds + "all alerts" button
- **Reconfigure** — change source entity / model without re-adding

### Storage & compliance

- **SQLite persistence** — schema v14, retention, daily rollups
- **9 services** — reset, export, label, recompute, maintain, test-notify,
  export-cop-hourly, import-datasheet, remove-user-datasheet
- **8 repair issues** — source stale, missing attrs, DB corrupt, notify
  fail, migration fail, 3x datasheet
- **IQS Bronze + Silver + Gold**
- **HACS-installable** — Custom repository, no workarounds
- **6 CI workflows** — Ruff, Pylint, Coverage, Mypy strict, HACS,
  Hassfest
- **~2231 tests, 100% branch coverage, mypy strict clean**

### Entities (v1.6.0 total)

- **63 entities** — 45 sensors + 15 binary sensors + 1 update + 2 controls
- **45 sensors** — see §9.1
- **15 binary sensors** — see §9.2

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

### Workaround: onboarding fails with 'Sensor mist vereiste ESPAltherma-attributen'

If the wizard aborts on screen 1 with this message and you cannot proceed:

1. Re-run **Add Integration**.
2. On screen 1, switch **Attribute mode** from `Automatic` to `Manual`.
3. On the next screen, map each canonical attribute to the matching
   attribute name on your sensor (as visible in **Developer Tools -> States**
   under the source entity). Leave a field empty if the canonical name
   already exists on the sensor.
4. If `INV frequency (rps)` is not exposed by your firmware, leave that
   field empty - cycle detection falls back to a current-based heuristic.

If `Manual` mode still fails, please open an issue with the output of
the following snippet, run in **Developer Tools -> Template**:

```
{% for k in states.sensor.althermasensors.attributes.keys() %}
{{ k }}
{% endfor %}
```

That gives us the exact key list for your firmware.


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

Available models (v1.6.0, 17 total): 15 bundled Daikin models
(8 EPRA + 7 ERLA) plus `Custom`. Bundled models get datasheet-backed
COP normalization via `cop_normalized_a7w35`.

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

### 8.2 Options menu (v1.6.0)

Open via **Settings -> Devices & Services -> Daikin Cycle ML -> Configure**.
FORM steps use HA `section()` blocks; each step saves independently.

**Top-level menu (7 items):** device, pendulum, quality_ml, notifications
(sub-menu), advanced, test_notification, test_all_notifications.

#### Screen 1 - device (3 sections)

**Sensors:** `power_sensor_entity` (none), `cop_sensor_entity` (none),
`indoor_temp_sensor` (none).

**Detection:** `compressor_rps_threshold` (3, range 1-100),
`fallback_power_threshold_w` (200, range 10-10000).

**Comfort:** `comfort_min_c` (20.0, range 15-22, step 0.5),
`comfort_max_c` (24.0, range 22-28, step 0.5).

`comfort_min_c` is the floor (never advise lowering LWT below this
projected indoor temp). `comfort_max_c` is the ceiling (never advise
raising above).

#### Screen 2 - pendulum (3 sections)

**Run/off:** `short_run_threshold_min` (20, range 1-240),
`short_off_threshold_min` (5, range 1-120).

**Pendulum:** `pendulum_cycles_per_hour` (4, range 1-100),
`pendulum_cycles_per_day` (40, range 1-200),
`dhw_pendulum_cycles_per_hour` (3, range 1-20).

**Setpoint:** `setpoint_oscillation_threshold` (6, range 1-100),
`setpoint_osc_window_min` (30, range 5-180),
`setpoint_osc_min_delta` (0.5, range 0.1-2.0, step 0.1).

#### Screen 3 - quality_ml (2 sections)

**Quality:** `good_run_threshold_min` (45, range 1-240),
`good_dt_threshold_k` (5.0, range 0.1-20.0, step 0.1),
`good_off_threshold_min` (20, range 1-240),
`target_cycles_per_day` (8, range 1-100).

**Adaptive:** `adaptive_thresholds_enabled` (false),
`adaptive_min_samples` (20, range 5-500).

#### Screen 4 - notifications (menu, 4 sub-pages)

**4a notifications_delivery:** `persistent_enabled` (true),
`notify_service` (empty, runtime dropdown), `notify_emoji_enabled` (true),
`action_advice_enabled` (true).

**4b notifications_quiet_hours:** `quiet_hours_enabled` (false),
`quiet_hours_start` (22:00), `quiet_hours_end` (07:00),
`alert_aggregation_minutes` (30, range 1-1440),
`status_update_enabled` (false),
`status_update_interval_hours` (24, range 1-168).

**4c notifications_content:** `notification_language` (en or nl),
`alert_group_pendulum` (true), `alert_group_short_cycle` (true),
`alert_group_ml` (true), `alert_group_setpoint` (true),
`alert_group_cop_stooklijn` (true).

**4d notifications_test_menu:** sub-menu leading to `test_notification`
and `test_all_notifications`.

#### Screen 5 - advanced (2 sections)

**Retention:** `retention_enabled` (true),
`cycle_retention_days` (90, range 7-3650),
`alert_retention_days` (30, range 7-3650),
`vacuum_enabled` (true).

**Season:** `season_start_month` (10, range 1-12). Drives the SPF season
window. Renders as dropdown but stores int.

#### Screen 6 - test_notification

`alert_kind` (status_summary; 10 options: status_summary, pendulum_hourly,
pendulum_daily, short_run, short_off, ml_anomaly, setpoint_osc, cop_low,
stooklijn_advies, all_alerts), `ignore_group_filters` (false). Respects
language + emoji settings.

#### Screen 7 - test_all_notifications

Single submit. Fires every alert kind at once. Ignores per-group filters.

**Backwards compatibility.** `_save()` flattens one level
(`{section_key: {field: value}}` -> `{field: value}`), so the stored
options schema is unchanged from pre-v1.6.0. Existing config entries
keep working.

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

### 9.1 Sensors (45)

Entity IDs follow `sensor.daikin_cycle_ml_<key>`.

**Cycle & state (7):** `cycle_state` (idle/running/cooldown),
`current_cycle`, `last_cycle` (score; attr `cluster`), `cycles_today`,
`quality_today`, `source_health` (s, DURATION), `learned_thresholds`.

**Live performance (1):** `thermal_power_live` (kW, POWER; flow x 4.18 x dT / 60).

**Advice (1):** `heating_curve_advice` (see 9.3).

**COP legacy & KPIs (5):** `cop_today` (heating-only, v1.6.0 BREAKING),
`cop_combined_today` (blended, previous cop_today value), `cop_mean_day`,
`cop_mean_week`, `cop_mean_month`.

**COP per-mode (9):** `cop_heating_day`, `cop_heating_week`,
`cop_heating_month`, `cop_dhw_day`, `cop_dhw_week`, `cop_dhw_month`,
`cop_cooling_day`, `cop_cooling_week`, `cop_cooling_month`.

**COP curve (1):** `cop_curve_recent` (48 h window, recorder-safe).

**SPF / SCOP (3):** `spf_season`, `spf_ytd`, `scop_running_365d`.

**Daikin datasheets (3):** `hp_specs` (attrs + provenance),
`cop_normalized_a7w35`, `cop_vs_datasheet_pct` (%).

**Degradation (3):** `cop_degradation_status` (enum: none/info/warning/
critical), `cop_degradation_week_pct` (%), `cop_trend_30d` (%).

**Runtime (6):** `runtime_compressor_today` (s, DURATION),
`runtime_buh_today` (s, DURATION), `compressor_starts_today` (count),
`defrost_count_today` (count), `defrost_duration_today` (s, DURATION),
`duty_cycle_today` (%).

**Energy kWh (6):** `electrical_energy_heating_today`,
`electrical_energy_dhw_today`, `electrical_energy_cooling_today`,
`electrical_energy_total_today`, `thermal_energy_heating_today`,
`thermal_energy_cooling_today`. All have `device_class=ENERGY`,
`state_class=total_increasing`.
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


### 10.8 import_datasheet

Import a user datasheet for a non-bundled model, or override a bundled one.

| Field | Type | Required |
|---|---|---|
| entry_id | string | auto-resolved if 1 entry |
| payload | object | yes (full datasheet JSON) |
| source_url | string | no (provenance only) |

Response: `{"imported": [model_keys], "errors": [messages]}`.

Repairs raised on error: `datasheet_import_invalid` (validation failed),
`datasheet_schema_unknown` (schema_version mismatch),
`datasheet_load_failed` (Store unreadable at startup).

### 10.9 remove_user_datasheet

Remove a user-imported datasheet. Bundled datasheets cannot be removed.

| Field | Type | Required |
|---|---|---|
| entry_id | string | auto-resolved if 1 entry |
| model_key | string | yes |

Response: `{"removed": bool, "model_key": str}`.

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
- If onboarding blocks on screen 1, switch **Attribute mode** to
  **Manual** and map each required attribute (see the Custom attribute
  map section for details).

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

---

## 23. Upgrade from 1.5.x

### Breaking change: cop_today is heating-only

In v1.6.0, sensor.daikin_cycle_ml_cop_today reports the heating-only COP
for today. The previous value (blended across heating, DHW and cooling)
is preserved on the new sensor sensor.daikin_cycle_ml_cop_combined_today.

Action required if you have automations or templates that consume
cop_today and expect the blended value. Replace:

    Before:  {{ states('sensor.daikin_cycle_ml_cop_today') }}
    After:   {{ states('sensor.daikin_cycle_ml_cop_combined_today') }}

No change needed for other COP sensors.

### No-op for other sensors

cop_mean_day / cop_mean_week / cop_mean_month keep their semantics
(heating-weighted mean). cop_curve_recent, thermal_power_live and all
binary sensors are unchanged.

### Optional: re-select your Daikin model

The wizard now offers 17 models (was 5). If your Daikin was previously
configured as Custom, re-select your specific model to enable
datasheet-backed COP normalization:

1. Settings -> Devices & Services -> Daikin Cycle ML -> Reconfigure.
2. Pick your exact model from the dropdown.
3. Save. Reload fires automatically (OptionsFlowWithReload).

If your model is not bundled, use the new
daikin_cycle_ml.import_datasheet service to import it.

### Database

No migration. Schema is unchanged at v14. Existing DBs keep working.

---

## 24. Known limitations

The following are intentional design decisions or accepted trade-offs
in v1.6.0. They are candidates for future releases.

### BUH step power is a model-based estimate

BUH_STEP_KW_BY_MODEL maps 14 Daikin models to their step heater power
(typically 3 kW or 6 kW per step). If your installation has a different
backup-heater configuration, runtime_buh_today will drift.

### Defrost duration is a monotone accumulator

_defrost_duration_s grows monotonically while a defrost is active. It is
not decremented mid-cycle. A non-monotone summation is planned for
v1.6.1.

### Energy fallback uses rps_heuristic

If power_sensor_entity is not configured, energy values are computed via
rps_heuristic (compressor RPS x nominal kW). For accurate Energy
Dashboard numbers, configure a real power sensor in the Device
OptionsFlow step.

### Mid-cycle mode switch uses start mode

If the unit switches from heating to DHW mid-cycle, the cycle keeps the
mode it started in. This is by design; mode-switch detection is a
v1.6.1 candidate.

### BUH-share sensors not implemented

buh_high_share fires as an alert based on the runtime ratio, but there
are no dedicated BUH-share sensors. Sensor exposure is deferred to
v1.6.1.

### Energy sensors toggle deferred

An energy_sensors_enabled toggle was planned for C6b but is deferred to
v1.6.1. All 6 energy sensors are always registered in v1.6.0.

### Cost tracking deferred

Tariff options and cost-tracking sensors (EUR/day, EUR/month, cost_acc
persistence, DB schema v15) are planned for v1.6.1 / C6b + C7.

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