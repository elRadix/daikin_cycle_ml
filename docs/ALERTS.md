# Alerts and notifications

What each alert means, when it fires, how it reaches you and how to tune
it. Settings are under **Configure → Notifications**.

## Contents

- [1. Overview](#1-overview)
- [2. The alerts](#2-the-alerts)
- [3. Delivery](#3-delivery)
- [4. Quiet hours, aggregation and repeat windows](#4-quiet-hours-aggregation-and-repeat-windows)
- [5. Switching alerts off](#5-switching-alerts-off)
- [6. Testing](#6-testing)
- [7. Status updates](#7-status-updates)
- [8. Troubleshooting](#8-troubleshooting)

## 1. Overview

- **21 alert types**: 19 follow a binary sensor or a computed check, plus
  the standalone `cop_low` and `stooklijn_advies` (heating-curve advice).
- Each alert has a **level**: ℹ️ *no action needed*, ⚠️ *keep an eye on
  it*, ⛔ *action needed*. Only *action needed* passes quiet hours; today
  that is `source_stale`.
- Every message says what was seen, what it means for the heat pump and,
  when **action advice** is on, what to do. English, Dutch or French
  (Configure → Notifications → Content; *auto* follows Home Assistant).
- Hybrid installs: a boiler-only period never raises a heat-pump cycling
  alert.
- Alerts only notify; they never change the heat pump.

## 2. The alerts

| Alert | Level | Group | Repeat | Fires when |
|---|---|---|---|---|
| `pendulum_hourly` | ⚠️ | pendulum | 60 min | Cycles in the last hour above `pendulum_cycles_per_hour` (4) |
| `pendulum_daily` | ⚠️ | pendulum | 24 h | Cycles today above `pendulum_cycles_per_day` (40) |
| `dhw_pendulum` | ⚠️ | pendulum | 60 min | Hot-water cycles per hour above `dhw_pendulum_cycles_per_hour` (3) |
| `short_run` | ℹ️ | short_cycle | 30 min | The last run was shorter than `short_run_threshold_min` (20) |
| `short_off` | ℹ️ | short_cycle | 30 min | The pause before the last run was shorter than `short_off_threshold_min` (5) |
| `short_cycling_pattern` | ⚠️ | short_cycle | 60 min | `short_cycling_min_cycles` (3) short runs within `short_cycling_window_min` (60) |
| `high_cycle_rate` | ⚠️ | short_cycle | 60 min | Starts in the last hour above 1.5 × `pendulum_cycles_per_hour` |
| `setpoint_osc` | ℹ️ | setpoint | 30 min | The water setpoint keeps reversing (6 changes in 30 min with reversals) |
| `ml_anomaly` | ℹ️ | ml | 60 min | A cycle unlike the usual ones at that outdoor temperature ([ML §3](ML.md#3-behaviour-baseline-and-ml_anomaly)) |
| `energy_daily_anomaly` | ⚠️ | ml | 24 h | Yesterday's electricity 2 σ and 2 kWh above the baseline (after 7 days) |
| `kmeans_retrain_stale` | ℹ️ | ml | 24 h | The clusters were not retrained for 14 days |
| `cop_low` | | cop_stooklijn | 30 min | Today's heating COP below 2.5 (3 samples or more) |
| `cop_degradation` | ⚠️ | cop_stooklijn | 24 h | COP this week more than 15 % below last week at matching outdoor temperatures |
| `cop_vs_datasheet_low` | ℹ️ | cop_stooklijn | 24 h | A steady hour of heating more than 10 % below the datasheet |
| `stooklijn_advies` | | cop_stooklijn | 7 days | Heating-curve advice with confidence 0.7 or more |
| `defrost_excessive` | ⚠️ | component_health | 24 h | More defrosts in 7 days than the weather allows (below) |
| `buh_excessive` | ⚠️ | component_health | 24 h | Backup heater more than 15 % of the compressor time over 7 days |
| `db_retention_warning` | ⚠️ | component_health | 24 h | More than 100 rows older than the retention period (cleanup not running) |
| `source_stale` | ⛔ | data_quality | 60 min | No update from ESPAltherma for 60 s |
| `missing_attributes` | ⚠️ | data_quality | 24 h | Required values missing from the source |
| `cop_physically_impossible` | ⚠️ | data_quality | 24 h | COP samples above the physical limit were rejected |

Defaults in brackets are options (Configure → Pendulum).

### 2.1 Notes per alert

**Pendulum and short runs.** Frequent starts cost efficiency and wear the
compressor. Check the curve (water temperature too high for the
weather), the room thermostat hysteresis and the minimum run time. A
single short pause is usually a hot-water switch or a defrost: the heat
pump keeps its own minimum pause. Segments of one run (a heating ↔
hot-water switch, the 48 h cap) never count as short runs or pauses.

**`ml_anomaly`.** The message names the value that stood out
(`top_dim_name`). One alert after a settings change is expected; repeated
alerts on the same value deserve a look. See [ML](ML.md#8-reading-the-results).

**`cop_vs_datasheet_low`.** The reference is the datasheet COP at the
live outdoor and water temperature (the nearest datasheet points, bridged
with the Carnot ratio). It is judged on the mean of a steady hour:
heating for 15 minutes or more, no defrost, no backup heater, at least 20
ticks. Models with only an A7/W35 point use the Carnot estimate from that
point. Basic profile and Custom without points have no reference.

**`cop_degradation`.** Compares this week with last week at matching
outdoor temperatures, without backup-heater and defrost time. Keep the
outdoor unit free of leaves and snow (never scrape ice: it defrosts
itself) and check that the curve or room temperature was not raised. If
it lasts two weeks, or `cop_trend_30d` is negative too, ask the
installer.

**`defrost_excessive`.** The weekly limit follows the weather: the
running hours of the last 7 days (heating and hot water) times the highest
plausible defrost rate at that outdoor temperature, times 1.5, at least
10.

| Outdoor (mean of the running hour) | Defrosts per running hour |
|---|---|
| below -7 °C | 1.0 |
| -7 to -2 °C | 1.5 |
| -2 to 3 °C | 2.0 |
| 3 to 7 °C | 1.5 |
| 7 to 10 °C | 0.5 |
| 10 °C and warmer | 0.1 |

It also fires when 2 or more days at 10 °C or warmer had more than 2
defrosts. Each start of *Defrost Operation* counts once. The option
`defrost_7d_count_threshold` replaces the dynamic limit by a fixed count.
Diagnostics show the limit under `defrost.limit_7d`.

**`buh_excessive`.** Backup-heater minutes divided by compressor minutes
over 7 days. The backup heater is meant for cold starts and defrost
recovery; a high share points at an undersized heat pump, very cold
weather below its range, or long defrosts.

**`source_stale`.** Without data nothing else works, so this alert passes
quiet hours. Check the ESP board, Wi-Fi and MQTT; a short reboot clears
it by itself.

**`missing_attributes`.** Lists the missing values. Enable them in the
ESPAltherma definition ([Getting started §1](GETTING_STARTED.md#1-before-you-start)).
Sent at most once a day.

**`kmeans_retrain_stale`.** Run `daikin_cycle_ml.recompute_kmeans`; a
mode needs 12 cycles in 28 days.

**`stooklijn_advies`.** The advice to raise or lower the water
temperature, with the expected COP gain and the comfort guard. Repeats
at most weekly.

## 3. Delivery

| Channel | Setting | Notes |
|---|---|---|
| Sidebar notification | *Persistent notifications* (on) | One notification per alert type, replaced on the next one |
| Notify target | *Notify target* | A notify entity (recommended: `notify.mobile_app_*`, a Telegram bot entity) or a legacy `notify.*` service |

Under **Configure → Notifications → Delivery**: *Emoji in notifications*
and *Include action advice*. Telegram text is escaped for the bot's parse
mode. When the target keeps failing, the `notify_failed` repair appears.

## 4. Quiet hours, aggregation and repeat windows

**Quiet hours** (Configure → Notifications → Quiet hours and status; off by
default, 22:00-07:00): alerts below *action needed* are dropped during the
window. The window may cross midnight.

**Aggregation** (`alert_aggregation_minutes`, default 30): triggers of the
same alert within the window are merged into one message.

**Repeat windows:** after an alert, the same alert waits for its window
(the *Repeat* column in §2) before it notifies again. Each window can be
changed per alert in the options (`alert_agg_<alert>_min`). The windows
survive a restart.

## 5. Switching alerts off

Two levels, both under Configure → Notifications:

- **Groups** (*Content and language*): `pendulum`, `short_cycle`,
  `setpoint`, `ml`, `cop_stooklijn`, `component_health`, `data_quality`. A
  group off silences all its alerts.
- **Per alert** (*Per-alert enables*): `cop_degradation`,
  `cop_vs_datasheet_low`, `defrost_excessive`, `buh_excessive`,
  `dhw_pendulum`, `high_cycle_rate`, `energy_daily_anomaly`,
  `kmeans_retrain_stale`, `db_retention_warning`, `source_stale`,
  `missing_attributes`.

An alert notifies only when its group and its own switch are on. Too many
cycling alerts? Raise the thresholds first (Configure → Pendulum) rather
than switching them off.

## 6. Testing

- **Configure → Notifications → Test notifications**: send one alert of
  your choice, or **all** of them at once (filters bypassed).
- Service `daikin_cycle_ml.send_test_notification` with `alert_kind`
  (one type, `all_alerts` or `status_summary`), `message`, `target` and
  `ignore_filters`.

Home Assistant may merge sidebar notifications sent in one burst, so the
sidebar can show one fewer than were sent; the notify target receives all.

## 7. Status updates

Optional (*Periodic status updates*, every 24 h by default): a summary of
cycles, quality, COP, runtime and open issues for the period, sent to the
notify target. It has no repeat window.

## 8. Troubleshooting

| Problem | Check |
|---|---|
| No notifications at all | A notify target set? Its group and switch on? Quiet hours? Try *Test notifications* |
| Only in the sidebar | The notify target: the `notify_failed` repair names the error |
| Too many | Raise thresholds, lengthen the repeat window, or switch the group off |
| An alert never comes | Its condition: see the binary sensor of the same name ([Entities §3](ENTITIES.md#3-binary-sensors)) |
| Wrong language | Configure → Notifications → Content → *Notification language* |

More in [Troubleshooting §6](TROUBLESHOOTING.md#6-alerts-and-notifications).
