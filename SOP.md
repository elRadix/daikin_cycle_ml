# SOP - Daikin Cycle ML

Standard Operating Procedure: install, configure, operate, troubleshoot, release.

## 1. Scope

Local-only Home Assistant integration that detects compressor cycles on
Daikin Altherma heat pumps, classifies pendulum behaviour, scores cycle
quality, and advises on configuration. No cloud. No setpoint writes.

Out of scope: cost tracking, HACS publication, supervised ML,
COP calculation (provided by external package).

## 2. Install

1. Copy custom_components/daikin_cycle_ml/ into the HA config tree.
2. Restart Home Assistant.
3. Settings -> Devices & Services -> Add Integration -> Daikin Cycle ML.
4. Complete the 8-step wizard:
   user -> model_custom -> attributes -> cycle -> pendulum -> quality
   -> notifications -> finalize.

## 3. Configuration

Options can be edited via:
- Settings -> Devices & Services -> Daikin Cycle ML -> Configure (quick)
- Reconfigure -> quick (source + model) or full wizard

Key options:
- compressor_rps_threshold (default 3)
- short_run_threshold_min (default 20)
- good_run_threshold_min (default 45)
- pendulum_cycles_per_day (default 40)
- persistent_enabled (default true)
- quiet_hours_enabled / start / end
- notify_service (e.g. notify.telegram_rachid)
- notify_emoji_enabled (default true)
- status_update_enabled (default false)
- status_update_interval_hours (default 24)
- retention_enabled / cycle_retention_days / alert_retention_days
- vacuum_enabled

## 4. Daily operation

Sensors (26): state, mode, quality, last_cycle_*, pendulum counters,
baseline stats, etc.
Binary sensors (16): short_run, short_off, pendulum_hourly, pendulum_daily,
dhw_pendulum, defrost_short, setpoint_osc, ml_anomaly, ...

Services:
- daikin_cycle_ml.reset_counters
- daikin_cycle_ml.export_cycles
- daikin_cycle_ml.label_cycle
- daikin_cycle_ml.recompute_baseline
- daikin_cycle_ml.run_maintenance

Scheduled jobs (automatic):
- poll every 30s
- baseline save every 6h
- maintenance daily 03:00
- k-means Sunday 04:00
- status update every N hours (opt-in)

## 5. Troubleshooting

| Symptom | Check |
|---------|-------|
| No cycles detected | source sensor entity_id, source_stale repair |
| All modes unknown | I/U operation mode attr present? |
| No notifications | notify_service configured, quiet hours not active |
| No status updates | status_update_enabled = true? |
| DB errors | path /config/.storage/daikin_cycle_ml.db, permissions |
| Baseline empty | wait >= 3 cycles; check model_state['baseline_state'] |
| k-means empty | wait 1 week; check model_state['kmeans_state'] |
| Missing attrs | repairs issue list_missing_attributes |

Diagnostics endpoint: Settings -> Devices & Services -> Daikin Cycle ML
-> Download diagnostics. Includes:
- entry (redacted), coordinator state, store counters, last cycle
- baseline summary (per-mode sample counts)
- database counts (5 tables) + extra (daily_summary 7d, model_state keys)

## 6. Release procedure

For each release:
1. Bump VERSION in const.py and version in manifest.json (must match).
2. Update CHANGELOG.md with a new [x.y.z] - YYYY-MM-DD section.
3. Update ROADMAP.md: mark completed items, adjust next phase.
4. Update SOP.md if install/config/procedure changed.
5. Run full test suite:
   export PYTHONPATH=/workspace
   cd /workspace/daikin_cycle_ml
   pytest -q
   Gate: coverage >= 95%, 0 failures.
6. Optional: git tag if repo tracked.

## 7. Known limitations (v0.2)

- No COP / cost (out of scope)
- No HACS publication (out of scope)
- All ML is unsupervised; no training labels
- Cluster sensors not exposed yet (12b)
- Adaptive thresholds not wired yet (12a)

## 8. Reference

- README.md - quick start
- DOCUMENTATION.md - full architecture + ML flow
- ROADMAP.md - phase tracking
- CHANGELOG.md - release history

## 9. Update log (append-only)

### 2026-09-25 - 12a adaptive thresholds

- New module ml/adaptive_thresholds.py (pure, no HA imports).
- Learned values via percentile: short_run p20, good_off p50,
  target_cycles_per_day p50.
- Wired into coordinator via _effective_threshold(key, default):
  only active when adaptive_thresholds_enabled=True (default false).
- Persisted as model_state['adaptive_thresholds'] on the 6h hook.
- 3 new sensors expose learned values (return unknown below
  adaptive_min_samples, default 20).
- Entity count: 26 -> 29 sensors.

### 2026-09-25 - 12b cluster activation

- ml/clustering.py extended with nearest_centroid + classify_clusters.
- storage/schema.sql: cycles.cluster_id column added.
- storage/db.py: async_update_cycle_cluster (lazy ALTER TABLE migration),
  async_count_by_cluster, async_ensure_cluster_column.
- Coordinator loads model_state['kmeans_state'] at startup and assigns
  cluster_id to every new cycle via nearest-centroid.
- 3 new binary sensors: cluster_pendulum, cluster_normal, cluster_dhw_like.
- Diagnostics: cluster summary (centroids, labels, counts per cluster).
- Cluster labels auto-derived from centroid properties.
- Entity count: 16 -> 19 binary sensors.

### Current total

- 29 sensors + 19 binary sensors = 48 entities.
- Coverage gate: >=95% (currently ~95.5%).
- Old DBs auto-migrate on first cluster write.