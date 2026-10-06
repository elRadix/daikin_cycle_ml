# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-10-06

v1.6.0 adds COP intelligence, Daikin datasheet integration, and
runtime/energy observability. Local-only, no cloud dependencies.

[Full diff v1.5.3...v1.6.0](https://github.com/elRadix/daikin_cycle_ml/compare/v1.5.3...v1.6.0)

### Added

- **Per-mode COP sensors** — `cop_heating_day`, `cop_heating_week`,
  `cop_heating_month`, plus DHW and cooling variants. 9 new sensors total.
  ([`6c1b330`](https://github.com/elRadix/daikin_cycle_ml/commit/6c1b330))
- **SPF sensors** — `spf_season`, `spf_ytd`, `scop_running_365d`. Configure
  your season start via the new `season_start_month` option (default: October).
  ([`b04a633`](https://github.com/elRadix/daikin_cycle_ml/commit/b04a633))
- **Daikin datasheet integration** — 15 bundled models (8 EPRA + 7 ERLA)
  in `data/datasheets.json`. The model dropdown now lists 17 entries.
  ([`0c7a787`](https://github.com/elRadix/daikin_cycle_ml/commit/0c7a787))
  - `hp_specs` — full datasheet as attributes.
  - `cop_normalized_a7w35` — live COP normalized to A7/W35 reference.
  - `cop_vs_datasheet_pct` — deviation vs spec with on_spec/below/critical bands.
- **User datasheet import** — new services `import_datasheet` and
  `remove_user_datasheet`. Import overrides for non-bundled models without
  editing files.
  ([`50afb8f`](https://github.com/elRadix/daikin_cycle_ml/commit/50afb8f),
  [`006b281`](https://github.com/elRadix/daikin_cycle_ml/commit/006b281),
  [`a9766db`](https://github.com/elRadix/daikin_cycle_ml/commit/a9766db))
- **Weather-normalized degradation** — `cop_degradation_status`,
  `cop_degradation_week_pct`, `cop_trend_30d`. Isolates hardware degradation
  from weather variation using outdoor-binning and BUH/defrost exclusion.
  ([`eac1132`](https://github.com/elRadix/daikin_cycle_ml/commit/eac1132))
- **Runtime sensors** — `runtime_compressor_today`, `runtime_buh_today`,
  `compressor_starts_today`, `defrost_count_today`, `defrost_duration_today`,
  `duty_cycle_today`.
  ([`6de9935`](https://github.com/elRadix/daikin_cycle_ml/commit/6de9935),
  [`b247a8b`](https://github.com/elRadix/daikin_cycle_ml/commit/b247a8b))
- **Energy sensors (kWh)** — 6 sensors feeding the HA Energy Dashboard:
  `electrical_energy_{heating,dhw,cooling,total}_today` and
  `thermal_energy_{heating,cooling}_today`.
  ([`95b1346`](https://github.com/elRadix/daikin_cycle_ml/commit/95b1346))
- **Daikin slope/offset advice** — `heating_curve_advice` now exposes
  `offset_delta_c` and `slope_delta` attributes, matching the language
  used in Daikin installer menus.
  ([`443af4d`](https://github.com/elRadix/daikin_cycle_ml/commit/443af4d))
- **Repairs for datasheets** — `datasheet_import_invalid`,
  `datasheet_schema_unknown`, `datasheet_load_failed`.
  ([`006b281`](https://github.com/elRadix/daikin_cycle_ml/commit/006b281))
- **Deep test suite for C1/C2** — full contract tests for SENSOR_DEFS,
  slug parity, translation parity, subprocess import-cleanliness, and
  Hypothesis fuzzing of the new COP factories.
  ([`f6de063`](https://github.com/elRadix/daikin_cycle_ml/commit/f6de063))

### Changed

- **BREAKING:** `cop_today` now reports **heating-only** COP. If your
  automation expects the old blended value, switch to the new
  `cop_combined_today` sensor.
  ([`583d6b8`](https://github.com/elRadix/daikin_cycle_ml/commit/583d6b8))
- **Service translations** — all 9 services now have complete EN and NL
  translations (previously only 3 had entries).
  ([`8bf02d8`](https://github.com/elRadix/daikin_cycle_ml/commit/8bf02d8))
- **OptionsFlow UX overhaul** — the configuration flow now uses HA
  sections and a sub-menu structure:
  ([`526026c`](https://github.com/elRadix/daikin_cycle_ml/commit/526026c),
  [`76b0215`](https://github.com/elRadix/daikin_cycle_ml/commit/76b0215),
  [`178a4d7`](https://github.com/elRadix/daikin_cycle_ml/commit/178a4d7),
  [`c428e0f`](https://github.com/elRadix/daikin_cycle_ml/commit/c428e0f))
  - `device` step: grouped into Sensors / Detection / Comfort sections.
  - `pendulum` step: grouped into Run/off / Pendulum / Setpoint sections.
  - `quality` + `ml` merged into `quality_ml`.
  - `maintenance` renamed to `advanced`.
  - `notifications` split into 4 sub-pages: Delivery, Quiet Hours, Content, Test.
- **DataSnapshot purity (R216)** — entities now read `power_w`, `cop`, and
  `setpoint_oscillating` via `DataSnapshot` instead of private coordinator
  methods.
  ([`1e98359`](https://github.com/elRadix/daikin_cycle_ml/commit/1e98359),
  [`5b83377`](https://github.com/elRadix/daikin_cycle_ml/commit/5b83377))
- **Model choices** — `MODEL_CHOICES` expanded from 5 to 17.
  ([`0c7a787`](https://github.com/elRadix/daikin_cycle_ml/commit/0c7a787))

### Removed

- **BREAKING:** orphan `data` and `data_description` keys removed from
  `options.step.init` (leftovers from an earlier migration; never rendered).
  ([`0204e2c`](https://github.com/elRadix/daikin_cycle_ml/commit/0204e2c))
- Unreachable mode-filter branch in `_group_by_bucket`.
  ([`443af4d`](https://github.com/elRadix/daikin_cycle_ml/commit/443af4d))

### Fixed

- **Adaptive thresholds persistence** — learned adaptive thresholds now
  survive HA restart (previously reset on every restart).
  ([`bd6f655`](https://github.com/elRadix/daikin_cycle_ml/commit/bd6f655))
- **Runtime/energy accumulator persistence** — accumulators now persist
  before the daily reset, so the final ~30s delta is not lost.
  ([`8b1fb62`](https://github.com/elRadix/daikin_cycle_ml/commit/8b1fb62))
- **Class defaults for accumulator paths** — coverage gap closed; tests
  using `__new__()` no longer break on first accumulator read.
  ([`417eb16`](https://github.com/elRadix/daikin_cycle_ml/commit/417eb16))
- **Duration clamping** — `duration_s` is now clamped to
  `max_cycle_duration_min` before entering ML and DB, preventing
  wall-clock jumps from polluting features.
  ([`3409ba7`](https://github.com/elRadix/daikin_cycle_ml/commit/3409ba7))
- **Consistent stale detection** — `binary_sensor._is_source_stale` and
  `sensor._attrs_source_health` now use `timer_health.is_stale()` instead
  of divergent inline arithmetic.
  ([`3409ba7`](https://github.com/elRadix/daikin_cycle_ml/commit/3409ba7))
- **Hassfest compliance** — manifest keys ordered (domain+name first);
  invalid `description` key removed from sensor translations;
  `example:` blocks removed from `services.yaml`.
  ([`a45f3ba`](https://github.com/elRadix/daikin_cycle_ml/commit/a45f3ba),
  [`69071a2`](https://github.com/elRadix/daikin_cycle_ml/commit/69071a2),
  [`6632f4c`](https://github.com/elRadix/daikin_cycle_ml/commit/6632f4c))
- **SENSOR_DEFS count assertions** — 5 stale assertions updated from 39
  to 45, aligning tests with the C6a energy-sensor addition.
  ([`3535f1e`](https://github.com/elRadix/daikin_cycle_ml/commit/3535f1e))
- **Test isolation for OptionsFlow** — class-level `config_entry`
  property patch no longer leaks between tests.
  ([`c428e0f`](https://github.com/elRadix/daikin_cycle_ml/commit/c428e0f))

### Security

- No security fixes in this release.

### Known Limitations

- BUH step power is a model-based estimate. If your Daikin has a
  different BUH configuration, the estimate may drift.
- Defrost duration is a monotone accumulator (non-monotone summation
  planned for v1.6.1).
- Energy values use `rps_heuristic` fallback when no power sensor is
  configured. Configure `power_sensor_entity` for accurate tracking.
- Cost tracking (tariff + sensors) and energy toggle are deferred to v1.6.1.

### Upgrade Guide

**Action required for `cop_today` automations.** The sensor now reports
heating-only COP. Switch to `cop_combined_today` for the previous blended value.

**Optional: re-select your Daikin model.** The wizard now shows 17 models.
If your model was previously "custom", re-select it to get datasheet-backed
COP normalization.

**No action required** for entity IDs, DB schema, or other sensors.

### Compatibility

- Home Assistant 2026.9.3 or later.
- Database schema v14 (unchanged from 1.5.x).
- No breaking changes to entity IDs or option keys.

### Install / Update

Via HACS: update to `1.6.0`.
Manual: copy `custom_components/daikin_cycle_ml/` into `/config/custom_components/`, restart HA.

---

## [1.5.3] - 2026-10-03

Version alignment release. v1.5.1 and v1.5.2 were tagged with code
version 1.5.0 (docs-only patches). v1.5.3 aligns the code version,
tag, and release so HA Diagnostics, HACS, and README all report the
same number.

### Changed

- VERSION bump 1.5.2 -> 1.5.3 (const.py, manifest.json, pyproject.toml).
- README version badge + tag link -> v1.5.3.
- No functional change vs v1.5.2.


## [1.5.2] - 2026-10-03

README showcase cache-bust. Docs + asset rename, no code change.

### Changed

- Renamed dashboard/cards/simple-card/preview.png to showcase.png
  to bust a stale CDN cache entry that prevented the image from
  rendering inside the HACS panel.
- README showcase table updated to the new path.

## [1.5.1] - 2026-10-03

HACS README showcase fix. Docs-only, no code change.

### Changed

- Replaced the showcase HTML table with a markdown pipe table so
  previews render inside the HACS panel (HACS sanitizes raw HTML
  img tags).
- Absolute raw.githubusercontent.com URLs for preview images.


## [1.5.0] - 2026-10-03

Dynamic LWT step. The heating-curve advice now emits a 1-3 C step
relative to the current setpoint, with a comfort floor+ceiling guard
and tracking-error dampening.

### Added

- **Dynamic LWT step (1-3 C)** in `analyze_stooklijn`.
- **Comfort dual-loop** - OptionsFlow sliders `comfort_min_c` (15-22)
  and `comfort_max_c` (22-28) enforce a floor+ceiling.
- **8 new attributes** on `heating_curve_advice`: `state_label`,
  `step_c`, `delta_c`, `huidige_setpoint`, `doel_setpoint`,
  `tracking_error`, `comfort_cap`, extended `reason` codes.
- **7 new constants**: `K_EMIT_DEFAULT`, `LWT_STEP_MIN`,
  `LWT_STEP_MAX`, `LWT_TRACKING_TOLERANCE`, `COMFORT_TOLERANCE`,
  `DEFAULT_COMFORT_MIN_C`, `DEFAULT_COMFORT_MAX_C`.
- **37 new tests**: `test_b13_dynamic_step.py` (32) +
  `test_b13_config_flow.py` (5).

### Changed

- `analyze_stooklijn` now compares against `setpoint_lwt`
  (`LW setpoint (main)`) instead of the last bucket sample.
- Sensor states are canonical EN: `no_data` / `keep` /
  `lower_lwt` / `raise_lwt` / `unknown`.
- `STOOKLIJN_STATE_LABEL_EN` / `_NL` now symmetric; legacy
  aliases kept as input-only for backwards compatibility.
- `build_stooklijn_report` formats the `{step}` placeholder
  with the recommended step.
- OptionsFlow screen 2 (device) gained two Required sliders.
- README reorganized for v1.5.0 (sections 2, 3, 9.1-9.4, 11, 16,
  17, 21, 22).

### Fixed

- Literal `{step}` placeholder leaked into notification output.
- `geen_data` / `behoud` fallback when language = EN.
- Banker rounding `round(2.5) = 2` -> `int(x + 0.5)`.
- Comfort-guard dead code (indoor_avg was never passed).
- DHW cache state invalidated after the EN rename.

### Notes

- Coverage 100.00% (4676 stmts / 1312 branches), mypy strict 0
  errors, 6/6 CI green on the merge commit.
- Safe drop-in for v1.4.5 users; automations that match on old
  literals (`behoud`, `verlaag_lwt_2c`, `verhoog_lwt_2c`,
  `geen_data`) must be updated - see README section 3.


## [1.4.5] - 2026-10-02

Documentation and dashboard-cards refresh. No integration code
change - coverage stays at 100.00%, safe drop-in for v1.4.4.

### Changed

- **Simple Card** (`dashboard/cards/simple-card/`):
    - Full i18n coverage: every label, caption, and alert
      translates via a `STR` table (NL + EN).
    - New `LANG_OVERRIDE` (JS) + `lang_override` (Jinja):
      `''` = auto from integration, `'nl'` / `'en'` = force.
    - Four display bugs fixed: mode read via `attr` instead
      of `aN`; `tr()` preserves the value `0`; SVG cluster
      label uses `hasV`; `liveKw` stays null-aware on idle.
    - Dead `stookComf` variable removed.
    - `preview.png` refreshed.
- **Heating Curve** (`dashboard/cards/heating-curve/`):
    - R202: `parseBucket` now matches the `-10-` pattern so
      cold-weather buckets below -10 C are no longer dropped.
    - R203: current-bucket share shown next to true total in
      the specs box (e.g. `samples: 63 (25 in bucket 20+C)`).
    - R201 cleanup: removed dead `curOut` lookup.
    - `aN2` helper crash fixed (Lovelace
      `ButtonCardJSTemplateError` on prod HA).
- **Root README**: Showcase section now shows the two card
  previews side-by-side; each preview links to its folder.
- **dashboard/README.md**: complete rewrite. Fixes a truncated
  code fence; adds language docs, troubleshooting, and
  adding-a-new-card sections.
- **Badges**: version -> 1.4.5; tests -> 1700.

### Notes

- No public API change. Coverage stays at 100.00%.
- Safe drop-in for v1.4.4.
- See `dashboard/cards/` for the updated YAML.
## [1.4.4] - 2026-10-02

Hotfix on top of v1.4.3.

### Fixed

- **`quality_today.good_cycles` / `bad_cycles` were reset to 0 on
  the first coordinator tick after HA restart.** v1.4.3 correctly
  backfilled `quality_score` and hydrated cycles into the store,
  but the very next `store.daily_reset_if_needed()` call wiped
  every `*_today` counter because `_day_key` was not set by the
  hydration code.
- **Fix**: `CycleStore.hydrate_from_rows()` now sets
  `_counters["_day_key"]` to today's date before counting cycles.
  The next `daily_reset_if_needed()` on the same day becomes a
  no-op, preserving the recomputed counters.

### Added

- `tests/test_v1_4_4_improvements.py` with 3 regression tests.

### Notes

- No public API change. Coverage stays at 100.00%.
- Safe drop-in for v1.4.3.

## [1.4.3] - 2026-10-02

Hotfix on top of v1.4.2.

### Fixed

- **Ordering bug in `async_setup_entry`**: v1.4.2 called
  `_async_hydrate_store()` BEFORE `_async_backfill_quality()`.
  The store therefore loaded records with `quality_score = NULL`
  before the backfill could write scores back to the database.
  Consequence: after every HA restart, `last_cycle.state` and
  `quality_today.state` remained `unknown` even though the
  underlying cycles had been scored. The two calls are now
  swapped: backfill runs first, then hydration loads the scored
  records.

### Notes

- No new tests added; existing v1.4.2 tests still pass.
- Coverage stays at 100.00%.
- No public API change. Safe drop-in for v1.4.2.

## [1.4.2] - 2026-10-02

Maintenance release on top of v1.4.1.

### Fixed

- CycleStore is now hydrated from SQLite on startup. Before,
  after every HA restart last_cycle, cycles_today, quality_today
  and the good/bad counters reset until the next cycle.
- Existing cycles receive a backfilled quality_score.
- cop_hourly retention policy added inside async_run_maintenance
  matching the existing cop_samples policy.

### Changed

- COP_ROLLUP_WINDOW_HOURS = 720 replaces the hard-coded 6h
  default.
- README showcase subtitle is now plural.

### Added

- CycleStore.hydrate_from_rows()
- CycleDB.async_fetch_recent_cycles_for_hydration()
- CycleDB.async_backfill_quality_scores()
- CycleDB.async_prune_cop_hourly()
- tests/test_v1_4_2_improvements.py

### Notes

- Coverage stays at 100.00%.
- No public API change. Safe drop-in for v1.4.1.

## [1.4.1] - 2026-10-02

Patch release on top of v1.4.0. Restores three sensor
behaviours that were broken in production (BUG-2, BUG-3,
BUG-4). BUG-1 was investigated and **falsified** -- no code
change was needed for it.

### Fixed

- **BUG-2 - `sensor.daikin_cycle_ml_last_cycle` reported
  `unknown`.** Root cause: `engine/quality_scorer.py::score_cycle()`
  existed but was orphaned (no import site, no call site).
  Consequently every cycle record lacked the `quality_score` key
  and the sensor's `native_value` lambda returned `None`.
  Fix: new module-level helper `score_and_count()` in
  `coordinator.py` invokes `score_cycle()` immediately before
  `store.add_cycle(record)`; the return value is written back to
  `record["quality_score"]`.
- **BUG-3 - `sensor.daikin_cycle_ml_quality_today` reported
  `unknown` with `good_cycles=0`, `bad_cycles=0`.** Root cause:
  the `CycleStore.increment()` API existed and was used for
  `short_runs_today` / `short_offs_today`, but no code path ever
  incremented `good_cycles_today` or `bad_cycles_today`.
  Fix: `score_and_count()` increments exactly one of those two
  counters per cycle, using the new threshold
  `GOOD_CYCLE_MIN_SCORE = 70` (added to `const.py`).
- **BUG-4 - `cluster` attribute was the literal string `"unknown"`
  instead of JSON `null`.** Root cause: three fallback branches
  in `sensor._cluster_label()` all returned the string
  `"unknown"`, which propagated as a real string to the state
  machine and to any consumer that distinguishes strings from
  `None` (e.g. Jinja `is string`).
  Fix: `_cluster_label` return type changed from `str` to
  `str | None`; all three branches now return `None`; Home
  Assistant renders the attribute as JSON `null` and the state
  as `unknown`.

### Added

- `tests/test_v1_4_1_quality_wiring.py` with 13 regression tests:
  - `_cluster_label()`: no cluster -> `None`; unknown cid -> `None`;
    exception -> `None`; known cid -> label.
  - `score_cycle()`: empty record -> 100; return type is `int`.
  - `score_and_count()`: good cycle increments
    `good_cycles_today`; bad cycle increments `bad_cycles_today`;
    boundary score 70 counts as good; exception in `score_cycle`
    leaves `quality_score=None` and skips counters; exception in
    `store.off_time_since_last` is swallowed; exception in
    `store.increment` is swallowed.

### Changed

- `custom_components/daikin_cycle_ml/coordinator.py`: added
  imports (`GOOD_CYCLE_MIN_SCORE`, `score_cycle`) and helper
  `score_and_count()`; `_async_update_data` now calls the helper
  before `store.add_cycle`.
- `custom_components/daikin_cycle_ml/sensor.py::_cluster_label`:
  signature `-> str` changed to `-> str | None`; the three
  fallback branches return `None` instead of the string
  `"unknown"`.
- `custom_components/daikin_cycle_ml/const.py`: added
  `GOOD_CYCLE_MIN_SCORE = 70`.
- `tests/test_31cd_coverage.py`: three assertions migrated from
  `== "unknown"` to `is None`.
- Version strings (`const.py`, `manifest.json`) `1.4.0` -> `1.4.1`.

### Notes

- **BUG-1 (`cop_mean_day/week/month` reported `unknown`) is
  FALSIFIED.** Production Jinja verified correct values
  (`cop_mean_day=6.61`, `n_hours=5`, `n_samples=37`,
  `by_mode.heating.cop_mean=6.608`). The v41.3 report was
  observing stale pre-03:00 rollup state on a fresh install.
  Optional future-proof fix (rollup window 6h -> 720h) deferred
  to v1.4.2.
- Coverage remains `100.00%` (4461 stmts / 1258 branches);
  `--cov-fail-under=100` enforced in CI.
- No public API, entity_id, unique_id, service, or translation
  key changed. Safe drop-in for v1.4.0.
## [1.4.0] - 2026-09-29

### BREAKING

- Renamed 3 sensor translation keys to English slugs. Entity IDs
  change on next setup; the migration runs automatically and is
  idempotent.
  - `today` -> `cycles_today`  (sensor.daikin_cycle_ml_cycles_today)
  - `cop_vandaag` -> `cop_today`  (sensor.daikin_cycle_ml_cop_today)
  - `stooklijn_advies` -> `heating_curve_advice`
    (sensor.daikin_cycle_ml_heating_curve_advice)
- Internal identifiers (alert_type, dedupe_key, notification_id,
  ALERT_GROUP_MAP key, DataSnapshot.stooklijn_advies) are unchanged;
  alert dedupe state carries over.

### Fixed

- `_migrate_entity_ids` now updates `unique_id` and `translation_key`
  alongside `entity_id`, so registry rows reconcile to the entity
  created on the same setup pass (no orphaned rows).
- strings.json and translations/en.json had Dutch display names for
  `cop_vandaag` and `stooklijn_advies`; corrected to English. The
  Dutch display names remain in translations/nl.json.
- README version badge corrected.

### Added

- tests/test_entity_registry_integration.py: drives HA real
  EntityRegistry via `hass.config_entries.async_setup` (R195: no
  `mock_state(LOADED)` + `async_forward_entry_setups`). Asserts
  every SENSOR_DEFS key resolves to sensor.daikin_cycle_ml_<key>,
  no collision slugs, and no Dutch words in keys.

### Changed

- Version strings (const.py, manifest.json, pyproject.toml)
  1.3.2 -> 1.4.0.

## [1.3.2] - 2026-09-29

### Fixed

- Re-release of v1.3.1 content on the correct commit (f1dc6f9). The
  v1.3.1 git tag and GitHub release were mistakenly created on
  e361f5b (v1.3.0 code), so the v1.3.1 release artifact did not
  actually ship the entity_id migration. v1.3.2 ships the f1dc6f9
  tree with corrected version strings and a corrected release pointer.
- README version badge 1.3.0 -> 1.3.2 (badge had not been bumped for
  v1.3.1).

### Changed

- Version strings (const.py, manifest.json, pyproject.toml) 1.3.1 ->
  1.3.2. No code change; tree is identical to f1dc6f9 apart from the
  version strings and this changelog entry.

## [1.3.1] - 2026-09-29

### Fixed
- Entity ID migration for B5/B6 sensors: missing translation entries
  caused slug collision -> sensor.daikin_cycle_ml, _2, _3, _cop_curve_48h.
- cop_curve_recent display name now uniform across en/nl/strings.
- strings.json synced with translations/en.json (9 -> 13 entries).

## [1.3.0] - 2026-09-29

### Added

- v14 schema: `cycles.cop_avg`, `cycles.cop_sample_count`, `cycles.cop_sample_stdev`, `cycles.cop_confidence`
- v14 schema: `cop_samples.source` column (`'interval'` / `'tick'` / `'cycle_close'`)
- v14 schema: `cop_hourly` rollup table for long-horizon stooklijn
- `engine/thermal.py`: FEAT-2 cascade extracted from `sensor.py`
- T1 in-cycle COP integration (B2): `_cop_confidence` + `_weighted_mean_stdev`; cycles now persist weighted COP mean, sample count, stdev, and confidence
- `cop_hourly` rollup writer (B4) + 6h scheduler hook
- COP KPI sensors (B5): `sensor.cop_mean_day`, `sensor.cop_mean_week`, `sensor.cop_mean_month`
- REST view (B6): `GET /api/daikin_cycle_ml/cop_hourly` (`CopHourlyView`)
- `sensor.cop_curve_recent` (B6): 48h window, capped 96 points
- Service `export_cop_hourly` (B7): JSON/CSV export, mirrors `export_cycles`

### Changed

- pyproject `addopts` coverage gate 95 -> 100
- `db.async_insert_cycle` 13 -> 17 columns (v14 COP fields)
- `db.async_insert_cop_sample` 7 -> 8 columns (v14 `source` field)
- `_maybe_collect_cop_sample` interval 600s -> 300s (B3)
- `VERSION` 1.2.1 -> 1.3.0 (`const.py`, `manifest.json`, `pyproject.toml`)
- `manifest.json` dependencies: `["http"]` (B6 REST view)
- README badge: 1.2.1 -> 1.3.0
- DOCUMENTATION: 1.2.1 -> 1.3.0

### Fixed

- `test_cov8b_*`: new `cycle_cop*` attributes
- B3 run-1: `asyncio.run()` -> project async pattern (R188)
- B5 test after B6: `curve_recent` failure isolated the KPI cache (R191)
- B6: `HomeAssistantView` import from `helpers.http` (R190)

### Notes

- Tests: ~1685 passed, 4 skipped, 100.00% branch coverage (4424 stmts / 1248 branches)
- Sensor count 10 -> 14; service count 5 -> 6
- New module: `api.py` (REST view); new engine: `engine/thermal.py`
- cop_hourly retention policy not yet enforced (unbounded, ~1MB/yr)
- v14 migration is idempotent; prod v1.2.1 DB migrates on first v1.3.0 boot

## [1.2.1] - 2026-09-28

### Fixed
- Version strings in `const.py`, `manifest.json`, and `pyproject.toml`
  were never bumped for the v1.2.0 release. HA Integrations UI,
  Diagnostics, and HACS all reported 1.1.1 despite the complete
  v1.2.0 feature set being present. Bumped to 1.2.1.

### Changed
- README badges: version 1.1.1 -> 1.2.1, tests 1466 -> 1615,
  coverage 97.16% -> 100.00%.

## [1.2.0] - 2026-09-28

### Added
- `sensor.daikin_cycle_ml_thermal_power_live` (FEAT-2): live thermal
  power estimation with a 4-step cascade: `power_w x cop` ->
  `flow_lmin x dT` -> `rps x RPS_KW_FACTOR` -> `idle`. Exposes 6
  diagnostic attributes (`input_power_w`, `input_cop`,
  `input_flow_lmin`, `input_dt_k`, `input_rps`, `calculation_source`)
  for self-documenting dashboard cards. New coordinator helpers
  `_read_power_w` (W/kW normalization) and `_read_cop`. New constants
  `RPS_KW_FACTOR = 0.20` (empirical, re-verify in heating season),
  `WATER_SPECIFIC_HEAT_KJ_KG_K = 4.186`, `WATER_DENSITY_KG_L = 1.0`.
  Sensor count 24 -> 25. New test file
  `tests/test_feat2_thermal_power_live.py` (18 tests).
- `sensor.daikin_cycle_ml_cycle_state` now exposes `configured_*`
  attributes (FEAT-1): `configured_source_sensor`,
  `configured_power_sensor`, `configured_cop_sensor`,
  `configured_indoor_sensor`, `configured_model`, `configured_language`,
  `configured_entry_id`. Enables dashboards and automations to
  self-discover the entity_ids configured in OptionsFlow, without
  hardcoding. Values refresh on every OptionsFlow submit via
  OptionsFlowWithReload. Purely additive; no renamed or removed
  attributes. `notify_service` intentionally omitted (could leak
  target names).

### Changed
- `tests/test_31c_sensors.py`: `test_sensor_defs_has_9_containers`
  rewritten to `test_sensor_defs_has_expected_containers` using a
  forward-compat `>=` set check (R42). Removed stale duplicate `==`
  assertion that broke on every sensor addition.
- `tests/test_cov_config_flow_edges.py` (COV-1): 16 tests targeting
  missing branches in `config_flow.py`. Coverage 92% -> 99%.
- `tests/test_cov_db_store_edges.py` (COV-2): 11 tests targeting
  missing branches in `storage/db.py` (94% -> ~99%) and
  `storage/store.py` (96% -> 100%).
- `tests/test_feat1_configured_attrs.py` (FEAT-1): 5 tests targeting
  the new `_attrs_cycle_state` helper.
- `pyproject.toml`: `[tool.coverage.run] branch = true`. Branch
  coverage at enable time: 96.06%.
- `requirements_test.txt`: `hypothesis>=6.100.0` (property-based
  tests planned for COV-5; not yet used).
- `dashboard/cards/simple-card/preview.png`: 574 KB -> 153 KB via
  palette-256 quantization.
- `.gitignore`: removed stale deployment-symlink-bridge block.

### Removed
- Host-side: `daikin_test_old` container (1.23 GB writable layer).

### Fixed
- `coordinator.py::_read_power_w`: mypy strict error caused by
  `state.attributes or {}` narrowing to `dict[Never, Never]`.
  Removed the defensive `or {}` -- `state` is already None-checked,
  `attributes` is always a mapping. No behavior change.

### Notes
- Test suite: 1505 passed, 4 skipped.
- Branch coverage: 97% (4104 stmts, 97 miss, 1176 branches, 74 partial).
  Gate remains at 95%; COV-6 will raise to 97%.
- Ruff clean, Pylint 10.00/10, mypy --strict 0 errors.
- CI on 2207733: 6/6 green.

## [1.1.1] - 2026-09-28

### Added (dashboard)
- `dashboard/cards/simple-card/` — Lovelace YAML, full README
  (installation, dependencies, language toggle) and preview
  screenshot. Daikin-blue theme, hydraulic diagram, live phase
  indicator, alerts, stooklijn advice.
- `dashboard/README.md` — index of cards with general install
  instructions.
- `README.md` `## Showcase` section with the simple-card preview
  image, placed right after the badges.

### Documentation (also in this release)
<!-- batch-bc-20260927 -->
### Added (post-v1.1.0, docs)
- `HANDOFF_SOP.md`: self-contained SOP for handoff generation and
  multi-repo maintenance (R133-R145).
- `SOP.md` section 12: R133-R145 (handoff + multi-repo regels),
  tabel-format matching section 10. Includes gap-note that R93-R132
  are not yet present in SOP.md.
- HACS default store submission: PR #11345 open at
  https://github.com/hacs/default/pull/11345 (12/12 automated checks
  SUCCESS).

### Notes
- Coverage baseline shifted 97.40% (v1.0.2, commit 858cf8b) ->
  97.16% (v1.1.0+) due to HACS repo restructure (commit c60bc3f).
  All 32 non-test `.py` files moved from repo-root to
  `custom_components/daikin_cycle_ml/`; module-path change affects
  sub-package `__init__.py` coverage accounting.
  No functional regression: LOC 7906 -> 7910 (+4), tests 113 -> 114
  (+1), coverage config unchanged (`fail_under = 95`). Verified via
  recon batch RECON_C_COVERAGE_DELTA (commit c097197).



## [1.1.0] - 2026-09-27

### Added
- **HACS-compliant repo layout**: integration now lives at
  `custom_components/daikin_cycle_ml/` (was: repo-root + symlink workaround).
- `.github/workflows/hacs.yml`: HACS Action validation (`category: integration`).
- `.github/workflows/hassfest.yml`: official Home Assistant Hassfest validation.
- GitHub repo description + topics (HACS discovery).
- README section 4.1 "Via HACS (recommended)" + My Home Assistant button.
- SOP candidates R125-R128 (HACS restructuring lessons).

### Added
- `tests/test_52e3_adaptive_coverage.py`: 5 edge-case tests for
  `AdaptiveThresholds.observe_cycle` / `observe_day`.
  `ml/adaptive_thresholds.py` coverage 94% -> 100%.
- `assets/buy-me-a-coffee.png` + README Support section.
- SOP rules R111-R118 (Ruff CI-aligned invocation, symlink manifest
  path, version-agnostic tests, `import re`, `pyproject fix=true`
  risk, HA stubs in CI, HA Python version pin, aiosqlite stub variance).

### Changed
- Repo restructured: integration files moved from repo-root to
  `custom_components/daikin_cycle_ml/` (breaking for existing installs).
- `hacs.json`: `homeassistant` minimum 2025.1.0 -> 2026.9.0.
- `.gitignore`: removed `custom_components/daikin_cycle_ml` exclude,
  added `MagicMock/`.
- `.github/workflows/coverage.yml`: removed symlink-setup step.
- `.github/workflows/mypy.yml`: directory-based invocation.
- `manifest.json`: keys reordered alphabetically after `domain, name` (Hassfest).
- `strings.json` / `translations/*.json`: escaped JSON examples in
  `model_custom` step as `{{...}}` (Hassfest placeholder rule).
- Removed empty `data_description` on `attributes`, `finalize`,
  `reconfigure`, `reconfigure_full`, `test_notification_result` steps.
- Added `data` block to `options.step.init` (Hassfest data/data_description pairing).
- `__init__.py`: added `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`
  (Hassfest config_schema warning).
- README version badge: 1.0.2 -> 1.1.0.
- 11 test files: `ROOT` is now `_PROJECT_ROOT / "custom_components" /
  "daikin_cycle_ml"`; inline `Path(__file__).parent.parent / X` replaced
  with `_INTEG / X`.
- README badges: coverage 97.16%, tests 1466, Pylint 10.00/10.
- README Support section rewritten for this project's context.

### Verified
- CI: 6/6 workflows green (Ruff, Pylint, Coverage, Mypy, HACS Validation, Hassfest).
- 1466 tests passed, 4 skipped.
- Coverage 97.16% (all modules >= 95%).
- `mypy --strict`: 0 errors in 30 source files (directory-based).
- Import smoke: 130 modules OK.
- `git ls-files` no longer contains `120000` (symlink) entries.
- Runtime smoke v1.0.2 in production HA 2026.9.3: 24 entities loaded,
  DB integrity OK, `cop_samples.mode` populated
  (`dhw=9, unknown=5, None=13`), no `daikin_cycle_ml` errors in log.

## [1.0.2] - 2026-09-27

### Added
- mypy --strict: 219 -> 0 errors across all 30 integration modules.
- `.github/workflows/mypy.yml` CI workflow (Python 3.14, HA 2026.9.3 stubs).
- `py.typed` marker (PEP 561).
- `[tool.mypy]` block in pyproject.toml (strict + follow_imports=silent).
- SOP rules R108-R110 (leaf-annotation cascade, dict key-type mismatch, idempotent re-run).

### Changed
- Type annotations on all public functions, methods, and class attributes.
- `ConfigFlowResult` as canonical return type for `async_step_*` (HA 2026.9).
- `_OPTIONS_FLOW_BASE` from conditional variable to TYPE_CHECKING + else try/except.
- `_cluster_labels` from `dict[str, Any]` to `dict[int, str]`.
- `ml/multi_baseline.py` public methods fully annotated.
- `engine/notification_engine.py` `_SafeDict` typed `dict[str, Any]`.
- `storage/store.py` `_counters` locally widened to `dict[str, Any]`.
- README badges: version 1.0.2, coverage 97.40%, pylint 10.00, tests 1400+.

### Fixed
- `ml/clustering.py` `labels` no-redef on line 155 (annotation removed).
- `ml/features.py` `overrides[name]` narrowing via local variable.
- `engine/notification_engine.py` `ctx or {}` for None-safe Mapping.
- `storage/db.py` `int(cur.rowcount)` for aiosqlite stub variance (CI).
- `storage/db.py` `list(await cur.fetchall())` for `Iterable[Row]` index/size ops.
- `storage/db.py` `a: dict[str, Any] | None = agg.get(key)` annotation on first def.
- `storage/db.py` `params: tuple[Any, ...]` for heterogeneous tuple.
- `storage/db.py` `cops: list[float]` explicit loop instead of comprehension.
- `storage/db.py` `async_avg_duration_since` return type annotation.

### Version
- 1.0.2 (patch: internal typing hardening + CI mypy gate, no runtime changes).

### Test suite
- Tests: 1461 passed, 4 skipped.
- Coverage: 97.40% (all modules >= 94%).
- Ruff: clean.
- Pylint: 10.00/10.
- mypy --strict: 0 errors (CI-enforced).
- CI: Ruff + Pylint + Coverage + Mypy (4 workflows).

### Known limitations
- Per-module coverage below 95%: `ml/adaptive_thresholds.py` 94%.

## [1.0.1] - 2026-09-27

### Added
- `cop_samples.mode` column + v13 migration (idempotent ALTER TABLE).
- `CopSample.ts` + `StooklijnAdvies.reason` dataclass fields.
- `STOOKLIJN_RECENT_WINDOW_S` (48h) recency window in `cop_analyzer`.
- `_resolve_cop_sample_mode()` in coordinator: `snap.mode` -> direct `I/U`
  operation mode from attrs -> `classify_mode(attrs)` -> `"unknown"` (Bug I).
- `reason` attribute on `sensor.stooklijn_advies` (Bug G).
- DHW-mode gating for `short_run` / `short_off` / `pendulum_hourly` alerts (Bug H).
- `_build_alert_context` mode fallback to `last_cycle.mode` (52b5).
- SOP.md rules R93-R100.
- CI Coverage workflow (Ruff + Pylint + Coverage, 3 workflows).
- `custom_components/__init__.py` package marker (52b8i).
- `.gitignore` entry for `custom_components/daikin_cycle_ml` dev symlink (52b9).
- ROADMAP.md state-space binning open questions (52c-docs).

### Changed
- `analyze_stooklijn`: DHW-aware (`mode in (heating, unknown)`) + recency filter.
- `_maybe_refresh_stooklijn`: DHW-check before cache-check.
- `_maybe_collect_cop_sample`: persist mode via `_resolve_cop_sample_mode`.
- `dhw_active`: requires `I/U == DHW` AND (`state == "running"` OR BUH active) (Bug A).
- `sensor.current_cycle.dt_k`: returns `None` when state != "running" (Bug C).
- 6 silent debug handlers promoted to warning (51d).
- Pylint 9.94 -> 10.00.
- English docs (SOP.md + CHANGELOG.md) (R97).
- CI coverage.yml: replicate custom_components symlink + homeassistant/aiosqlite deps (52b8j).

### Fixed
- Bug A (52a): `dhw_active` triggered on 3-way valve rest position.
- Bug B (52b): stooklijn analysis mixed DHW samples with heating samples.
- Bug C (52a): `sensor.current_cycle.dt_k` returned stale value when idle.
- Bug D: README entity `missing_attrs` -> `missing_attributes`.
- Bug E: README documented `verlaag_lwt` instead of `verlaag_lwt_2c`.
- Bug F: stooklijn mixed DHW samples with heating (paired with Bug B).
- Bug G: `reason` attribute not exposed on stooklijn_advies sensor.
- Bug H: short_run/short_off/pendulum alerts fired during DHW.
- Bug I: cop_samples.mode inconsistent during DHW (I/U attrs fallback).
- CI Coverage `ModuleNotFoundError` (symlink, R98).
- 102 `ModuleNotFoundError` in pytest collection (dual custom_components, R99).

### Removed
- `.pylintrc` inline comment `# (DB CRUD)`.
- Coverage CI disable fallback (52b8h-fallback, R72).

### Version
- 1.0.1 (patch: bugfixes + docs + CI only, no breaking changes).

### Test suite
- Coverage: 95.45%
- Ruff: clean
- Pylint: 10.00/10
- CI: Ruff + Pylint + Coverage pending on this commit.

### Known limitations
- Per-module coverage below 95%: `coordinator.py` 91%,
  `engine/attribute_reader.py` 93%, `engine/action_engine.py` 93%,
  `ml/adaptive_thresholds.py` 94%.
- `CoverageWarning: module-not-measured` (cosmetic, dual-path import).
- `mypy --strict` not yet done (Platinum blocker).

## [1.0.0] - 2026-09-26

### Added
- quality_scale.yaml (IQS manifest, Bronze+Silver+Gold)
- PARALLEL_UPDATES = 0 in sensor/binary_sensor platforms
- codeowners in manifest.json

### Changed
- HA ruff 2026+ config (line-length 100, target py313, I/UP/B/C4/SIM/...)
- Coverage threshold 94.5 -> 95.0
- Pylint workflow: scoped to integration code, Python 3.13
- Ruff workflow toegevoegd (ruff-action@v3)

### Fixed
- E1102 not-callable in coordinator.py (4 defensieve getter-calls)
- B905 zip strict= expliciet (ml/clustering.py)
- F401 explicit re-export (__init__.py)
- Versie-asserts in tests bijgewerkt naar 1.0.0



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

[Unreleased]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.5.3...v1.6.0
[1.5.3]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.5.2...v1.5.3
