# Alerts v2 — Audit, Taxonomy & Migration Plan

**Status:** planning · **Target release:** v1.9.0 · **Supersedes:** handoff §19 / §21 alert matrices
**Author:** session v73.8→audit · **Date:** 2026-10-08 · **Baseline:** main @ a1d6c38 (v1.8.1)

## 1. Purpose

This document records the findings of a full audit of the alert and
notification surface of `daikin_cycle_ml` (v1.8.1) and proposes an
Alert Taxonomy v2 for v1.9.0. It is a planning document — no code
change is included. Every claim below is code-referenced to a1d6c38.

Goals:
- Ensure every alert that can fire has a valid trigger, correct
  severity, actionable advice, and monitoring data the user can use.
- Align the alert surface with the capabilities that actually exist
  in the component (sensors, binaries, engines, ML signals).
- Fix known bugs found during the audit.
- Correct the documentation drift between handoff §19/§21 and the
  real code.

## 2. Audit summary (executive)

- **9 alerts are live.** 6 flow through `evaluate_alerts` +
  `BINARY_ALERT_MAP`; `cop_low` and `stooklijn_advies` are emitted
  from dedicated coordinator methods that bypass the filter chain;
  `status_summary` is a 6h scheduler tick.
- **4 alerts documented in §19.1 / §21 do not exist in code:**
  `cop_degradation`, `defrost_excessive`, `buh_excessive`,
  `service_due`. No trigger, no schema, no advice, no group entry.
- **3 critical bugs**: pendulum_daily can never fire; short_off
  trigger/display threshold mismatch; and a phantom-alert class.
- **7 major bugs**: filter/language bypass on the two standalone
  emitters; ml_anomaly SB-3 regression; cop_low hardcoded 2.5 in
  three places; short_off + pendulum_daily key mismatch; cop_low
  payload leak into notify service.
- **~90 lines of dead bilingual templates** (`ALERT_TEMPLATES_EN` /
  `_NL`) that never render because every bkey is in `ALERT_SCHEMA`.
- **Single aggregation window** (30 min) used for all schema alerts,
  overriding the per-type windows promised by §19.4.
- **`_last_alert_sent` is in-memory** → options save → coordinator
  reload → dedup reset → duplicate notifications on next tick.

## 3. Live alert inventory

| alert_type | Trigger | Emitter | Group | Persistent | Notes |
|---|---|---|---|---|---|
| `pendulum_hourly` | `cycles_in_window(3600) >= pendulum_cycles_per_hour` | evaluate_alerts | pendulum | yes | shares alert_type with daily |
| `pendulum_daily` | `len(cycles_today) >= target_cycles_per_day` | evaluate_alerts | pendulum | yes | **can never fire** — see 5.1 |
| `short_run` | `last_cycle.duration_s < effective_threshold(short_run_threshold_min)` | evaluate_alerts | short_cycle | yes | display uses raw option, not effective |
| `short_off` | `off_time_since_last < effective_threshold(good_off_threshold_min)` | evaluate_alerts | short_cycle | yes | display reads different key |
| `ml_anomaly` | `snap.anomaly.is_anomaly` | evaluate_alerts | ml | yes | mode overwrite — see 6.2 |
| `setpoint_osc` | `len(_setpoint_history) >= setpoint_oscillation_threshold` (30m rolling) | evaluate_alerts | setpoint | yes | correct; `advice` empty string |
| `cop_low` | `cop_today < 2.5 && samples >= 3` | `_maybe_notify_cop_low` | cop_stooklijn | yes | hardcoded; bypasses filters; EN-only |
| `stooklijn_advies` | `state in {lower_lwt, raise_lwt} && betrouwbaarheid >= 0.7 && besparing >= 5.0` | `_maybe_notify_stooklijn` | cop_stooklijn | yes | bypasses filters; EN-only |
| `status_summary` | 6h scheduler tick | `async_emit_status_update` | — | yes | rich report |

## 4. Phantom alert inventory

| alert_type | §19.1 claims | §21.2 claims | Code reality |
|---|---|---|---|
| `cop_degradation` | "week-over-week < -15%" | persistent + telegram + weekly | not in code |
| `defrost_excessive` | "7d defrost impact > threshold" | persistent + telegram + weekly | not in code |
| `buh_excessive` | "7d BUH impact > threshold" | persistent + telegram + weekly | not in code |
| `service_due` | "runtime > service_interval" | persistent + telegram + daily | not in code |

Sensors that would support each already exist:
- `cop_degradation` → cop_degradation_week_pct, cop_trend_30d, cop_degradation_status
- `defrost_excessive` → defrost_count_today, defrost_duration_today
- `buh_excessive` → runtime_buh_today, electrical_energy_heating_today
- `service_due` → runtime_compressor_today (cumulative needed)

## 5. Critical findings (code-referenced)

### 5.1 `pendulum_daily` can never fire
`BINARY_ALERT_MAP["pendulum_hourly"]` and `["pendulum_daily"]` both
map to `alert_type = "pendulum"` (notification_engine.py:137-150).
`evaluate_alerts` dedupes by alert_type (`if alert_type in emitted:
continue`), so the second is always suppressed when both binaries
are true. Same `notif_id`, same `dedup_key`. Effect: users see
"Pendulum detected (hourly)" only.

**Fix:** distinct alert_types (`pendulum_hourly`, `pendulum_daily`),
distinct notif_ids.

### 5.2 `short_off` displays a different threshold than it fires on
- Trigger: `_effective_threshold("good_off_threshold_min", 5)` (coordinator.py:2082)
- Display: `opts.get("short_off_threshold_min", 5)` (coordinator.py:2468)

In prod (`good_off_threshold_min=20`, `short_off_threshold_min=5`),
the alert fires at off < 20 min but renders "drempel 5.0 min".

Same class of bug for `pendulum_daily`:
- Trigger: `_effective_threshold("target_cycles_per_day", 40)`
- Display: `opts.get("pendulum_cycles_per_day", 40)`

In prod (`target_cycles_per_day=8`, `pendulum_cycles_per_day=40`),
the alert fires at 8 cycles but renders "target <= 40".

### 5.3 Phantom alerts in user-facing documentation
§19.1 and §21.2 promise 13 alerts. §21.3 provides user-action
guidance for 12. Only 9 exist.

## 6. Major findings

### 6.1 `cop_low` and `stooklijn_advies` bypass filters and language
Both are emitted via `_emit_alert` directly, not `evaluate_alerts`.
Consequences: quiet_hours and alert_group_cop_stooklijn options are
ignored; aggregation window hardcoded 20h; language not passed to
message builders — both render EN field labels on a Dutch install.

### 6.2 `ml_anomaly` mode overwrite reintroduces SB-3
`_build_alert_context` computes `mode_str` with a 3-stage fallback
then overwrites with raw `snap.mode` when anomaly.severity is set.

### 6.3 `cop_low` threshold hardcoded three ways
Trigger: `2.5` literal. Report: `"2.50"` literal. No shared constant.
Not learned; `adaptive_thresholds_enabled` has no effect.

### 6.4 `cop_low` context leaks into notify service payload
`_emit_alert` merges `alert.context` into notify call. Telegram
notify does not accept `cop` / `samples` / `mode` kwargs.

### 6.5 Single aggregation window for all alerts
One `alert_aggregation_minutes` (default 30) for every alert_type.
§19.4 promised per-type windows (60 min for ml_anomaly, daily for
pendulum_daily, etc.). Not implemented.

### 6.6 `_last_alert_sent` is in-memory only
Coordinator instance dict. Options save → reload → dict reset →
dedup windows lost → pending alerts re-fire.

### 6.7 Dead alert templates
`notification_engine.py:47-134` defines `ALERT_TEMPLATES_EN/NL`.
Every bkey is in `ALERT_SCHEMA`, so these templates never render.
Their advice text is more actionable than `ALERT_ADVICE` in places.

## 7. Minor findings

- `_avg_duration_min()` returns last-cycle duration, not an average.
- `ctx["pendulum"]` is populated but has no schema/title entry.
- `async_send_notification` fallback tries `notify.<name>` twice.
- Two emoji maps: `const.ALERT_TYPE_EMOJI` and
  `status_report.ALERT_EMOJI`. Drift risk.
- `DEFAULT_ALERT_RETENTION_DAYS = 30` vs prod option 90.

## 8. Alert Taxonomy v2 — proposal

Groups (5 → 7):

1. cycle_behaviour — short_run, short_off, high_cycle_rate (new)
2. pendulum — pendulum_hourly, pendulum_daily, dhw_pendulum (new)
3. setpoint_control — setpoint_osc
4. cop_performance — cop_low, cop_degradation (new), cop_vs_datasheet_low (new)
5. component_health — defrost_excessive (new), buh_excessive (new), service_due (new)
6. data_quality — source_stale (new), missing_attributes (new), datasheet_missing (new)
7. advisory — stooklijn_advies, status_summary, quality_degradation (new)

New candidates, ordered by value and existing sensor support:

| alert_type | Trigger source | Group | Severity | Priority |
|---|---|---|---|---|
| `cop_degradation` | cop_degradation_week_pct < -15 | cop_performance | warning | P1 |
| `defrost_excessive` | defrost_count_today > threshold (7d) | component_health | warning | P1 |
| `buh_excessive` | runtime_buh_today / total_runtime > 0.15 (7d) | component_health | warning | P1 |
| `source_stale` | binary source_stale | data_quality | critical | P1 |
| `missing_attributes` | binary missing_attributes | data_quality | warning | P1 |
| `dhw_pendulum` | binary dhw_pendulum (no alert yet) | pendulum | warning | P2 |
| `high_cycle_rate` | binary high_cycle_rate (no alert yet) | cycle_behaviour | warning | P2 |
| `cop_vs_datasheet_low` | cop_vs_datasheet_pct < -10 | cop_performance | info | P2 |
| `datasheet_missing` | cop_normalized_a7w35 unknown 7d+ | data_quality | info | P3 |
| `quality_degradation` | quality_today 7d trend < baseline - 20% | advisory | info | P3 |
| `energy_daily_anomaly` | daily thermal / baseline > 2 sigma | cop_performance | info | P3 |
| `service_due` | cumulative compressor runtime > interval | component_health | info | P3 |
| `kmeans_retrain_stale` | kmeans refresh skipped 2x expected | data_quality | info | P3 |
| `db_retention_warning` | cycles table > retention_days x 2 | data_quality | info | P3 |

## 9. Migration and rollout

- **Per-alert opt-out.** New options `alert_enabled_<type>: bool`.
- **Backwards compat.** Existing `alert_group_*` continue working.
- **Per-alert dedup windows.** `alert_agg_<type>_min: int`, defaults
  matching §19.4.
- **Filter chain unification.** Route cop_low and stooklijn_advies
  through a shared `_maybe_emit_alert` that applies the same chain.
- **Persistence.** Save `_last_alert_sent` to HA `Store` (see §12 Q3).
  Mitigates options-save duplicates.

## 10. Test and gate plan

- Unit tests per new alert: trigger, dedup, group gating, language,
  schema fields, advice string presence.
- `ALERT_SCHEMA` extended per new alert. Each entry must resolve to
  a live context key (regression against R331 class).
- Coverage: keep 100% branch.
- **Plan-B live-fire gate (MANDATORY per v1.8.1 §3.9 step 8).**
  Trigger = OptionsFlow → Notifications → Test all notifications.
- Docs update: rewrite §19.1 / §21 to match reality.

## 11. PR sequence

Independent PRs, no fix+release mixing (R205):

1. **PR A (this one).** docs/alerts_v2_plan.md. Docs only.
2. **PR B.** Fix critical: pendulum_daily alert_type, short_off and
   pendulum_daily threshold key, ml_anomaly mode overwrite,
   cop_low payload leak. No new alerts.
3. **PR C.** Route cop_low / stooklijn_advies through shared filter
   chain plus language propagation.
4. **PR D.** Per-alert dedup windows plus persistence.
5. **PR E.** New P1: cop_degradation, defrost_excessive,
   buh_excessive, source_stale, missing_attributes.
6. **PR F.** New P2: dhw_pendulum, high_cycle_rate,
   cop_vs_datasheet_low.
7. **PR G.** New P3 plus docs rewrite.
8. **PR H (release).** v1.9.0 version bump plus CHANGELOG plus tag.
   Plan-B gate mandatory.

## 12. Decisions (locked for v1.9.0)

- **Q1 — Default enablement.** All alerts enabled by default.
  P3 alerts are quiet for the first week after release (persistent
  only, no notify push), then normal.
- **Q2 — Service-level Plan-B trigger.** Yes. `send_test_notification`
  gains `alert_kind` and `ignore_filters` parameters, routed through
  `coord.async_emit_test_alert`. Preserves `{message, target}`
  back-compat. Backlog item #32. Ships in v1.9.0 alongside PR B.
- **Q3 — `_last_alert_sent` persistence.** HA native storage:
  `homeassistant.helpers.storage.Store` at `.storage/daikin_cycle_ml.alerts`,
  schema `{"version": 1, "data": {"last_sent": {...}}}`. Loaded in
  `async_setup_entry`, saved debounced (5s) via `async_call_later`.
  Rationale: atomic writes, version migration handled by framework,
  correct path on HA OS, no lock races with SQLite.
- **Q4 — setpoint_osc trigger.** Require oscillation, not just count.
  Trigger = N deltas >= `min_delta` in window **AND** at least one
  direction reversal (sign change of consecutive deltas). Reduces
  false positives from slow monotonic drift.
- **Q5 — Duration fields.** Rename current metric to
  `last_duration_min`. Add true `avg_duration_7d_min` computed
  across cycles in the last 7 days for `pendulum_*` and `ml_anomaly`
  schemas. Labels: EN "Last duration" / "Avg duration 7d",
  NL "Laatste duur" / "Gem. duur 7d".
