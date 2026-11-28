# Entities

Every sensor, binary sensor, service and repair issue of Daikin Cycle ML.
Automations to copy: [Recipes](RECIPES.md).

## Contents

- [1. Overview](#1-overview)
- [2. Sensors](#2-sensors)
- [3. Binary sensors](#3-binary-sensors)
- [4. Entity ids and languages](#4-entity-ids-and-languages)
- [5. Services](#5-services)
- [6. Repair issues](#6-repair-issues)

## 1. Overview

| Kind | Count | Notes |
|---|---|---|
| Sensors | 51 | 3 only on hybrid installs |
| Binary sensors | 20 | 2 only on hybrid installs; 3 diagnostic ones are off by default |
| Services | 14 | Developer tools → Actions, or in automations |
| Repair issues | 11 | Settings → System → Repairs |

- All entities belong to one device per heat pump (one config entry each).
  With several heat pumps, every service takes `entry_id`.
- Hybrid-only entities are created only when the source is an EVLQ hybrid.
- Off by default (diagnostic): `dhw_installed`, `boiler_operation_demand`,
  `boiler_dhw_demand`. Enable them on the device page.
- Attributes that grow with time (`daily_summary_recent`,
  `cop_curve_recent`, `alerts_today`, `hp_specs`, `heating_curve_advice`)
  are not written to the recorder; the cards read them live.
- `*_today` values cover the calendar day and survive a restart.

## 2. Sensors

Entity ids are shown for an English install
(`sensor.daikin_cycle_ml_<key>`), see [§4](#4-entity-ids-and-languages).

### 2.1 Cycles

| Key | Unit | Meaning |
|---|---|---|
| `cycle_state` | | `idle` or `running` |
| `current_cycle` | | The run in progress: mode, start, duration, live score |
| `last_cycle` | score | Quality (0-100) of the last closed cycle; attributes below |
| `cycles_today` | | Cycles started today, short transient runs included (`non_transient_cycles_today` without them). The daily summary's `runs` also counts a run carried over from yesterday; `compressor_starts_today` (native) counts every start the unit reports, restarts inside a run included |
| `quality_today` | score | Mean quality of today's cycles |
| `compressor_starts_today` | | Compressor starts today |
| `learned_thresholds` | min | The short-run threshold in use (learned, never below half the configured value); attributes `short_run_learned_min`, `good_off_min`, `target_cycles_per_day` |
| `alerts_today` | | Alerts sent today; attributes per alert type with times |
| `daily_summary_recent` | | Days with data; attributes `days` (per day and mode), `totals_by_mode`, `events_by_day` (backup heater minutes, defrosts) |
| `source_health` | s | Seconds since the source last updated |

**`last_cycle` attributes:** `start_ts`, `end_ts`, `duration_min`, `mode`,
`dt_avg_k`, `dt_max_k`, `rps_avg`, `rps_max`, `outdoor_temp`,
`thermal_kw_avg`, `buh_used`, `buh_min`, `defrost_used`, `defrost_min`,
`quality_penalties` (points per reason, see [ML](ML.md)) and `cluster`.

### 2.2 Runtime and energy

| Key | Unit | Meaning |
|---|---|---|
| `runtime_compressor_today` | s | Compressor runtime |
| `runtime_buh_today` | s | Backup-heater runtime. `buh_energy_kwh_est`: from the backup-heater meter when one is set (`buh_energy_source: power_meter`), else step time × the step powers in Configure (`computed`) |
| `defrost_count_today` | | Defrosts |
| `defrost_duration_today` | s | Time in defrost |
| `duty_cycle_today` | % | Share of the day the compressor ran |
| `electrical_energy_heating_today` | kWh | Electricity for heating |
| `electrical_energy_dhw_today` | kWh | Electricity for hot water |
| `electrical_energy_cooling_today` | kWh | Electricity for cooling |
| `electrical_energy_total_today` | kWh | All electricity |
| `thermal_energy_heating_today` | kWh | Heat delivered for heating |
| `thermal_energy_cooling_today` | kWh | Cooling delivered |

The energy sensors are `total_increasing` and reset at midnight: the
Energy dashboard reads them directly.

### 2.3 Live power

| Key | Unit | Meaning |
|---|---|---|
| `thermal_power_live` | kW | Heat output now: flow × 4.18 × ΔT / 60, else power × COP. Attributes: the inputs (`input_power_w`, `input_cop`, `input_flow_lmin`, `input_dt_k`, `input_rps`, `calculation_source`) and live temperatures (`lwt_c`, `lwt_after_buh_c`, `return_c`, `outdoor_c`, `lw_setpoint_c`, `room_c`, `room_setpoint_c`, `refrigerant_liquid_c`) |
| `electrical_power_estimated` | W | Electrical input now (diagnostic). `source`: `power_meter`, `espaltherma_v2_stats`, `inverter_estimated_v1` or `none`; see [Configuration](CONFIGURATION.md) for the priority |

### 2.4 COP

| Key | Unit | Meaning |
|---|---|---|
| `cop_today` | COP | Heating COP today, from every COP sample since midnight |
| `cop_combined_today` | COP | Heating, hot water and cooling together today |
| `cop_mean_day`, `cop_mean_week`, `cop_mean_month` | COP | Mean COP over 24 h, 7 and 30 days, from the hourly table (incomplete and outlier hours left out, so the counts differ from `cop_today`); `by_mode` per mode |
| `cop_heating_day` / `_week` / `_month` | COP | Heating COP per period (own mode only) |
| `cop_dhw_day` / `_week` / `_month` | COP | Hot-water COP per period |
| `cop_cooling_day` / `_week` / `_month` | COP | Cooling COP per period |
| `cop_curve_recent` | | Hourly COP points of the last 48 h (attribute `points`) |
| `spf_season` | SPF | Seasonal performance factor since the season start month (option) |
| `spf_ytd` | SPF | Since 1 January |
| `scop_running_365d` | SPF | Rolling 365 days |
| `last_month_report` | COP | COP of the last finished month; attributes `period`, `el_kwh`, `th_kwh`, `el_per_dd`, `cop_vs_previous_pct`, `cop_vs_last_year_pct`, `verdict_vs_previous`, `verdict_vs_last_year`, `coverage_days` ([Reports](REPORTS.md)) |

COP values leave out samples flagged by the physics checks, start-up
transients and boiler periods (hybrid / bivalent). Day, week and month
means and SPF include backup-heater time: that is what you pay for.

### 2.5 Against the datasheet

| Key | Unit | Meaning |
|---|---|---|
| `cop_vs_datasheet_pct` | % | Live COP against the datasheet COP at the same outdoor and water temperature; 0 = on spec. Attributes `cop_datasheet_live`, `reference_point`, `reference_distance_k`, `band` (`on_spec`, `below_spec`, `critical`) |
| `cop_normalized_a7w35` | COP | Your COP scaled to A7/W35 with the datasheet's own ratio |
| `hp_specs` | | Model data in use (diagnostic): datasheet values with their source, your model profile, learned compressor range and maximum heat, `target_dt_k`; with the [P1/P2 bridge](P1P2.md#5-field-settings) also `installer_settings` and `installer_target_dt_k` |
| `cop_degradation_status` | | `none`, `info`, `warning` or `critical` |
| `cop_degradation_week_pct` | % | This week against last week at matching outdoor temperatures; negative = worse |
| `cop_trend_30d` | % | 30-day regression trend |

The `cop_vs_datasheet_low` alert fires when the mean of a steady hour of
heating is more than 10 % below spec ([Alerts](ALERTS.md)).

### 2.6 Heating-curve advice

`heating_curve_advice` states: `keep`, `lower_lwt`, `raise_lwt`,
`no_data`.

| Attribute | Meaning |
|---|---|
| `state_label` | The advice in your language, with the step |
| `step_c`, `delta_c` | Suggested step (1-3 °C) and measured minus optimal water temperature |
| `huidige_lwt`, `optimale_lwt` | Measured and best-COP water temperature for the current outdoor band |
| `huidige_setpoint`, `doel_setpoint` | Setpoint now and suggested |
| `besparing_cop_pct` | Expected COP gain |
| `betrouwbaarheid` | Confidence 0-1 |
| `bucket`, `samples`, `buckets` | Current outdoor band, its samples, all bands |
| `tracking_error` | Water temperature minus setpoint |
| `comfort_cap`, `err_indoor` | Comfort guard and room error |
| `reason` | Why: `no_recent_heating`, `dhw_active`, `buh_active`, `within_deadband`, `room_warm_enough`, `comfort_floor_reached`, `comfort_ceiling_reached`, `unit_tracking_behind`, `low_confidence`, `no_indoor_sensor` |

Raising is only advised when the room is more than 0.5 K below its
setpoint (or below `comfort_min_c` without a room setpoint); lowering never
while the room is cold. The room comes from `indoor_temp_sensor`, else the
controller's room sensor. Samples taken with the backup heater on are left
out.

### 2.7 Hybrid (EVLQ only)

| Key | Unit | Meaning |
|---|---|---|
| `hybrid_mode` | | `H/P only`, `Hybrid` or `Boiler only` |
| `boiler_efficiency_cop` | COP | The controller's boiler efficiency (information only) |
| `boiler_contribution_today_pct` | % | Share of today's samples with the boiler firing |

Bivalent installs that publish `Bivalent Operation` get the boiler
handling, not these sensors.

## 3. Binary sensors

| Key | Class | On when |
|---|---|---|
| `compressor_running` | running | The compressor runs |
| `heating_active` | heat | Heating |
| `cooling_active` | cold | Cooling |
| `dhw_active` | | Hot water |
| `defrost_active` | running | Defrosting |
| `buh_active` | heat | Backup heater on (attribute `step`: 0, 1, 2) |
| `pendulum_hourly` | problem | Cycles per hour at or above the threshold |
| `pendulum_daily` | problem | Cycles per day at or above the threshold |
| `short_run` | problem | The last run was shorter than the short-run threshold |
| `short_off` | problem | The last pause was shorter than the short-off threshold |
| `short_cycling_pattern` | problem | Several short runs within the short-cycling window |
| `high_cycle_rate` | problem | Cycles per hour above 1.5 × the pendulum threshold |
| `dhw_pendulum` | problem | Hot-water cycles per hour at or above the threshold |
| `setpoint_oscillating` | problem | The water setpoint keeps reversing |
| `cop_physically_impossible` | problem | COP samples above the physical limit were rejected today |
| `source_stale` | problem | The source has not updated for 60 s (critical: passes quiet hours) |
| `missing_attrs` | problem | Required values are missing from the source (id `..._missing_attributes`) |
| `dhw_installed` | | A hot-water tank is detected (diagnostic, off by default) |
| `boiler_operation_demand` | running | Boiler heating (hybrid, diagnostic, off by default) |
| `boiler_dhw_demand` | running | Boiler making hot water (hybrid, diagnostic, off by default) |

## 4. Entity ids and languages

Home Assistant builds entity ids from the translated entity name:
`sensor.daikin_cycle_ml_cycle_state` on an English install,
`sensor.daikin_cycle_ml_cyclus_status` on a Dutch one,
`sensor.daikin_cycle_ml_etat_du_cycle` on a French one. A custom device
name changes the prefix. Unique ids never change, so renaming an entity
keeps its history; the native cards find their entities by unique id in
any language.

## 5. Services

All in the `daikin_cycle_ml` domain. `entry_id` selects the heat pump; it
may be left out when there is only one (except where marked required in
the UI).

| Service | Fields | What it does |
|---|---|---|
| `reset_counters` | `counters` (optional list) | Resets today's counters, all or the ones listed |
| `export_cycles` | `days` (30), `format` (`json` / `csv`) | Writes stored cycles to `/config` |
| `export_cop_hourly` | `days` (30), `mode`, `format` | Writes hourly COP rows to `/config` |
| `label_cycle` | `cycle_id`, `label` | Labels a stored cycle |
| `recompute_baseline` | `days` (7) | Relearns the ML baseline, adaptive thresholds and clusters from stored cycles |
| `recompute_kmeans` | `days` (28) | Retrains the clusters and reports the result |
| `run_maintenance` | `cycle_retention_days`, `alert_retention_days`, `vacuum` | Prunes old rows and optionally runs VACUUM now |
| `send_test_notification` | `message`, `target`, `alert_kind`, `ignore_filters` | Sends a test; `alert_kind: all_alerts` sends one of every alert ([Alerts](ALERTS.md)) |
| `set_model_profile` | `fields`, `points`, `reset` | Sets your own datasheet values or points for the model; empty = back to the datasheet (the Performance card uses it) |
| `import_datasheet` | `payload`, `source_url` | Imports a datasheet for a model (required: `family`, `kw`, `lwt_min`, `lwt_max`, `nom_cop`; optional `points` and more) |
| `remove_user_datasheet` | `model_key` | Removes an imported datasheet |
| `assign_legacy_db` | `target_entry_id` | Moves a database to another heat pump (several heat pumps from before v1.10) |
| `archive_legacy_db` | | Renames the database to `.legacy-<time>` and starts a new one |
| `export_legacy_db` | | Exports every table to CSV in `/config/daikin_cycle_ml_export_<entry>_<time>/` |
| `get_report` | `period_type` (`month`), `period`, `mode` (`all`), `compare` (`previous` / `last_year` / `none`), `history` (12), `include_days` | Returns one week / month / year / season with its comparison, trend and history (the Reports card uses it; [Reports](REPORTS.md)) |
| `export_reports` | `table` (`periods` / `days`), `period_type`, `mode`, `first_day`, `last_day`, `format` | Returns the stored reports as JSON or CSV |
| `rebuild_reports` | `full` | Builds the reports now; `full` clears and rebuilds them from the kept history |

Services that return data (`export_*`, `recompute_*`, `set_model_profile`, `get_report`, `rebuild_reports`)
can be called with *Return response* in Developer tools.

## 6. Repair issues

| Issue | Raised when | What to do |
|---|---|---|
| `source_stale` | The source has not updated for 60 s | Check the ESP board, Wi-Fi and MQTT; clears by itself |
| `missing_attrs` | Required values are missing from a v1 source | Enable them in the ESPAltherma definition ([Getting started §1](GETTING_STARTED.md#1-before-you-start)) |
| `espaltherma_v2_missing_attrs` | Required ESPAltherma v2 entities are missing | Enable them in the ESPAltherma v2 web UI, restart ESPAltherma |
| `dhw_missing_suspect` | No hot-water tank is detected, but the history has hot-water cycles | Ignore without a tank; otherwise check the source, or set *Hot-water tank* to *always* (Configure → Advanced) |
| `model_mismatch` | The unit code ESPAltherma reports (`Unit model`) does not fit the configured model | Reconfigure and pick one of the models named in the repair; clears by itself within an hour |
| `notify_failed` | The notify target failed repeatedly | Check the notify entity or service |
| `db_corrupt` | The database integrity check failed | Back up and delete `daikin_cycle_ml_<entry>.db`, restart ([Database](DATABASE.md)) |
| `migration_failed` | A database migration failed | See [Troubleshooting §8](TROUBLESHOOTING.md#8-database) and open an issue with the log |
| `legacy_db_multi_entry` | A pre-v1.10 shared database was given to the oldest of several heat pumps | Correct with `assign_legacy_db`, `archive_legacy_db` or `export_legacy_db` |
| `datasheet_import_invalid` | `import_datasheet` got invalid data | The repair names the field |
| `datasheet_schema_unknown` | The imported datasheet has an unknown `schema_version` | Use `schema_version: 1` |
| `datasheet_load_failed` | The stored datasheets cannot be read | Bundled datasheets still work; remove `/config/.storage/daikin_cycle_ml.user_datasheets` to reset |
