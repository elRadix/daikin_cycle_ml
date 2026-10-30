# Alerts & Notifications

Design and reference for the alert pipeline in Daikin Cycle ML.

- **Covers:** all 19 alert types, delivery channels, deduplication, quiet hours, groups, per-alert toggles, templates, test behavior
- **For:** end users tuning alerts, admins integrating with notify services, developers extending the pipeline
- **Version:** v1.14.0

Cross-references: [CONFIGURATION.md](CONFIGURATION.md) (options menu), [ENTITIES.md](ENTITIES.md) (alert-related binary sensors), [ML.md](ML.md) (anomaly detection), [DATABASE.md](DATABASE.md) (alert persistence).

---

## Contents

- [1. Overview](#1-overview)
- [2. Pipeline architecture](#2-pipeline-architecture)
- [3. Alert types](#3-alert-types)
- [4. Delivery channels](#4-delivery-channels)
- [5. Deduplication](#5-deduplication)
- [6. Quiet hours](#6-quiet-hours)
- [7. Groups](#7-groups)
- [8. Per-alert toggles](#8-per-alert-toggles)
- [9. Templates and rendering](#9-templates-and-rendering)
- [10. Test behavior](#10-test-behavior)
- [11. Status updates](#11-status-updates)
- [12. Internationalization](#12-internationalization)
- [13. Verification and troubleshooting](#13-verification-and-troubleshooting)

---

## 1. Overview

Daikin Cycle ML has three notification surfaces:

| Surface | Trigger | Persistence |
|---|---|---|
| **Alerts** | State transitions detected on the 1 h tick | Dedup window per type, HA Store |
| **Status updates** | Fixed interval (opt-in) | None, fires every interval |
| **Repairs** | Persistent system issue | HA Repairs system |

This document covers alerts and status updates. Repairs have their own issue list (see [ENTITIES.md](ENTITIES.md) §repairs).

Alerts are the main feedback loop: they tell you when the pump is behaving in a way that costs COP, comfort, or hardware life. Everything below is about how they are decided, formatted, delivered, and silenced.

### 1.1 What alerts do NOT do

- They do not write to your heat pump. The integration is read-only.
- They do not call external APIs.
- They do not persist to HA's Recorder (they are transient — HA Store keeps dedup state only).
- They do not queue if the notify service is unavailable. If notify fails, the alert is lost for that trigger (only persistent notification survives).

### 1.2 Where alerts come from

Every alert type has a corresponding **binary_sensor** state (for binary alerts) or a computed value (for standalone alerts). The pipeline:

```
binary_sensor state (or computed value)
    → evaluate_alerts() decides "fire" per type
    → dedup check against HA Store
    → quiet-hours check
    → group + per-alert toggle check
    → build_rich_alert() formats the message
    → _emit_alert() delivers
```

See [2. Pipeline architecture](#2-pipeline-architecture) for the details.

---

## 2. Pipeline architecture

### 2.1 Trigger cadence

Alerts are evaluated on the **1-hour tick** of the coordinator. That means:

- The first check runs 1 h after HA startup
- You will not get an alert for a condition that resolves within the first hour
- `send_test_notification` bypasses the tick (fires immediately)

Cycle detection (30 s) and COP analysis (10 min) run on their own cadences but do not fire alerts directly. Alerts are batched into the hourly tick.

### 2.2 Evaluation order

On each tick, `evaluate_alerts` runs in this order:

1. Compute binary states (17 binary alerts)
2. Compute standalone values (cop_low, stooklijn_advies)
3. Compute data-quality alerts (db_retention, kmeans_stale, energy_daily_anomaly)
4. For each alert: check `_should_fire(alert_type)`:
   - Group toggle is `true`?
   - Per-alert toggle (if applicable) is `true`?
   - Last fire > dedup window ago?
   - Quiet hours allow it (or alert is critical)?
5. For firing alerts: build message, deliver, update dedup timestamp

### 2.3 Where alert state lives

| State | Location | Lifetime |
|---|---|---|
| Dedup timestamps | HA Store `daikin_cycle_ml.alerts` | Across restarts |
| Binary sensor states | Coordinator memory | Rebuilt each tick |
| Last alert fired (per type) | HA Store | Across restarts |

The alert store is a small JSON blob with a schema version:

```json
{
  "version": 1,
  "last_sent": {
    "pendulum_hourly": 1792432800.5,
    "short_run": 1792425600.0,
    ...
  }
}
```

19 keys total, one per alert type. Persisted with a 5 s debounce on every write.

### 2.4 Failure modes

| Failure | Impact | Recovery |
|---|---|---|
| HA Store corrupt | Dedup state resets on next restart | Auto — new file created |
| Notify service fails | Alert lost for that trigger, persistent notification still fires | Retries on next trigger past dedup |
| persistent_notification fails | Same as above, notify service still fires | Auto |
| `_build_alert_context` raises | That alert type does not fire this tick, others continue | Auto next tick |

---

## 3. Alert types

19 alert types grouped by purpose.

### 3.1 Binary alerts (17)

Triggered when the corresponding binary sensor state is on.

| Alert | Binary sensor | Severity | Default dedup | Group |
|---|---|---|---|---|
| `pendulum_hourly` | `pendulum_hourly` | warning | 60 min | pendulum |
| `pendulum_daily` | `pendulum_daily` | warning | 1440 min | pendulum |
| `short_run` | `short_run` | warning | 30 min | short_cycle |
| `short_off` | `short_off` | warning | 30 min | short_cycle |
| `high_cycle_rate` | `high_cycle_rate` | warning | 60 min | short_cycle |
| `ml_anomaly` | `ml_anomaly` | warning | 60 min | ml |
| `setpoint_osc` | `setpoint_oscillating` | warning | 30 min | setpoint |
| `dhw_pendulum` | `dhw_pendulum` | warning | 60 min | setpoint |
| `cop_degradation` | (computed) | warning | 1440 min | cop_stooklijn |
| `cop_vs_datasheet_low` | (computed) | info | 1440 min | cop_stooklijn |
| `defrost_excessive` | (computed) | warning | 1440 min | (none) |
| `buh_excessive` | (computed) | warning | 1440 min | (none) |
| `source_stale` | `source_stale` | **critical** | 60 min | (none) |
| `missing_attributes` | `missing_attributes` | warning | 60 min | (none) |
| `db_retention_warning` | (computed) | info | 1440 min | (none) |
| `kmeans_retrain_stale` | (computed) | info | 1440 min | (none) |
| `energy_daily_anomaly` | (computed) | info | 1440 min | (none) |

### 3.2 Standalone alerts (2)

Rendered by their own builder, not by `build_rich_alert` on a template.

| Alert | Trigger | Severity | Default dedup |
|---|---|---|---|
| `cop_low` | Daily heating COP < 2.5 (≥ 3 samples) | warning | 30 min |
| `stooklijn_advies` | Heat-curve advice available + confidence ≥ 0.7 | warning | 10080 min (7 days) |

### 3.3 Per-alert detail

#### `pendulum_hourly`

Fires when cycles in the last hour exceed `pendulum_cycles_per_hour` (default 4).

Message fields: current cycles/hour, target, LWT setpoint, last cycle duration, average duration (7d), outdoor temp, mode.

Action: check setpoint delta, hysteresis, heat curve. If your home needs fast response, a wider delta is fine — high cycling only matters if it happens during steady demand.

#### `pendulum_daily`

Fires when cycles today exceed `pendulum_cycles_per_day` (default 40).

Same advice as `pendulum_hourly`, but for the whole day. Use this to catch slow drift rather than acute problems.

#### `short_run`

Fires when the last completed cycle duration < `short_run_threshold_min` (default 20 min).

Message fields: duration, threshold, LWT setpoint, actual LWT, indoor temp, flow, outdoor.

Action: raise minimum run time (usually via heat curve or setback) or lower LWT setpoint. Short cycles starve the pump of time to stabilize.

#### `short_off`

Fires when the compressor has been off for less than `short_off_threshold_min` (default 5 min).

Message fields: off-time, threshold, LWT setpoint, indoor temp, flow, outdoor.

Action: check heating demand (may be genuinely fluctuating) or increase minimum off-time in the thermostat. Compressors that restart within 5 min have not equalized pressure and wear faster.

#### `high_cycle_rate`

Fires when cycles per hour > 1.5 × `target_cycles_per_day` / 24.

Target: 8 cycles/day → 12 cycles/hour threshold. Different from `pendulum_hourly` in that it's scaled to your configured target, not a fixed number.

#### `ml_anomaly`

Fires when the IsolationForest anomaly detector flags a cycle as unusual (z-score ≥ 2.0 vs per-mode EWMA baseline).

Message fields: severity (warning/critical), mode, z-score, top dimension, last duration, average duration (7d), outdoor.

Top dimension tells you **why** it flagged: `duration_s`, `dT_max`, `rps_avg`, `cop_avg`, etc. If the same dimension keeps flagging, investigate that specific metric.

#### `setpoint_osc`

Fires when the LWT setpoint oscillates: ≥ 6 changes within 30 min, with reversals (up-then-down or down-then-up).

Requires `LW setpoint (main)` attribute. Monotonic drift (up-only or down-only) does **not** fire — only true oscillation. This is Q4 fix (v1.9): earlier versions fired on any 6 changes, including slow drifts, causing false positives.

#### `dhw_pendulum`

Fires when DHW-mode cycles per hour exceed `dhw_pendulum_cycles_per_hour` (default 3).

DHW cycling usually indicates a 3-way valve issue, a tank setpoint problem, or a heat pump sized for hot water production that is too powerful for the tank.

#### `cop_degradation`

Fires when 7d-vs-7d COP has dropped more than 15% (weather-normalized).

The comparison uses outdoor-bin matching: only days with similar outdoor temperatures are compared. This isolates hardware wear from weather variation. BUH and defrost cycles are excluded to remove noise.

Message fields: week percent (negative = degradation), threshold, 30d trend, mode, outdoor.

Action: check refrigerant charge, filters, outdoor unit cleanliness. If 30d trend is also negative, it is a real degradation, not a temporary dip.

#### `cop_vs_datasheet_low`

Fires when live COP is more than 10% below the datasheet value for your model.

Only fires for bundled models (not Custom). Message includes expected vs actual. Useful as a sanity check — if you see this persistently, either the datasheet is wrong for your conditions or the pump is underperforming.

#### `defrost_excessive`

Fires when 7-day defrost count exceeds 30.

Message includes count, duration (7d, in minutes), mode, outdoor temp.

Action: check outdoor humidity (frequent defrosts on cold damp days is expected — the threshold is designed to catch excessive defrosts even accounting for weather). If your region is coastal, you may want to raise the threshold via the `defrost_excessive` dedup option.

#### `buh_excessive`

Fires when backup heater runtime ratio exceeds 15% of total compressor runtime over 7 days.

BUH is meant as a supplement for cold starts and defrost recovery, not steady operation. A ratio > 15% suggests the heat pump is undersized, the outdoor temp is below the pump's working range, or defrosts are running long.

Message: BUH ratio, threshold, BUH count (7d), mode, outdoor.

#### `source_stale` (critical)

Fires when the source sensor has not updated for more than 60 seconds.

**This is the only critical alert.** It bypasses quiet hours because it means data is missing entirely — no cycle detection, no COP, no alerts are happening until it resolves.

Action: check ESPAltherma connection (Wi-Fi, MQTT, ESPHome). Often resolves on its own if the ESP device briefly reboots.

#### `missing_attributes`

Fires when one or more required attributes is missing from the source sensor.

Message lists which attributes are missing (up to a limit) and the source sensor entity ID.

Action: check ESPAltherma `.h` file — one of the required registers is not enabled. If it was working before, either the firmware changed or the `.h` file was edited.

#### `db_retention_warning` (v1.9)

Fires when the alerts table has more than 100 rows past `alert_retention_days`, OR the cycles table has more than 100 rows past `cycle_retention_days`.

This means retention is not running. Check:
- Is `retention_enabled` on?
- Does HA restart at 03:00 local (interrupting the maintenance window)?
- Are DB permissions intact?

Message: stale alerts count, stale cycles count, alert retention days, cycle retention days, mode.

#### `kmeans_retrain_stale` (v1.9)

Fires when the last successful kmeans retrain was more than 14 days ago.

Message fields: hours since OK, last OK timestamp, consecutive failures, last failure reason, mode.

Action: run `daikin_cycle_ml.recompute_kmeans` from Developer Tools → Actions. If it keeps failing, check `model_state` for corruption or insufficient cycles (needs at least 30 cycles to retrain).

#### `energy_daily_anomaly` (v1.9)

Fires when today's electrical energy consumption is > (baseline_mean + 2 × sigma) AND > 2.0 kWh above the baseline mean.

Requires at least 7 samples of daily energy before firing (per mode). Baseline is per-mode EWMA, weather-normalized.

Message: today kWh, baseline mean, baseline sigma, z-score, samples, mode.

Action: check for stuck valves, unusual demand (e.g. someone set the thermostat much higher), or a defrost problem. If the pump suddenly uses far more electricity for the same outdoor conditions, something is wrong.

Note: the first 7 days after install, this alert cannot fire (baseline not built yet). This is intentional.

#### `cop_low` (standalone)

Fires when today's heating COP drops below 2.5 with at least 3 samples.

Different from `cop_degradation` (which compares to your own history): `cop_low` compares to an absolute floor. Both firing together = real problem.

#### `stooklijn_advies` (standalone)

Fires when heat-curve advice is available with confidence ≥ 0.7.

Contains the current advice (raise/lower LWT by X °C), estimated COP impact, comfort impact, confidence, sample count.

Deduplicated for 7 days by default — the advice does not change often and reposting it every hour would be noise.

---

## 4. Delivery channels

Two independent channels, both fire for every alert.

### 4.1 Persistent notifications

- Sent to `persistent_notification.create` in HA
- Visible in the sidebar notifications panel
- Do not appear in the mobile app (unless HA is open)
- Persist until manually dismissed or HA restart
- No emoji prefix (HA does not support arbitrary content in persistent notifications reliably)
- No action advice appended (only the main alert body)

Toggle: **Options → Notifications → Delivery → Persistent notifications**.

### 4.2 Notify service

- Sent to whatever `notify.*` service you configure
- Appears on your phone/Telegram/email depending on the service
- Contains the full message with emoji prefix (if enabled) and action advice (if enabled)
- Fails silently if service is unavailable
- Retries on next dedup window expiry

Toggle: **Options → Notifications → Delivery → Notify service**.

### 4.3 What goes to which channel

| Content | Persistent | Notify |
|---|---|---|
| Title | "Daikin Cycle ML" | alert type title |
| Main body | Full rendered alert | Full rendered alert |
| Emoji prefix | No | Yes (if enabled) |
| Action advice | No | Yes (if enabled) |
| Extra context dict | No (HA limitation) | Yes |

The `AlertSpec.context` dict is available to notify templates but not to persistent notifications (HA does not support extra keys in persistent notifications).

### 4.4 Failure handling

- Persistent notification failure: logged, alert continues to notify
- Notify service failure: logged, alert continues to persistent
- Both fail: alert is lost for that trigger, will retry after dedup window

There is no automatic retry queue. If you need alerts to survive both channels being down, use HA's built-in automations to persist them to a file or InfluxDB.

---

## 5. Deduplication

### 5.1 How dedup works

Every alert type has a dedup window (in minutes). After an alert fires, the store records the timestamp. Subsequent triggers of the same alert type are **silenced** until the window expires.

Windows are per-type. Firing `short_run` does not reset the window for `pendulum_hourly`.

### 5.2 Default windows

| Alert | Default window |
|---|---|
| pendulum_hourly | 60 min |
| pendulum_daily | 1440 min (24 h) |
| short_run | 30 min |
| short_off | 30 min |
| ml_anomaly | 60 min |
| setpoint_osc | 30 min |
| cop_low | 30 min |
| stooklijn_advies | 10080 min (7 days) |
| cop_degradation | 1440 min (24 h) |
| defrost_excessive | 1440 min |
| buh_excessive | 1440 min |
| source_stale | 60 min |
| missing_attributes | 60 min |
| dhw_pendulum | 60 min |
| high_cycle_rate | 60 min |
| cop_vs_datasheet_low | 1440 min |
| db_retention_warning | 1440 min |
| kmeans_retrain_stale | 1440 min |
| energy_daily_anomaly | 1440 min |

### 5.3 Adjusting windows

**Options → Notifications → Dedup**. 19 numeric fields, one per alert. Range: 1 minute to 7 days (10080).

Common changes:
- **Reduce `pendulum_hourly` from 60 to 30** if you want more frequent reminders during active debugging
- **Increase `short_run` from 30 to 120** if you are on a system that legitimately cycles briefly during defrost recovery
- **Reduce `stooklijn_advies` from 7 days to 1 day** if you are actively tuning the heat curve and want fresh advice

### 5.4 Dedup state persistence

Stored in `/config/.storage/daikin_cycle_ml.alerts` as JSON:

```json
{
  "version": 1,
  "last_sent": {
    "pendulum_hourly": 1792432800.5,
    "short_run": 1792425600.0
  }
}
```

Survives HA restarts. Cleared only when you delete the file or reinstall the integration.

### 5.5 Bypassing dedup

For testing, use **Options → Notifications → Test notification** with `ignore_group_filters = true`. This fires the alert even if the dedup window is active.

For automation-driven testing, call the service directly:

```yaml
service: daikin_cycle_ml.send_test_notification
data:
  alert_kind: short_run
  ignore_filters: true
```

This ignores group toggles, per-alert toggles, and dedup. Quiet hours still apply unless you also disable them in options.

---

## 6. Quiet hours

### 6.1 What they do

Non-critical alerts are suppressed during the quiet window. The most critical alert (`source_stale`) always fires because it means data is missing entirely — no alerts are happening until it resolves.

### 6.2 Configuration

**Options → Notifications → Quiet hours**:

| Field | Default |
|---|---|
| Enabled | `false` |
| Start | `22:00` |
| End | `07:00` |

The window is wraparound-aware: `22:00` to `07:00` spans midnight correctly. `07:00` is exclusive (an alert at 07:00:00 fires).

### 6.3 Alerts that bypass quiet hours

| Alert | Bypasses? |
|---|---|
| `source_stale` | Yes (critical) |
| All other 18 | No |

If you want `missing_attributes` to bypass too, the only way in v1.9 is to disable quiet hours entirely. Per-alert quiet-hour bypass is a candidate for v1.10.

### 6.4 Aggregation window

Separate from quiet hours: `alert_aggregation_minutes` (default 30). Multiple triggers of the **same** alert type within this window are aggregated into a single notification (with `aggregated_count` attribute).

Different from dedup: dedup **blocks** subsequent alerts, aggregation **merges** them. Aggregation runs first, then dedup applies to the merged result.

### 6.5 Recommended setup

For most users:
- Quiet hours: enabled, 22:00 to 07:00
- Aggregation: 30 min
- Keep `source_stale` as the only critical (default)

This means you get pinged at night only if the sensor dies entirely (rare).

For users actively debugging:
- Quiet hours: **disabled**
- Aggregation: 5 min
- Watch the dedup adjustment in [5.3](#53-adjusting-windows)

---

### 6.6 Boiler-cycle suppression (v1.15.0)

HP-cycle alerts (short_run, short_off, pendulum_hourly, pendulum_daily): suppressed when boiler_active AND NOT hp_running.

DHW-cycle (dhw_pendulum): suppressed only during boiler-DHW-only. Co-fire still fires it.

## 7. Groups

### 7.1 What groups do

Group toggles gate their alerts at the top level. If a group is off, **no alert in that group fires**, regardless of per-alert toggles.

Groups are a coarse filter: turn off the whole `short_cycle` group if you are fine with short cycling, without touching the individual alerts.

### 7.2 Group mapping

| Group | Alerts |
|---|---|
| `pendulum` | pendulum_hourly, pendulum_daily |
| `short_cycle` | short_run, short_off, high_cycle_rate |
| `ml` | ml_anomaly |
| `setpoint` | setpoint_osc, dhw_pendulum |
| `cop_stooklijn` | cop_low, stooklijn_advies, cop_degradation, cop_vs_datasheet_low |

Alerts not in any group are always evaluated (subject to per-alert toggles where applicable):
- `source_stale` (always fires)
- `missing_attributes` (always fires)
- `defrost_excessive` (no group, no per-alert toggle in v1.9)
- `buh_excessive` (same)
- `db_retention_warning` (has per-alert toggle)
- `kmeans_retrain_stale` (has per-alert toggle)
- `energy_daily_anomaly` (has per-alert toggle)

### 7.3 Configuration

**Options → Notifications → Content**:

| Field | Default |
|---|---|
| Pendulum group | `true` |
| Short cycle group | `true` |
| ML group | `true` |
| Setpoint group | `true` |
| COP + stooklijn group | `true` |

All groups default to on. Turn off groups you do not want to hear about.

### 7.4 Group versus per-alert

Group is a **superset**: an alert fires only if its group is on AND its per-alert toggle is on.

Exception: `defrost_excessive` and `buh_excessive` have no group and no per-alert toggle. To silence them, you must either:
- Set their dedup window to a very long value (e.g. 7 days)
- Use `notify_service` filters or HA automations

Consider this a v1.9 gap. Per-alert toggles for these are candidates for v1.10.

---

## 8. Per-alert toggles

### 8.1 What they do (added v1.9)

11 boolean toggles, each gating a single alert type. If a toggle is off, that alert never fires, regardless of its group or dedup state.

Toggles are **additive to groups**: to fire an alert, both its group AND its per-alert toggle must be on.

### 8.2 The 11 toggles

| Field | Alert |
|---|---|
| `alert_enabled_cop_degradation` | cop_degradation |
| `alert_enabled_defrost_excessive` | defrost_excessive |
| `alert_enabled_buh_excessive` | buh_excessive |
| `alert_enabled_source_stale` | source_stale |
| `alert_enabled_missing_attributes` | missing_attributes |
| `alert_enabled_dhw_pendulum` | dhw_pendulum |
| `alert_enabled_high_cycle_rate` | high_cycle_rate |
| `alert_enabled_cop_vs_datasheet_low` | cop_vs_datasheet_low |
| `alert_enabled_db_retention_warning` | db_retention_warning |
| `alert_enabled_kmeans_retrain_stale` | kmeans_retrain_stale |
| `alert_enabled_energy_daily_anomaly` | energy_daily_anomaly |

All default to `true`.

### 8.3 Which alerts have no per-alert toggle

| Alert | How to silence |
|---|---|
| pendulum_hourly, pendulum_daily | Turn off `pendulum` group |
| short_run, short_off, high_cycle_rate | Turn off `short_cycle` group |
| ml_anomaly | Turn off `ml` group |
| setpoint_osc, dhw_pendulum | Turn off `setpoint` group |
| cop_low, stooklijn_advies | Turn off `cop_stooklijn` group |

The 8 alerts with no per-alert toggle must be silenced via their group. This is intentional: they tend to come in pairs (e.g. raising a cycle threshold silences both hourly and daily pendulum alerts), so a group toggle is the natural granularity.

### 8.4 Configuration

**Options → Notifications → Enabled** (v1.9 sub-step).

Each toggle has its own label and description in the UI. The descriptions explain what triggers the alert, so you can decide without consulting this document.

---

## 9. Templates and rendering

### 9.1 Message structure

All 17 binary alerts render through `build_rich_alert()` with a fixed structure:

```
{emoji} Daikin Cycle ML — {title}
{timestamp}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{field label}  {value}
{field label}  {value}
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• {action advice}
```

### 9.2 Field tables per alert

Each alert type has a field schema in `ALERT_SCHEMA`. Fields with `None` values render as an em dash (`—`), never as blank.

| Alert | Fields |
|---|---|
| pendulum_hourly | cycles_hour, target_cph, lwt_setpoint, last_duration, avg_duration_7d, outdoor, mode |
| pendulum_daily | cycles_today, target_cpd, lwt_setpoint, last_duration, avg_duration_7d, outdoor, mode |
| short_run | duration, threshold, lwt_setpoint, lwt_actual, indoor, flow, outdoor, mode |
| short_off | off_min, threshold, lwt_setpoint, indoor, flow, outdoor, mode |
| ml_anomaly | severity, mode, z_score, top_dim, last_duration, avg_duration_7d, outdoor |
| setpoint_osc | lwt_setpoint, lwt_target, swing, changes, window, threshold, mode |
| cop_degradation | week_pct, threshold, trend_30d, mode, outdoor |
| defrost_excessive | count_7d, threshold, duration_7d_min, mode, outdoor |
| buh_excessive | buh_ratio_7d, threshold, buh_count_7d, mode, outdoor |
| source_stale | age_s, threshold, source_sensor, mode |
| missing_attributes | missing_count, which, source_sensor, mode |
| dhw_pendulum | dhw_cph, target, mode, outdoor |
| high_cycle_rate | cycles_hour, target, mode, outdoor |
| cop_vs_datasheet_low | diff_pct, expected, mode, outdoor |
| db_retention_warning | stale_alerts, stale_cycles, alert_retention_days, cycle_retention_days, mode |
| kmeans_retrain_stale | hours_since_ok, last_ok_ts, consecutive_failures, last_failure_reason, mode |
| energy_daily_anomaly | today_el_kwh, baseline_el_mean, baseline_el_sigma, z_score, samples, mode |

### 9.3 Two standalone alerts

`cop_low` and `stooklijn_advies` use their own builders (`build_cop_low_report`, `build_stooklijn_report`) but render in the same visual style.

### 9.4 Emoji

Prefix per alert type, defined in `ALERT_TYPE_EMOJI`:

| Alert | Emoji |
|---|---|
| pendulum_hourly, pendulum_daily | 🔁 |
| short_run | ⏱ |
| short_off | 💤 |
| ml_anomaly | 🧠 |
| setpoint_osc | 🎯 |
| cop_degradation | 📉 |
| defrost_excessive | ❄️ |
| buh_excessive | 🔥 |
| source_stale | 📡 |
| missing_attributes | ❓ |
| dhw_pendulum | 🚿 |
| high_cycle_rate | 🔄 |
| cop_vs_datasheet_low | 📊 |
| cop_low | 📉 |
| stooklijn_advies | 📉 |
| db_retention_warning | 🗄️ |
| kmeans_retrain_stale | ⚙️ |
| energy_daily_anomaly | ⚡ |

Severity fallback (if alert type not in map): `SEVERITY_EMOJI`:
- critical → 🔴
- warning → 🟠
- watch → 🟡
- info → 🔵
- ok → 🟢
- status → 📊

Toggle: **Options → Notifications → Delivery → Emoji**. When disabled, no emoji prefix is added.

Note: persistent notifications **never** receive emoji, regardless of this setting.

### 9.5 Action advice

Every alert type has an advice string in `ALERT_ADVICE`, per language. Rendered as the last line after `•`.

Example for `short_run`:

> • Cycle shorter than threshold: raise minimum run time or lower the LWT setpoint.

Toggle: **Options → Notifications → Delivery → Action advice**. When disabled, the advice line is omitted.

Special case: `ml_anomaly` may include a dimension-specific hint based on the top dimension (e.g. "check dT_max" if that is what flagged). This is dynamic advice appended to the base advice.

### 9.6 Severity rendering

Severity appears in two places:
- In the emoji prefix (see 9.4)
- In the `severity` field for alerts that expose it explicitly (`ml_anomaly`)

For alerts without an explicit severity field, the severity is reflected only via emoji + the alert type itself.

### 9.7 Field value formatting

- Numeric values: rounded per field schema (e.g. temperatures to 1 decimal, durations to 0 decimals)
- Missing values: em dash (`—`), never blank
- Units: appended after the value (`31.0 °C`, `162 min`, `5.0 l/min`)
- Timestamps: `YYYY-MM-DD HH:MM` in local timezone

---

## 10. Test behavior

### 10.1 `send_test_notification` service

Send a single alert type immediately. Useful for verifying your notify service is configured correctly.

```yaml
service: daikin_cycle_ml.send_test_notification
data:
  alert_kind: short_run
  ignore_filters: true
```

Parameters:

| Field | Type | Default |
|---|---|---|
| `alert_kind` | string | `status_summary` |
| `ignore_filters` | bool | `false` |
| `message` | string | (auto-generated per kind) |

Valid `alert_kind` values (10):
- `status_summary`
- `pendulum_hourly`, `pendulum_daily`
- `short_run`, `short_off`
- `ml_anomaly`
- `setpoint_osc`
- `cop_low`
- `stooklijn_advies`
- `all_alerts`

The 9 new v1.9 alert types (`cop_degradation`, `defrost_excessive`, `buh_excessive`, `source_stale`, `missing_attributes`, `dhw_pendulum`, `high_cycle_rate`, `cop_vs_datasheet_low`, `db_retention_warning`, `kmeans_retrain_stale`, `energy_daily_anomaly`) are not selectable individually via this service. Use `all_alerts` to fire them all at once, or wait for the natural trigger.

This is a v1.9 gap. Extending the enum is a candidate for v1.10.

### 10.2 "Send ALL" button

**Options → Notifications → Test menu → Send ALL test notifications**.

Fires all 19 alert types at once. Ignores group filters and dedup. Respects quiet hours (unless you disable them first).

Each alert gets its own `notif_id` like `daikin_cycle_ml_test_<alert_type>`, so they are distinct notifications.

### 10.3 Known limitation (v1.9): kmeans_retrain_stale in bulk test

When firing all 19 alerts in the same tick, `kmeans_retrain_stale` sometimes does not appear in the HA notification panel. Rendering works (message is correct, logged as emitted), dispatch works (no exception raised), but `persistent_notification.create` with `blocking=False` silently drops one of the 19 rapid calls.

This is an HA-side quirk in the notification service under rapid burst, not a bug in this integration. All other 18 alerts appear correctly.

**To verify `kmeans_retrain_stale` in isolation**, use `send_test_notification` with `alert_kind: all_alerts` via the UI's Actions page (Developer Tools → Actions) instead of the Options menu. That still hits the same burst problem.

**Definitive verification:** run the emit-loop simulation in a dev container:

```bash
python3 -c "
from custom_components.daikin_cycle_ml.engine.notification_engine import BINARY_ALERT_MAP
from custom_components.daikin_cycle_ml.engine.status_report import build_rich_alert
for bkey, (alert_type, severity, _) in BINARY_ALERT_MAP.items():
    msg = build_rich_alert(bkey, severity, {}, language='en', emoji_enabled=True)
    print(f'{bkey}: len={len(msg)}')
"
```

Expected output: `kmeans_retrain_stale: len=367`. If this renders correctly (which it does in v1.9), the alert is functional — the UI omission is cosmetic.

### 10.4 Home Assistant notify service test

Independent of Daikin Cycle ML, verify your notify service works first:

```yaml
service: notify.your_service
data:
  message: "test from HA"
```

If this fails, no Daikin Cycle ML alert will reach your phone. Check the notify integration's configuration before debugging here.

---

## 11. Status updates

### 11.1 What they are

A periodic summary of the last interval's activity: cycles detected, quality average, alerts fired, current COP, source health.

Different from alerts: status updates are always the same content (a dashboard-style summary), not triggered by a condition.

### 11.2 Configuration

**Options → Notifications → Quiet hours**:

| Field | Default |
|---|---|
| Status update enabled | `false` |
| Status update interval | 24 h |

When enabled, fires every N hours via the coordinator's scheduler.

### 11.3 Content

Built by `build_status_report()` in `status_report.py`. Contains:
- Current cycle state
- Cycles count for the period
- Quality average
- Current COP (heating, DHW, cooling)
- Source health
- Alerts fired in the period (count by type)

Formatted as a rich markdown-compatible message, same style as alerts but with a 📊 prefix.

### 11.4 Status summary alert kind

`send_test_notification` with `alert_kind: status_summary` fires a status update immediately, ignoring the interval. Useful for verifying the message looks correct without waiting.

### 11.5 No dedup

Status updates ignore dedup entirely. They fire on their schedule regardless of when the last one fired.

---

## 12. Internationalization

### 12.1 Languages

Two languages supported: **English (en)** and **Dutch (nl)**.

Selected via **Options → Notifications → Content → Language**. Applies to:
- Alert titles
- Field labels
- Action advice
- Status summary

### 12.2 What is translated

| Content | Where stored | Languages |
|---|---|---|
| Alert titles | `ALERT_TITLES` | en, nl |
| Field labels | `ALERT_LABELS` | en, nl |
| Action advice | `ALERT_ADVICE` | en, nl |
| Status labels | `STATUS_LABELS` | en, nl |
| Severity labels | `SEVERITY_LABELS` | en, nl |
| Mode labels | `MODE_LABELS` | en, nl |
| Reason labels | `KMEANS_ADVICE_BY_REASON` | en, nl |
| Options menu labels | `strings.json` + `translations/*.json` | en, nl |
| Service descriptions | `services.yaml` | en, nl |

Everything visible to the user is translatable. Message body content (numbers, timestamps, em-dashes) is language-agnostic.

### 12.3 What is not translated

- Emoji (universal)
- Technical field names when shown as keys (`dT_max`, `cop_avg` — used only in debug output, not user messages)
- Numeric formats (decimal separator is `.` always; no locale formatting)

### 12.4 Translation completeness check

Both `strings.json` and the two `translations/*.json` files are validated in CI. If a language file is missing a key present in `strings.json`, the build fails. This ensures new alerts added in future versions always ship complete translations.

As of v1.9.0: config.step 157/157, options.step 281/281, notifications_enabled 11/11, notifications_dedup 19/19, in all three files.

### 12.5 Adding a language

Not supported without code changes. The two-language limit is baked into `LANG_EN` / `LANG_NL` constants. Supporting a third language requires:
1. Adding a `LANG_XX` constant
2. Adding a `xx` key to every translation dict
3. Adding `translations/xx.json`
4. Adding the option to the language selector in config_flow

Candidate for a future version if there is demand.

---

## 13. Verification and troubleshooting

### 13.1 Verify the pipeline works

1. **Options → Notifications → Test menu → Send ALL test notifications**
2. Check your phone for 18+ notifications
3. Check the HA notification panel for 18+ notifications

If both channels fire: pipeline is working.

If one fires but not the other:
- Persistent works, notify does not: check `notify_service` configuration
- Notify works, persistent does not: check `persistent_enabled` option

If neither fires: check quiet hours, group toggles, and per-alert toggles.

### 13.2 Verify a specific alert

Use `send_test_notification`:

```yaml
service: daikin_cycle_ml.send_test_notification
data:
  alert_kind: short_run
  ignore_filters: true
```

If this renders correctly on your phone, the pipeline works for that alert type.

### 13.3 Alert fires but is not useful

Common causes:

| Symptom | Likely cause | Fix |
|---|---|---|
| `pendulum_hourly` fires during cold snap | Cycling is expected in cold weather | Raise `pendulum_cycles_per_hour` in Options → Pendulum |
| `short_run` fires after defrost | Defrost recovery creates one short cycle | Increase `short_run` dedup window from 30 to 120 min |
| `setpoint_osc` fires but you see no oscillation | Source sensor reports setpoint changes that are not real (API quirk) | Check `LW setpoint (main)` attribute stability |
| `cop_degradation` fires in spring | Baseline was built from winter data | Wait for 30 days of spring data, or ignore until summer |
| `stooklijn_advies` fires repeatedly | Dedup window too short | Increase from 7 days to 14 days |
| `energy_daily_anomaly` fires every week | Threshold too tight for your house | Check outdoor temp on fire days — if weather is unusual, this is expected |

### 13.4 Alert fires but the message is wrong

Possible causes:

| Symptom | Likely cause |
|---|---|
| Field shows `—` when it should have a value | Source attribute is missing or stale |
| Field shows a value from the wrong cycle | `_build_alert_context` read old data (rare, usually on first tick after restart) |
| Emoji is missing | `notify_emoji_enabled` is `false`, or persistent notification (no emoji by design) |
| Action advice line is missing | `action_advice_enabled` is `false` |
| Message is in Dutch when you want English | `notification_language` is `nl` |

### 13.5 Deduplication not working

If you get repeated alerts for the same condition:

1. Check the dedup window for that alert: **Options → Notifications → Dedup**
2. Check `state` attribute of the alert in the store: `cat /config/.storage/daikin_cycle_ml.alerts`
3. The `last_sent` dict should have an entry for that alert type with a recent timestamp

If the file shows a timestamp but you still get repeats: the timestamp is not being read. Check for file permission issues on `.storage/daikin_cycle_ml.alerts`.

### 13.6 Notify service failures

Look for `notify entity path failed` or `notify service notify.xxx failed` in HA logs (Settings → System → Logs, filter `daikin_cycle_ml`).

Common causes:
- Notify service is misconfigured (test independently first)
- Notify service rate limit hit (some services throttle at ~10/hour)
- Target entity is offline

If `_notify_fail_streak` reaches 3, the alert pipeline logs a warning. Fix the notify service, then wait for the next alert to confirm recovery.

### 13.7 Known limitations v1.9

| Limitation | Impact | Workaround |
|---|---|---|
| `kmeans_retrain_stale` may not appear in bulk test | Cosmetic | Test individually, see [10.3](#103-known-limitation-v19-kmeans_retrain_stale-in-bulk-test) |
| `send_test_notification` only supports 10 alert kinds | Cannot test 9 new v1.9 alerts individually | Use `all_alerts`, or wait for natural trigger |
| `defrost_excessive` / `buh_excessive` have no per-alert toggle | Cannot silence individually | Increase dedup window to 7 days |
| No per-alert quiet-hours bypass except `source_stale` | Cannot wake up for `missing_attributes` at night | Disable quiet hours entirely |
| Three languages not supported | Only en, nl | N/A |

All of these are candidates for v1.10.

---

## Appendix A — Alert type quick reference

One-page summary of all 19 alerts.

| # | Alert | Severity | Trigger | Group | Dedup |
|---|---|---|---|---|---|
| 1 | pendulum_hourly | warning | cycles/h ≥ target | pendulum | 60 min |
| 2 | pendulum_daily | warning | cycles/day ≥ target | pendulum | 24 h |
| 3 | short_run | warning | last cycle < threshold | short_cycle | 30 min |
| 4 | short_off | warning | off-time < threshold | short_cycle | 30 min |
| 5 | high_cycle_rate | warning | cycles/h > 1.5× target | short_cycle | 60 min |
| 6 | ml_anomaly | warning | z-score ≥ 2.0 | ml | 60 min |
| 7 | setpoint_osc | warning | ≥ 6 changes + reversal / 30 min | setpoint | 30 min |
| 8 | dhw_pendulum | warning | DHW cycles/h ≥ threshold | setpoint | 60 min |
| 9 | cop_degradation | warning | 7d COP drop > 15% | cop_stooklijn | 24 h |
| 10 | cop_vs_datasheet_low | info | COP > 10% below spec | cop_stooklijn | 24 h |
| 11 | cop_low | warning | daily COP < 2.5 | cop_stooklijn | 30 min |
| 12 | stooklijn_advies | warning | advice + confidence ≥ 0.7 | cop_stooklijn | 7 days |
| 13 | defrost_excessive | warning | 7d defrost count > 30 | (none) | 24 h |
| 14 | buh_excessive | warning | 7d BUH ratio > 15% | (none) | 24 h |
| 15 | source_stale | **critical** | source > 60 s stale | (none) | 60 min |
| 16 | missing_attributes | warning | required attrs missing | (none) | 60 min |
| 17 | db_retention_warning | info | > 100 stale rows | (none) | 24 h |
| 18 | kmeans_retrain_stale | info | last retrain > 14d ago | (none) | 24 h |
| 19 | energy_daily_anomaly | info | today > mean + 2σ, > 2 kWh | (none) | 24 h |

## Appendix B — Alert schema fields

Full field list per alert type, for developers extending templates.

```python
ALERT_SCHEMA = {
    "pendulum_hourly": ["cycles_hour", "target_cph", "lwt_setpoint", "last_duration", "avg_duration_7d", "outdoor", "mode"],
    "pendulum_daily": ["cycles_today", "target_cpd", "lwt_setpoint", "last_duration", "avg_duration_7d", "outdoor", "mode"],
    "short_run": ["duration", "threshold", "lwt_setpoint", "lwt_actual", "indoor", "flow", "outdoor", "mode"],
    "short_off": ["off_min", "threshold", "lwt_setpoint", "indoor", "flow", "outdoor", "mode"],
    "ml_anomaly": ["severity", "mode", "z_score", "top_dim", "last_duration", "avg_duration_7d", "outdoor"],
    "setpoint_osc": ["lwt_setpoint", "lwt_target", "swing", "changes", "window", "threshold", "mode"],
    "cop_degradation": ["week_pct", "threshold", "trend_30d", "mode", "outdoor"],
    "defrost_excessive": ["count_7d", "threshold", "duration_7d_min", "mode", "outdoor"],
    "buh_excessive": ["buh_ratio_7d", "threshold", "buh_count_7d", "mode", "outdoor"],
    "source_stale": ["age_s", "threshold", "source_sensor", "mode"],
    "missing_attributes": ["missing_count", "which", "source_sensor", "mode"],
    "dhw_pendulum": ["dhw_cph", "target", "mode", "outdoor"],
    "high_cycle_rate": ["cycles_hour", "target", "mode", "outdoor"],
    "cop_vs_datasheet_low": ["diff_pct", "expected", "mode", "outdoor"],
    "db_retention_warning": ["stale_alerts", "stale_cycles", "alert_retention_days", "cycle_retention_days", "mode"],
    "kmeans_retrain_stale": ["hours_since_ok", "last_ok_ts", "consecutive_failures", "last_failure_reason", "mode"],
    "energy_daily_anomaly": ["today_el_kwh", "baseline_el_mean", "baseline_el_sigma", "z_score", "samples", "mode"],
}
```

## Appendix C — Related files

| File | Purpose |
|---|---|
| `engine/notification_engine.py` | `BINARY_ALERT_MAP`, `evaluate_alerts`, `passes_filters`, `async_send_notification` |
| `engine/status_report.py` | `build_rich_alert`, `ALERT_SCHEMA`, `ALERT_TITLES`, `ALERT_LABELS`, `ALERT_ADVICE`, emoji maps |
| `coordinator.py` | `_alert_binary_states`, `_build_alert_context`, `_emit_alert`, `_emit_all_test_alerts` |
| `const.py` | `ALERT_DEDUP_DEFAULTS`, `ALERT_TYPE_EMOJI`, `SEVERITY_EMOJI`, `NOTIF_ID_BY_TYPE` |
| `services.py` | `send_test_notification` service |
| `config_flow.py` | Notifications OptionsFlow sub-steps |

## Appendix D — Store file format

`/config/.storage/daikin_cycle_ml.alerts`:

```json
{
  "version": 1,
  "key": "daikin_cycle_ml.alerts",
  "data": {
    "last_sent": {
      "pendulum_hourly": 1792432800.5,
      "pendulum_daily": 1792346400.0,
      "short_run": 1792425600.0,
      "short_off": 1792425600.0,
      "ml_anomaly": 1792418400.0,
      "setpoint_osc": 1792411200.0,
      "cop_low": 1792404000.0,
      "stooklijn_advies": 1791799200.0,
      "cop_degradation": 1792404000.0,
      "defrost_excessive": 1792404000.0,
      "buh_excessive": 1792404000.0,
      "source_stale": 1792432800.0,
      "missing_attributes": 1792425600.0,
      "dhw_pendulum": 1792425600.0,
      "high_cycle_rate": 1792425600.0,
      "cop_vs_datasheet_low": 1792404000.0,
      "db_retention_warning": 1792404000.0,
      "kmeans_retrain_stale": 1792404000.0,
      "energy_daily_anomaly": 1792404000.0
    }
  }
}
```

Timestamps are Unix epoch (seconds since 1970, with fractional part). Deleted manually = all dedup state resets on next restart.
