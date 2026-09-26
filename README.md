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

- [Why](#why)
- [Features](#features)
- [Installation](#installation)
- [Config flow — step by step](#config-flow--step-by-step)
  - [Initial setup wizard (8 steps)](#initial-setup-wizard-8-steps)
  - [Options menu (6 screens)](#options-menu-6-screens)
- [Services](#services)
- [Entities](#entities)
- [Alerts](#alerts)
- [ML pipeline](#ml-pipeline)
- [Clustering](#clustering)
- [Scheduled jobs](#scheduled-jobs)
- [Retention & storage](#retention--storage)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Out of scope](#out-of-scope)

---

## Why

Pendelen (short-cycling) is the #1 cause of reduced COP and extra wear on
Daikin Altherma heat pumps. Existing HA integrations do not detect it,
because they look at temperature or power — not at the actual compressor
runtime pattern.

Daikin Cycle ML watches the ESPAltherma sensor stream, detects every
compressor cycle (start → run → stop), scores it, learns what "normal" looks
like for **your** installation per mode (Heating / Cooling / DHW), and warns
you when patterns drift.

No cloud. No external API. Everything runs inside your Home Assistant box.

---

## Features

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
- **Setpoint-oscillation detection** — rolling 30-min window, change counter
  against a tunable threshold
- **Bilingual notifications** — EN + NL templates with clear situation +
  advice, selectable per installation
- **Per-group alert toggles** — 5 groups (pendulum / short-cycle / ML /
  setpoint / COP-stooklijn) can be silenced independently
- **COP stooklijn analysis** — daily advice + bucket table
- **Custom attribute map** — remap non-standard ESPAltherma firmware keys
- **Selected attributes** — restrict processing to opt-in attributes
- **SQLite persistence** — retention, daily rollups, auto-migration 8→11 dim
- **50 entities** — 31 sensors + 19 binary sensors
- **6 services** — reset, export, label, recompute, maintain, test-notify

---

## Installation

1. Copy `custom_components/daikin_cycle_ml/` into your HA config tree
   (usually `/config/custom_components/daikin_cycle_ml/`).
2. **Restart Home Assistant** (Settings → System → Restart).
3. **Settings → Devices & Services → Add Integration → "Daikin Cycle ML"**.
4. Follow the 8-step wizard (see next section).

**Requirements**
- Home Assistant 2026.9 or newer
- ESPAltherma publishing attributes on a sensor
- Recommended: an outdoor temp attribute + a leaving-water temp attribute
  (needed for dT and COP)

---

## Config flow — step by step

### Initial setup wizard (8 steps)

After clicking **Add Integration → Daikin Cycle ML**, the wizard walks you
through 8 steps.

#### Step 1 — Source & model

| Field | Type | Default | Notes |
|---|---|---|---|
| **Source sensor** | entity picker | `sensor.althermasensors` | Your ESPAltherma sensor. Must publish the attributes below. |
| **Model** | dropdown | `EPRA12EAV3` | Picks a model profile (defaults for thresholds). Choose **Custom** if your pump is not in the list. |

#### Step 2 — Custom attribute map *(only if Model = Custom)*

Optional. A JSON object mapping **standard keys → your actual attribute names**:

```json
{
  "INV frequency (rps)": "my_inv_rps",
  "I/U operation mode": "my_iu_mode"
}
```

Leave empty if your firmware already uses the standard keys.

#### Step 3 — Selected attributes

Multi-select list of which ESPAltherma attributes to process.

- **Recommended** attributes are pre-selected (13 items, always safe).
- **Optional** attributes can be added for extra features (COP, BUH step2, etc).
- **Required** attributes (I/U mode, RPS, LWT, inlet, outdoor) are **always
  kept** regardless of your selection — cycle detection depends on them.

#### Step 4 — Cycle detection

| Field | Default | Notes |
|---|---|---|
| **Compressor RPS threshold** | `3` | Compressor is "on" when RPS > this. |
| **Power sensor** | *(none)* | Optional. If set, used as fallback when RPS is missing. |
| **Fallback power threshold (W)** | `200` | Power above this counts as compressor on. |
| **Indoor temp sensor** | *(none)* | Optional. Enables `indoor_temp_avg` in the ML vector. |

#### Step 5 — Pendulum thresholds

| Field | Default | Notes |
|---|---|---|
| **Short run threshold (min)** | `20` | Cycles shorter than this are flagged. |
| **Short off threshold (min)** | `5` | Off-times shorter than this are flagged. |
| **Pendulum cycles per hour** | `4` | Triggers hourly pendulum alert. |
| **DHW pendulum cycles per hour** | `3` | Triggers DHW-specific pendulum alert. |

#### Step 6 — Quality thresholds

| Field | Default | Notes |
|---|---|---|
| **Good run threshold (min)** | `45` | Below = quality penalty. |
| **Good dT threshold (K)** | `5.0` | Below = quality penalty. |
| **Good off threshold (min)** | `20` | Below = quality penalty. |
| **Target cycles per day** | `8` | Used in daily rollup advice. |

#### Step 7 — Notifications

| Field | Default | Notes |
|---|---|---|
| **Persistent notifications** | `true` | Show alerts in HA sidebar. |
| **Notify target** | *(empty)* | Pick a `notify.*` entity or legacy service. Empty = no push. |
| **Quiet hours** | `false` | |
| **Quiet hours start / end** | `22:00` / `07:00` | Non-critical alerts suppressed. |

You can set `notification_language`, emoji, action-advice, alert groups and
status updates later via the Options menu.

#### Step 8 — Finalize

Review and click **Submit**. The integration starts polling every 30 s.

---

### Options menu (6 screens)

Go to **Settings → Devices & Services → Daikin Cycle ML → Configure**.
A menu with 6 screens opens. Each screen saves independently — you can
change one field and go back without losing the rest.

#### 1. Device

Runtime detection parameters.

| Field | Default | Notes |
|---|---|---|
| **Compressor RPS threshold** | `3` | |
| **Power sensor** | *(none)* | |
| **Fallback power threshold (W)** | `200` | |
| **Indoor temp sensor** | *(none)* | |
| **COP sensor** | *(none)* | If set, daily COP samples are collected. |

#### 2. Pendulum

Thresholds that decide what counts as a "bad" cycle.

| Field | Default | Notes |
|---|---|---|
| **Short run threshold (min)** | `20` | |
| **Short off threshold (min)** | `5` | |
| **Pendulum cycles per hour** | `4` | Hourly alert trigger. |
| **Pendulum cycles per day** | `40` | Daily alert trigger. |
| **DHW pendulum cycles per hour** | `3` | |
| **Setpoint oscillation threshold** | `6` | Number of setpoint changes in window before alert fires. Default 6 filters normal thermostat tuning, warns on real oscillation. |
| **Setpoint window (min)** | `30` | Rolling window. |
| **Minimum setpoint change (°C)** | `0.5` | Filters floating-point noise. |

#### 3. Quality

| Field | Default | Notes |
|---|---|---|
| **Good run threshold (min)** | `45` | |
| **Good dT threshold (K)** | `5.0` | |
| **Good off threshold (min)** | `20` | |
| **Target cycles per day** | `8` | |

#### 4. Notifications

| Field | Default | Notes |
|---|---|---|
| **Persistent notifications** | `true` | |
| **Notify target** | *(empty)* | Dropdown of `notify.*` entities. |
| **Emoji in notifications** | `true` | Prefix with emoji for quick scanning. |
| **Include action advice** | `true` | Append the top advice line. |
| **Quiet hours** | `false` | |
| **Quiet hours start / end** | `22:00` / `07:00` | |
| **Alert aggregation (minutes)** | `30` | Dedup window per alert type. |
| **Periodic status updates** | `false` | Opt-in summary. |
| **Status interval (hours)** | `24` | |
| **Notification language** | `English` | Dropdown: **English** or **Nederlands**. |
| **Alert: pendulum** | `true` | |
| **Alert: short cycle** | `true` | |
| **Alert: ML anomaly** | `true` | |
| **Alert: setpoint oscillation** | `true` | |
| **Alert: COP / heat curve** | `true` | |

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

---

## Services

All services live under the `daikin_cycle_ml.` domain.

| Service | Purpose | Key fields |
|---|---|---|
| `reset_counters` | Reset daily counters | *(none)* |
| `export_cycles` | Export cycles (JSON/CSV) | `days`, `format`, `path` |
| `label_cycle` | Attach a user label to a cycle | `cycle_id`, `label` |
| `recompute_baseline` | Rebuild MultiBaseline from DB history | `days` (default 30) |
| `run_maintenance` | Retention prune + optional VACUUM | *(none)* |
| `send_test_notification` | Send a test notification to the configured target | `entry_id` (opt), `message` (opt), `target` (opt) |

Example — send a test notification:

```yaml
service: daikin_cycle_ml.send_test_notification
data:
  message: "Hello from Daikin Cycle ML"
```

---

## Entities

**31 sensors** — cycle state, current/last cycle metrics, daily counters,
learned thresholds, source health, stooklijn advice, COP today.

**19 binary sensors** — compressor running, hourly/daily pendulum, short run,
short off, defrost, BUH step1/2, DHW, heating, cooling, source stale,
missing attributes, setpoint oscillating, DHW pendulum, high cycle rate,
cluster membership (pendulum / normal / dhw-like).

Full list: see `sensor.py` and `binary_sensor.py` entity description dicts.

---

## Alerts

Alerts are dispatched on cycle-close (or on a schedule for daily/weekly
ones). Each alert has:

- a **severity** (`info` / `watch` / `warning` / `critical`)
- a **group** (`pendulum` / `short_cycle` / `ml` / `setpoint` / `cop_stooklijn`)
- a **dedup key** (aggregation window, default 30 min)
- a **language** (EN or NL, set via Options)

The message body is a **full sentence**: what happened → why → what to do.

| Alert | Trigger | Group |
|---|---|---|
| `pendulum` (hourly) | cycles/h ≥ target | pendulum |
| `pendulum` (daily) | cycles today ≥ target | pendulum |
| `short_run` | last cycle < threshold | short_cycle |
| `short_off` | off-time < threshold | short_cycle |
| `ml_anomaly` | z-score ≥ watch | ml |
| `setpoint_osc` | N setpoint changes in window | setpoint |
| `cop_low` | daily COP below 2.5 | cop_stooklijn |
| `stooklijn_advies` | daily heat-curve advice | cop_stooklijn |
| `status_update` | opt-in periodic summary | *(none)* |

**Delivery channels**

- **Persistent notification** — always shown in HA sidebar (if enabled)
- **Notify target** — configurable `notify.*` entity or legacy service

**Quiet hours** suppress non-critical alerts.

---

## ML pipeline

Every closed cycle becomes an **11-dimensional feature vector**:

```
duration_s, dT_max, dT_avg, rps_max, rps_avg,
outdoor_temp, buh_used, defrost_used,
cop_avg, lwt_avg, indoor_temp_avg
```

Missing values are filled with `0.0` (JSON-safe, no NaN).

The vector feeds three self-learning layers:

1. **MultiBaseline** — per-mode EWMA, produces z-scores for anomaly detection.
   Dim-guarded: if a legacy 8-dim baseline is detected, it is reset.
2. **AdaptiveThresholds** — per-mode percentile, learns `short_run` and
   `good_off` thresholds from your real cycles (opt-in).
3. **K-means clusters** — weekly retrain, per-cycle nearest-centroid.

No labels. No supervised training. Everything is self-learning.

---

## Clustering

Weekly k-means over the last 7 days produces **3 centroids**.

New cycles are assigned via nearest-centroid and stored as `cluster_id`.

Cluster labels are auto-derived from centroid properties:

- shortest mean duration → **cluster_pendulum**
- highest `dT_max` → **cluster_dhw_like**
- rest → **cluster_normal**

Three binary sensors expose membership for the latest cycle.

---

## Scheduled jobs

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

## Retention & storage

- **Storage**: `/config/.storage/daikin_cycle_ml.db` (SQLite)
- **Tables**: `cycles`, `features`, `alerts`, `daily_summary`,
  `cop_samples`, `model_state`, `sqlite_sequence`
- **Cycle retention**: `cycle_retention_days` (default **90**)
  — older cycles are rolled up into `daily_summary` before pruning
- **Alert retention**: `alert_retention_days` (default **30**)
- **Features**: orphan-pruned via FK
- **VACUUM**: optional, runs after prune

Schema migration is automatic (`8 → 11 dim feature vectors`).

---

## Troubleshooting

**Binary sensors stay off (`heating_active`, `cooling_active`, `dhw_active`)**
- Fixed in **v0.6.0**. If you are on an older version, upgrade.
- If you still see stuck sensors after upgrade, do a **full HA restart**
  (Settings → System → Restart). A config-entry reload is not enough.

**`source_stale` repair is shown**
- ESPAltherma is not publishing fresh data. Check the ESP device and
  Wi-Fi. The repair resolves automatically when data resumes.

**`missing_attrs` repair is shown**
- The source sensor is missing one or more required attributes. Verify
  that ESPAltherma is publishing all fields, or add a custom attribute
  map in the Options → Device screen.

**Alerts are noisy**
- Increase **Alert aggregation (minutes)** in Options → Notifications.
- Disable one or more alert groups you do not care about.
- Raise **Pendulum cycles per hour** or **per day**.
- Enable **Quiet hours** for overnight suppression.

**Notifications are in the wrong language**
- Options → Notifications → **Notification language** → pick EN or NL.

**`setpoint_osc` alert never fires**
- Check that the source sensor actually publishes **LW setpoint (main)**.
- Default threshold is **6 changes in 30 minutes** — most installations
  never hit that (which is correct; it means you do not have the problem).

---

## Testing

- **987 tests**, **95.65% coverage** (as of v0.6.0)
- Framework: `pytest` + `pytest_homeassistant_custom_component`
- Coverage threshold enforced at **95%** in `pyproject.toml`

Run locally:

```bash
PYTHONPATH=/workspace pytest -q
```

---

## Out of scope

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