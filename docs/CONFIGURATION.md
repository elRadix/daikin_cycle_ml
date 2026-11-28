# Configuration

The source, the setup wizard, every option and the reconfigure flow. For a
first install with screenshots, start with [Getting started](GETTING_STARTED.md).

## Contents

- [1. Where settings live](#1-where-settings-live)
- [2. Source sensor](#2-source-sensor)
- [3. Setup wizard](#3-setup-wizard)
- [4. Options menu](#4-options-menu)
- [5. Reconfigure](#5-reconfigure)
- [6. Cookbook](#6-cookbook)
- [7. Scheduled jobs](#7-scheduled-jobs)

## 1. Where settings live

| What | Where | Changed with |
|---|---|---|
| Source, model, attribute names | The config entry (data) | Reconfigure |
| Thresholds, sensors, notifications, maintenance | The config entry (options) | Configure |
| Your model values (`kw`, compressor range, points) | The model profile store | Configure → Model profile, Performance card, `set_model_profile` |
| Imported datasheets | `.storage/daikin_cycle_ml.user_datasheets` | `import_datasheet` / `remove_user_datasheet` |

Saving options reloads the integration; nothing is lost (the run in
progress and today's counters are restored).

## 2. Source sensor

ESPAltherma publishes the heat pump's values in one of two ways:

| Source type | What it is | Chosen in the wizard |
|---|---|---|
| Monolithic | ESPAltherma v1: one sensor (`sensor.althermasensors`) with every value as an attribute | *Monolithic entity* |
| Individual | ESPAltherma v2: one entity per value (`sensor.espaltherma_*`) | *Individual entities*, with the entity prefix |
| Auto | Uses whichever is complete, per value | *Auto-detect* |

The wizard detects what is there and suggests a type. The values to
enable in ESPAltherma are listed in
[Getting started §1](GETTING_STARTED.md#1-before-you-start).

**Names.** Spellings differ per model, firmware and language (`(R1T)`
suffixes, `I/U` / `O/U` prefixes, German names, the hybrid and HT
profiles). The integration knows all of these
([Model compatibility](MODEL_COMPATIBILITY.md)). Only when your firmware
uses a name it does not know, choose attribute mode *Manual* and map it.

**Missing values.** A value the cycle detector needs stops detection
until it is published again (a partial publish after a restart). Others
only switch off what uses them, and the `missing_attrs` repair lists them.
The 3-way valve, the pump state, the backup-heater steps and the setpoint
are not needed for detection.

**External sensors.** Optional, under Configure → Device → Sensors:

| Option | Use |
|---|---|
| `power_sensor_entity` | Electrical power of the heat pump in W (a real meter is the best COP source) |
| `buh_power_sensor_entity` | Electrical power of the backup heater, added for COP only |
| `cop_sensor_entity` | A COP sensor of your own (otherwise COP is computed) |
| `indoor_temp_sensor` | Room temperature for the curve advice's comfort guard |

Check the unit: a power sensor in kW or kWh instead of W, or a COP sensor
that reads 0 between runs, makes samples drop silently.

## 3. Setup wizard

### 3.1 Paths

| Your setup | Screens |
|---|---|
| Bundled model, standard names | family → sensor and model → attribute check → cycle → pendulum → quality → notifications → confirm |
| ESPAltherma v2 entities | family → entity prefix → review → sensor and model → ... |
| Names the integration found under another spelling | ... → sensor and model → **diagnose** → attribute check → ... |
| Attribute mode *Manual* | ... → sensor and model → **map attributes** → attribute check → ... |
| Model *Custom* | ... → sensor and model → **heat-pump data** → **attribute mapping** (simple or advanced JSON) → attribute check → ... |

### 3.2 Screens

- **Model family.** Pick the family, or type any code you know: the indoor
  unit (`EHBX08EF6V`), the outdoor unit (`ERGA06EAV3`), both, or family and
  size (`ERGA06`, `EPRA14DAW1`). Empty means the basic profile. What you
  typed is kept as `model_code` (shown in diagnostics).
- **Sensor and model.** The source sensor, the exact model (the list
  names the indoor units sold with each) and the attribute mode.
- **Heat-pump data** (Custom): nominal kW, water temperature range,
  nominal COP, optional points; the same fields as `import_datasheet`.
- **Attribute mapping** (Custom / Manual): one field per value, or a JSON
  object `{"<name the integration uses>": "<your name>"}`.
- **Attribute check.** What was found and what is missing.
- **Cycle detection, Pendulum, Quality, Notifications.** The same options
  as in [§4](#4-options-menu), with their defaults.
- **Confirm.** Creates the entry and the device.

## 4. Options menu

**Settings → Devices & services → Daikin Cycle ML → Configure.**

### 4.1 Device

| Option | Default | Meaning |
|---|---|---|
| `compressor_rps_threshold` | 3 | The compressor counts as running above this speed |
| `fallback_power_threshold_w` | 200 | Running when the power sensor is above this and there is no speed |
| `power_sensor_entity`, `buh_power_sensor_entity`, `cop_sensor_entity`, `indoor_temp_sensor` | | See [§2](#2-source-sensor) |
| `comfort_min_c`, `comfort_max_c` | 20, 24 | Comfort guard of the curve advice |

### 4.2 Pendulum

| Option | Default | Meaning |
|---|---|---|
| `short_run_threshold_min` | 20 | A run shorter than this is a short run |
| `short_off_threshold_min` | 5 | A pause shorter than this is a short pause |
| `short_cycling_window_min`, `short_cycling_min_cycles` | 60, 3 | That many short runs within the window raise `short_cycling_pattern` |
| `pendulum_cycles_per_hour` | 4 | Cycles per hour for `pendulum_hourly` (`high_cycle_rate` at 1.5 ×) |
| `pendulum_cycles_per_day` | 40 | Cycles per day for `pendulum_daily` |
| `dhw_pendulum_cycles_per_hour` | 3 | Hot-water cycles per hour for `dhw_pendulum` |
| `setpoint_oscillation_threshold`, `setpoint_osc_window_min`, `setpoint_osc_min_delta` | 6, 30, 0.5 °C | Setpoint changes with reversals within the window raise `setpoint_osc` |

### 4.3 Quality & ML

| Option | Default | Meaning |
|---|---|---|
| `good_run_threshold_min` | 45 | Run length for full marks |
| `good_dt_threshold_k` | 5 | ΔT for full marks (also the Efficiency card's target, 2-15 K) |
| `good_off_threshold_min` | 20 | Pause for full marks |
| `target_cycles_per_day` | 8 | Used in the advice |
| `buh_penalty_legionella_waived` | on | No backup-heater penalty on legionella runs |
| `adaptive_thresholds_enabled` | off | Use the learned thresholds ([ML §4](ML.md#4-adaptive-thresholds)) |
| `adaptive_min_samples` | 20 | Runs per mode before learned values are used |

### 4.4 Notifications

A sub-menu; see [Alerts](ALERTS.md) for every alert.

| Screen | Options |
|---|---|
| Delivery | `persistent_enabled`, `notify_service` (notify entity or service), `notify_emoji_enabled`, `action_advice_enabled` |
| Quiet hours and status | `quiet_hours_enabled`, `quiet_hours_start` / `_end` (22:00-07:00), `alert_aggregation_minutes` (30), `status_update_enabled`, `status_update_interval_hours` (24) |
| Content and language | The seven alert groups, `notification_language` (`auto`, `en`, `nl`, `fr`) |
| Per-alert enables | One switch per alert ([Alerts §5](ALERTS.md#5-switching-alerts-off)) |
| Test notifications | Send one alert or all of them |

### 4.5 Advanced

| Option | Default | Meaning |
|---|---|---|
| `dhw_present` | `auto` | Hot-water tank: `auto` (detected), `always`, `never` (see [§6.4](#64-bivalent-and-no-hot-water-tank)) |
| `retention_enabled` | on | Daily maintenance at 03:00 |
| `cycle_retention_days` | 90 | Older cycles are rolled up and removed |
| `alert_retention_days` | 90 | Older alert records are removed |
| `vacuum_enabled` | on | VACUUM after pruning |
| `daily_summary_live_enabled` | on | Update the daily summary as each cycle closes |
| `season_start_month` | 10 | First month of the heating season (SPF, season reports) |
| `degree_day_scheme` | `auto` | Degree days used to compare report periods: `auto` (country of Home Assistant), `nl18`, `nl18w`, `be1515`, `be165`, `fr18`, `fr17`, `fr15` ([Reports](REPORTS.md#5-degree-days)) |

### 4.6 COP calculation

Electrical input, highest priority first:

1. your **power sensor** (`power_sensor_entity`, plus `buh_power_sensor_entity`);
2. **ESPAltherma 2.0 Stats** (`Stats: Electrical input estimated (kW)`), detected automatically;
3. **estimate from the inverter current**: `INV primary current × 230 V ×
   supply_phases` + the backup heater (`buh_step1_kw`, `buh_step2_kw`,
   default 3 kW each) + 100 W for pump, fan and electronics.

`supply_phases` (1 or 3) and the backup-heater steps only matter for the
estimate. `sensor.daikin_cycle_ml_electrical_power_estimated` shows the
value and, in `source`, which path was used.

### 4.7 Model profile

Your own values for the model chosen in setup. They win over the
datasheet everywhere (COP against the datasheet, the alert, every card).
Empty = use the datasheet or the learned value.

| Field | Meaning |
|---|---|
| `kw` | Nominal heat output, when your unit differs from the datasheet |
| `rps_min`, `rps_max` | Compressor speed range. Learned from steady runs of 20 min or more over 60 days (5th percentile of run means, 95th of run peaks) after 20 runs |
| `points` | Datasheet points: `t_out`, `t_lwc`, `hmax` (maximum heat), `cop` |

**Maximum heat per point:** your value wins; else an estimate from the
A7/W35 maximum (1 % less per K outdoor below 7 °C, 0.5 % less per K water
above 35 °C), never below a Daikin rating point or what your heat pump
delivered at 90 % of its top speed or more.

Every value shows its source on `hp_specs` (`datasheet`, `learned`,
`manual`). The Performance card and the service `set_model_profile` edit
the same profile (`null` removes a value, `reset: true` starts over).

## 5. Reconfigure

**⋮ → Reconfigure** on the integration:

- **Basic:** change the source sensor or the model, keep everything else.
- **Full:** run the whole wizard again with the current values filled in.

History stays; the entry id and entity ids do not change.

## 6. Cookbook

### 6.1 Model not in the list

Type the indoor or outdoor code in the family field first. Still nothing:
choose the basic profile, or Custom with your own data, and add points
later in Configure → Model profile.

### 6.2 Firmware with other attribute names

Attribute mode *Manual* and map only the names that differ; leave the
others empty.

### 6.3 Only the important alerts

Keep the groups `data_quality` and `component_health` on, switch the
others off (Content and language), and turn on quiet hours.

### 6.4 Bivalent and no hot-water tank

**Boiler signals.** In ESPAltherma enable `Bivalent Operation`,
`Boiler Operation Demand` and `Boiler DHW Demand` (German firmware:
`Bivalenter Betrieb`). When the source publishes `Bivalent Operation`,
boiler-only periods give no heat-pump COP samples and no short-cycle or
pendulum alerts, as on an EVLQ hybrid. Without it the boiler values are
ignored.

| Setup | `dhw_present` |
|---|---|
| Heat pump with a hot-water tank | `auto` |
| No hot-water tank (for example bivalent direct, space heating only) | `never` |
| The boiler heats the tank but the heat pump sees its sensor | `always` |

`binary_sensor.daikin_cycle_ml_dhw_installed` (diagnostic) shows the
result. The `dhw_missing_suspect` repair appears when no tank is detected
but the history has hot-water cycles.

### 6.5 Curve advice too eager

Raise `comfort_min_c` so it lowers less, or lower `comfort_max_c` so it
raises less. Link the room thermostat or a room sensor
(`indoor_temp_sensor`) so the comfort guard works from the real room.

### 6.6 Clusters keep failing

`daikin_cycle_ml.recompute_kmeans` with `days: 28`; each mode needs 12
cycles. The result is sent as a notification.

## 7. Scheduled jobs

| Job | When |
|---|---|
| Read the source | Every 30 s |
| Save the ML state | Every 6 h and on stop |
| Maintenance (retention, rollups, VACUUM) | Daily 03:00 |
| Cluster retrain | Sunday 04:00 |
| Status update | Every `status_update_interval_hours` when enabled |

`run_maintenance`, `recompute_baseline` and `recompute_kmeans` run them on
demand.
