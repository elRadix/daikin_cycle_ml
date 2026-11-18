# Pre-0.1.0 development log

Internal batch notes from 2026-09-25, moved out of CHANGELOG.md when it
was reformatted to Keep a Changelog. Kept verbatim for history.

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
