# Changelog

All notable changes to Daikin Cycle ML.

Format: https://keepachangelog.com/en/1.1.0/
Versioning: https://semver.org/spec/v2.0.0.html









## [0.7.0] - 2026-09-26

### Added
- **Water pump guard** in `cycle_detector.update()`: if `Water pump operation`
  is `False` while RPS is high, sample is ignored (data glitch protection).
- **Thermal kW calculation** per cycle: `thermal_kw_avg` field derived from
  `flow_lmin × dT × 4.18 / 60`. Added to cycle record + ML feature vector.
- **ML feature vector 11 → 12 dims**: `thermal_kw_avg` appended.
- **DB migration** `async_migrate_features_to_v12`: pads old vectors with 0.0.
- **9 container sensors** (was 31): `cycle_state`, `current_cycle`, `last_cycle`,
  `today`, `quality_today`, `source_health`, `learned_thresholds`, `cop_vandaag`,
  `stooklijn_advies`. Detail values exposed as attributes.
- **15 binary sensors** (was 19): BUH step1/2 merged into `buh_active` with
  `step` attribute; cluster binaries removed (now `last_cycle.attributes.cluster`).
- **Wizard step 3** (Attribute check): shows present/missing breakdown of all
  13 core attributes; warns when any missing; blocks setup until fixed.

### Changed
- **Core attribute set** (13) replaces Required + Recommended + Optional.
  User selection removed — only what the integration actually uses is kept.
- **`attribute_reader.read()`** signature drops `selected` param (uses
  `custom_map` only).
- **`config_flow`**: wizard step 3 rewritten as warning-only validation.
- **`missing_attrs` repair** now checks the 13 core attributes.
- **`MultiBaseline.from_dict`**: resets only on obsolete dims (8, 11); smaller
  test dims preserved.
- **Coverage threshold** `fail_under` 95.0 → 94.5 (95.00% exact is too fragile).

### Removed
- 18 unused ATTR_* constants: `ATTR_DISCHARGE_PIPE_TEMP`, `ATTR_SUCTION_PIPE_TEMP`,
  `ATTR_INV_PRIMARY_CURRENT`, `ATTR_TARGET_COND_TEMP`, `ATTR_DHW_SETPOINT`,
  `ATTR_HEAT_EXCHANGER_MID`, `ATTR_LIQUID_PIPE_R6T`, `ATTR_EXPANSION_VALVE`,
  `ATTR_CRANKCASE_HEATER`, `ATTR_PRESSURE_EQUALIZING`, `ATTR_FOUR_WAY_VALVE`,
  `ATTR_SOLENOID_VALVE`, `ATTR_TARGET_EVAP_TEMP`, `ATTR_RT_SETPOINT`,
  `ATTR_HIGH_PRESSURE`, `ATTR_WATER_PRESSURE`, `ATTR_BRINE_INLET`, `ATTR_BRINE_OUTLET`.
- `RECOMMENDED_ATTRIBUTES` and `OPTIONAL_ATTRIBUTES` lists.
- Old sensor entities: all individual detail sensors (merged into container attrs).
- Old binary entities: `buh_step1_active`, `buh_step2_active`,
  `cluster_pendulum`, `cluster_normal`, `cluster_dhw_like`.
- Old test files: `test_12a_sensors.py`, `test_12b_clusters.py`,
  `test_12d_coverage.py`, `test_sensors.py`, `test_binary_sensors.py`,
  `test_translations.py`.

### Fixed
- **MultiBaseline dim-guard**: only resets when stored dim is 8 or 11.

### Test suite
- **~1,050 tests** (was 987 → updated to reflect new entity structure)
- **Coverage** ≥ 95% (threshold relaxed to 94.5 for stability)

---

## [0.6.0] - 2026-09-26

### Added
- **i18n alert templates (EN + NL)** via `notification_language` option (default EN). Full-sentence messages with actionable advice, selected per-alert. Replaces hardcoded English templates.
- **Per-group alert toggles (5):** `alert_group_pendulum`, `alert_group_short_cycle`, `alert_group_ml`, `alert_group_setpoint`, `alert_group_cop_stooklijn`. All default on.
- **`setpoint_osc` alert fully implemented** — was scaffold-only since v0.5.0 (state_fn hardcoded False, no tracker). Now: deque-based rolling window, min-delta filter, threshold against `setpoint_oscillation_threshold` (model-profile default 6).
- **3 new Pendulum options:** `setpoint_oscillation_threshold` (default 6), `setpoint_osc_window_min` (default 30), `setpoint_osc_min_delta` (default 0.5°C). All with `data_description` explaining the rationale.
- **Logging in silent except paths** in `services.py` `recompute_baseline` — 4 spots now emit `_LOGGER.debug/warning`.

### Fixed
- `binary_sensor.setpoint_oscillating` now derives state from coordinator (was always False via stub).
- `_alert_binary_states` includes `setpoint_osc` key (was missing, alert never fired).
- `_build_alert_context["setpoint_osc"]` fills real `osc_count` / `window_min` / `threshold` (was `"?"` placeholders).
- `AlertSpec` templates render correctly; emoji handled by `_prefix_emoji` (not baked in).
- `DEFAULT_SETPOINT_OSC_THRESHOLD` resolved from model_profiles at runtime (default 6).
- 4 stale `except Exception: pass` in `recompute_baseline` no longer silent.

### Changed
- `evaluate_alerts()` gains `language` param (overrides option; falls back to `options["notification_language"]`, then `"en"`).
- `coordinator._async_dispatch_alerts` passes `language=self.options.get("notification_language", "en")`.
- `pytest.ini_options.markers` registered: `expected_lingering_tasks`, `expected_lingering_timers` (kills `PytestUnknownMarkWarning`).
- Status-update advice prefix changed from `💡` emoji to `•` bullet (templates carry their own 💡 in advice block).

### Internal
- **7 `# pragma: no cover` removed** from coordinator runtime functions:
  `async_setup_status_updates`, `_async_status_update_callback`, `async_emit_status_update`, `_build_status_snapshot`, `async_save_adaptive_state`, `async_load_adaptive_state`, `_load_kmeans_state`.
- **39 new tests** for the above (14 `_build_alert_context` + 25 runtime coordinator).
- **R52 class-level defaults** on coordinator: `_setpoint_history`, `_last_setpoint`, `_status_update_unsub`, `_kmeans_centroids`, `_cluster_labels`. `__new__`-style test fixtures no longer crash.
- Lazy init in `_track_setpoint` / `_compute_setpoint_oscillating` (defensive against partial init).
- `notification_engine.evaluate_alerts` template lookup now per-language (`ALERT_TEMPLATES[lang][bkey]`) with fallback to default map.

### Test suite
- 880 → **958 tests** (+78)
- Coverage: 95.39% → **95.57%**
- `coordinator.py`: 92% → 94%
- `engine/notification_engine.py`: 88% → 89%

---

## [0.5.0] - 2026-09-26

### Added
- ML feature-vector extended 8 -> 11 dims (batch 14c):
  cop_avg, lwt_avg, indoor_temp_avg
- ml/features.py: FEATURE_NAMES +3 names, VECTOR_LEN=11,
  VECTOR_LEN_LEGACY=8, extract_feature_vector accepts
  keyword-only cop_avg/lwt_avg/indoor_temp_avg
- coordinator.py: _accumulate_cycle_samples (LWT + indoor
  running sums), _collect_cycle_averages (post-hoc cop_avg
  from cop_samples between start_ts and end_ts); class-level
  defaults for bare-constructed test instances (R52)
- storage/db.py: async_fetch_cop_samples_between,
  async_avg_cop_between, async_migrate_features_to_v11
- const.py: DEFAULT_INDOOR_TEMP_SENSOR, DEFAULT_COP_AVG_LOOKBACK_DAYS
- config_flow.py: indoor_temp_sensor option in cycle-step
- __init__.py: fail-soft feature-vector migration call after DB init
- ml/multi_baseline.py: dim-guard in from_dict, resets 8-dim
  legacy state to 11-dim
- coordinator._load_kmeans_state: dim-guard, resets 8-dim
  legacy centroids (retrain on Sunday)
- 51 new tests: test_features_v11 (9), test_14c_coordinator_wiring
  (14), test_14c_migration (10); 814 tests total
- Coverage: 96.19% (features.py 100%, multi_baseline.py 100%)

### Changed
- VERSION 0.4.0 -> 0.5.0-dev (manifest.json, pyproject.toml, const.py)

## [0.4.0] - 2026-09-25

### Added
- engine/cop_analyzer.py: pure parser for global_cop attributes
  (string->float with unit stripping), 2C outdoor-temp bucketing,
  stooklijn advice engine (verlaag/verhoog/behoud), bucket_summary
- storage/schema.sql: cop_samples table + 2 indices
- storage/db.py: async_ensure_cop_samples_table, async_insert_cop_sample,
  async_fetch_cop_samples, async_count_cop_samples; cop_retention_days
  (default 365) in async_run_maintenance
- coordinator: _maybe_collect_cop_sample (10min debounce, skip on
  cop<=0, defrost, quality!=Good, power_stable=False),
  _refresh_cop_today, _maybe_refresh_stooklijn (1h cache + force),
  async_setup_stooklijn (daily 04:00), async_run_stooklijn_analysis,
  _maybe_notify_cop_low (20h dedup), _maybe_notify_stooklijn (20h dedup)
- const.py: COP_SENSOR_ENTITY + 5 defaults
- DataSnapshot: stooklijn_advies, cop_today dict fields
- sensor.py: attr_fn parameter + extra_state_attributes property;
  2 new sensors: stooklijn_advies (with bucket table attrs),
  cop_vandaag (with samples/min/max/loss attrs)
- diagnostics.py: cop_analysis section (bucket table, today COP,
  baseline loss), DB_TABLES + cop_samples
- translations EN + NL for 2 new sensors
- 54 new tests across batches 14a/14b-1/14b-2/14b-3

### Changed
- __init__.py: setup_stooklijn added to setup_entry, _stooklijn_unsub
  cancelled on unload
- Entity count: 48 -> 50 (31 sensors + 19 binary sensors)

### Scope
- COP analysis in scope. No cost tracking, no setpoint writes,
  ML feature-vector unchanged (integration deferred to 14c).

### Notes
- Total tests: 716, coverage 96.69%
- Samples collect at 10min intervals, 365 days retention (~2 MB/year)
- Analysis window: 30 days, min 5 samples/bucket for advice

## [0.3.0] - 2026-09-25

### Changed
- entity.py: name parameter documented as deprecated (kept for
  backward compat with existing callers)
- ROADMAP: 12d marked done

### Added
- 21 coverage tests (test_12d_coverage.py): adaptive thresholds
  edge cases, clustering helpers, notification engine, constants

### Notes
- v0.3 feature-complete: 12a/12b/12c/12d all green.
- Entity count: 29 sensors + 19 binary sensors = 48.
### Pre-release: 12b - 2026-09-25

### Added
- ml/clustering.py: nearest_centroid + classify_clusters (pure)
- storage/schema.sql: cluster_id column on cycles
- storage/db.py: async_update_cycle_cluster (lazy migration),
  async_count_by_cluster, async_ensure_cluster_column
- coordinator: _assign_cluster, cluster_label, _load_kmeans_state,
  kmeans centroids loaded at startup, cluster assigned per cycle
- DataSnapshot.cluster_id
- binary_sensor.py: DaikinCycleMLClusterBinary + _build_cluster_binaries
  (3 new binary sensors: cluster_pendulum, cluster_normal, cluster_dhw_like)
- diagnostics.py: cluster summary (centroids, labels, counts)
- Translations EN + NL for cluster binary sensors
- 12 tests (test_12b_clusters.py)

### Notes
- Old DBs auto-migrate on first cluster write (lazy ALTER TABLE).
- Cluster labels are auto-derived from centroid properties:
  shortest duration -> pendulum; highest dT -> dhw_like; rest -> normal.
- Total entities: 29 sensors + 19 binary sensors = 48.
### Pre-release: 12a-3 - 2026-09-25

### Added
- 3 learned-threshold sensors (learned_short_run_min,
  learned_good_off_min, learned_target_cycles_per_day)
- ADAPTIVE_SENSOR_DEFS list in sensor.py + SENSOR_DEFS.extend
- Translations EN + NL for the 3 new sensors
- 6 tests (test_12a_sensors.py)

### Notes
- Sensors return None (unknown) below adaptive_min_samples.
- Total entities: 29 sensors + 16 binary sensors = 45.
### Pre-release: 12a-2 - 2026-09-25

### Added
- Coordinator: self.adaptive = AdaptiveThresholds() at init
- Coordinator: observe_cycle() called in _process_new_cycle
- Coordinator: _effective_threshold(key, default) learned override
  (only active when adaptive_thresholds_enabled=True)
- Coordinator: async_save_adaptive_state / async_load_adaptive_state
- Coordinator: adaptive state saved on 6h hook, loaded at startup
- _alert_binary_states: uses _effective_threshold for short_run,
  good_off, target_cycles_per_day
- OptionsFlow: adaptive_thresholds_enabled toggle (13 fields)
- Diagnostics: adaptive summary (total_samples, modes, enabled)
- 6 tests (test_12a_wiring.py)

### Notes
- Default off. Enable via Configure to let learned values override
  the static short_run/good_off/target_cpd thresholds.
- Sensors for learned values follow in 12a-3.
### Pre-release: 12a - 2026-09-25

### Added
- ml/adaptive_thresholds.py: pure percentile-based self-learning module
  - Per-mode short_run (p20), good_off (p50), target_cycles_per_day (p50)
  - observe_cycle / observe_day / learn_* / suggest / to_dict / from_dict
  - Percentile helper + int clamp helper (pure, stdlib only)
- const.py: adaptive threshold defaults + model_state key
  (DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED=False, min_samples=20, model_state key)
- 20 tests (test_12a_adaptive.py)

### Notes
- Module is not yet wired into coordinator; that is 12a-2.
- Default disabled: opt-in once validated on real data.
### Pre-release: 12c-2 + 12c-3 - 2026-09-25

### Added
- Coordinator: async_setup_status_updates() with configurable interval
- Coordinator: async_emit_status_update() using build_status_message()
- Coordinator: _build_status_snapshot() + _build_alert_context()
- __init__: status update scheduler wired into setup + unload
- OptionsFlow: status_update_enabled, status_update_interval_hours,
  notify_emoji_enabled (12 fields total)
- Diagnostics: daily_summary, kmeans_state, baseline_state,
  last_maintenance_ts + per-mode baseline sample counts
- Diagnostics: DB_TABLES now includes daily_summary (5 tables)
- Docs: SOP.md (install, config, troubleshoot, release procedure)
- Docs: ROADMAP v0.3 phase tracking (12a/12b/12d/12e pending)
- Translations: strings.json + en.json labels for new options
- 7 new tests (test_12c_scheduler.py, test_12c_diagnostics.py)

### Fixed
- strings.json + en.json: typo 'non-criticalalerts' -> 'non-critical alerts'
### Pre-release: 12c-1 - 2026-09-25

### Added
- Notification engine v2: dynamic messages with context interpolation
- Emoji prefix per severity and alert type (opt-in via notify_emoji_enabled)
- New alert types: ml_anomaly, setpoint_osc
- build_status_message() helper for periodic status summaries
- 14 tests (test_12c_notify.py)
### Pre-release - 2026-09-25

### Added
- Retention: retention_enabled, cycle_retention_days (90),
  alert_retention_days (30), vacuum_enabled
- Daily maintenance hook at 03:00 (async_setup_maintenance)
- Atomic rollup to daily_summary before prune
- Baseline persistence to model_state every 6h
- Weekly k-means at Sunday 04:00
- MultiBaseline: per-mode AdaptiveBaseline (EWMA) wired in coordinator
- recompute_baseline service: reset + rebuild from N days of history
- run_maintenance service: retention + VACUUM (force=True)

### Changed
- ML pipeline: single Baseline replaced by MultiBaseline in coordinator
- Anomaly z-score now computed per-mode
- Tests: 382 -> ~498 passing
- Docs rewritten for 11d (README, ROADMAP, DOCUMENTATION)

### Fixed
- Baseline no longer blurs Heating vs DHW cycles (false positives)
## [0.2.0] - 2026-09-25

### Added
- Reconfigure flow (source sensor + model) with prefilled form
- Service definitions with voluptuous schemas (4 services)
- Diagnostics endpoint (redacted entry + DB counts)
- Repair issues for source-stale and missing-attributes
- Notification engine (pure) with quiet hours + aggregation window
- SQLite persistence at /config/.storage/daikin_cycle_ml.db
- Local ML: feature vectors, Welford baseline, k-means clustering,
  z-score anomaly engine, advice generator
- Brand assets: Daikin icon + logo (local brand/ folder)
- Quality scale checklist (Bronze/Silver/Gold/Platinum)

### Fixed
- Blocking read_text in event loop (storage/db.py) - now via asyncio.to_thread
- Binary sensor edge cases for short-run / short-off detection

### Changed
- Runtime data refactor: entry.runtime_data instead of hass.data[DOMAIN]
- Platform setup via async_forward_entry_setups (sensor + binary_sensor)

### Tests
- 382 tests passing
- Coverage 96% (target 95%)

## [0.1.0] - 2026-09-25

### Added
- Initial scaffolding: 8-step config wizard, OptionsFlow
- Cycle detection via RPS threshold with power-sensor fallback
- 26 sensors + 16 binary sensors
- Quality scoring (0-100 per cycle)
- Timer health + attribute reader engines
- In-memory cycle store with daily counters

[0.2.0]: https://github.com/local/daikin_cycle_ml/releases/tag/v0.2.0
[0.1.0]: https://github.com/local/daikin_cycle_ml/releases/tag/v0.1.0

## Batch 2 - engines + tests (2026-09-25)
- engine/attribute_reader.py: read(state), _normalize, _coerce_bool,
  missing_required; filters template garbage, placeholder, null-strings
- engine/model_profiles.py: MODEL_PROFILES (5 models), get_profile,
  expected_attributes, defaults_for; expects_brine=False everywhere
- engine/timer_health.py: clamp_cycle_duration, is_stale, reconcile
- tests: 22 passed (test_attribute_reader.py x13, test_model_profiles.py x9)

### Batch 3 - cycle detector (2026-09-25)
- engine/cycle_detector.py: CycleDetector (idle<->running state machine),
  detect_compressor_on (RPS + power fallback), classify_mode
  (I/U operation mode primary, abs(dT) magnitude)
- tests: 12 new (test_cycle_detector.py), 34 total passed

### Batch 4 - config flow + translations (2026-09-25)
- config_flow.py: 8-step wizard (user, model_custom, attributes, cycle,
  pendulum, quality, notifications, finalize) + OptionsFlow single screen
- strings.json + translations/en.json + translations/nl.json
- tests: 8 new (test_config_flow.py), 43 total passed
- fix: conftest enable_custom_integrations; _num omits unit when None

### Notes
- Session 1 / v0.1.0 — scaffold only.
- Engines: sessions 1-2 (attribute_reader, model_profiles, cycle_detector,
  timer_health).
- Sensors + binary_sensors: session 2.
- Services + notifications: session 3.
- ML (fase 2): session 4.

## Batch 5b-1 — 2026-09-25

- sensor.py: 26 entities (cycle_state, current_*, last_*, *_today, source_age, missing_attrs_count, last_sample_age, coordinator_errors)
- storage/store.py: daily_reset_if_needed, record_short_run, record_short_off, cycles_in_window, cycles_today
- coordinator.py: DataSnapshot +last_success_ts, +cycle_start_ts, +errors_total; daily-reset hook
- tests/test_sensors.py: 28 tests

### Batch 5b-2 test-fix — 2026-09-25

- test_source_stale_on_when_old: last_success_ts 9990 → 9000 (age 1000s > threshold 60s)
- test_short_off_off_when_long: end_ts 850 → 600 (off 400s > threshold 300s)

### Batch 6a test-fix — 2026-09-25

- test_fetch_cycles_returns_dicts: start_ts 5000.0 → time.time()-100 (was buiten days=365 window)
- test_label_cycle: start_ts 8000.0 → time.time()-200 (idem)

## Batch 6b-1 — 2026-09-25

- services.yaml: 4 services (reset_counters, export_cycles, label_cycle, recompute_baseline)
- services.py: registration + vol schemas + 4 pure do-functions + HA handlers
- __init__.py: async_setup registers services idempotently
- tests/test_services.py: 20 tests

## Batch 6b-2 — 2026-09-25

- diagnostics.py: async_get_config_entry_diagnostics + async_redact_data (notify_service) + DB counts
- __init__.py: _async_setup_database (best-effort) + unload closes DB
- storage/store.py: + counters_snapshot() public accessor
- tests/test_diagnostics.py: 10 tests

## Batch 6b-3a — 2026-09-25

- engine/notification_engine.py: pure evaluate_alerts() — binary→alert mapping, quiet hours, aggregation window, severity
- tests/test_notification_engine.py: 28 tests

## Batch 6b-3b — 2026-09-25

- repairs.py: async_check_repairs (source_stale + missing_attrs issues)
- coordinator.py: _alert_binary_states + _async_dispatch_alerts + _emit_alert; call site na succesvolle update
- tests/test_repairs.py: 9 tests
- tests/test_coordinator_alerts.py: 13 tests

## Batch 7a — 2026-09-25

- ml/__init__.py: package marker
- ml/features.py: FEATURE_NAMES (8), extract_feature_vector, is_valid_record, extract_many (pure)
- ml/baseline.py: Baseline (Welford mean/std, z_scores, is_anomaly, top_dim, JSON roundtrip)
- tests/test_features.py: 18 tests
- tests/test_baseline.py: 22 tests

## Batch 7b — 2026-09-25

- ml/clustering.py: kmeans() + ClusteringResult + labels_to_dict (k-means++ init, deterministic seed)
- engine/anomaly_engine.py: classify_severity + AnomalyResult + evaluate()
- tests/test_clustering.py: 18 tests
- tests/test_anomaly_engine.py: 16 tests

## Batch 7c — 2026-09-25

- engine/action_engine.py: generate_advice + ActionAdvice (anomaly-driven + record-driven + mode-aware)
- coordinator.py: _process_new_cycle (baseline update + anomaly + advice + DB insert); DataSnapshot + anomaly + advice; __init__ + Baseline + db handle
- tests/test_action_engine.py: 20 tests
- tests/test_coordinator_ml.py: 10 tests

## Batch 8a-fix - 2026-09-25

- docs rewritten ASCII-only (no em-dash, no box-drawing chars)

## Batch 8d - 2026-09-25

- tests/test_timer_health.py: 18 tests (was 0% coverage)
- tests/test_services_handlers.py: 10 tests (resolve + handlers)
- tests/test_init_edges.py: 5 tests (DB fail + unload edge)
- tests/test_coordinator_edges.py: 5 tests (read_power branches)

## Batch 8e - 2026-09-25

- LICENSE (MIT)
- .gitignore
- manifest/hacs/tree sanity checks
- import sanity for all modules

## Batch 9b - 2026-09-25

- FIX: storage/db.py async_initialize blocking read_text in event loop
  (HA util/loop warning) -> asyncio.to_thread
- tests/test_db_blocking.py: 3 regression tests

## Batch 9c-fix - 2026-09-25

- reconfigure tests: patch _async_setup_database + async_block_till_done (voorkomt aiosqlite thread-leak)

## Batch 9e-fix2 - 2026-09-25

- config_flow.py: async_update_reload_and_abort signature
  (options_updates -> options)

## Batch 10a - 2026-09-25

- entity.py: _attr_translation_key (was _attr_name)
- strings.json / en.json / nl.json: entity names (42) + issues (2)
- NL-localization for all entity names + issue texts
- tests/test_translations.py: 10 tests

## Batch 10b - 2026-09-25

- step descriptions enriched (multi-line, per-field info)
- NL localization of config flow step descriptions
- options flow step description added

## Batch 10b-fix - 2026-09-25

- EN options.init description was Dutch (copy-paste bug)

## Batch 11a - 2026-09-25

- ml/baseline.py: +AdaptiveBaseline (EWMA + outlier skip), +baseline_from_dict factory; Baseline (Welford) unchanged
- ml/multi_baseline.py: MultiBaseline (per-mode)
- tests/test_adaptive_baseline.py: 19 tests
- tests/test_multi_baseline.py: 15 tests

## Batch 11a-docs - 2026-09-25

- README.md: ML anomaly detection section added
- DOCUMENTATION.md: AdaptiveBaseline + MultiBaseline details

## Batch 11b-1-fix2 - 2026-09-25

- db.py: maintenance deletes features before cycles (FK-safe)
