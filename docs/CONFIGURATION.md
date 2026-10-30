# Configuration

Complete user guide to every configurable option in Daikin Cycle ML.

- **Covers:** source sensor requirements, setup wizard, options menu, reconfigure flows
- **For:** end users, admins tuning alerts, developers reading the config schema
- **Version:** v1.14.0

Cross-references: [ENTITIES.md](ENTITIES.md) (sensors/services), [ALERTS.md](ALERTS.md) (alert tuning), [ML.md](ML.md) (adaptive thresholds), [DATABASE.md](DATABASE.md) (retention).

---

## Contents

- [1. Where configuration lives](#1-where-configuration-lives)
- [2. Source sensor](#2-source-sensor)
- [3. Setup wizard](#3-setup-wizard)
- [4. Options menu](#4-options-menu)
- [5. Reconfigure](#5-reconfigure)
- [6. Cookbook](#6-cookbook)
- [7. Verification](#7-verification)

---

## 1. Where configuration lives

Daikin Cycle ML has three places where settings are stored:

| Place | When | Saves to |
|---|---|---|
| Setup wizard | One-time onboarding | Config-entry **DATA** |
| Options menu | Tuning after install | Config-entry **OPTIONS** |
| Reconfigure | Change source sensor or model | Config-entry **DATA** |

**DATA** and **OPTIONS** are separate dictionaries inside the same config entry. That is why changing `source_sensor` or `model` requires **Reconfigure**, not Options — those two fields live in DATA.

All entries persist to `/config/.storage/core.config_entries` under the integration's entry ID.

### 1.1 What lives where

| Field group | Location | Editable via |
|---|---|---|
| `source_sensor`, `model`, `attribute_mode` | DATA | Setup wizard, Reconfigure |
| `custom_attribute_map` | DATA | Setup wizard (Custom branch) |
| Thresholds (run/off, pendulum, quality) | OPTIONS | Setup wizard, Options |
| Notifications (delivery, quiet hours, content, per-alert, dedup) | OPTIONS | Setup wizard (basic), Options (full) |
| Retention, season | OPTIONS | Options |
| Sensor entity IDs (power, COP, indoor temp) | OPTIONS | Options |

### 1.2 What happens on save

- **Wizard save**: creates the config entry, starts the coordinator
- **Options save**: reloads the coordinator with new options (no cycle data loss)
- **Reconfigure save**: reloads with new DATA (existing cycles and DB preserved for the same entity IDs)

---

## 2. Source sensor

Daikin Cycle ML reads from **one** Home Assistant sensor entity — typically `sensor.althermasensors` published by ESPAltherma. Everything is computed from that sensor's **attributes**, not its state.

### 2.1 Required attributes (12)

Without these, cycle detection degrades or stops, and the `missing_attributes` repair is raised.

| Attribute | Feeds | Why it matters |
|---|---|---|
| `Operation Mode` | Mode fallback | Used only if `I/U operation mode` missing |
| `I/U operation mode` | Mode source | Heating / Cooling / DHW |
| `3way valve` | DHW discriminator | DHW vs space heating |
| `Defrost Operation` | Defrost flag | Marks cycles with defrost |
| `Leaving water temp after BUH (R2T)` | LWT | dT and COP inputs |
| `Inlet water temp (R4T)` | Return water temp | dT and COP inputs |
| `Flow sensor (l/min)` | Water flow | Thermal kW calculation |
| `Water pump operation` | Pump on/off | Cycle validity gate |
| `Outdoor air temp (R1T)` | Outdoor temp | Heat-curve bucketing |
| `BUH Step1` | Backup heater 1 | BUH flag on cycle record |
| `BUH Step2` | Backup heater 2 | BUH flag on cycle record |
| `LW setpoint (main)` | Setpoint tracking | Setpoint-oscillation alert + modern LWT advice |

Even if you deselect these in the wizard, they are **always kept**. Cycle detection depends on them.

> ⚠️ **R1T ambiguity on some models** — up to 3 attributes can share the `(R1T)` suffix (outdoor air, LWT before BUH, indoor ambient). The alias resolver disambiguates per model. See [MODEL_COMPATIBILITY §5](MODEL_COMPATIBILITY.md#5-per-model-matrix). This was the root cause of #196.

#### 2.1.1 External sensor failure modes

Two failure modes silently break COP/thermal calculation without raising an error:

- **`cop_sensor` returning 0.0** during compressor transitions — COP samples are skipped. Verify the sensor reports stable values during steady-state operation.
- **`power_sensor` configured in kWh instead of W** — thermal samples are skipped. Check `unit_of_measurement` is `W`, not `kWh`.

### 2.2 Recommended attributes (7)

Pre-selected in the wizard. Safe to enable. Improve quality and unlock extra features.

| Attribute | Feeds | When you need it |
|---|---|---|
| `Discharge pipe temp.` | Compressor health | ML feature vector + anomaly detection |
| `Suction pipe temp.` | Refrigerant context | ML feature vector |
| `INV primary current (A)` | Power proxy | Fallback when no power sensor configured |
| `Target Cond. Temp.` | Heat-curve target | Better stooklijn comparison |
| `DHW setpoint` | DHW context | DHW cycle annotation |
| `INV frequency (rps)` | Compressor RPS | Refines short-cycle alerts (not required for cycle detection) |
| `DHW tank temp (R5T)` | DHW annotation | DHW cycle record enrichment (3-way valve alone identifies DHW) |

### 2.3 Optional attributes

Default off. Enable only if your installation publishes them:

`Heat exchanger mid-temp.`, `Liquid pipe temp. (R6T)`, `Expansion valve (pls)`, `Crank case heater 1`, `Pressure equalizing operation`, `4 Way Valve 1`, `Solenoid Valve 1`, `Target Evap. Temp.`, `RT setpoint`, `High Pressure`, `Water pressure`, `Brine inlet temp.`, `Brine outlet temp.`

None of these are used for cycle detection or COP. They are stored on the cycle record for ML feature extraction and forward-compatibility.

For per-model availability of these attributes across all supported Daikin families, see [MODEL_COMPATIBILITY §5](MODEL_COMPATIBILITY.md#5-per-model-matrix).

### 2.4 Verify your sensor

Before starting the wizard, confirm your sensor exposes the required attributes.

**In Home Assistant:**

1. Developer Tools, States
2. Search `sensor.althermasensors`
3. Expand Attributes
4. Check each of the 12 required names is present as a key

**Or via Template (Developer Tools, Template):**

```jinja
{% set attrs = state_attr('sensor.althermasensors', 'attributes') or {} %}
{% for k in attrs.keys() %}
{{ k }}
{% endfor %}
```

If a required attribute is missing:

1. Open ESPAltherma configuration
2. Enable that register in the `.h` file
3. Restart the ESP device
4. Wait for the sensor to republish with all attributes
5. Then run the wizard

### 2.5 Custom attribute names

If your firmware uses different attribute names (e.g. `lwt_after_buh` instead of `Leaving water temp after BUH (R2T)`), you have two options.

**Option A: JSON attribute map** — preferred for a few renames:

```json
{
  "Leaving water temp after BUH (R2T)": "lwt_after_buh",
  "INV frequency (rps)": "compressor_hz"
}
```

Left is canonical key, right is your actual attribute name. Unlisted keys use the canonical name as-is.

**Option B: Manual mapping** — one field per attribute in the wizard, leave blank to auto-fill.

Both options are part of the Custom model branch, see §3.3.

### 2.6 JSON attribute map rules

- Must be a valid JSON object
- Values must be string attribute names, not paths
- Empty value (`""`) means "leave original untouched"
- Only the keys you list are renamed; others pass through

Malformed JSON shows an inline error, wizard does not advance.

---

## 3. Setup wizard

### 3.1 Before you start

1. Confirm HA Core ≥ 2026.9 (required for Python 3.14)
2. Confirm ESPAltherma sensor exists and publishes attributes (§2.4)
3. Decide: **automatic** (auto-detect) or **manual** (map each attribute) mode
4. Decide: bundled model (17 options) or **Custom** (you provide spec + map)

### 3.2 Wizard paths

Your wizard path depends on your model and mapping choice:

| Selection | Path |
|---|---|
| Model ≠ Custom, automatic | user → attributes → cycle → pendulum → quality → notifications → finalize |
| Model ≠ Custom, manual | user → map_attributes → attributes → cycle → pendulum → quality → notifications → finalize |
| Custom, automatic, all canonicals present | user → **Page A** → **Page B** → **Page C** → attributes → cycle → pendulum → quality → notifications → finalize |
| Custom, automatic, 3+ via alias/fuzzy | user → **diagnose** → **Page A** → **Page B** → **Page C** → attributes → cycle → pendulum → quality → notifications → finalize |
| Custom, manual | user → **Page A** → **Page B** → **map_attributes** → attributes → cycle → pendulum → quality → notifications → finalize |

**The Custom branch has 3 extra pages (A/B/C)** because a Custom model has no bundled profile — both the heat-pump spec and the attribute mapping must be collected explicitly.

### 3.3 Step 1 — Source & model

| Field | Code key | Type | Default |
|---|---|---|---|
| Source sensor | `source_sensor` | entity picker | `sensor.althermasensors` |
| Model | `model` | dropdown | `EPRA12EAV3` |
| Attribute mode | `attribute_mode` | dropdown (`auto` / `manual`) | `auto` |

**Source sensor.** Any entity with the required attributes. Must be `sensor.*` domain.

**Model.** Bundled models enable `cop_normalized_a7w35`, `cop_vs_datasheet_pct`, and `hp_specs`. Available families:

- **Altherma 3 R** (ERGA/ERLA) — Split/monobloc heat pumps
- **Altherma 3 H** (EPRA/EBLA/EDLA) — Mid-temp and high-temp
- **Altherma Monobloc** (EDLQ/EBLQ)
- **Altherma 4** (EPSK) — R290 models
- **Altherma R Hybrid** (EVLQ05CV3, EVLQ08CV3) — bivalent with Intergas boiler
- **Custom** — needs Page A HP spec

**Hybrid models (EVLQ series).** Selecting an EVLQ model activates:

- HP-COP isolation (co-fire samples excluded from `cop_today`) — see `MODEL_COMPATIBILITY.md` §6.6
- 2 extra binary sensors (`boiler_operation_demand`, `boiler_dhw_demand`)
- 3 extra sensors (`hybrid_mode`, `boiler_efficiency_cop`, `boiler_contribution_today_pct`)

**⚠️ Hybrid attributes are optional.** If your ESPAltherma source exposes
`Boiler Operation Demand`, `Boiler DHW Demand`, and `Hybrid Op. Mode`,
leave the fields in the next step as-is (canonical names). If absent, setup
still succeeds with a warning — boiler-cycle detection will be inactive
until those attributes are enabled in ESPAltherma (`ALTHERMA(HYBRID).h`).

**Normalization.** Hybrid Op. Mode case-insensitive; aliases hp/h-p/boiler accepted; unknown -> unknown.

**None-safe hybrid_hint.** Fires on absent OR None-valued attrs.

**Switching HP ↔ Hybrid later.** Use **Reconfigure → Basic** to change the
model. Both directions are supported; existing cycle history is preserved
unchanged, new cycles use the new detection logic. A confirmation message
flags the transition.

**Attribute mode.**

- `auto` — canonical ESPAltherma names (recommended)
- `manual` — one field per attribute in the wizard

### 3.4 Custom model — Page A (HP spec)

Only shown when **Model = Custom**.

| Field | Code key | Type | Required |
|---|---|---|---|
| HP spec JSON | `custom_datasheet_json` | multiline text | No |

**Required keys:** `family`, `kw`, `lwt_min`, `lwt_max`, `nom_cop`

**Optional keys:** `bivalent`, `buh_kw`, `refrigerant` (`R32` / `R290` / `R410A`), `min_modulation_kw`, `max_flow_lmin`, `noise_db`, `points[]`

Example:

```json
{
  "family": "Custom Altherma",
  "kw": 12.0,
  "lwt_min": 25,
  "lwt_max": 55,
  "nom_cop": 4.2,
  "buh_kw": 6.0,
  "refrigerant": "R32"
}
```

Empty = inherit Basic profile defaults. Malformed JSON shows an inline error.

### 3.5 Custom model — Page B (mapping mode)

| Field | Code key | Type | Default |
|---|---|---|---|
| Mapping mode | `mapping_mode` | dropdown (`json` / `manual`) | `json` |

`json` routes to Page C. `manual` routes to `map_attributes`.

### 3.6 Custom model — Page C (JSON map)

| Field | Code key | Type | Required |
|---|---|---|---|
| Attribute map JSON | `custom_attribute_map` | multiline text | Yes |

Format per §2.5. Malformed JSON shows an inline error.

### 3.7 Diagnose screen (conditional)

Shown only when automatic mode triggered alias/fuzzy fallback (≥ 3 canonicals resolved via alias table). Read-only.

Shows per canonical:

- Resolved key name
- Match kind: `EXACT` / `ALIAS` / `FUZZY` / `MISSING`
- Sanity warnings (e.g. hint at wrong `.h` file when a constant value looks suspicious)

Unresolved attributes must be mapped later.

### 3.8 Attributes screen (warning-only)

Shows how many of the 12 required attributes are present on the selected source sensor. Missing ones are listed but do not block the wizard.

### 3.9 Map attributes screen

Only shown when `attribute_mode = manual` OR on the Custom manual branch.

One text field per required (13) + optional (1) attribute. Field label = canonical key. Value = your actual attribute name.

Leave blank if the canonical name exists on your sensor. The wizard auto-fills.

### 3.10 Cycle screen

| Field | Code key | Type | Default | Range |
|---|---|---|---|---|
| RPS threshold | `compressor_rps_threshold` | numeric | 3 | 0–100 |
| Power sensor | `power_sensor_entity` | entity picker | (none) | sensor.* |
| Fallback power threshold | `fallback_power_threshold_w` | numeric | 200 | 0–10000 W |
| Indoor temp sensor | `indoor_temp_sensor` | entity picker | (none) | sensor.* |

**`compressor_rps_threshold`** — compressor "on" when RPS exceeds this. Typical 2–5. Lower = catches brief modulation dips; higher = misses short cycles.

**`power_sensor_entity`** — optional W sensor. Fallback when `INV frequency (rps)` missing from firmware.

**`fallback_power_threshold_w`** — power threshold when the power sensor is the cycle signal. Typical 200 W (compressor only), 500 W (whole system).

**`indoor_temp_sensor`** — optional room temp. Added as `indoor_temp_avg` (dim 10) to the feature vector. Enables comfort guards.

### 3.11 Pendulum screen

| Field | Code key | Default | Range |
|---|---|---|---|
| Short run threshold | `short_run_threshold_min` | 20 | 1–240 min |
| Short off threshold | `short_off_threshold_min` | 5 | 1–120 min |
| Pendulum cycles/day | `pendulum_cycles_per_day` | 40 | 1–200 |
| DHW pendulum cycles/hour | `dhw_pendulum_cycles_per_hour` | 3 | 1–20 |

**`short_run_threshold_min`** — cycle shorter than this triggers `short_run`. Typical 20 min.

**`short_off_threshold_min`** — off-time shorter than this triggers `short_off`. Typical 5 min.

**`pendulum_cycles_per_day`** — days with more cycles than this trigger `pendulum_daily`. Typical 40 for low-mass; lower for radiators.

**`dhw_pendulum_cycles_per_hour`** — DHW-mode cycles/hour threshold. Typical 3.

### 3.12 Quality screen

| Field | Code key | Default | Range |
|---|---|---|---|
| Good run threshold | `good_run_threshold_min` | 45 | 1–240 min |
| Good dT threshold | `good_dt_threshold_k` | 5.0 | 0.1–20.0 K |
| Good off threshold | `good_off_threshold_min` | 20 | 1–240 min |
| Target cycles/day | `target_cycles_per_day` | 8 | 1–100 |

**`good_dt_threshold_k`** — dT (LWT − RWT) for full efficiency points. Typical 5 K.

**`target_cycles_per_day`** — expected good cycles. Drives `high_cycle_rate` (1.5× this).

### 3.13 Notifications screen (wizard basic)

| Field | Code key | Default |
|---|---|---|
| Persistent notifications | `persistent_enabled` | `true` |
| Notify service | `notify_service` | (empty) |
| Quiet hours enabled | `quiet_hours_enabled` | `false` |
| Quiet hours start | `quiet_hours_start` | `22:00` |
| Quiet hours end | `quiet_hours_end` | `07:00` |

Full config (7 groups, 11 per-alert toggles, 19 dedup windows, language, emoji, action advice, status updates) lives in **Options → Notifications** (§4.4) and is documented in [ALERTS.md](ALERTS.md).

### 3.14 Finalize screen

Review-only. Submit starts the coordinator — 30 s polling, no data until first valid sample.

---

## 3A. Onboarding troubleshooting

### "Sensor mist vereiste ESPAltherma-attributen"

The wizard aborts when the source sensor is missing one or more of the 12 required attributes.

**Fix 1 — Manual mode:**

1. Re-run **Add Integration**
2. On step 1: set **Attribute mode** to `Manual`
3. On the next screen, map each canonical attribute to your sensor's actual attribute name (visible in Developer Tools → States → Attributes)
4. Leave a field empty if the canonical name already exists on your sensor
5. If `INV frequency (rps)` is not exposed by your firmware, leave it empty — cycle detection falls back to a current-based heuristic

**Fix 2 — Enable missing registers in ESPAltherma:**

1. Open the ESPAltherma `.h` file
2. Enable the missing register (see log or `missing_attrs` repair for the exact name)
3. Restart the ESP device
4. Wait for the sensor to republish
5. Retry the wizard

**Fix 3 — Custom branch with JSON map:** see §2.5.

### Getting the exact key list from your firmware

Run in **Developer Tools → Template**:

```jinja
{% for k in state_attr('sensor.althermasensors', 'attributes').keys() %}
{{ k }}
{% endfor %}
```

That gives the exact attribute names available on your sensor.

---

## 3B. Smart auto-import (v1.8.0+)

When the canonical attribute names are not present, the wizard falls back to smart auto-import:

1. **Entity discovery** — scans all `sensor.*` entities for overlap with the 13 canonical attributes and scores candidates. Renamed entities like `sensor.altherma` are auto-detected.
2. **Alias table** — 14+ known community firmware variants resolve automatically (benthouse, akaQ, Videopac, ...)
3. **Fuzzy matching** — Jaccard similarity as fallback when alias table misses
4. **Anti-alias guard** — `Leaving water temp. after BUH (R2T)` never wrongly resolves to a `R1T` variant (would corrupt COP ≈ 11 on hybrid setups)
5. **Diagnose screen** — shown when auto-import triggers, displays per-canonical match kind (`EXACT` / `ALIAS` / `FUZZY` / `MISSING`) and sanity warnings

When diagnose shows `MISSING` on a critical attribute, use the following `map_attributes` step to fix it manually.

---

## 3C. Scheduled jobs

The coordinator runs these tasks on fixed intervals. All times are local timezone.

| When | What | Config key |
|---|---|---|
| Every 30 s | Poll source sensor, detect cycle transitions, dispatch alerts | — |
| Every 5 min | Collect COP sample (if `cop_sensor_entity` configured) | — |
| Every 300 s | Persist runtime + energy accumulators (independent gates — I8) | — |
| Every 1 h | Refresh 7-day rollups + alert dispatch + energy baseline + data-quality alerts | — |
| Every 6 h | Persist baseline + adaptive thresholds to `model_state` | — |
| Daily 03:00 | Retention rollup + prune + optional VACUUM | `retention_enabled` |
| Daily 04:00 | Stooklijn analysis (force refresh) | — |
| Sunday 04:00 | K-means retrain over last 7 days | `adaptive_thresholds_enabled` independent |
| Every N h (opt-in) | Status summary via `build_status_report` | `status_update_enabled` |

### 3C.1 Manual triggers

All scheduled jobs except the 30 s poll can be triggered manually:

| Job | Manual trigger |
|---|---|
| Maintenance prune | `daikin_cycle_ml.run_maintenance` service |
| K-means retrain | `daikin_cycle_ml.recompute_kmeans` service |
| Baseline recompute | `daikin_cycle_ml.recompute_baseline` service |
| Status summary | `send_test_notification` with `alert_kind: status_summary` |
| COP hourly export | `daikin_cycle_ml.export_cop_hourly` service |

### 3C.2 Backend detail — `_save()` flattening

All OptionsFlow FORM steps use HA `section()` blocks internally. On save, `_save()` flattens one level (`{section_key: {field: value}}` → `{field: value}`), so the stored options schema is unchanged from pre-v1.6.0. Existing config entries keep working without migration.
---

## 4. Options menu

**Open:** Settings → Devices & Services → Daikin Cycle ML → **Configure**.

Each screen saves independently. All FORM steps use HA `section()` blocks — collapsible, independent saves.

Top-level menu (7 items): device · pendulum · quality_ml · notifications (sub-menu) · advanced · test_notification · test_all_notifications.

### 4.1 Screen 1 — Device

Three sections: **Sensors**, **Detection**, **Comfort**.

**Sensors**

| Field | Code key | Type | Default |
|---|---|---|---|
| Power sensor | `power_sensor_entity` | entity picker | (from data, or empty) |
| COP sensor | `cop_sensor_entity` | entity picker | (empty) |
| Indoor temp sensor | `indoor_temp_sensor` | entity picker | (empty) |

- **Power sensor** — W sensor for energy accounting + cycle fallback
- **COP sensor** — COP sensor (`measurement` or `ratio`), enables rolling COP analysis
- **Indoor temp sensor** — room temp, ML feature + comfort guards

**Detection**

| Field | Code key | Default | Range |
|---|---|---|---|
| RPS threshold | `compressor_rps_threshold` | 3 | 0–100 |
| Fallback power threshold | `fallback_power_threshold_w` | 200 | 0–10000 W |

**Comfort**

| Field | Code key | Default | Range |
|---|---|---|---|
| Comfort floor | `comfort_min_c` | 20.0 | 15.0–22.0 °C |
| Comfort ceiling | `comfort_max_c` | 24.0 | 22.0–28.0 °C |

**Comfort floor** — projected indoor temp below which LWT advice never suggests lowering further.

**Comfort ceiling** — projected indoor temp above which LWT advice never suggests raising further.

Both are projected, not measured. They gate the LWT advice algorithm.

### 4.2 Screen 2 — Pendulum

Three sections: **Run/off**, **Pendulum**, **Setpoint**.

**Run/off**

| Field | Code key | Default | Range |
|---|---|---|---|
| Short run threshold | `short_run_threshold_min` | 20 | 1–240 min |
| Short off threshold | `short_off_threshold_min` | 5 | 1–120 min |

**Pendulum**

| Field | Code key | Default | Range |
|---|---|---|---|
| Cycles per hour | `pendulum_cycles_per_hour` | 4 | 1–100 |
| Cycles per day | `pendulum_cycles_per_day` | 40 | 1–200 |
| DHW cycles per hour | `dhw_pendulum_cycles_per_hour` | 3 | 1–20 |

**Setpoint**

| Field | Code key | Default | Range |
|---|---|---|---|
| Oscillation threshold | `setpoint_oscillation_threshold` | 6 | 1–100 |
| Window | `setpoint_osc_window_min` | 30 | 5–180 min |
| Min delta | `setpoint_osc_min_delta` | 0.5 | 0.1–2.0 °C |

**Oscillation alert** fires only when all three conditions are met **and** changes show a reversal (up-then-down or down-then-up). Monotonic drifts are not treated as oscillation (Q4 fix, v1.9).

### 4.3 Screen 3 — Quality & ML

Two sections: **Quality**, **Adaptive**.

**Quality**

| Field | Code key | Default | Range |
|---|---|---|---|
| Good run threshold | `good_run_threshold_min` | 45 | 1–240 min |
| Good dT threshold | `good_dt_threshold_k` | 5.0 | 0.1–20.0 K |
| Good off threshold | `good_off_threshold_min` | 20 | 1–240 min |
| Target cycles/day | `target_cycles_per_day` | 8 | 1–100 |

**Adaptive**

| Field | Code key | Default | Range |
|---|---|---|---|
| Enabled | `adaptive_thresholds_enabled` | `false` | bool |
| Minimum samples | `adaptive_min_samples` | 20 | 5–500 |

**Adaptive thresholds** — when enabled, `short_run_threshold` and `good_off_threshold` are learned from your cycle history. Percentile-based. Needs `adaptive_min_samples` cycles before activating.

`sensor.daikin_cycle_ml_learned_thresholds` exposes current learned values. Adaptive never overrides your hardcoded values as *bounds* — it refines within a safe range.

### 4.4 Screen 4 — Notifications (menu)

Four sub-pages + two sub-menus:

```
Notifications
├── Delivery           (4.4a)
├── Quiet hours        (4.4b)
├── Content            (4.4c)
├── Enabled            (4.4d) — v1.9
├── Dedup              (4.4e) — v1.9
└── Test menu          (4.4f)
    ├── Send test notification
    └── Send ALL test notifications
```

#### 4.4a — Delivery

| Field | Code key | Default |
|---|---|---|
| Persistent notifications | `persistent_enabled` | `true` |
| Notify service | `notify_service` | (empty) |
| Emoji | `notify_emoji_enabled` | `true` |
| Action advice | `action_advice_enabled` | `true` |

- **Persistent** — HA sidebar; independent of notify service
- **Notify service** — any `notify.*` entity. Unset = only persistent fire
- **Emoji** — per-alert emoji prefix. Disable if your notify service mangles UTF-8
- **Action advice** — appends `• &lt;advice&gt;` line. Disable for minimal output

#### 4.4b — Quiet hours

| Field | Code key | Default | Range |
|---|---|---|---|
| Enabled | `quiet_hours_enabled` | `false` | bool |
| Start | `quiet_hours_start` | `22:00` | time |
| End | `quiet_hours_end` | `07:00` | time |
| Aggregation window | `alert_aggregation_minutes` | 30 | 1–1440 min |
| Status updates | `status_update_enabled` | `false` | bool |
| Status interval | `status_update_interval_hours` | 24 | 1–168 h |

- **Quiet hours** — non-critical suppressed. `source_stale` bypasses
- **Aggregation** — same-type alerts within window collapse to one
- **Status updates** — periodic summary via `build_status_report`

#### 4.4c — Content

| Field | Code key | Default |
|---|---|---|
| Language | `notification_language` | `en` (or `nl`) |
| Pendulum group | `alert_group_pendulum` | `true` |
| Short cycle group | `alert_group_short_cycle` | `true` |
| ML group | `alert_group_ml` | `true` |
| Setpoint group | `alert_group_setpoint` | `true` |
| COP + heat-curve group | `alert_group_cop_stooklijn` | `true` |

**Group mapping**

| Group | Alerts |
|---|---|
| `pendulum` | pendulum_hourly, pendulum_daily |
| `short_cycle` | short_run, short_off, high_cycle_rate |
| `ml` | ml_anomaly |
| `setpoint` | setpoint_osc, dhw_pendulum |
| `cop_stooklijn` | cop_low, stooklijn_advies, cop_degradation, cop_vs_datasheet_low |

**Always fire (no group)**: `source_stale` (critical), `missing_attributes`, `defrost_excessive`, `buh_excessive`, `db_retention_warning`, `kmeans_retrain_stale`, `energy_daily_anomaly`.

#### 4.4d — Per-alert toggles (v1.9)

11 boolean toggles, each gates one alert. Defaults `true`.

| Field | Code key | Alert |
|---|---|---|
| COP degradation | `alert_enabled_cop_degradation` | `cop_degradation` |
| Defrost excessive | `alert_enabled_defrost_excessive` | `defrost_excessive` |
| Backup heater excessive | `alert_enabled_buh_excessive` | `buh_excessive` |
| Source stale | `alert_enabled_source_stale` | `source_stale` |
| Missing attributes | `alert_enabled_missing_attributes` | `missing_attributes` |
| DHW pendulum | `alert_enabled_dhw_pendulum` | `dhw_pendulum` |
| High cycle rate | `alert_enabled_high_cycle_rate` | `high_cycle_rate` |
| COP below datasheet | `alert_enabled_cop_vs_datasheet_low` | `cop_vs_datasheet_low` |
| DB retention warning | `alert_enabled_db_retention_warning` | `db_retention_warning` |
| K-means retrain stale | `alert_enabled_kmeans_retrain_stale` | `kmeans_retrain_stale` |
| Energy daily anomaly | `alert_enabled_energy_daily_anomaly` | `energy_daily_anomaly` |

Alerts without per-alert toggle (silenced via their group): pendulum_hourly, short_run, ml_anomaly, setpoint_osc, cop_low, stooklijn_advies.

An alert fires only if **both** its group toggle **and** its per-alert toggle are `true`.

#### 4.4e — Dedup windows (v1.9)

19 numeric fields, one per alert type, value = minutes. Range 1–10080 (1 min to 7 days). Persist across restarts.

| Alert | Default |
|---|---|
| pendulum_hourly | 60 |
| pendulum_daily | 1440 |
| short_run | 30 |
| short_off | 30 |
| ml_anomaly | 60 |
| setpoint_osc | 30 |
| cop_low | 30 |
| stooklijn_advies | 10080 |
| cop_degradation | 1440 |
| defrost_excessive | 1440 |
| buh_excessive | 1440 |
| source_stale | 60 |
| missing_attributes | 60 |
| dhw_pendulum | 60 |
| high_cycle_rate | 60 |
| cop_vs_datasheet_low | 1440 |
| db_retention_warning | 1440 |
| kmeans_retrain_stale | 1440 |
| energy_daily_anomaly | 1440 |

Two identical alerts of the same type within the window collapse to one. To force-fire: `send_test_notification` with `ignore_filters: true`.

#### 4.4f — Test menu

- **Send test notification** (§4.6) — single alert type
- **Send ALL test notifications** (§4.7) — all types at once

### 4.5 Screen 5 — Advanced

Two sections: **Retention**, **Season**.

**Retention**

| Field | Code key | Default | Range |
|---|---|---|---|
| Enabled | `retention_enabled` | `true` | bool |
| Cycle retention | `cycle_retention_days` | 90 | 7–3650 |
| Alert retention | `alert_retention_days` | 90 | 7–3650 |
| VACUUM | `vacuum_enabled` | `true` | bool |

Rows older than retention days are deleted daily at 03:00 local. VACUUM reclaims disk space.

**Season**

| Field | Code key | Default | Range |
|---|---|---|---|
| Season start month | `season_start_month` | 10 (October) | 1–12 |

Used by `spf_season`. Set to the month that starts your heating season. October is safe for Europe.

### 4.6 Screen 6 — Test notification

| Field | Code key | Type | Default |
|---|---|---|---|
| Alert kind | `alert_kind` | dropdown | `status_summary` |
| Ignore group filters | `ignore_group_filters` | bool | `false` |

**Alert kind** options (10): `status_summary`, `pendulum_hourly`, `pendulum_daily`, `short_run`, `short_off`, `ml_anomaly`, `setpoint_osc`, `cop_low`, `stooklijn_advies`, `all_alerts`.

**Ignore group filters** — when `true`, ignores both group and per-alert toggles. Quiet hours still apply unless disabled.

Respects `notification_language` and `notify_emoji_enabled`.

### 4.7 Screen 7 — Test ALL notifications

Single submit. Fires **every** alert type at once, ignoring group filters. Useful for template verification.

Known limitation (v1.9): `kmeans_retrain_stale` may not appear in the HA notification panel when fired as part of this bulk test. Rendering works, dispatch works, but HA's `persistent_notification.create` with `blocking=False` sometimes silently drops one of 19 rapid calls. Verify individually via `send_test_notification`. See [ALERTS.md §10.3](ALERTS.md#103-known-limitation-v19-kmeans_retrain_stale-in-bulk-test) for details.

---

### 4.10 COP calculation (v1.14.0)

Configures the electrical-input estimate used for COP.

| Option | Default | Meaning |
|---|---|---|
| Supply phases | 1 | 1 = single-phase (most EU homes); 3 = three-phase installations. |
| BUH step 1 (kW) | 3.0 | Rated power of backup-heater step 1 (Daikin standard: 3 kW). |
| BUH step 2 (kW) | 3.0 | Rated power of step 2. Some units use 6 kW — check your installation manual. |

**When these settings apply:** only when no `power_sensor_entity` is configured AND the source sensor lacks the ESPAltherma 2.0 `Stats:` section. If either is present, the integration uses the better source automatically and these fields are ignored.

**Priority order:** power meter > ESPAltherma 2.0 Stats > v1 inverter fallback (+100 W offset). See **README → COP without a power meter** for full explanation.

**Verify:** `sensor.daikin_cycle_ml_electrical_power_estimated` shows the current estimate. Its `source` attribute reveals which path was taken at any moment.

## 5. Reconfigure

**Open:** Settings → Devices & Services → Daikin Cycle ML → **Reconfigure**.

### 5.1 Basic reconfigure

Change `source_sensor` and `model` only. Prefilled with current values.

| Field | Code key |
|---|---|
| Source sensor | `source_sensor` |
| Model | `model` |

Saves to config-entry **DATA**. Reloads on save.

### 5.2 Full reconfigure

Re-runs the entire setup wizard with every step prefilled. Use to re-apply default thresholds across the board, or after hardware change.

Saves to **DATA** and **OPTIONS**. Existing cycles and DB remain untouched.

---

## 6. Cookbook

### 6.1 Custom pump without datasheet

1. Model = Custom
2. Page A: leave `custom_datasheet_json` empty (inherit Basic profile)
3. Page B: choose `manual`
4. `map_attributes`: fill only attributes that differ from canonical
5. Continue with wizard

You will not have `cop_normalized_a7w35` or `cop_vs_datasheet_pct`. Everything else works.

### 6.2 Non-canonical attribute names

**Option 1** — Custom branch with JSON map (§2.5).

**Option 2** — Non-Custom branch + `attribute_mode = manual`, map only differing keys.

**Option 3** — Rename attributes in ESPAltherma's `.h` file. Requires ESP reflash.

### 6.3 Only critical alerts

1. Notifications → Content: disable all 5 groups
2. Notifications → Enabled: disable all 11 toggles **except** `alert_enabled_source_stale`
3. Optionally disable `alert_enabled_missing_attributes`

Result: only `source_stale` fires (critical, bypasses quiet hours).

### 6.4 Fewer alerts but not zero

1. Notifications → Quiet hours: enable 22:00–07:00
2. Notifications → Quiet hours: raise `alert_aggregation_minutes` to 120
3. Notifications → Content: disable `alert_group_pendulum` if pendelen is acceptable for your system
4. Pendulum: raise `pendulum_cycles_per_hour` from 4 to 8

Result: fewer alerts, still catches real problems.

### 6.5 Heat curve advice too aggressive

1. Device → Comfort: raise `comfort_min_c` from 20.0 to 21.0
2. Device → Comfort: lower `comfort_max_c` from 24.0 to 23.0

Tighter comfort band → smaller advisory steps → less aggressive LWT recommendations.

### 6.6 Retrain kmeans after failures

If `kmeans_retrain_stale` alert fires:

1. Go to Developer Tools → Actions
2. Find `daikin_cycle_ml.recompute_kmeans`
3. Call it with default parameters
4. Check for `ok: true` in the response

If it fails, check the `last_failure_reason` in `sensor.daikin_cycle_ml_hp_specs` attributes or in diagnostics download.

---

## 7. Verification

### 7.1 After install / wizard

Check in order:

1. `sensor.daikin_cycle_ml_source_health` — should show < 30 s
2. `binary_sensor.daikin_cycle_ml_source_stale` — should be `off`
3. `binary_sensor.daikin_cycle_ml_missing_attributes` — should be `off`
4. `sensor.daikin_cycle_ml_current_cycle` — appears when compressor starts
5. After 1 hour: `sensor.daikin_cycle_ml_cycles_today` — increments
6. After 1 hour: check diagnostics — `database.counts.cycles` should grow

### 7.2 After options change

- **Threshold changes**: cycle detection reflects the change immediately on next tick
- **Notification changes**: fire a test to verify, or wait for next alert
- **Retention changes**: prune happens at 03:00 local, not immediately
- **Language change**: next alert is in the new language

### 7.3 Diagnostics download

Settings → Devices & Services → Daikin Cycle ML → menu → **Download diagnostics**.

Contains:
- HA info + Python version
- Integration manifest
- Config entry (redacted)
- Coordinator state
- Store counters + last cycle
- Baseline summary
- Adaptive thresholds
- Cluster summary
- COP analysis
- Database counts + extra (recent daily summaries, kmeans state, baseline state)

Use this file to diagnose every configuration issue before opening a GitHub issue.

### 7.4 Common verification failures

| Symptom | Cause | Fix |
|---|---|---|
| `source_health` growing | ESPAltherma not publishing | Check ESP device, Wi-Fi, `.h` file |
| `missing_attributes` on | Attribute names differ | Use Custom map or manual mode |
| `current_cycle` stays idle | RPS threshold too high | Lower `compressor_rps_threshold` in Options → Device |
| No cycles detected after 1 h | Sensor missing required attributes | Check `missing_attributes` repair details |
| Notifications silent | notify_service empty | Configure in Options → Notifications → Delivery |
| `setpoint_osc` never fires | `LW setpoint (main)` missing | Enable in ESPAltherma |

---

## Appendix — Default options table

Complete list of every option with default, for backup and migration.

```python
DEFAULT_OPTIONS = {
    "compressor_rps_threshold": 3,
    "fallback_power_threshold_w": 200,
    "indoor_temp_sensor": None,
    "power_sensor_entity": None,
    "cop_sensor_entity": None,
    "comfort_min_c": 20.0,
    "comfort_max_c": 24.0,
    "short_run_threshold_min": 20,
    "short_off_threshold_min": 5,
    "pendulum_cycles_per_hour": 4,
    "pendulum_cycles_per_day": 40,
    "dhw_pendulum_cycles_per_hour": 3,
    "setpoint_oscillation_threshold": 6,
    "setpoint_osc_window_min": 30,
    "setpoint_osc_min_delta": 0.5,
    "good_run_threshold_min": 45,
    "good_dt_threshold_k": 5.0,
    "good_off_threshold_min": 20,
    "target_cycles_per_day": 8,
    "adaptive_thresholds_enabled": False,
    "adaptive_min_samples": 20,
    "persistent_enabled": True,
    "notify_service": "",
    "notify_emoji_enabled": True,
    "action_advice_enabled": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "alert_aggregation_minutes": 30,
    "status_update_enabled": False,
    "status_update_interval_hours": 24,
    "notification_language": "en",
    "alert_group_pendulum": True,
    "alert_group_short_cycle": True,
    "alert_group_ml": True,
    "alert_group_setpoint": True,
    "alert_group_cop_stooklijn": True,
    "retention_enabled": True,
    "cycle_retention_days": 90,
    "alert_retention_days": 90,
    "vacuum_enabled": True,
    "season_start_month": 10,
}
```

## Appendix — Related files

| File | Purpose |
|---|---|
| `config_flow.py` | All wizard, options, and reconfigure steps |
| `const.py` | `DEFAULT_*` constants |
| `strings.json` + `translations/*.json` | Wizard/options translations |
| `services.yaml` | Service schemas |
