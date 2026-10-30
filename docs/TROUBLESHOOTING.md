# Troubleshooting

Diagnostic guide for common issues with Daikin Cycle ML.

- **Covers:** setup problems, cycle detection failures, alert issues, entity problems, database errors, HA integration problems
- **For:** end users debugging their install
- **Version:** v1.14.0

Cross-references: [CONFIGURATION.md](CONFIGURATION.md) (fix via options), [ENTITIES.md](ENTITIES.md) (entity reference), [DATABASE.md](DATABASE.md) (DB recovery), [ALERTS.md](ALERTS.md) (alert tuning), [ML.md](ML.md) (ML behavior).

---

## Contents

- [1. First steps for any issue](#1-first-steps-for-any-issue)
- [2. Setup and onboarding](#2-setup-and-onboarding)
- [3. Cycle detection](#3-cycle-detection)
- [4. Sensors and entities](#4-sensors-and-entities)
- [5. COP and energy](#5-cop-and-energy)
- [6. Alerts and notifications](#6-alerts-and-notifications)
- [7. ML and clustering](#7-ml-and-clustering)
- [8. Database](#8-database)
- [9. HA integration](#9-ha-integration)
- [10. Log reference](#10-log-reference)
- [11. When all else fails](#11-when-all-else-fails)

---

## 1. First steps for any issue

Before anything else, always check:

### 1.1 The three gate entities

| Entity | Should be | If not |
|---|---|---|
| `sensor.daikin_cycle_ml_source_health` | < 30 s | ESPAltherma not publishing → fix that first |
| `binary_sensor.daikin_cycle_ml_source_stale` | `off` | Same as above |
| `binary_sensor.daikin_cycle_ml_missing_attributes` | `off` | Check `.h` file for missing registers |

If any of these is wrong, no other data is trustworthy. Fix these first.

### 1.2 Diagnostics download

Settings → Devices & Services → Daikin Cycle ML → menu → **Download diagnostics**.

The JSON file contains:
- Full config entry (options + data)
- Coordinator state
- Store counters
- Baseline + adaptive + cluster state
- COP analysis
- Database counts
- Recent daily summaries

**The first thing to look at** for any issue. Almost every question can be answered by inspecting the diagnostics file.

### 1.3 Logs

Settings → System → Logs, filter `daikin_cycle_ml`.

Look for:
- `ERROR` — real failures that need fixing
- `WARNING` — usually benign, but check if repeated
- `Coordinator update failed` — indicates the whole tick failed

### 1.4 HA startup

If something worked yesterday and doesn't today, first check:
1. Did HA restart? (common cause of "config entry not loaded")
2. Did you upgrade the integration? (migration may have run)
3. Did the source sensor entity_id change? (rare but happens with ESP reflash)

---

## 2. Setup and onboarding

### 2.1 Wizard aborts with "Sensor mist vereiste ESPAltherma-attributen"

The source sensor is missing one or more required attributes.

**Fix 1 — Use Manual mode:**
1. Start wizard
2. On step 1, set **Attribute mode = Manual**
3. Next screen: map each canonical attribute to your sensor's actual attribute name
4. Leave blank if the canonical name exists

**Fix 2 — Enable missing registers in ESPAltherma:**
1. Open ESPAltherma `.h` file
2. Find the missing register (see log or `missing_attrs` repair for the exact name)
3. Enable it
4. Restart ESP device
5. Wait for sensor to republish with all attributes
6. Retry wizard

**Fix 3 — Custom branch with JSON map:**
1. Model = Custom
2. Page B: choose JSON mode
3. Page C: paste a JSON map of non-canonical attribute names

See [CONFIGURATION.md §2.5](CONFIGURATION.md#25-custom-attribute-names).

### 2.2 Wizard shows "attribute_not_found" for a custom map

One of your mapping entries points to an attribute name that doesn't exist on the sensor.

**Fix:**
1. Developer Tools → States → select source sensor
2. Expand Attributes
3. Check that each key in your `custom_attribute_map` exists (exact case-sensitive match)
4. Fix the map, retry

### 2.3 Wizard shows "model not in list"

Your heat pump model isn't in the 17 bundled models.

**Fix:** Use **Model = Custom**. Provide the HP spec JSON (Page A) if you have it, or leave empty to inherit the Basic profile defaults.

### 2.4 Wizard shows "sensor entity not found"

The `source_sensor` doesn't exist or isn't a `sensor.*` entity.

**Fix:**
1. Developer Tools → States
2. Confirm the entity ID exists exactly as typed
3. Confirm it's `sensor.*`, not `binary_sensor.*` or another domain
4. Common mistake: `sensor.altherma` vs `sensor.althermasensors`

### 2.5 Config entry says "not loaded"

HA can't start the integration.

**Check in order:**
1. **Logs** — look for the specific error. Most common:
   - `ImportError` — a dependency is missing (rare)
   - `KeyError` — translation file corrupted (redeploy from HACS)
   - `ModuleNotFoundError` — custom_components folder is missing files
2. **`.storage/core.config_entries`** — verify your entry exists and has `state: loaded`
3. **Entity registry** — check `platform: daikin_cycle_ml` entries exist

**Fix:**
1. Settings → Devices & Services → Daikin Cycle ML → menu → **Reload**
2. If reload fails: restart HA Core
3. If still fails: check `.storage/core.config_entries` for `state: setup_retry` — this means setup failed, likely due to missing source sensor

### 2.6 Wizard succeeded but zero entities appear

Rare. Usually means config entry is registered but never started.

**Fix:**
1. Settings → Devices & Services → Daikin Cycle ML
2. Is it in the "Devices & Services" tab? Or "Integrations" tab (not loaded)?
3. If not loaded: menu → **Reload**
4. If reload fails: HA restart (full restart, not just reload)

If still no entities, check `.storage/core.config_entries` — the entry might have a `disabled_by: user` flag.

---

## 3. Cycle detection

### 3.1 No cycles detected after install

**Check order:**

1. **Is the compressor actually running?** `sensor.daikin_cycle_ml_cycle_state` should be `running` when RPS > threshold
2. **Is RPS > threshold?** Options → Device → `compressor_rps_threshold`. Default 3. If your source reports RPS < 3 during stable operation, lower it to 2 or 1
3. **Is the source sensor fresh?** `sensor.daikin_cycle_ml_source_health` < 30 s
4. **Is water pump on?** Cycles only count when pump is running (water pump guard)
5. **Is required attributes complete?** `binary_sensor.daikin_cycle_ml_missing_attributes` off
6. **Wait 1 hour.** The first cycle is only registered after a full start→run→stop transition, which can take an hour

If all checks pass and no cycles after 2 hours, download diagnostics and check `database.counts.cycles` — if 0, cycles aren't being recorded at all.

### 3.2 All cycles are short (2-5 minutes)

**Cause:** `compressor_rps_threshold` too low. The compressor briefly spins up during standby, and the detector registers that as a cycle.

**Fix:**
1. Options → Device → `compressor_rps_threshold` → raise to 5 or 8
2. Check `sensor.daikin_cycle_ml_thermal_power_live` — should be near 0 when off
3. If thermal power is > 0 during "off" periods, water pump is running but compressor is not — the RPS threshold is the correct fix

### 3.3 Cycles are extremely long (4+ hours)

**Cause:** water pump guard missing, or RPS never drops to 0 due to minimum compressor speed.

**Fix:**
1. Confirm `Water pump operation` attribute is in the source sensor
2. Raise `compressor_rps_threshold` to 3-5 (some pumps idle at 1-2 RPS)
3. Check `sensor.daikin_cycle_ml_current_cycle` attributes — if `rps_max` is 2, and threshold is 3, that cycle would not have been detected. But if it's 0 and pump is on, that's the bug

### 3.4 Mode is always "unknown"

**Cause:** `I/U operation mode` and `Operation Mode` attributes are missing from the source sensor.

**Fix:**
1. Enable those registers in ESPAltherma `.h` file
2. Restart ESP, wait for republish
3. Reload integration (Settings → Daikin Cycle ML → Reload)

### 3.5 DHW cycles are recorded as heating

**Cause:** `3way valve` attribute missing or wrong.

**Fix:**
1. Verify `3way valve` is present in source sensor attributes
2. Check if its value changes when DHW is active
3. If it doesn't change, your ESPAltherma `.h` file is picking up the wrong register

---

## 4. Sensors and entities

### 4.1 Some sensors show "unknown" permanently

**Causes:**

| Sensor | Common cause |
|---|---|
| `thermal_power_live` | Flow = 0 or dT = 0 (compressor off) — this is expected |
| `cop_today` | No COP samples yet (needs ≥ 3) |
| `cop_curve_recent` | No data in last 48 h |
| `spf_season` / `spf_ytd` | Season hasn't started yet, or no cycles |
| `heating_curve_advice` | No heating samples, or DHW active |
| `learned_thresholds` | Adaptive disabled, or < 20 cycles |

**How to fix:** Each is by design. Check the reason attribute (for `heating_curve_advice`) or diagnostics for sample counts.

### 4.2 All COP sensors show 0 or empty

**Cause:** No COP sensor configured.

**Fix:**
1. Options → Device → `cop_sensor_entity` → select your COP sensor
2. Wait 10 minutes for samples to accumulate
3. If still 0, verify the COP sensor itself is publishing values

Without a COP sensor, `sensor.daikin_cycle_ml_cop_today` etc. will not populate.

### 4.3 `heating_curve_advice` stuck on "unknown" or "no_data"

**Check the `reason` attribute** — it tells you exactly why.

| Reason | Fix |
|---|---|
| `no_recent_heating` | Wait for heating cycles |
| `dhw_active` | Wait for DHW to end |
| `within_deadband` | Advice is "keep" — this is normal |
| `comfort_floor_reached` | Lower `comfort_min_c` in Options |
| `comfort_ceiling_reached` | Raise `comfort_max_c` in Options |
| `unit_tracking_behind` | Compressor lags setpoint — will resolve |
| `low_confidence` | Not enough samples in current bucket |
| `no_indoor_sensor` | Configure `indoor_temp_sensor` in Options |

### 4.4 `setpoint_oscillating` fires but I don't see oscillation

**Causes:**
1. **Source sensor quirk:** Some ESPAltherma firmware reports setpoint jitter of ±0.1 °C between reads. This triggers a false positive if `setpoint_osc_min_delta` is too low.
   **Fix:** Options → Pendulum → `setpoint_osc_min_delta` → raise from 0.5 to 1.0

2. **Real oscillation from your thermostat:** Your thermostat may cycle the setpoint. Not a bug.
   **Fix:** Adjust thermostat hysteresis

### 4.5 Binary sensors (heating_active etc.) stuck "off"

**Cause:** Fixed in v0.6.0. If you see this on v1.9, something is wrong.

**Fix:**
1. HA restart (full restart, not reload)
2. If still broken, check that `Operation Mode` attribute is present
3. If operation mode is present, check its value in Developer Tools → States

---

## 4.5 Hybrid-specific issues

### 4.5.1 Hybrid sensors show "unavailable"

**Expected behavior** on non-hybrid installs. `hybrid_mode`,
`boiler_efficiency_cop`, `boiler_contribution_today_pct`,
`boiler_operation_demand`, `boiler_dhw_demand` are all `unavailable`
unless the configured model is an EVLQ series (EVLQ05CV3 / EVLQ08CV3).

**To activate:** change the model via **Reconfigure → Basic** to a hybrid
EVLQ model. If your source sensor publishes `Boiler Operation Demand` /
`Boiler DHW Demand`, the sensors activate immediately after reload.

**If already on EVLQ model but sensors stay unavailable:**

1. Verify ESPAltherma is using `ALTHERMA(HYBRID).h` profile (not a
   non-hybrid one)
2. Check `sensor.althermasensors` for `Boiler Operation Demand`,
   `Hybrid Op. Mode`
3. Restart HA — the model resolves at config load

### 4.5.2 DHW tank temperature shows -40.7°C

**Expected behavior** on hybrid installs. The Intergas boiler handles DHW,
so the Daikin R5T probe is disconnected and reports `-40.7°C`. The
integration treats any value `< -20°C` as `None` before surfacing it — the
DHW-active binary sensor and `cop_today` (DHW mode) will not be polluted
by this sentinel.

**If you see -40.7°C as a live value:**

- This should not happen with v1.15.0+ (sentinel filter active)
- Check the raw value via `sensor.daikin_cycle_ml_*` attributes; if R5T is
  genuinely `< -20°C` it is filtered
- File an issue if the raw -40.7°C leaks through the filter

### 4.5.3 Short-cycle alerts don't fire when boiler is active

**Expected behavior.** During boiler-only operation
(`Boiler Operation Demand = ON`, HP compressor = OFF), these alerts are
suppressed:

- `short_run`
- `short_off`
- `pendulum_hourly`
- `pendulum_daily`

Rationale: boiler producing heat is not a "heat pump short cycle". Firing
these alerts during boiler operation would be a false positive.

**What still fires:** `dhw_pendulum`, `source_stale`, `cop_degradation` —
independent of HP cycle status.

**To verify:** watch `binary_sensor.daikin_cycle_ml_boiler_operation_demand`.
When ON and compressor OFF, the 4 cycle-shape alerts are suppressed at the
`evaluate_alerts` level.

## 5. COP and energy

### 5.1 COP values are unrealistic (> 10 or < 1)

**Cause:** Power sensor is missing or wrong. If using `rps_heuristic` fallback, COP is an estimate.

**Fix:**
1. Options → Device → `power_sensor_entity` → configure a real W sensor
2. If no real sensor available, expect heuristic COP (± 20% error)
3. `sensor.daikin_cycle_ml_cop_today` attributes will show `cop_confidence: low` when heuristic

### 5.2 Energy dashboard shows zero consumption

**Cause:** Energy sensors not added to dashboard, or state_class mismatch.

**Fix:**
1. Settings → Dashboards → Energy → Add consumption
2. Select `sensor.daikin_cycle_ml_electrical_energy_heating_today`
3. Confirm the sensor has `state_class: total_increasing` (check entity attributes)
4. If sensor shows `unknown`, wait for a full hour of operation

### 5.3 Energy accumulators reset every HA restart

**Cause:** Fixed in v1.9 (I8). Should not happen anymore.

**Fix:** If still seeing resets:
1. Check `.storage/daikin_cycle_ml.db` — `model_state` table should have `energy_acc.<today>`
2. Check that `.db` file is not being deleted on restart (some automations do this)
3. Check HA log for `energy_acc persist failed`

### 5.4 `cop_degradation` fires when nothing changed

**Cause:** Weather normalization is imperfect during rapid outdoor temp changes.

**Fix:**
1. Wait 7 days for the baseline to stabilize
2. Check `cop_trend_30d` — if it's still ~0, it's a weather fluke, not real degradation
3. Increase `cop_degradation` dedup window to 7 days

---

## 6. Alerts and notifications

### 6.1 No notifications on my phone

**Check in order:**

1. **Is `notify_service` configured?** Options → Notifications → Delivery
2. **Does your notify service work independently?** Developer Tools → Actions → `notify.your_service` with a test message
3. **Is the alert firing?** Check Options → Notifications → Enabled (per-alert toggles)
4. **Is the alert group enabled?** Options → Notifications → Content
5. **Is quiet hours active?** Options → Notifications → Quiet hours
6. **Is the alert deduplicated?** Check `.storage/daikin_cycle_ml.alerts` `last_sent` timestamps

### 6.2 Persistent notifications appear but phone doesn't buzz

**Cause:** Notify service fails silently.

**Fix:**
1. HA logs → filter `notify.your_service failed`
2. Common causes:
   - Telegram bot token expired
   - Push notification rate limit hit
   - Mobile app out of sync (re-register device)
3. Test with `notify.your_service` directly first

### 6.3 Alerts stop after HA restart

**Cause:** HA Store dedup timestamps get corrupted on restart.

**Fix:**
1. Delete `/config/.storage/daikin_cycle_ml.alerts`
2. Restart HA
3. All dedup state resets — every alert can fire once again

### 6.4 Test-all fires 18 of 19 alerts

**Known limitation (v1.9).** `kmeans_retrain_stale` sometimes does not appear in the persistent notification panel under bulk test. The alert is functional (renders correctly, dispatch succeeds) — HA's `persistent_notification.create` with `blocking=False` drops one of the rapid calls.

**Verify individually:**
```yaml
service: daikin_cycle_ml.send_test_notification
data:
  alert_kind: all_alerts
  ignore_filters: true
```

Or, if you only want to see `kmeans_retrain_stale`, wait for natural trigger (when last retrain is stale > 14 days).

### 6.5 Alerts come in the wrong language

**Fix:** Options → Notifications → Content → `notification_language` = `en` or `nl`.

Next alert fires in the new language. Existing notifications stay in their original language.

### 6.6 Emoji is missing

**Fix:** Options → Notifications → Delivery → `notify_emoji_enabled` = `true`.

Note: persistent notifications never include emoji — only `notify.*` targets do.

### 6.7 `source_stale` alert wakes me up at night

**This is by design.** `source_stale` is critical and bypasses quiet hours because if it fires, ALL alerts are silent (no data → no detection → no alerts). Missing data is a worse problem than missing alerts.

**Fix:** If you want it silenced, disable `alert_enabled_source_stale` in Options → Notifications → Enabled. But understand: you will miss data-outage events entirely.

### 6.8 `stooklijn_advies` fires repeatedly

**Fix:** Options → Notifications → Dedup → raise `stooklijn_advies` from 10080 min (7 days) to 20160 (14 days) or 43200 (30 days). Heat curve advice does not change often.

---

## 7. ML and clustering

### 7.1 `ml_anomaly` never fires

**Check:**
1. Baseline has ≥ 20 cycles per mode (diagnostics → baseline section)
2. `alert_group_ml` is enabled
3. No per-alert toggle silencing it (v1.9 doesn't have one for `ml_anomaly`)
4. Quiet hours allow it

### 7.2 `ml_anomaly` fires too often

**Fix:**
1. Disable `alert_group_ml` (Options → Notifications → Content)
2. Or increase `ml_anomaly` dedup window from 60 min to 720+ min

**Note:** `ml_anomaly` has no per-alert toggle in v1.9. Only the group and dedup controls apply.

### 7.3 Cluster labels keep changing between retrains

**Cause:** K-means instability at low sample counts.

**Fix:** Wait for more data — stability improves with cycle count. Or reduce retrain frequency (candidate for future feature; not exposed in v1.9).

### 7.4 `kmeans_retrain_stale` fires

**Check:**
1. Settings → Devices & Services → Daikin Cycle ML → menu → Download diagnostics
2. Check `database.extra.kmeans_state`:
   - `last_ok_ts` — when did it last succeed?
   - `consecutive_failures` — how many failed attempts?
   - `last_failure_reason` — why did the last attempt fail?

**Fix:**
1. Run `daikin_cycle_ml.recompute_kmeans` manually
2. Check response: `{"ok": true, "n": N, "k": 3}` on success
3. Common failure: fewer than 30 cycles in last 7 days (need more data)
4. If repeated failures with plenty of cycles → DB issue (see §8)

### 7.5 Adaptive thresholds give surprising values

**Cause:** Adaptive learns percentiles from your data. Short_run = p20 means 20% of your cycles are "short".

**Fix:**
1. Disable `adaptive_thresholds_enabled`
2. Use hardcoded `short_run_threshold_min` (default 20)
3. Adaptive is opt-in precisely because it can surprise

---

## 8. Database

### 8.1 `db_corrupt` repair issue

**Fix:**
1. **Backup first:** `cp /config/.storage/daikin_cycle_ml.db /backup/daikin_cycle_ml.db.bak`
2. Run integrity check: `sqlite3 /config/.storage/daikin_cycle_ml.db "PRAGMA integrity_check"`
3. If it fails:
   - Delete the DB file
   - Restart HA
   - Integration creates a fresh DB
   - All historical cycles are lost (see [DATABASE.md §8](DATABASE.md#8-backup-and-recovery) for partial recovery)

### 8.2 `migration_failed` repair issue

**Fix:**
1. Backup DB: `cp /config/.storage/daikin_cycle_ml.db /backup/`
2. Check HA logs for the specific migration name and error
3. Try `daikin_cycle_ml.run_maintenance` with `vacuum: true`
4. If still fails: delete DB, restart HA (data lost)

### 8.3 Database grows too large

**Fix:**
1. Options → Advanced → lower `cycle_retention_days` from 90 to 60 or 30
2. Options → Advanced → lower `alert_retention_days` from 90 to 30
3. Ensure `vacuum_enabled = true`
4. Run `daikin_cycle_ml.run_maintenance` manually
5. Check `database.path` file size (should be < 50 MB for typical use)

### 8.4 `db_retention_warning` alert

**Cause:** Maintenance not running.

**Fix:**
1. Verify `retention_enabled = true` in Options → Advanced
2. Check `last_maintenance_ts` in diagnostics — should be within 24-48 h
3. Run `daikin_cycle_ml.run_maintenance` manually
4. If maintenance keeps failing, check HA logs for `maintenance failed`

### 8.5 `database is locked` errors

**Cause:** A long-running query or VACUUM is blocking writes.

**Fix:**
1. Wait — VACUUM can take up to 30 seconds on large DBs
2. If persistent: restart HA to reset connections
3. If recurring: reduce retention to shrink DB

### 8.6 All historical cycles gone after upgrade

**Cause:** Migration failure or DB deletion.

**Fix:** Check backups. If HA backup was enabled, restore `.storage/daikin_cycle_ml.db` from a pre-upgrade snapshot. Historical data loss is not recoverable without a backup.

---

## 9. HA integration

### 9.1 "Invalid handler specified" in UI

**Cause:** A backup folder was placed inside `custom_components/`.

**Fix:**
1. Check `/config/custom_components/` for folders like `daikin_cycle_ml.bak-*`, `daikin_cycle_ml_old`, etc.
2. Move them to `/config/backups/` or delete
3. Restart HA

**Never place backups inside `custom_components/`** — HA scans every subdirectory as an integration.

### 9.2 Config entry shows "Setup failed"

**Fix:**
1. Check `.storage/core.config_entries` — `state: setup_retry` means setup failed
2. Look at HA logs for the actual error
3. Common causes:
   - Source sensor entity doesn't exist
   - DB permissions issue
   - Import error (dependencies)
4. Fix root cause, then reload integration

### 9.3 Entities disappeared after upgrade

**Cause:** Entity IDs changed (should not happen in v1.9, but did in v1.4.0).

**Fix:**
1. Check Settings → Devices & Services → Daikin Cycle ML → Entities
2. If entities exist but with different IDs: update your automations
3. If entities are in "unavailable" state: HA restart
4. If entities are truly gone: check entity registry for orphaned entries with `unique_id: daikin_cycle_ml_*`

### 9.4 HA startup is very slow (30+ seconds) after install

**Cause:** DB migration running on first startup after upgrade.

**Fix:** Wait — first startup after a migration is slower. Second startup should be normal. If consistently slow:
1. Check DB size (should be < 50 MB)
2. Check for large `cop_samples` table (365-day retention accumulates)
3. Consider reducing `cop_retention_days` (not exposed as option in v1.9)

### 9.5 Multiple config entries appear

**Cause:** You added the integration twice by mistake.

**Fix:**
1. Settings → Devices & Services → Daikin Cycle ML
2. Look for duplicate entries
3. Remove the one with fewer entities (or the one without recent activity)
4. Only one entry per source sensor is supported in v1.9

---

## 10. Log reference

Common log messages and their meaning.

### 10.1 Errors

| Message | Meaning | Fix |
|---|---|---|
| `Coordinator update failed` | Whole tick failed — usually source sensor issue | Check `source_health` |
| `persistent_notification failed` | Notification service unavailable | Retry, or check HA Core |
| `notify entity path failed` | Configured notify service unreachable | Test service independently |
| `Alert dispatch failed` | `evaluate_alerts` raised — usually context build issue | Check specific alert in logs |
| `energy_acc persist failed` | DB write failed | Check DB permissions, disk space |
| `kmeans persist failed` | DB write failed | Same as above |
| `db_cycle_stats failed` | DB query failed | Restart HA, check integrity |
| `maintenance failed` | 03:00 prune failed | Check DB, run manually |

### 10.2 Warnings

| Message | Meaning | Action |
|---|---|---|
| `source_stale: no update for N seconds` | Source sensor silent | Check ESP device |
| `missing attributes: [list]` | Attributes removed from source | Check `.h` file |
| `migration running, do not interrupt` | Schema migration in progress | Wait |
| `notify fail streak N` | N consecutive notify failures | Fix notify service |

### 10.3 Debug hints

To increase log verbosity temporarily:

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.daikin_cycle_ml: debug
```

Then restart HA and reproduce the issue. Debug logs show:
- Every coordinator tick
- Every cycle detected
- Every alert decision
- Every DB query

**Revert to `info` when done** — debug is very verbose and fills HA logs quickly.

---

## 11. When all else fails

### 11.1 Full reset procedure

Last resort. **All historical data is lost.**

1. **Export what you can:**
   ```yaml
   service: daikin_cycle_ml.export_cycles
   data:
     format: json
     days: 365
   ```
2. **Remove integration:** Settings → Devices & Services → Daikin Cycle ML → **Remove**
3. **Delete DB files:**
   ```bash
   rm /config/.storage/daikin_cycle_ml.db
   rm /config/.storage/daikin_cycle_ml.alerts
   rm /config/.storage/daikin_cycle_ml.user_datasheets
   ```
4. **Restart HA Core**
5. **Re-add integration** via Settings → Devices & Services → Add Integration

Historical cycles, alerts, and ML state are gone. Config options start at defaults.

### 11.2 Partial reset

To reset only ML state without losing cycles:

```sql
-- Reset baseline
DELETE FROM model_state WHERE key = 'baseline_state';

-- Reset adaptive thresholds
DELETE FROM model_state WHERE key = 'adaptive_thresholds';

-- Reset k-means
DELETE FROM model_state WHERE key = 'kmeans_state';

-- Reset energy baseline
DELETE FROM model_state WHERE key = 'thermal_daily_baseline';
```

Then restart HA. Cycles remain in the DB. Baseline relearns from future cycles.

### 11.3 Report an issue

If troubleshooting doesn't resolve it:

1. **Download diagnostics:** Settings → Devices & Services → Daikin Cycle ML → menu → Download diagnostics
2. **Collect HA logs:** Settings → System → Logs → Download full log
3. **Note the exact behavior:** what you did, what happened, what you expected
4. **Include:** version of the integration, HA Core version, Python version
5. **Open issue:** https://github.com/elRadix/daikin_cycle_ml/issues

**Redact any sensitive info** — diagnostics already redacts `notify_service`, but double-check for entity names you don't want public.

### 11.4 Community support

- **Discussions:** https://github.com/elRadix/daikin_cycle_ml/discussions
- **Tweakers forum:** ESPAltherma topic (Dutch, mixed English)
- **Home Assistant Community:** search "Daikin Cycle ML"

The Tweakers topic has the largest user base. Search before posting — most issues have been seen before.

## 9B. Ruff/mypy fails on CI but passes locally

**Cause:** local ruff or mypy runs with different flags than CI.

**Fix:** use the exact CI commands:

    ruff check --no-fix --select E,F,W --ignore E501,E402,F401 custom_components/daikin_cycle_ml tests

    /opt/mypy-ci-venv/bin/mypy --strict --python-version 3.14 custom_components/daikin_cycle_ml


## 9C. Coverage fails at 99.99%

**Cause:** a new code path lacks a test, or a test was modified to pass without exercising the path.

**Fix:**

1. Run pytest locally and see which file/line lacks coverage
2. Write a test that exercises that specific line
3. Never add pragma no-cover to silence a real gap
4. Never reduce cov-fail-under from 100 in pyproject.toml

The 100% coverage gate is non-negotiable in this project.

