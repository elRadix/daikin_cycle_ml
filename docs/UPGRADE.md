# Upgrade Guide

Version-by-version upgrade notes for Daikin Cycle ML, with migration steps and breaking changes.

- **Covers:** breaking changes, migration paths, deprecated options, DB migrations, entity renames
- **For:** existing users upgrading from v1.4 to v1.9, users troubleshooting upgrade issues
- **Version:** v1.9.0

Cross-references: [DATABASE.md](DATABASE.md) (schema migrations), [CONFIGURATION.md](CONFIGURATION.md) (options), [ENTITIES.md](ENTITIES.md) (entity surface), [TROUBLESHOOTING.md](TROUBLESHOOTING.md) (when upgrade fails).

---

## Latest: v1.14.0

**Released:** <pending, in development on main>
**Breaking:** none

### What changes

New electrical-input cascade for COP. Power-meter users, ESPAltherma 2.0 users (Stats section present), and ESPAltherma 1.x users without a power meter now all get consistent per-sample COP.

### What you need to do

**Power-meter users (most common):** nothing. Your `power_sensor_entity` remains ground truth, no offset applied.

**ESPAltherma 2.0 users:** nothing. The integration auto-detects `Stats: Electrical input estimated (kW)` and uses it directly. Configure phases/BUH in ESPAltherma itself. The integration does not add an offset here (prevents double-counting).

**ESPAltherma 1.x users without a power meter:** open Settings, then Devices & Services, then Daikin Cycle ML, then Configure, then COP calculation. Set supply phases (1 for most homes, 3 for three-phase). Adjust BUH step kW if step 2 is 6 kW on your unit. Defaults are correct for a standard single-phase installation with 3 kW + 3 kW BUH.

### New entity

`sensor.daikin_cycle_ml_electrical_power_estimated` (W) with `source` attribute. Useful for verifying which cascade path was chosen.

### Historical samples

Not rewritten (backwards compat). Pre-v1.14.0 samples retain legacy thermal derivation. Post-upgrade samples use the improved formula.

---

## v1.10.0

**Released:** 2026-10-20
**Breaking:** only for multi-entry users with pre-existing history

### What changes

The integration historically stored its SQLite DB in a single shared
file (`/config/.storage/daikin_cycle_ml.db`) across all config entries.
This caused cross-entry data leaks in the historical aggregate tables
(`daily_summary`, `cop_hourly`, `cop_samples`). v1.10.0 gives each
config entry its own DB file: `/config/.storage/daikin_cycle_ml_<entry_id>.db`.

### What you need to do

**Single-entry users (majority): nothing.** First setup after upgrade
silently migrates the legacy DB to `daikin_cycle_ml_<entry_id>.db` with
a backup in `/config/.daikin_backups/`. Zero downtime, zero data loss.

**Multi-entry users: verify the auto-assignment.** The legacy DB is
assigned to your oldest entry (by config-entry registration order). A
repair issue `legacy_db_multi_entry` appears. Three services are
available to correct the assignment if needed:

- `daikin_cycle_ml.assign_legacy_db` — move the DB to a different entry
- `daikin_cycle_ml.archive_legacy_db` — archive and start fresh
- `daikin_cycle_ml.export_legacy_db` — dump to CSV for audit

After calling any of these services, reload both affected config
entries (Settings > Devices & Services > Daikin Cycle ML > Reload).

### Known limitation

If two or more entries ran concurrently on the shared DB before v1.10.0,
per-entry historical attribution is not recoverable — the data was
physically interleaved. The repair issue and export service make this
visible. New cycles/samples from v1.10.0 forward are fully isolated.

### Rollback

Not supported. Once migrated, downgrading to v1.9.x will create a fresh
legacy DB (the per-entry files will be ignored). If you need to revert,
restore the backup from `/config/.daikin_backups/` manually.

---

## Contents

- [1. Quick upgrade checklist](#1-quick-upgrade-checklist)
- [2. v1.8.x to v1.9.0](#2-v18x-to-v190)
- [3. v1.7.x to v1.8.x](#3-v17x-to-v18x)
- [4. v1.6.x to v1.7.x](#4-v16x-to-v17x)
- [5. v1.5.x to v1.6.x](#5-v15x-to-v16x)
- [6. v1.4.x to v1.5.x](#6-v14x-to-v15x)
- [7. v1.0.x to v1.4.x](#7-v10x-to-v14x)
- [8. Downgrade procedure](#8-downgrade-procedure)
- [9. Recovering from failed upgrade](#9-recovering-from-failed-upgrade)
- [10. Version history timeline](#10-version-history-timeline)

---

## 1. Quick upgrade checklist

For every upgrade, do these first:

- [ ] **Back up `/config/.storage/`** (Settings → System → Backups → Create backup, or `cp -r /config/.storage /backup/.storage.bak`)
- [ ] **Read the CHANGELOG** for the target version — check for "Breaking changes" section
- [ ] **Read the specific upgrade section** below for your version jump
- [ ] **Note your current options:** Settings → Devices & Services → Daikin Cycle ML → Configure — screenshot or write down non-default settings
- [ ] **Note your entity IDs** used in automations — screenshot the entity list
- [ ] **Verify HA Core version** is >= 2026.9 (required for Python 3.14)

After upgrade:
- [ ] **Verify all entities are back:** Settings → Devices & Services → Daikin Cycle ML → Entities
- [ ] **Run Test-all:** Options → Notifications → Test menu → Send ALL test notifications
- [ ] **Check logs:** Settings → System → Logs, filter `daikin_cycle_ml` — no unexpected errors
- [ ] **Verify entity count:** compare with pre-upgrade (was 61 in v1.8.x)
- [ ] **Verify config options:** check that non-default settings persisted

If anything is wrong, see §9 (failed upgrade recovery) before doing anything else.

---

## 2. v1.8.x to v1.9.0

### 2.1 Summary

**Breaking changes:** none.

**New features:**
- 3 new alerts: `db_retention_warning`, `kmeans_retrain_stale`, `energy_daily_anomaly`
- Per-alert toggles (11 new boolean options)
- Dedup windows (19 new numeric options)
- New service: `recompute_kmeans`
- Q4 fix: `setpoint_osc` no longer fires on monotonic drift
- I7 fixes: retention fallbacks, defrost duration, energy None semantics
- I8 fix: energy_acc decoupled from runtime lifecycle

### 2.2 What changes for you

**Nothing breaks.** v1.9 is backward compatible with v1.8 config.

**New alert types** will fire if their conditions are met:
- `db_retention_warning` — if your DB has > 100 stale rows
- `kmeans_retrain_stale` — if last retrain > 14 days ago
- `energy_daily_anomaly` — if today's energy > 2σ above baseline

You can silence them individually via Options → Notifications → Enabled.

**Energy accumulators** now survive HA restarts independently. Before v1.9, a runtime restore failure could wipe your daily energy data. This is fixed.

**`setpoint_oscillating` alert** is now less noisy — it requires actual reversals (up-then-down), not just monotonic changes.

### 2.3 Migration steps

1. **Back up `.storage/`**
2. **Update via HACS** (or manual deploy)
3. **Restart HA Core**
4. **Verify:** all 61 entities present
5. **Run Test-all** to verify alerts
6. **Review new options:** Options → Notifications → Enabled and → Dedup

**Nothing to configure manually** — new options default to safe values.

### 2.4 If you had custom dedup settings

Pre-v1.9 used a single global `alert_aggregation_minutes` setting. v1.9 replaces it with 19 per-alert dedup windows.

**Your old value is NOT migrated automatically.** If you had `alert_aggregation_minutes: 60`, all 19 dedup windows default to their built-in defaults (mostly 30-1440 min, not 60).

To replicate your old setting: Options → Notifications → Dedup → set each alert you care about to your old value.

### 2.5 If Test-all shows 18 of 19 alerts

Known limitation — `kmeans_retrain_stale` may not appear in the bulk test. See [ALERTS.md §10.3](ALERTS.md#103-known-limitation-v19-kmeans_retrain_stale-in-bulk-test). Not a bug, verify individually if needed.

---

## 3. v1.7.x to v1.8.x

### 3.1 Summary

**Breaking changes:** none.

**New features:**
- Smart auto-import wizard (issue #51)
- Diagnose screen
- Custom attribute map improvements

### 3.2 What changes for you

**Nothing breaks.** v1.8 is backward compatible with v1.7 config.

**If your sensor uses non-canonical attribute names**, the wizard now auto-detects them (alias + fuzzy matching). You may be able to complete the wizard in Automatic mode where v1.7 required Manual.

**If you already have a working install**, nothing changes — your existing config stays.

### 3.3 Migration steps

1. **Back up `.storage/`**
2. **Update via HACS**
3. **Restart HA Core**
4. **Verify** entities

No manual steps required.

### 3.4 v1.8.1 fix (advice bleed)

If you were on v1.8.0: v1.8.1 fixes a bug where global advice from one alert bled into others (R331). **Upgrade to v1.8.1 if you were on v1.8.0.**

No config changes needed.

---

## 4. v1.6.x to v1.7.x

### 4.1 Summary

**Breaking changes:** none.

**New features:**
- 4 helper defrost sensors (disabled by default)

### 4.2 What changes for you

**Nothing breaks.** v1.7 is backward compatible with v1.6 config.

The 4 new helper sensors (`*_daily_history`, `*_daily_summary`, `*_monthly_history`, `*_monthly_summary`) are **disabled by default**. Enable them via the entity registry if you want them.

### 4.2 Migration steps

1. **Back up `.storage/`**
2. **Update via HACS**
3. **Restart HA Core**
4. **Verify** entities (61 total, same as v1.6)

### 4.3 v1.7.1 and v1.7.2

- **v1.7.1** — security updates (no user-facing changes)
- **v1.7.2** — hotfix for issue #49 (defrost tracking edge case)

If you were on v1.7.0, upgrade to v1.7.2.

---

## 5. v1.5.x to v1.6.x

### 5.1 Summary

**Breaking changes:** YES — `sensor.daikin_cycle_ml_cop_today` changed from blended COP to heating-only COP.

**New features:**
- Per-mode COP (9 new sensors)
- SPF / SCOP (3 new sensors)
- Daikin datasheets (3 new sensors + 2 services)
- Weather-normalized degradation (3 new sensors)
- Runtime + energy accounting (12 new sensors)
- OptionsFlow overhaul with sections + notifications sub-menu

### 5.2 The breaking change

**`sensor.daikin_cycle_ml_cop_today` now reports heating-only COP.**

The previous value (blended across heating, DHW, cooling) is preserved on the new sensor `sensor.daikin_cycle_ml_cop_combined_today`.

**Action required if you have automations consuming `cop_today` and expect blended:**

Before:
```yaml
{{ states('sensor.daikin_cycle_ml_cop_today') }}
```

After (if you want blended):
```yaml
{{ states('sensor.daikin_cycle_ml_cop_combined_today') }}
```

**No action** if you want heating-only (the new default) — the entity ID stayed the same.

### 5.3 What changes for you

**Entity count:** 63 total (was 24). Most are new COP/datasheet/runtime/energy sensors.

**Options menu:** completely restructured. Old flat menu → grouped sections + notifications sub-menu. All old options are still there, just better organized.

**`heating_curve_advice`:** gains 8 new attributes. Existing automations using old attributes still work.

**New services:** `export_cop_hourly`, `import_datasheet`, `remove_user_datasheet`.

### 5.4 Migration steps

1. **Back up `.storage/`**
2. **Screenshot your old Options menu** (in case you need to re-enter values)
3. **Update via HACS**
4. **Restart HA Core**
5. **Update automations** that use `cop_today` (see §5.2)
6. **Verify** entity count = 63
7. **Consider re-selecting your model** if you were on `Custom` before — v1.6 has 17 bundled models (was 5). Reconfigure to enable datasheet-backed COP.

### 5.5 Re-select your model (optional but recommended)

The wizard now has 17 models instead of 5. If your Daikin was configured as Custom, re-select your specific model:

1. Settings → Devices & Services → Daikin Cycle ML → **Reconfigure**
2. Pick your exact model from the dropdown
3. Save

This enables `cop_normalized_a7w35` and `cop_vs_datasheet_pct` for your model.

If your model is not bundled, use the `import_datasheet` service to add it.

### 5.6 Database

**No migration.** Schema stays at v14 (v14 was introduced in v1.5, so v1.6 inherits it).

Wait — that's not right. Let me correct: v1.6 did NOT introduce schema changes. The schema migration from v1.5 to v1.6 is minimal (just COP metadata columns that were added in v1.5).

If you're on v1.5 schema (v14), v1.6 works directly.

### 5.7 v1.6.1 and v1.6.2

- **v1.6.1** — energy tick fix (standby power not counted as heating)
- **v1.6.2** — onboarding fix (Automatic/Manual mode for issue #25)

If you were on v1.6.0, upgrade to v1.6.2 directly.

---

## 6. v1.4.x to v1.5.x

### 6.1 Summary

**Breaking changes:** none, but behaviour changes in LWT advice.

**New features:**
- Dynamic LWT step (1-3 °C instead of hardcoded 2)
- Comfort dual-loop (floor + ceiling)
- Setpoint comparison (uses `LW setpoint (main)` instead of last bucket sample)
- Tracking-error dampening
- 8 new attributes on `heating_curve_advice`

### 6.2 What changes for you

**Nothing breaks.** v1.5 is backward compatible with v1.4 config.

**LWT advice may suggest different steps:**
- Before: always step 2 °C
- After: step 1-3 °C based on delta and tracking error

If you preferred the fixed 2 °C step, you'll need to modify your automation to cap `step_c` at 2.0.

**Two new comfort options** in the wizard: `comfort_min_c` (floor, default 20) and `comfort_max_c` (ceiling, default 24). These gate the advice algorithm.

### 6.3 Migration steps

1. **Back up `.storage/`**
2. **Update via HACS**
3. **Restart HA Core**
4. **Verify** entity count = 24 (unchanged from v1.4)
5. **Optional:** configure `indoor_temp_sensor` in Options → Device — enables the comfort guardrails

### 6.4 Attribute changes on `heating_curve_advice`

New attributes in v1.5:
- `state_label` — localized label with step substituted
- `step_c` — recommended step (1.0-3.0)
- `delta_c` — `huidige_lwt − optimale_lwt`
- `huidige_setpoint` — current LWT setpoint
- `doel_setpoint` — suggested new setpoint
- `tracking_error` — LWT − setpoint
- `comfort_cap` — `floor` / `ceiling` / `ok` / `unavailable`
- `reason` — machine-readable reason code

**Reason codes** are new. Existing automations that only check `state` still work — `reason` is additive.

---

## 7. v1.0.x to v1.4.x

### 7.1 Summary

**Breaking changes:** YES — entity slug renames in v1.4.0.

**New features (cumulative):**
- v1.1.0: HACS-compliant layout
- v1.2.x: IQS Silver + Gold
- v1.3.0: COP hourly rollup + KPI sensors + REST endpoint
- v1.4.0: Entity slug renames
- v1.4.1-1.4.5: Bug fixes

### 7.2 The breaking change (v1.4.0)

Entity IDs were renamed from a legacy scheme to `sensor.daikin_cycle_ml_<key>`.

**Old IDs** (v1.0-v1.3):
```
sensor.daikin_cycle_state
sensor.daikin_current_cycle
sensor.daikin_cycles_today
sensor.daikin_quality_today
...
```

**New IDs** (v1.4+):
```
sensor.daikin_cycle_ml_cycle_state
sensor.daikin_cycle_ml_current_cycle
sensor.daikin_cycle_ml_cycles_today
sensor.daikin_cycle_ml_quality_today
...
```

**Fix in automations:** find-replace `daikin_` prefix with `daikin_cycle_ml_` in all entity IDs.

### 7.3 Migration steps

1. **Back up `.storage/` AND `configuration.yaml`** (and any UI-managed automations)
2. **Update via HACS**
3. **Restart HA Core**
4. **Verify** entity count = 24 (v1.4)
5. **Update all automations, dashboards, and templates** that reference entity IDs
6. **Verify** with Developer Tools → States — the new entity IDs should all be present

### 7.4 If you skip the entity rename

Old entity IDs will show as `unavailable` after upgrade. HA may offer to migrate them automatically (Settings → System → Repairs → check for migration hints). If migration doesn't happen automatically, use the entity registry to manually map old → new.

**Note:** history is preserved for the same `unique_id`. Renaming the entity ID does not lose history.

### 7.5 Cumulative changes v1.0 → v1.4

Beyond the entity rename, v1.0 to v1.4 added:
- COP hourly rollup (v1.3)
- REST endpoint `/api/daikin_cycle_ml/cop_hourly` (v1.3)
- `export_cop_hourly` service (v1.3)
- `sensor.cop_curve_recent` (v1.3)
- IQS Silver + Gold compliance (v1.2)
- HACS-compliant layout (v1.1)

All backward compatible except the entity rename.

---

## 8. Downgrade procedure

**Downgrading is not officially supported.** If you must:

1. **Back up current data:**
   ```bash
   cp /config/.storage/daikin_cycle_ml.db /backup/db-v190-backup.db
   cp /config/.storage/daikin_cycle_ml.alerts /backup/alerts-backup.json
   cp /config/.storage/daikin_cycle_ml.user_datasheets /backup/datasheets-backup.json
   ```

2. **Export cycles** via `daikin_cycle_ml.export_cycles`:
   ```yaml
   service: daikin_cycle_ml.export_cycles
   data:
     format: json
     days: 365
     path: /config/cycles-backup.json
   ```

3. **Note current options** (screenshot of Options menu)

4. **Remove the DB:**
   ```bash
   rm /config/.storage/daikin_cycle_ml.db
   rm /config/.storage/daikin_cycle_ml.alerts
   ```

5. **Downgrade via HACS:** HACS → Integrations → Daikin Cycle ML → three dots → Redownload → select older version → Download

6. **Restart HA Core**

7. **Re-add the integration** (wizard will run)

**What is lost:**
- All historical cycles
- All ML state (baseline, adaptive, kmeans)
- All alert history

**What is preserved:**
- Your config options (if you re-enter them manually)
- Your user datasheets (if you kept the backup and re-import)

**Alternatives to downgrading:**
- If a version breaks something, upgrade to a newer patch (v1.8.1 instead of v1.8.0, etc.)
- If a specific feature is missing in the new version, disable it via options rather than downgrading

---

## 9. Recovering from failed upgrade

### 9.1 Symptom: HA won't start after upgrade

1. **Disable the custom component:** rename `/config/custom_components/daikin_cycle_ml/` to `daikin_cycle_ml.disabled`
2. **Restart HA Core** — should start now (integration is disabled)
3. **Check logs** for the actual error
4. **Restore from backup** if needed

### 9.2 Symptom: Config entry won't load

**Fix:**
1. Settings → Devices & Services → Daikin Cycle ML → menu → **Reload**
2. If reload fails, restart HA Core
3. If still failing, check `.storage/core.config_entries` for `state: setup_retry` — means setup failed
4. Common causes:
   - Migration failure (check logs for `migration_failed`)
   - Source sensor missing (unlikely after upgrade but possible)
   - DB corruption (see [TROUBLESHOOTING.md §8](TROUBLESHOOTING.md#8-database))

### 9.3 Symptom: Migration failed

**Fix:**
1. **Restore `.storage/daikin_cycle_ml.db`** from your pre-upgrade backup
2. **Reinstall previous version** via HACS
3. **Restart HA Core**
4. **Open an issue** with the migration error from logs — the migration path needs debugging

Alternatively:
1. Delete the DB (data lost)
2. Restart HA Core
3. Integration creates fresh DB with new schema
4. Accept data loss

### 9.4 Symptom: Entities disappeared

**Check:**
1. Settings → Devices & Services → Daikin Cycle ML → **Entities** — are they listed?
2. If entities exist but with different IDs: entity rename happened (see §7.2)
3. If entities are `unavailable`: reload or restart
4. If entities are truly gone: check entity registry for orphans

**If entity registry shows them as "restored" entities:** they were removed by the integration. Reload should restore them. If not, open an issue.

### 9.5 Symptom: Automations stopped working

**Cause:** Most often entity ID changes (see §7.2 for v1.4 rename).

**Fix:**
1. Settings → System → Logs → filter automation — find the broken one
2. Check the entity ID referenced — does it exist?
3. Update to the new entity ID
4. Restart the automation

### 9.6 Symptom: Options lost after upgrade

**Cause:** OptionsFlow restructure in v1.6 could have dropped unknown keys.

**Fix:**
1. Settings → Devices & Services → Daikin Cycle ML → Configure
2. Re-enter your options manually
3. This should not happen in v1.7+ — OptionsFlow preserves unknown keys

### 9.7 Rollback via HA backup

The safest rollback is a full HA restore:

1. **Back up current state** (in case restore fails)
2. Settings → System → Backups
3. Select a backup from before the upgrade
4. **Restore**

This restores: `.storage/`, config, custom_components, everything. The integration is at the previous version.

---

## 10. Version history timeline

| Version | Date | Key changes | Breaking? |
|---|---|---|---|
| v1.9.0 | 2026-10-20 | 3 new alerts, per-alert toggles, dedup windows, `recompute_kmeans` service | No |
| v1.8.2 | 2026-10-19 | Docs split (this file), no code changes | No |
| v1.8.1 | 2026-10-08 | R331 alert advice bleed fix | No |
| v1.8.0 | 2026-10-08 | Smart auto-import wizard | No |
| v1.7.2 | 2026-09 | Hotfix for issue #49 | No |
| v1.7.1 | 2026-09 | Security updates | No |
| v1.7.0 | 2026-09 | Defrost history helper sensors | No |
| v1.6.2 | 2026-10-06 | Onboarding fix (issue #25) | No |
| v1.6.1 | 2026-10-06 | Energy tick fix | No |
| v1.6.0 | 2026-10-06 | HVAC Parity: 3× features + breaking `cop_today` | **Yes** |
| v1.5.0 | 2026-10-03 | Dynamic LWT step + comfort dual-loop | No |
| v1.4.5 | 2026-10-03 | Dashboard cards refresh | No |
| v1.4.4 | 2026-10-02 | `_day_key` hydrate fix | No |
| v1.4.3 | 2026-10-02 | Order-swap hotfix | No |
| v1.4.2 | 2026-10-02 | Hydrate + backfill + rollup 720 h | No |
| v1.4.1 | 2026-10-02 | Cycle/quality/notify fixes | No |
| v1.4.0 | 2026-09-29 | Entity slug renames | **Yes** |
| v1.3.0 | 2026-09-26 | COP hourly rollup + REST endpoint | No |
| v1.2.x | 2026-09-20 | IQS Silver + Gold | No |
| v1.1.0 | 2026-09-15 | HACS-compliant layout | No |
| v1.0.x | 2026-09-10 | Initial release | — |

Only **two breaking changes** in the entire history:
- **v1.4.0** — entity slug renames
- **v1.6.0** — `cop_today` changed to heating-only

Everything else is backward compatible.

---

## Appendix A — Changelog cross-reference

The full, line-by-line changelog is in [CHANGELOG.md](../CHANGELOG.md). This UPGRADE.md summarizes what matters for existing users. When in doubt, consult CHANGELOG.md for specifics.

## Appendix B — Pre-upgrade backup script

```bash
#!/bin/bash
# Run on HA host before upgrade
BACKUP_DIR=/backup/daikin-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

cp /config/.storage/daikin_cycle_ml.db "$BACKUP_DIR/" 2>/dev/null
cp /config/.storage/daikin_cycle_ml.alerts "$BACKUP_DIR/" 2>/dev/null
cp /config/.storage/daikin_cycle_ml.user_datasheets "$BACKUP_DIR/" 2>/dev/null
cp -r /config/custom_components/daikin_cycle_ml "$BACKUP_DIR/custom_components" 2>/dev/null

echo "Backed up to: $BACKUP_DIR"
ls -la "$BACKUP_DIR"
```

Save as `/config/scripts/backup-daikin.sh`, `chmod +x`, run before any upgrade.

## Appendix C — Support

If upgrade fails and §9 doesn't help:

1. Restore from backup first (don't try to debug on a broken install)
2. Download diagnostics from the previous working install
3. Open an issue: https://github.com/elRadix/daikin_cycle_ml/issues
4. Include: current version, target version, exact error from logs, diagnostics

## 5A. v1.6.0 behavioural notes (still applicable in v1.9)

These were documented as Known limitations in the v1.6.0 release and remain true in v1.9.

### BUH step power is a model-based estimate

BUH_STEP_KW_BY_MODEL maps 14 Daikin models to their step heater power (typically 3 kW or 6 kW per step). If your backup heater is configured differently, runtime_buh_today will drift.

**Fix:** set power_sensor_entity in Options > Device for accurate energy accounting.


### Defrost duration is a monotone accumulator

_defrost_duration_s grows monotonically while a defrost is active. It is not decremented mid-cycle.

**Consequence:** defrost_duration_today can occasionally over-count if a defrost is aborted mid-cycle.

### Energy fallback uses rps_heuristic

If power_sensor_entity is not configured, energy values are computed via rps_heuristic (compressor RPS x nominal kW). This is an estimate with plus-minus 20 percent error.

**Fix:** configure a real power sensor for Energy Dashboard accuracy.


### Mid-cycle mode switch uses start mode

If the unit switches from heating to DHW mid-cycle, the cycle keeps the mode it started in. Mode-switch detection is on the roadmap.

### BUH-share sensors not implemented

buh_excessive fires as an alert based on the runtime ratio, but there are no dedicated buh_share sensors.

### Energy sensors toggle deferred

All 6 energy sensors are always registered. There is no energy_sensors_enabled toggle.

### Cost tracking deferred

Tariff options and cost-tracking sensors are out of scope for v1.9.


## 5B. v1.6.2 onboarding modes (detailed)

The v1.6.2 wizard split attribute handling into two modes.

**Automatic mode** (canonical names required):

- INV frequency (rps) is now optional
- Required set shrinks from 13 to 12
- Units without a compressor-frequency attribute can onboard

**Manual mode** (new):

- One text field per required (12) and optional (1) attribute
- Leave blank if the canonical name exists
- Fields not present fail fast with attribute_not_found

**Custom map fallback** (resolution order):

1. options.custom_attribute_map
2. data.custom_attribute_map
3. data.attribute_map

