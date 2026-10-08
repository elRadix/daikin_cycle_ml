# Alerts v2 — Audit and Action Plan

**Baseline:** a1d6c38 (v1.8.1). **Target:** v1.9.0. **Date:** 2026-10-08.

**Purpose:** Working reference for the alert revamp. Combines the full
audit (findings, evidence) with the action plan (taxonomy, decisions,
PR sequence). Update as each PR lands.

## How to use

- Sections 1-6: audit. What exists, what is broken, evidence.
- Sections 7-9: decisions. Capability map, taxonomy, locked options.
- Sections 10-12: plan. Migration, PR sequence, test gates.

## 1. Executive summary

- **9 alerts are live.** 6 flow through evaluate_alerts and
  BINARY_ALERT_MAP. cop_low and stooklijn_advies bypass the filter
  chain. status_summary is a 6-hour scheduler tick.
- **4 alerts documented in section 19.1 and 21 do not exist in code:**
  cop_degradation, defrost_excessive, buh_excessive, service_due.
- **3 critical bugs:** pendulum_daily can never fire. short_off
  trigger and display read different threshold keys. ml_anomaly mode
  overwrite reintroduces the SB-3 regression.
- **7 major bugs:** filter chain bypass, cop_low hardcodes, payload
  leak, single dedup window, in-memory last_sent, phantom-alert
  class, dead templates.
- **5 minor bugs.**
- **14 new alert candidates** identified. All have existing sensor
  support.

## 2. Live alerts inventory

| # | alert_type | Emitter | Group | Severity | Status |
|---|---|---|---|---|---|
| 1 | pendulum_hourly | evaluate_alerts | pendulum | warning | OK |
| 2 | pendulum_daily | evaluate_alerts | pendulum | warning | broken, never fires |
| 3 | short_run | evaluate_alerts | short_cycle | warning | threshold key drift |
| 4 | short_off | evaluate_alerts | short_cycle | warning | threshold mismatch |
| 5 | ml_anomaly | evaluate_alerts | ml | warning | mode overwrite |
| 6 | setpoint_osc | evaluate_alerts | setpoint | warning | OK |
| 7 | cop_low | standalone emitter | cop_stooklijn | warning | bypass, hardcode, leak |
| 8 | stooklijn_advies | standalone emitter | cop_stooklijn | warning | bypasses filters |
| 9 | status_summary | scheduler tick | none | info | OK |

## 3. Phantom alerts inventory

| # | alert_type | Section 19.1 claim | Code reality | Effort | Priority |
|---|---|---|---|---|---|
| 10 | cop_degradation | week-over-week below -15 percent | not in code | 30 min | P1 |
| 11 | defrost_excessive | 7-day defrost impact above threshold | not in code | 45 min | P1 |
| 12 | buh_excessive | 7-day BUH impact above threshold | not in code | 45 min | P1 |
| 13 | service_due | runtime above service interval | not in code | 90 min | P3 |

Supporting sensors already exist for all four. See section 7.

Impact: users reading the handoff believe 13 monitoring workflows are
active. Only 9 are.

## 4. Bugs, severity ranked

### 4.1 CRITICAL: pendulum_daily can never fire

Both pendulum_hourly and pendulum_daily map to alert_type equals
"pendulum" in BINARY_ALERT_MAP (notification_engine.py lines 137-150).
evaluate_alerts dedupes by alert_type (notification_engine.py line 242).
The hourly entry wins, the daily entry dies. They also share notif_id
and dedup_key.

Fix: distinct alert_type per binary in BINARY_ALERT_MAP, distinct
notif_id constants in const.py.

### 4.2 CRITICAL: short_off trigger and display mismatch

- Trigger: coordinator.py line 2082 reads key good_off_threshold_min
  (prod value 20 min).
- Display: coordinator.py line 2468 reads key short_off_threshold_min
  (prod value 5 min).
- Symptom: alert fires at off below 20 min, message says threshold
  5.0 min. Contradictory on every fire.

Same class of bug in pendulum_daily:
- Trigger reads target_cycles_per_day (prod 8).
- Display reads pendulum_cycles_per_day (prod 40).

Fix: single source of truth. Trigger and display read the same key.

### 4.3 CRITICAL: ml_anomaly mode overwrite

- SB-3 fallback at coordinator.py lines 2485-2505 resolves mode in
  three stages: snap.mode, then last_cycle.mode, then
  attrs[operation_mode].
- Overwrite at coordinator.py line 2540 replaces the resolved value
  with raw snap.mode whenever anomaly.severity is set.
- Effect: the v1.8.1 SB-3 fix is annulled for exactly the case it
  was added to handle.

Fix: remove the overwrite block.

### 4.4 MAJOR: cop_low and stooklijn_advies bypass filter chain

- Emitters: _maybe_notify_cop_low (coordinator.py line 1793),
  _maybe_notify_stooklijn (coordinator.py line 1823).
- Do not call evaluate_alerts.
- Effect: quiet_hours_enabled, alert_group_cop_stooklijn,
  alert_aggregation_minutes, notification_language are all ignored.
  Disabling the cop_stooklijn group in Options has zero effect.

Fix: route through a shared _maybe_emit_alert that applies the same
filter chain as evaluate_alerts.

### 4.5 MAJOR: cop_low threshold hardcoded three ways

- Trigger: coordinator.py line 1797 compares cop to 2.5.
- Report: status_report.py line 280 renders the literal string 2.50.
- No shared constant. adaptive_thresholds_enabled has no effect.

Fix: single constant, optional learned threshold per Q1.

### 4.6 MAJOR: cop_low context leaks into notify payload

- _emit_alert (coordinator.py line 2770) merges alert.context into the
  notify service call.
- cop_low context contains keys cop, samples, mode.
- Telegram notify does not accept these kwargs. Behaviour depends on
  the integration: warning or silent drop.

Fix: do not pass context through to notify. Remove context from the
cop_low SimpleNamespace, or whitelist notify payload keys.

### 4.7 MAJOR: single aggregation window for all alerts

- alert_aggregation_minutes (default 30) applies to all six
  evaluate_alerts types (notification_engine.py line 265).
- Section 19.4 promises per-type windows.

Effective vs documented:

| alert_type | Documented | Actual |
|---|---|---|
| pendulum_hourly | 60 min | 30 min |
| pendulum_daily | daily | 30 min |
| short_run | 30 min | 30 min |
| short_off | 30 min | 30 min |
| ml_anomaly | 60 min | 30 min |
| setpoint_osc | 30 min | 30 min |
| cop_low | 30 min | 20 h |
| stooklijn_advies | weekly | 20 h |

Fix: per-type option alert_agg_TYPE_min per Q1 and Q3.

### 4.8 MAJOR: last_alert_sent is in-memory only

- coordinator.py line 362 declares an empty dict on the coordinator.
- Options save triggers reload. Dict resets. Dedup windows lost.
  Pending alerts re-fire on next tick.
- Observed in production on 2026-10-08.

Fix: persist to HA Store per Q3.

### 4.9 MAJOR: 4 phantom alert types

See section 3.

### 4.10 MAJOR: dead alert templates

- ALERT_TEMPLATES_EN and ALERT_TEMPLATES_NL at
  notification_engine.py lines 47-134.
- Only used in the else branch of evaluate_alerts when bkey is not in
  ALERT_SCHEMA. Every bkey IS in ALERT_SCHEMA. The branch is marked
  pragma no cover and never runs.
- Their advice is often more specific than ALERT_ADVICE. Merge the
  useful text into the live advice, delete the dead dicts.

### 4.11 MINOR: avg_duration_min is not an average

- coordinator.py line 2387 returns the last cycle duration.
- Rendered as "Gem. duur" or "Avg duration" in three schemas.

Fix: rename to last_duration_min, add real avg_duration_7d_min per Q5.

### 4.12 MINOR: dead ctx pendulum dict

- coordinator.py line 2455 populates a pendulum context dict.
- No schema or title uses it.

Fix: delete.

### 4.13 MINOR: async_send_notification legacy double-call

- notification_engine.py line 392. When domain is not notify, the
  fallback tries notify name twice.

Fix: single attempt, single fallback.

### 4.14 MINOR: two emoji maps

- const.ALERT_TYPE_EMOJI at const.py line 217.
- status_report.ALERT_EMOJI at status_report.py line 339.
- Both consulted at different stages. Drift risk.

Fix: single canonical map, or document two-stage usage explicitly.

### 4.15 MINOR: retention default mismatch

- const.py line 55 has DEFAULT_ALERT_RETENTION_DAYS equals 30.
- Production option is 90.

## 5. Cross-cutting architecture issues

### 5.1 Filter chain is not universal

evaluate_alerts applies quiet hours, group gating, aggregation, and
dedup by alert_type. cop_low and stooklijn_advies apply none of these.
This is the single largest architectural inconsistency.

### 5.2 Dedup window is one value

One alert_aggregation_minutes for six types. Two hardcoded 20-hour
windows for the standalone emitters. Four different behaviours.

### 5.3 Persistence gap

last_alert_sent in-memory only. See 4.8.

### 5.4 Two emitters, two architectures

Six alerts use one pipeline. Two use another. One is a scheduler tick.
v1.9.0 should unify to one pipeline.

### 5.5 Dead templates alongside live advice

Two parallel advice sources. See 4.10.

## 6. Per-alert status, compact

| alert_type | Trigger | Display | Advice | Monitoring | Verdict |
|---|---|---|---|---|---|
| pendulum_hourly | OK | OK | generic | cph, LWT, dur, outdoor | partial |
| pendulum_daily | broken | key mismatch | generic | never renders | broken |
| short_run | OK | key drift | specific | 8 fields | partial |
| short_off | key mismatch | key mismatch | specific | 7 fields | broken |
| ml_anomaly | OK | mode overwrite | general | z, top_dim, mode | partial |
| setpoint_osc | OK | OK | specific | 7 fields | OK |
| cop_low | hardcoded | hardcoded | none | COP, samples | broken |
| stooklijn_advies | OK | OK | state label | 5 fields | partial |
| status_summary | scheduler | OK | n/a | rich report | OK |

### 6.1 Schema field coverage

All schema field references resolve to real context keys. No
blank-render typos. R331 sentinel handling works: a missing field
collapses the whole row to a bare dash.

### 6.2 Advice quality

- short_run, short_off, setpoint_osc: specific and actionable.
- ml_anomaly: general but appropriate.
- pendulum_hourly and pendulum_daily: generic. The dead template has
  better wording.
- cop_low and stooklijn_advies: no explicit advice string.

### 6.3 Monitoring value

Every schema alert exposes at least 3 live system values. The user
can correlate a symptom with system state. Keep this in v2.

## 7. Capability inventory

### 7.1 Sensors with alert-supporting signal but no alert

| Sensor | Supports | Priority |
|---|---|---|
| cop_degradation_week_pct | cop_degradation | P1 |
| cop_trend_30d | cop_degradation | P1 |
| cop_degradation_status | cop_degradation | P1 |
| defrost_count_today | defrost_excessive | P1 |
| defrost_duration_today | defrost_excessive | P1 |
| runtime_buh_today | buh_excessive | P1 |
| electrical_energy_heating_today | buh_excessive | P1 |
| cop_vs_datasheet_pct | cop_vs_datasheet_low | P2 |
| cop_normalized_a7w35 | datasheet_missing | P3 |
| quality_today | quality_degradation | P3 |
| source_health | source_stale binary exists | P1 |
| runtime_compressor_today | service_due, needs cumulative | P3 |

### 7.2 Binaries with no alert attached

| Binary | Supports | Priority |
|---|---|---|
| source_stale | source_stale | P1 |
| missing_attributes | missing_attributes | P1 |
| dhw_pendulum | dhw_pendulum | P2 |
| high_cycle_rate | high_cycle_rate | P2 |

## 8. Taxonomy v2, 7 groups, 14 new candidates

### 8.1 Groups

1. cycle_behaviour: short_run, short_off, high_cycle_rate (new)
2. pendulum: pendulum_hourly, pendulum_daily, dhw_pendulum (new)
3. setpoint_control: setpoint_osc
4. cop_performance: cop_low, cop_degradation (new), cop_vs_datasheet_low (new)
5. component_health: defrost_excessive (new), buh_excessive (new), service_due (new)
6. data_quality: source_stale (new), missing_attributes (new), datasheet_missing (new)
7. advisory: stooklijn_advies, status_summary, quality_degradation (new)

Old groups (5) to new groups (7). Old group options remain valid.

### 8.2 New alert candidates

| alert_type | Trigger source | Group | Severity | Priority |
|---|---|---|---|---|
| cop_degradation | cop_degradation_week_pct below -15 | cop_performance | warning | P1 |
| defrost_excessive | defrost_count_today above threshold, 7d | component_health | warning | P1 |
| buh_excessive | BUH runtime ratio above 0.15, 7d | component_health | warning | P1 |
| source_stale | binary source_stale | data_quality | critical | P1 |
| missing_attributes | binary missing_attributes | data_quality | warning | P1 |
| dhw_pendulum | binary dhw_pendulum | pendulum | warning | P2 |
| high_cycle_rate | binary high_cycle_rate | cycle_behaviour | warning | P2 |
| cop_vs_datasheet_low | cop_vs_datasheet_pct below -10 | cop_performance | info | P2 |
| datasheet_missing | cop_normalized_a7w35 unknown 7d | data_quality | info | P3 |
| quality_degradation | quality_today 7d trend below -20 | advisory | info | P3 |
| energy_daily_anomaly | daily thermal above baseline +2 sigma | cop_performance | info | P3 |
| service_due | cumulative runtime above interval | component_health | info | P3 |
| kmeans_retrain_stale | kmeans refresh skipped twice | data_quality | info | P3 |
| db_retention_warning | cycles table above retention x2 | data_quality | info | P3 |

## 9. Locked decisions for v1.9.0

### Q1 Default enablement

All alerts enabled by default. P3 alerts are quiet for the first week
after release: persistent only, no notify push. Then normal.

### Q2 Service-level Plan-B trigger

Yes. send_test_notification gains alert_kind and ignore_filters
parameters, routed through coord.async_emit_test_alert. Preserves the
existing message and target args for back-compat. Backlog item 32.
Ships alongside PR B.

### Q3 last_alert_sent persistence

HA native Store at .storage/daikin_cycle_ml.alerts, schema version 1
with data.last_sent dict. Loaded in async_setup_entry. Saved debounced
5 seconds via async_call_later. Rationale: atomic writes, framework
versioning, correct path on HA OS, no lock races with SQLite.

### Q4 setpoint_osc trigger

Require oscillation, not just count: N deltas at or above min_delta
in window AND at least one direction reversal (sign change of
consecutive deltas). Reduces false positives from slow monotonic drift.

### Q5 Duration fields

Rename current metric to last_duration_min. Add true
avg_duration_7d_min computed across cycles in the last 7 days for
pendulum_hourly, pendulum_daily, ml_anomaly. Labels EN: Last duration,
Avg duration 7d. Labels NL: Laatste duur, Gem. duur 7d.

## 10. Migration and rollout

- Per-alert opt-out. New option alert_enabled_TYPE as bool. Existing
  alert_group options continue working.
- Per-alert dedup windows. New option alert_agg_TYPE_min, defaults
  from the section 4.7 table.
- Filter chain unification. Route cop_low and stooklijn_advies
  through evaluate_alerts, or a shared helper that replicates it.
- Persistence. HA Store per Q3.
- Templates. Merge dead template advice into ALERT_ADVICE, delete
  ALERT_TEMPLATES_EN and ALERT_TEMPLATES_NL.
- Emoji maps. Consolidate to one canonical map or document two-stage.
- Duration fields. Rename and add per Q5.
- Phantom documentation. Rewrite handoff section 19 and 21 to match
  reality: 9 alerts, not 13.

## 11. Fix sequence, PR B through H

| PR | Scope | Plan-B gate | Coverage |
|---|---|---|---|
| B | Critical bugs: pendulum_daily alert_type, short_off and pendulum_daily threshold keys, ml_anomaly mode overwrite, cop_low payload leak. Plus Q2 service test extension. | yes | 100 pct |
| C | Route cop_low and stooklijn_advies through shared filter chain and language. | yes | 100 pct |
| D | Per-alert dedup windows plus last_alert_sent persistence (Q3). | yes | 100 pct |
| E | New P1 alerts: cop_degradation, defrost_excessive, buh_excessive, source_stale, missing_attributes. | yes | 100 pct |
| F | New P2 alerts: dhw_pendulum, high_cycle_rate, cop_vs_datasheet_low. | yes | 100 pct |
| G | New P3 alerts plus handoff section 19 and 21 rewrite, template merge, emoji consolidation, duration rename (Q5). | yes | 100 pct |
| H | v1.9.0 release: version bump, CHANGELOG, tag, release. | yes | 100 pct |

Every PR touching the alert-render path requires Plan-B live-fire
before merge. Trigger is OptionsFlow, Notifications, Test all
notifications.

## 12. Test and gate plan

- Unit tests per new alert: trigger, dedup, group gating, language,
  schema fields, advice string presence.
- ALERT_SCHEMA extended per new alert. Every field reference must
  resolve to a live context key, regression against the R331 class.
- Coverage: 100 percent branch, mandatory.
- Mypy strict, 35 files.
- Ruff CI-parity clean.
- i18n parity 16/16/16.
- Plan-B live-fire mandatory per the section 11 table.
- Post live-fire output as a PR comment for the historical archive.

---

End of ALERTS_V2.md. Update as each PR lands.
