# Troubleshooting

Symptom first, then what to check. Start with [§1](#1-first-steps) for
any problem.

## Contents

- [1. First steps](#1-first-steps)
- [2. Setup](#2-setup)
- [3. Cycle detection](#3-cycle-detection)
- [4. Sensors and values](#4-sensors-and-values)
- [5. COP and energy](#5-cop-and-energy)
- [6. Alerts and notifications](#6-alerts-and-notifications)
- [7. Hybrid and bivalent](#7-hybrid-and-bivalent)
- [8. Database](#8-database)
- [9. Cards](#9-cards)
- [10. Reporting a problem](#10-reporting-a-problem)

## 1. First steps

Three entities tell you whether the integration gets its data:

| Entity | Healthy |
|---|---|
| `sensor.daikin_cycle_ml_source_health` | below 30 s |
| `binary_sensor.daikin_cycle_ml_source_stale` | off |
| `binary_sensor.daikin_cycle_ml_missing_attributes` | off |

Then:

- **Repairs:** Settings → System → Repairs lists what the integration
  found ([Entities §6](ENTITIES.md#6-repair-issues)).
- **Diagnostics:** **Download** or **Copy** at the bottom of a native card
  shows what the integration sees ([Diagnostics](DIAGNOSTICS.md)).
- **Logs:** Settings → System → Logs, filter `daikin_cycle_ml`. For more
  detail, temporarily:

```yaml
logger:
  logs:
    custom_components.daikin_cycle_ml: debug
```

## 2. Setup

| Symptom | Check |
|---|---|
| The wizard says values are missing | Enable them in the ESPAltherma definition and reboot the ESP ([Getting started §1](GETTING_STARTED.md#1-before-you-start)); check in Developer tools → States |
| *Unknown model* / *no datasheet* | Type the outdoor or indoor code, or family and size; or pick the basic profile |
| Source sensor not found | ESPAltherma v1: pick the sensor with the attributes; v2: choose *Individual entities* and the right prefix |
| Integration "not loaded" / "setup failed" | Settings → System → Logs for the error; restart Home Assistant |
| "Invalid handler specified" | Remove backup folders from `/config/custom_components/` |
| No entities after setup | Restart Home Assistant; entities disabled by default are under *+N disabled entities* on the device |

## 3. Cycle detection

| Symptom | Check |
|---|---|
| No cycles | Is the compressor running (`thermal_power_live` above 0)? Is the speed above `compressor_rps_threshold` (Configure → Device, default 3)? Source fresh and complete (§1)? The first cycle closes when the compressor stops |
| Many 2-5 min runs while the heat pump runs steadily | The compressor idles near the threshold: raise `compressor_rps_threshold` a little |
| Hours-long runs | Normal in steady weather: a modulating heat pump runs long. Runs are split at a heating ↔ hot-water switch and capped at 48 h |
| Mode `unknown` | Enable `Operation Mode` or `I/U operation mode` |
| Hot water recorded as heating | Enable the 3-way valve; without a tank, set *Hot-water tank* to `never` (Configure → Advanced) |
| Detection paused after a restart | A value the detector needs is missing in a partial publish; it resumes on the next complete publish |

## 4. Sensors and values

| Symptom | Check |
|---|---|
| `unknown` while the compressor is off | Expected for live values (`thermal_power_live`, `current_cycle`) |
| COP sensors empty | They need heating samples: flow, ΔT and power (or ESPAltherma 2.0 stats) while the compressor runs |
| `heating_curve_advice` on `no_data` or `keep` | Read `reason`: no recent heating, `buh_active`, `within_deadband`, `room_warm_enough`, `low_confidence`, `no_indoor_sensor` ([Entities §2.6](ENTITIES.md#26-heating-curve-advice)) |
| `setpoint_oscillating` on without real oscillation | Setpoint jitter: raise `setpoint_osc_min_delta` (Configure → Pendulum) |
| "Today" shows hundreds of hours, starts or defrosts | ESPAltherma 2.0 without a clock: its "today" counters never reset. The integration then uses its own counts (`source: computed`); give the ESP an NTP server and time zone |
| Learned thresholds empty | They need 20 runs per mode |

## 5. COP and energy

| Symptom | Check |
|---|---|
| COP far too high or low | The power source: a real meter in W is best. A COP sensor above 11 is ignored; samples below 1 (start-up) or above the physical limit are flagged and left out of every mean |
| COP reads about 20 % high with a template COP sensor | Clear `cop_sensor_entity` and let the integration compute it; add `buh_power_sensor_entity` if the backup heater has its own meter |
| `cop_vs_datasheet_pct` far from 0 | It compares with your datasheet at the same outdoor and water temperature; a wrong model gives a wrong reference (Reconfigure) |
| `cop_degradation` after a weather change | Check `cop_trend_30d`; a flat trend means weather, not wear |
| Energy dashboard shows nothing | Add the `electrical_energy_*_today` sensors as consumption; they are `total_increasing` |

## 6. Alerts and notifications

| Symptom | Check |
|---|---|
| Nothing on the phone | A notify target set (Configure → Notifications → Delivery)? Group and per-alert switch on? Quiet hours? Send a test |
| Only in the sidebar | The `notify_failed` repair names the error; test the notify entity on its own |
| Too many alerts | Raise the thresholds (Configure → Pendulum), lengthen the repeat window, or switch the group off |
| Wrong language | Configure → Notifications → Content → *Notification language* |
| Woken at night | Only `source_stale` passes quiet hours: check the ESP's Wi-Fi |
| The "send all" test shows one fewer in the sidebar | Home Assistant merges sidebar notifications in a burst; the notify target gets all |

Details: [Alerts](ALERTS.md).

## 7. Hybrid and bivalent

| Symptom | Check |
|---|---|
| Hybrid sensors missing | They exist only for the EVLQ hybrid model with ESPAltherma's `ALTHERMA(HYBRID).h`; Reconfigure to the EVLQ model (indoor EHYHBH / EHYHBX codes map to it) |
| Hot-water tank reads -40.7 °C | The boiler makes hot water and the probe is disconnected; values below -20 °C are ignored |
| No short-cycle alerts while the boiler runs | Expected: a boiler run is not a heat-pump cycle |
| Bivalent boiler periods counted as heat pump | Enable `Bivalent Operation` in ESPAltherma ([Configuration §6.4](CONFIGURATION.md#64-bivalent-and-no-hot-water-tank)) |
| Repair "DHW tank not detected" | Set *Hot-water tank* (Configure → Advanced): `never` without a tank, `always` when you have one |

## 8. Database

The database is `/config/.storage/daikin_cycle_ml_<entry>.db`, one per heat
pump. See [Database](DATABASE.md).

| Symptom | Check |
|---|---|
| `db_corrupt` repair | Back up the file, check with `sqlite3 <file> "PRAGMA integrity_check"`; if it fails, delete it and restart (history is lost) |
| `migration_failed` repair | Keep the file, open an issue with the log lines; deleting the file and restarting starts fresh |
| `db_retention_warning` | Maintenance did not run: `retention_enabled` on? Run `daikin_cycle_ml.run_maintenance` |
| Database large | Lower `cycle_retention_days`, keep `vacuum_enabled` on, run maintenance |
| "database is locked" for a moment | VACUUM in progress; it clears by itself |
| Start the ML over without losing cycles | `daikin_cycle_ml.recompute_baseline` relearns from the stored cycles |

## 9. Cards

| Symptom | Check |
|---|---|
| A native card shows an old version | Refresh the browser once (`Ctrl`+`Shift`+`R`; in the app, pull down) |
| `Custom element doesn't exist: daikin-…-card` | The integration serves the native cards once it is set up (Settings → Devices & services lists Daikin Cycle ML). Restart, refresh; Companion App: Settings → Companion App → Troubleshooting → Reset frontend cache. No other custom card is needed |
| Native card shows "entities not found" | Several heat pumps: choose one in the card editor. Otherwise check the integration is loaded |
| Values from two heat pumps mixed | Choose the heat pump in the card editor |
| YAML card empty or "—" | Re-paste the latest YAML from `dashboard/cards/`; check the custom cards it needs are installed ([Cards](../dashboard/cards/README.md)) |

## 10. Reporting a problem

1. **Download** or **Copy** the diagnostics at the bottom of a native card
   (it leaves out the list of your other integrations).
2. Note what you saw, what you expected, and when.
3. Open an [issue](https://github.com/elRadix/daikin_cycle_ml/issues/new/choose)
   and attach the file. Read it first if your entity names matter to you:
   secrets and location are removed, names are not.

Questions: [discussions](https://github.com/elRadix/daikin_cycle_ml/discussions)
or the Tweakers ESPAltherma topic.
