# Entities

Complete reference for every entity, service, and repair issue in Daikin Cycle ML.

- **Covers:** 50 sensors, 15 binary sensors, 10 services, 8 repairs, plus derived update entities
- **For:** end users building automations, dashboard builders, developers reading the entity surface
- **Version:** v1.14.0

Cross-references: [CONFIGURATION.md](CONFIGURATION.md) (options that affect entity behavior), [ALERTS.md](ALERTS.md) (alerts fired by binary sensors), [ML.md](ML.md) (ML-powered sensors), [DATABASE.md](DATABASE.md) (persistence).

---

## Contents

- [1. Entity overview](#1-entity-overview)
- [2. Sensors (50)](#2-sensors-50)
- [3. Binary sensors (15)](#3-binary-sensors-15)
- [4. Update entities (2)](#4-update-entities-2)
- [5. Services (10)](#5-services-10)
- [6. Repair issues (8)](#6-repair-issues-8)
- [7. Entity naming convention](#7-entity-naming-convention)
- [8. Device class reference](#8-device-class-reference)
- [9. Automations quick reference](#9-automations-quick-reference)

---

## 1. Entity overview

| Category | Count |
|---|---|
| Sensors | 50 |
| Binary sensors | 15 |
| Update entities | 2 |
| Services | 10 |
| Repair issues | 8 |

Total entities registered under `platform = daikin_cycle_ml` in the entity registry: **61** (some sensors are device-only or disabled by default).

### 1.1 Which entities are enabled by default

| Category | Enabled by default |
|---|---|
| Sensors | All except `*_daily_history`, `*_daily_summary`, `*_monthly_history`, `*_monthly_summary` |
| Binary sensors | All |
| Update | All |

To enable a disabled entity: Settings → Devices & Services → Daikin Cycle ML → Entities tab → click entity → enable toggle.

### 1.2 Which entities are useful for automations

The most commonly used entities in user automations:

- `sensor.daikin_cycle_ml_heating_curve_advice` — trigger for LWT advice automations
- `sensor.daikin_cycle_ml_current_cycle` — trigger for cycle start/end events
- `sensor.daikin_cycle_ml_last_cycle` — attributes give last cycle stats
- `binary_sensor.daikin_cycle_ml_compressor_running` — trigger for pump on/off
- `binary_sensor.daikin_cycle_ml_pendulum_hourly` — trigger for pendulum alerts

---

## 2. Sensors (50)

### 2.1 Cycle and state (7)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_cycle_state` | — | — | `idle` / `running` / `cooldown` |
| `sensor.daikin_cycle_ml_current_cycle` | — | — | Live cycle data (running cycle) |
| `sensor.daikin_cycle_ml_last_cycle` | score | measurement | Last completed cycle quality score (0–100) |
| `sensor.daikin_cycle_ml_cycles_today` | cycles | total_increasing | Cycle count for today |
| `sensor.daikin_cycle_ml_quality_today` | score | measurement | Average quality score today |
| `sensor.daikin_cycle_ml_source_health` | s | duration | Seconds since last successful source update |
| `sensor.daikin_cycle_ml_learned_thresholds` | min | — | Current adaptive thresholds (if enabled) |

**`last_cycle`** — key attributes:

| Attribute | Type | Meaning |
|---|---|---|
| `start_ts` | float | Unix timestamp of cycle start |
| `end_ts` | float | Unix timestamp of cycle end |
| `duration_min` | float | Cycle duration in minutes |
| `mode` | str | `heating` / `cooling` / `dhw` / `unknown` |
| `dt_max_k` | float | Maximum dT during cycle |
| `dt_avg_k` | float | Average dT during cycle |
| `rps_max` | int | Max compressor RPS |
| `rps_avg` | float | Average compressor RPS |
| `outdoor_temp` | float | Outdoor temperature during cycle |
| `buh_used` | int | 0/1 — was backup heater used |
| `defrost_used` | int | 0/1 — was defrost triggered |
| `thermal_kw_avg` | float | Average thermal kW |
| `quality_score` | int | 0–100 quality score |
| `cluster_id` | int | Assigned cluster (0/1/2) |
| `cluster` | str | Human label (`pendulum` / `dhw_like` / `normal`) |
| `label` | str | User label (if labeled via service) |
| `cop_avg` | float | Average COP during cycle (if COP sensor configured) |
| `cop_sample_count` | int | Number of COP samples |
| `cop_confidence` | str | `none` / `low` / `medium` / `high` (v1.12.5 #133) |

### 2.2 Live power (2)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_thermal_power_live` | kW | power | Live thermal power: flow × 4.18 × dT / 60 |
| `sensor.daikin_cycle_ml_electrical_power_estimated` | W | power | Electrical input estimate (v1.14.0). `source` attribute: `power_meter` / `espaltherma_v2_stats` / `inverter_estimated_v1` / `none`. Extra attributes: `supply_phases`, `buh_step1_kw`, `buh_step2_kw`, `buh_step1_on`, `buh_step2_on`, `inv_current_a`, `v2_stats_present`. |

Reports `unknown` when compressor is off or flow/dT invalid. Normal — not an error.

### 2.3 Advice (1)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_heating_curve_advice` | — | — | Heat-curve advice with rich attributes |

**States:**

| State | Meaning |
|---|---|
| `no_data` | No recent heating samples, or DHW active |
| `keep` | No change needed (delta within deadband) |
| `lower_lwt` | Lower LWT setpoint by `step_c` °C |
| `raise_lwt` | Raise LWT setpoint by `step_c` °C |
| `unknown` | Insufficient confidence or sensor unavailable |

**Attributes:**

| Attribute | Type | Meaning |
|---|---|---|
| `huidige_lwt` | float | Current measured LWT (°C) |
| `optimale_lwt` | float | Best-COP LWT for current bucket (°C) |
| `besparing_cop_pct` | float | Estimated COP saving if applied (%) |
| `comfort_impact` | float | Projected indoor-temp impact (°C) |
| `betrouwbaarheid` | float | 0.0–1.0 confidence |
| `bucket` | str | Outdoor bucket (`-10--8`, `12-14`, `20+`, etc.) |
| `samples` | int | Samples in current bucket |
| `buckets` | dict | Full bucket summary |
| `state_label` | str | Localized label with step substituted |
| `step_c` | float | Recommended step (1.0–3.0 °C) |
| `delta_c` | float | `huidige_lwt − optimale_lwt` |
| `huidige_setpoint` | float | Current LWT setpoint (from source sensor) |
| `doel_setpoint` | float | Suggested new setpoint (`huidige_setpoint ± step_c`) |
| `tracking_error` | float | LWT − setpoint (positive = ahead) |
| `comfort_cap` | str | `floor` / `ceiling` / `ok` / `unavailable` |
| `reason` | str | Machine-readable reason code |

**Reason codes:** `no_recent_heating`, `dhw_active`, `within_deadband`, `comfort_floor_reached`, `comfort_ceiling_reached`, `unit_tracking_behind`, `low_confidence`, `no_indoor_sensor`.

### 2.4 COP legacy & KPIs (5)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_cop_today` | COP | measurement | Today's **heating-only** COP |
| `sensor.daikin_cycle_ml_cop_combined_today` | COP | measurement | Today's blended COP (heating+DHW+cooling) |
| `sensor.daikin_cycle_ml_cop_mean_day` | COP | measurement | Mean COP over last 24 h (heating-weighted) |
| `sensor.daikin_cycle_ml_cop_mean_week` | COP | measurement | Mean COP over last 7 days |
| `sensor.daikin_cycle_ml_cop_mean_month` | COP | measurement | Mean COP over last 30 days |

**BREAKING (v1.6.0):** `cop_today` changed from blended to heating-only. If your automation expects the blended value, switch to `cop_combined_today`.

### 2.5 COP per-mode (9)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_cop_heating_day` | COP | measurement | Heating COP, today |
| `sensor.daikin_cycle_ml_cop_heating_week` | COP | measurement | Heating COP, last 7 days |
| `sensor.daikin_cycle_ml_cop_heating_month` | COP | measurement | Heating COP, last 30 days |
| `sensor.daikin_cycle_ml_cop_dhw_day` | COP | measurement | DHW COP, today |
| `sensor.daikin_cycle_ml_cop_dhw_week` | COP | measurement | DHW COP, last 7 days |
| `sensor.daikin_cycle_ml_cop_dhw_month` | COP | measurement | DHW COP, last 30 days |
| `sensor.daikin_cycle_ml_cop_cooling_day` | COP | measurement | Cooling COP, today |
| `sensor.daikin_cycle_ml_cop_cooling_week` | COP | measurement | Cooling COP, last 7 days |
| `sensor.daikin_cycle_ml_cop_cooling_month` | COP | measurement | Cooling COP, last 30 days |

### 2.6 COP curve (1)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_cop_curve_recent` | COP | measurement | 48 h COP curve (recorder-safe) |

**Attributes:**

| Attribute | Type |
|---|---|
| `points` | list of `{ts, cop, lwt, outdoor}` — 48 h rolling window |

### 2.7 SPF / SCOP (3)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_spf_season` | SPF | measurement | Seasonal performance factor (configurable start month) |
| `sensor.daikin_cycle_ml_spf_ytd` | SPF | measurement | Year-to-date SPF |
| `sensor.daikin_cycle_ml_scop_running_365d` | SPF | measurement | Rolling 365-day SCOP |

### 2.8 Daikin datasheets (3)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_hp_specs` | — | — | Datasheet specs with provenance |
| `sensor.daikin_cycle_ml_cop_normalized_a7w35` | COP | measurement | Live COP normalized to A7/W35 reference |
| `sensor.daikin_cycle_ml_cop_vs_datasheet_pct` | % | measurement | Live deviation vs datasheet |

**`hp_specs`** — key attributes: `family`, `kw`, `lwt_min`, `lwt_max`, `nom_cop`, `buh_kw`, `refrigerant`, `source` (`bundled` / `user`), `source_url`.

**`cop_vs_datasheet_pct`** — positive = better than spec, negative = worse. Alert fires below -10%.

### 2.9 Degradation analysis (3)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_cop_degradation_status` | — | enum | `none` / `info` / `warning` / `critical` |
| `sensor.daikin_cycle_ml_cop_degradation_week_pct` | % | measurement | Week-over-week COP change (weather-normalized) |
| `sensor.daikin_cycle_ml_cop_trend_30d` | % | measurement | 30-day COP regression trend |

**`cop_degradation_week_pct`** — negative = degradation. Below -15% triggers `cop_degradation` alert.

**`cop_trend_30d`** — negative = gradual degradation. Distinct from week_pct in that it uses linear regression over 30 days.

### 2.10 Runtime (6)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_runtime_compressor_today` | s | duration | Compressor runtime today |
| `sensor.daikin_cycle_ml_runtime_buh_today` | s | duration | BUH runtime today |
| `sensor.daikin_cycle_ml_compressor_starts_today` | starts | total_increasing | Compressor starts today |
| `sensor.daikin_cycle_ml_defrost_count_today` | defrosts | total_increasing | Defrost count today |
| `sensor.daikin_cycle_ml_defrost_duration_today` | s | duration | Defrost runtime today |
| `sensor.daikin_cycle_ml_duty_cycle_today` | % | measurement | Compressor duty cycle today |

Persist across HA restarts. The `*_today` suffix means calendar day, not 24h window.

### 2.11 Energy kWh (6)

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_electrical_energy_heating_today` | kWh | energy | Heating electrical energy today |
| `sensor.daikin_cycle_ml_electrical_energy_dhw_today` | kWh | energy | DHW electrical energy today |
| `sensor.daikin_cycle_ml_electrical_energy_cooling_today` | kWh | energy | Cooling electrical energy today |
| `sensor.daikin_cycle_ml_electrical_energy_total_today` | kWh | energy | Total electrical energy today |
| `sensor.daikin_cycle_ml_thermal_energy_heating_today` | kWh | energy | Heating thermal energy today |
| `sensor.daikin_cycle_ml_thermal_energy_cooling_today` | kWh | energy | Cooling thermal energy today |

All have `state_class: total_increasing`. Compatible with HA Energy Dashboard (Settings → Dashboards → Energy → Add consumption → select entity).

### 2.12 Helper sensors (4)

| Entity | Description | Enabled |
|---|---|---|
| `sensor.daikin_cycle_ml_defrost_daily_history` | 8-day defrost history | No (disabled) |
| `sensor.daikin_cycle_ml_defrost_daily_summary` | Daily defrost summary | No (disabled) |
| `sensor.daikin_cycle_ml_defrost_monthly_history` | 6-month defrost history | No (disabled) |
| `sensor.daikin_cycle_ml_defrost_monthly_summary` | Monthly defrost summary | No (disabled) |

Enable via entity registry if you want them.

---

### 2.13 Hybrid (3)

**Only available on hybrid installs (EVLQ series). Return `unavailable` on non-hybrid.**

| Entity | Unit | Device class | Description |
|---|---|---|---|
| `sensor.daikin_cycle_ml_hybrid_mode` | — | enum | `H/P only` / `Hybrid` / `Boiler only` — current bivalent operating mode from the Daikin controller |
| `sensor.daikin_cycle_ml_boiler_efficiency_cop` | COP | measurement | `BE COP` reference from the controller (typically 1.3 for condensing gas). Info only — never mixed with HP COP |
| `sensor.daikin_cycle_ml_boiler_contribution_today_pct` | % | measurement | Percentage of today's HP samples taken during boiler co-fire. Excluded from `cop_today` |

**Why "hybrid only":** on non-hybrid installations the source sensor does not publish `Boiler Operation Demand` or `Hybrid Op. Mode`. All 5 hybrid entities return `unavailable` so no zero-values pollute dashboards or automations.

## 3. Binary sensors (17)

| Entity | Device class | True means |
|---|---|---|
| `binary_sensor.daikin_cycle_ml_compressor_running` | running | Compressor is currently on |
| `binary_sensor.daikin_cycle_ml_heating_active` | heat | Currently in heating mode |
| `binary_sensor.daikin_cycle_ml_cooling_active` | cold | Currently in cooling mode |
| `binary_sensor.daikin_cycle_ml_dhw_active` | — | Currently in DHW mode |
| `binary_sensor.daikin_cycle_ml_defrost_active` | running | Defrost cycle in progress |
| `binary_sensor.daikin_cycle_ml_buh_active` | heat | Backup heater active (attr: `step` = 0/1/2) |
| `binary_sensor.daikin_cycle_ml_pendulum_hourly` | problem | Cycles/hour ≥ threshold |
| `binary_sensor.daikin_cycle_ml_pendulum_daily` | problem | Cycles/day ≥ threshold |
| `binary_sensor.daikin_cycle_ml_short_run` | problem | Last cycle < short-run threshold |
| `binary_sensor.daikin_cycle_ml_short_off` | problem | Off-time < short-off threshold |
| `binary_sensor.daikin_cycle_ml_high_cycle_rate` | problem | Cycles/hour > 1.5× target |
| `binary_sensor.daikin_cycle_ml_setpoint_oscillating` | problem | Setpoint oscillation detected (reversals) |
| `binary_sensor.daikin_cycle_ml_dhw_pendulum` | problem | DHW cycles/hour ≥ DHW threshold |
| `binary_sensor.daikin_cycle_ml_source_stale` | problem | Source sensor not updating (> 60s) |
| `binary_sensor.daikin_cycle_ml_missing_attributes` | problem | Required attributes missing from source |
| `binary_sensor.daikin_cycle_ml_boiler_operation_demand` | running | Boiler producing heat (hybrid only, `unavailable` otherwise) |
| `binary_sensor.daikin_cycle_ml_boiler_dhw_demand` | running | Boiler producing DHW (hybrid only, `unavailable` otherwise) |

**`buh_active`** — `step` attribute indicates which BUH step is active:
- 0 = not active
- 1 = step 1 only
- 2 = steps 1 + 2

**`source_stale`** — the only binary sensor that triggers a critical alert. Bypasses quiet hours.

---

## 4. Update entities (2)

| Entity | Description |
|---|---|
| `update.daikin_cycle_ml_update` | HA-managed HACS update entity for the integration repo |
| `update.daikin_cycle_ml_dashboard_update` | Update entity for dashboard card resources |

Both are HA-native (provided by HACS or the manual update integration). Not part of the integration's own sensor surface.

---

## 5. Services (10)

All under `daikin_cycle_ml` domain. Call via Developer Tools → Actions, or in automations.

### 5.1 `reset_counters`

Reset daily counters to zero.

| Field | Type | Required |
|---|---|---|
| `entry_id` | string | Yes |
| `counters` | string or list | No (default: all) |

Valid `counters`: `cycles_today`, `good_cycles_today`, `bad_cycles_today`, `runtime`, `energy`, or a list of these.

Response: `{"ok": true, "reset": [list of counters]}`.

### 5.2 `export_cycles`

Export cached cycles as JSON or CSV.

| Field | Type | Default |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `days` | int | 30 |
| `format` | string | `json` (or `csv`) |
| `path` | string | `/config/daikin_cycles_export.json` |

Response: `{"ok": true, "path": str, "count": int}`.

### 5.3 `label_cycle`

Attach a user label to a stored cycle for ML training.

| Field | Type | Required |
|---|---|---|
| `entry_id` | string | Yes |
| `cycle_id` | int | Yes |
| `label` | string | Yes |

Response: `{"ok": true, "cycle_id": int, "label": str}`.

### 5.4 `recompute_baseline`

Recompute ML baseline from stored cycles.

| Field | Type | Default |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `days` | int | 30 |

Response: `{"ok": true, "samples": int, "modes": [list]}`.

### 5.5 `run_maintenance`

Run retention prune + optional VACUUM manually.

| Field | Type | Default |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `cycle_retention_days` | int | from options |
| `alert_retention_days` | int | from options |
| `vacuum` | bool | from options |

Response: `{"ok": true, "pruned_cycles": int, "pruned_alerts": int, "vacuumed": bool}`.

### 5.6 `send_test_notification`

Send a test notification. See [ALERTS.md §10.1](ALERTS.md#101-send_test_notification-service) for full details.

| Field | Type | Default |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `message` | string | per alert_kind |
| `alert_kind` | string | `status_summary` |
| `ignore_filters` | bool | `false` |

Response: `{"ok": bool, "target": str, "message": str}`.

### 5.7 `export_cop_hourly`

Export aggregated COP-per-hour rows as JSON or CSV.

| Field | Type | Default |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `days` | int | 30 |
| `mode` | string | (all modes) |
| `format` | string | `json` |
| `path` | string | `/config/daikin_cop_hourly_export.json` |

Response: `{"ok": true, "path": str, "count": int}`.

### 5.8 `import_datasheet`

Import a user datasheet for a non-bundled model, or override a bundled one.

| Field | Type | Required |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `payload` | object | Yes |
| `source_url` | string | No (provenance only) |

**Payload required keys:** `family`, `kw`, `lwt_min`, `lwt_max`, `nom_cop`

**Optional keys:** `bivalent`, `buh_kw`, `refrigerant`, `min_modulation_kw`, `max_flow_lmin`, `noise_db`, `points[]`, `schema_version`

Response: `{"imported": [model_keys], "errors": [messages]}`.

On error, raises repair issue: `datasheet_import_invalid` / `datasheet_schema_unknown` / `datasheet_load_failed`.

### 5.9 `remove_user_datasheet`

Remove a user-imported datasheet. Bundled datasheets cannot be removed.

| Field | Type | Required |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `model_key` | string | Yes |

Response: `{"removed": bool, "model_key": str}`.

### 5.10 `recompute_kmeans`

Force a k-means retrain on the last N days of cycles.

| Field | Type | Default |
|---|---|---|
| `entry_id` | string | auto-resolved if 1 entry |
| `days` | int | 7 |

Response: `{"ok": bool, "n": int, "k": int, "reason": str or absent}`.

On success: fires persistent notification with cluster summary.
On failure: fires persistent notification with reason-derived advice (see `KMEANS_ADVICE_BY_REASON` in [ALERTS.md §kmeans_retrain_stale](ALERTS.md)).

Supports `supports_response: only` — returns data, no side effects if called via UI without response.

---

## 6. Repair issues (8)

All repair issues are currently `is_fixable: false` — they require manual intervention. They appear in Settings → System → Repairs.

### 6.1 `source_stale`

**Trigger:** Source sensor hasn't updated for > 60 seconds.

**Action:** Check ESPAltherma connection — Wi-Fi, MQTT broker, or ESPHome link. Auto-resolves when the sensor publishes again.

### 6.2 `missing_attrs`

**Trigger:** One or more required attributes is missing from the source sensor.

**Action:** Check ESPAltherma `.h` file — one of the required registers is not enabled. If it worked before, the firmware or config changed.

### 6.3 `db_corrupt`

**Trigger:** SQLite integrity check fails.

**Action:** Backup `/config/.storage/daikin_cycle_ml.db`, then delete the file and restart HA. Historical cycles will be lost; new cycles will be recorded normally.

### 6.4 `notify_failed`

**Trigger:** Notify service fails on 3+ consecutive attempts.

**Action:** Verify your `notify_service` entity exists and is configured. Test independently via `notify.your_service` service call. Check service rate limits.

### 6.5 `migration_failed`

**Trigger:** Database schema migration fails on startup.

**Action:** Check HA logs for the specific migration that failed. Usually indicates DB corruption — follow `db_corrupt` procedure.

### 6.6 `datasheet_import_invalid`

**Trigger:** User datasheet import failed validation.

**Action:** Check the payload against the required schema. Common issues: missing `nom_cop`, negative `kw`, malformed `points[]`. The error message in the repair issue tells you exactly which field.

### 6.7 `datasheet_schema_unknown`

**Trigger:** `schema_version` in the imported payload is not supported by this integration version.

**Action:** Check the import payload's `schema_version`. v1.9 supports schema version 1. Imported datasheets with `schema_version: 2+` are rejected until a future release adds support.

### 6.8 `datasheet_load_failed`

**Trigger:** User datasheets can't be read at startup (Store corrupt or inaccessible).

**Action:** Check `/config/.storage/daikin_cycle_ml.user_datasheets` file permissions. If corrupt, delete it — bundled datasheets still work, only user imports are lost.

---

## 7. Entity naming convention

All entities follow `{platform}.daikin_cycle_ml_{key}`:

- Platform: `sensor`, `binary_sensor`, `update`
- Slug: `daikin_cycle_ml`
- Key: `snake_case` identifier

Entity IDs are stable across versions for existing entities. Renaming an entity key is a breaking change and requires a migration (v1.4.0 had one).

Unique IDs follow `daikin_cycle_ml_{key}` — used by HA to detect renames.

### 7.1 Slug customization

In HA, you can rename an entity's display name without changing its `entity_id`. If you rename the `entity_id` (via entity registry), HA records the change and preserves history for the same unique_id.

Renames by the user are preserved across integration upgrades — HA translates the old unique_id to the new display name.

---

## 8. Device class reference

| Device class | Used by | What it means for HA |
|---|---|---|
| `measurement` | COP sensors, quality, thermal power | Value at a point in time |
| `total_increasing` | cycles_today, runtime_today, energy_today | Resets at midnight, HA computes deltas |
| `duration` | source_health, runtime_*, defrost_duration | Duration in seconds |
| `energy` | electrical_*, thermal_* | Energy in kWh (Energy Dashboard compatible) |
| `power` | thermal_power_live | Power in kW |
| `enum` | cop_degradation_status | Fixed set of string states |

All `total_increasing` sensors reset at midnight (calendar day, not 24h window). HA's long-term statistics handle the reset correctly.

---

## 9. Automations quick reference

### 9.1 Trigger on cycle completion

```yaml
trigger:
  - platform: state
    entity_id: sensor.daikin_cycle_ml_last_cycle
action:
  - service: notify.mobile_app_your_phone
    data:
      message: >-
        Cycle {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'duration_min') }} min
        · quality {{ states('sensor.daikin_cycle_ml_last_cycle') }}
        · mode {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'mode') }}
```

### 9.2 Trigger on heating curve advice

```yaml
trigger:
  - platform: state
    entity_id: sensor.daikin_cycle_ml_heating_curve_advice
    to:
      - "lower_lwt"
      - "raise_lwt"
condition:
  - condition: template
    value_template: >-
      {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice', 'betrouwbaarheid') | float(0) >= 0.6 }}
action:
  - service: notify.mobile_app_your_phone
    data:
      message: >-
        {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice', 'state_label') }}
        · step {{ state_attr('sensor.daikin_cycle_ml_heating_curve_advice', 'step_c') }} °C
```

### 9.3 Trigger on source stale

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.daikin_cycle_ml_source_stale
    to: "on"
    for: "00:02:00"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Daikin source stale"
      message: "Check ESPAltherma — sensor not updating"
```

### 9.4 Daily energy summary

```yaml
trigger:
  - platform: time
    at: "23:55:00"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Daikin daily"
      message: >-
        Cycles: {{ states('sensor.daikin_cycle_ml_cycles_today') }}
        · Heating: {{ states('sensor.daikin_cycle_ml_electrical_energy_heating_today') }} kWh
        · COP: {{ states('sensor.daikin_cycle_ml_cop_today') }}
```

### 9.5 Log every anomaly

```yaml
trigger:
  - platform: state
    entity_id: sensor.daikin_cycle_ml_last_cycle
action:
  - condition: numeric_state
    entity_id: sensor.daikin_cycle_ml_last_cycle
    below: 50
  - service: logbook.log
    data:
      name: "Daikin low-quality cycle"
      message: >-
        Score {{ states('sensor.daikin_cycle_ml_last_cycle') }}
        · {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'duration_min') }} min
        · dT {{ state_attr('sensor.daikin_cycle_ml_last_cycle', 'dt_avg_k') }} K
```

### 9.6 Energy Dashboard integration

The 6 energy sensors are directly compatible:

1. Settings → Dashboards → Energy
2. Under **Grid consumption** or **Solar production**, click **Add consumption**
3. Select `sensor.daikin_cycle_ml_electrical_energy_heating_today`
4. Optionally add `sensor.daikin_cycle_ml_thermal_energy_heating_today` under **Return to grid** (as thermal output — the dashboard handles it)

All `total_increasing` state_class ensures correct long-term statistics.

---

## Appendix A — Entity count breakdown

| Category | Enabled | Total |
|---|---|---|
| Sensors | 46 | 50 |
| Binary sensors | 15 | 15 |
| Update | 2 | 2 |
| **Entity registry total** | **63** | **67** |

The `61` mentioned in some documentation counts enabled entities at first install (before helper sensors are enabled manually).

## Appendix B — Related files

| File | Purpose |
|---|---|
| `sensor.py` | All 50 sensor definitions (`SENSOR_DEFS`) |
| `binary_sensor.py` | All 15 binary sensor predicates |
| `services.py` | All 10 service handlers |
| `services.yaml` | Service schemas (UI hints) |
| `repairs.py` | All 8 repair issue handlers |
| `const.py` | `SENSOR_*` / `BINARY_SENSOR_*` constants |
| `coordinator.py` | Where sensor values are computed |

## Appendix C — Version history of entity surface

| Version | Change |
|---|---|
| v1.4.0 | Entity slug renames (`sensor.daikin_cycle_ml_KEY`, where KEY is the snake_case identifier) |
| v1.5.0 | `heating_curve_advice` gained 8 attributes |
| v1.6.0 | `cop_today` breaking change (heating-only), +9 per-mode COP sensors, +3 SPF, +3 datasheets, +3 degradation, +6 runtime, +6 energy, +3 repairs, +1 service |
| v1.7.0 | +4 helper defrost sensors (disabled by default) |
| v1.9.0 | +1 service (`recompute_kmeans`), no new sensor entities |

If you upgraded from before v1.4.0, entity IDs are different — check entity registry for orphaned entities.
