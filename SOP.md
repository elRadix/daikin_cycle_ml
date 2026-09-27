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

Sensors (9): cycle_state, current_cycle, last_cycle, today,
quality_today, source_health, learned_thresholds, cop_vandaag,
stooklijn_advies.
Binary sensors (15): compressor_running, defrost_active, buh_active,
dhw_active, heating_active, cooling_active, pendulum_hourly,
pendulum_daily, short_run, short_off, source_stale,
missing_attributes, setpoint_oscillating, dhw_pendulum, high_cycle_rate.

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

- 9 sensors + 15 binary sensors = 24 entities.
- Coverage gate: >=95% (currently ~95.1%).
- Old DBs auto-migrate on first cluster write.
- Repairs (5): source_stale, missing_attrs, db_corrupt,
  notify_failed, migration_failed.
- Services (6): reset_counters, export_cycles, label_cycle,
  recompute_baseline, run_maintenance, send_test_notification.
- DB tables (7): cycles, features, alerts, daily_summary,
  cop_samples, model_state, sqlite_sequence.


## 10. Run.py regels (R83-R92)

Aanvulling op DEEL 2 van de handoff. Toegevoegd in batch 52c.

| Regel | Inhoud |
|-------|--------|
| R83 | Bootstrap P0: verifieer ruff + sqlite3 + pylint aanwezig voor gebruik |
| R84 | Fragile test-files: async setup_entry altijd asyncio.wait_for(timeout=3); OptionsFlow tests altijd conftest autouse reload-mock |
| R85 | Wall-time tracking. Full suite >90s -> flag voor refactor |
| R86 | Version bump = een commit. Versie + CHANGELOG + README + tag + push in een batch |
| R87 | Context oranje 80%+ en >3 iteraties op dezelfde batch: STOP, handoff, verse chat |
| R88 | CI compliance. Pylint + ruff beide groen. .pylintrc scope = integratie-code |
| R89 | Pytest exit code via pipe onbetrouwbaar. Gebruik subprocess.run(cmd, capture_output=True) zonder shell-pipe, dan Python-side tail |
| R90 | File Editor faalt stil bij bestanden >5 KB. Fallback: heredoc chunks via SSH addon (cat > /config/run.py << 'RUNEOF'). Verifieer altijd met marker-grep + wc -l |
| R91 | Amend + reset --soft: hash-bewust. Bij batch-mix: git commit --amend -m "<nieuwe boodschap>". Force-with-lease verwacht na amend |
| R92 | Amend-fix mag niet committen bij rode pytest. P5->P6 sequentie hard stoppen als pytest faalt. Geen try/except rond commit-stap |

## 11. Correcties op eerdere notities

- README executable bit: was 100644 (correct). Geen chmod nodig. Handoff-notitie was fout.
- Entity binary_sensor.daikin_cycle_ml_missing_attributes (niet _attrs).
  Repair issue-id blijft missing_attrs (interne identifier).
- Stooklijn advies states: verlaag_lwt_2c, verhoog_lwt_2c, behoud, unknown.
- Entity counts: 9 sensors + 15 binary sensors = 24 (niet 26+16 of 29+19).
- Repairs (5): source_stale, missing_attrs, db_corrupt, notify_failed, migration_failed.
- Services (6): reset_counters, export_cycles, label_cycle, recompute_baseline, run_maintenance, send_test_notification.
- DB tables (7): cycles, features, alerts, daily_summary, cop_samples, model_state, sqlite_sequence.
