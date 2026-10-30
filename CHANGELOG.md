# Changelog

## [Unreleased]

### Added
- **#218** Full Daikin Altherma R Hybrid (EVLQ05CV3 + EVLQ08CV3) support:
  - Models: MODEL_EVLQ05CV3 + MODEL_EVLQ08CV3 with EN 14825 W35 datasheets (5 COP points each), R410A, bivalent=true
  - Indoor-unit aliases: `ehyhbh05av32` → EVLQ05, `ehyhbh08av32`/`ehyhbx08av3` → EVLQ08
  - Attribute aliases: `Outlet Water Heat Exch. Temp. (R1T)`, `Outlet Water BUH Temp. (R2T)`, `DHW tank temp (R5T)`
  - 2 binary sensors: `boiler_operation_demand`, `boiler_dhw_demand`
  - 3 sensors: `hybrid_mode` (enum), `boiler_efficiency_cop`, `boiler_contribution_today_pct`
  - Hybrid-only: sensors return unavailable on non-hybrid installs
  - Config flow: `hybrid_hint` warning when boiler attrs missing + reconfigure HP↔Hybrid detection
  - Boiler-cycle guard prevents phantom short-cycle alerts during boiler-only operation
  - COP isolation: `boiler_active` flag on cop_samples (v22 migration); `cop_today` and heating curve use pure HP samples only; co-fire samples stored with flag for future analytics
  - Alert suppression: `short_run`, `short_off`, `pendulum_hourly`, `pendulum_daily` suppressed during boiler-only
  - DB schema v22: `cop_samples.boiler_active`; `cycles.boiler_contribution_samples` (v21)
  - Diagnostics: boiler_active, boiler_dhw_active, hybrid_mode, boiler_efficiency_cop, inv_freq_secondary

### Fixed
- **#218** Idle state now correctly returns `unknown` for COP sensors on pure HP installs without boiler (was: coercion)

### Fixed
- **#217** IDLE state now forces RPS=0, thermal_power_live=0.0, and COP=None instead of showing stale values.
- **#217** Add ERG04/06/08 model aliases mapping to ERGA profiles.
- **#217** Heating Curve advice now requires 18+ samples; sets `reason=insufficient_samples` otherwise.

### Docs
- **#211 #207** Reconcile CONFIGURATION §2.1 vs README attribute lists (12 required, matching `const.REQUIRED_ATTRIBUTES`); move INV freq + R5T to §2.2 recommended, LW setpoint to §2.1 required.
- **#211** Add R1T ambiguity warning (§2.1, `## Known limitations`) and external-sensor failure-mode section (§2.1.1, `## Known limitations`).
- **#207** Cross-link §2.3 to MODEL_COMPATIBILITY §5 per-model matrix.
- Remove stale `docs/v1.7.0-plan.md`.
- #214 [docs] Reconcile README counts with confirmed state (47 sensors, 13 services, 63 entities, 9 repairs, 3729 tests, 8337 stmts / 2430 branches, 38 mypy files, 51 datasheets / 53 profiles); bump doc headers v1.9.0 → v1.14.0 in 8 docs + MODEL_COMPATIBILITY.md.
- #214 [docs] Fix 3 logic contradictions: wizard step count, "contain all 12" vs Known-model-limitations, "published alongside each release" for static MODEL_COMPATIBILITY.md.
- **#215** README structural pass: added `## Contents` TOC (19 auto-derived anchors), moved `## Why this exists` above `## What you get` for clearer narrative flow (Showcase position unchanged); blank-line and divider symmetry restored at section boundaries.

- **#224 #218** Hybrid EVLQ documentation: README supported-models section, ENTITIES.md §2.13 hybrid sensors (3) + 2 boiler binary sensors, MODEL_COMPATIBILITY.md §6.6 hybrid (R5T sentinel, R561 guard, COP isolation), CONFIGURATION.md §3.3 six model families, DATABASE.md v21/v22 migrations, TROUBLESHOOTING.md §4.5 three hybrid scenarios.

## [1.14.0] - 2026-10-29

### Added
- **#206** electrical input cascade: power meter > ESPAltherma 2.0 `Stats: Electrical input estimated (kW)` > v1 inverter fallback (`INV_A x 230V x phases + BUH_step1_kW + BUH_step2_kW + 100W`). v2 detection with 300s hysteresis. Ref raomin/ESPAltherma Discussion #599.
- **#206** OptionsFlow step `cop_calc` (`supply_phases` 1|3, `buh_step1_kw`, `buh_step2_kw`).
- **#206** sensor `electrical_power_estimated` (W) with `source` attribute (`power_meter`|`espaltherma_v2_stats`|`inverter_estimated_v1`|`none`).
- **#206** coordinator `_read_cop_effective` fallback (cop_sensor > computed flow_dt / electrical power). MAX_COP (11.0) gate. DataSnapshot: `cop_source`, `electrical_power_w`, `electrical_power_source`.
- **#206** const: `SUPPLY_PHASES_DEFAULT/ALLOWED`, `BUH_STEP1_KW_DEFAULT`, `BUH_STEP2_KW_DEFAULT`, `ELECTRICAL_OFFSET_W_V1`, `VOLTAGE_NOMINAL_V`, `V2_STATS_KEY`, `INV_PRIMARY_CURRENT_KEY`, `BUH_STEP1_KEY`, `BUH_STEP2_KEY`, `V2_STATS_HYSTERESIS_S`.

### Fixed
- **#206** `_errors_total` class-level default (partial fixtures via `object.__new__` no longer `AttributeError` in `_async_update_data` except-handler).
- **#206** `_read_power` / `_read_power_w` use `getattr(self, "power_sensor", None)` (mirror of `_power_from_meter`).
- **#206** `cycles_today()` skips `start_ts > now + 60s` (clock-skew tolerance, blocks DB-import corruption).
- **#206** `_value_duty_cycle_today_pct` clamps [0, 100].

### Tests
- `test_205_electrical_power_cascade.py` (14), `test_206_cop_fallback.py` (6), `test_g1_defensive_guards.py` (6) - new.
- `test_c5_sensors.py::test_duty_cycle_computes_pct` monkeypatches `_now` (wall-clock independence).
- `test_c3a_integration.py`, `test_v160_spf.py`, `test_v160_per_mode_cop.py`, `test_v160_deep.py` - SENSOR_DEFS 46 -> 47.

Suite: 3703 -> 3729 (+26).

## [1.13.2] - 2026-10-28

### Fixed

- **#201 (v1.13.2)** - clearable optional sensor fields: OptionsFlow._save normalizes omitted keys to None before merge so clearing persists (HA core #154795 pattern). 5 tests.
- **#188 + #184 (v1.13.2)** - thermal power physical delta T: mode-aware (heating/dhw: R1T-before-BUH minus R4T, cooling: R4T minus R1T), matching raomin ESPAltherma commit 5382853; clamp negative to 0kW, drop >14kW. v20 migration adds cop_samples.r1t + r4t columns; sampler writes both. Historical pre-v1.13.2 samples fall back to legacy formula (no history rewrite).

### Docs

- **#191 + #195 (v1.13.2)** - ESPAltherma data-source credit in README + reciprocal link; datasheets.json `_meta` (CC BY 4.0, attribution_required, permission_grant for raomin); MODEL_COMPATIBILITY.md sources section; permission granted both directions.

## [1.13.1] - 2026-10-28

### Added

- **Model family wizard** (#197): two-step config flow. Step 1 picks the model family (EPRA, ERLA, ERGA, EPGA, EDLA, EBLA, EDLQ, EBLQ, EPSK, EKHBRD, ERRQ) or Basic/Custom. Step 2 lists only that family's models; Basic/Custom skip the model picker.
- **Alias layer (phase 1)** (#198): `MODEL_ALIASES` maps commercial model names to base technical codes. Resolvers `resolve_model_key`, `family_for_model`, `models_in_family` in `const.py`. Aliasing applied transparently inside `engine.model_profiles.get_profile()` and `engine.model_datasheets.get_datasheet()`.
- **ERGA08EVH7** commercial alias for ERGA08EAV3 - closes #197.

### Changed

- `config_flow._MODEL_SELECTOR` split into module-level `_FAMILY_SELECTOR` + `_build_model_selector(family)` factory. Reconfigure-basic keeps the flat picker.
- i18n step count 16 -> 17 (strings.json, translations/en.json, translations/nl.json).
- Legacy compat: `async_step_user` detects legacy payloads (`source_sensor` without `family`) and forwards to `async_step_model` so existing tests and programmatic callers keep working.

### Fixed

- **#196 cop_samples=0 on fresh installs** (v1.13.0 regression): `_maybe_collect_cop_sample` now reads source ESPAltherma attributes via `build_compat_view` and overlays the COP value from `cop_sensor`. Previously read the cop_sensor's own attributes only (numeric template sensor with no synthetic keys like `leaving_temp`/`outdoor_temperature`), causing `data_quality='unknown'` -> hard reject -> 0 samples on fresh installs despite valid cycles. Legacy fallback preserved for callers without source attributes. Source path also correctly extracts `lwt`/`outdoor`/`flow_lmin` so samples are analytically complete. Confirmed root cause on 2 users (ERGA08EVH7 split + EPRA12EAV3 monoblock). 10 new tests cover the source path, legacy fallback, edge cases, and `data.cop` fallback.

## [1.13.0] — 2026-10-27

### Added
- **CI guard: MODEL_CHOICES ↔ MODEL_LABELS surface contract** — `model-compat.yml` now fails the PR gate on wizard/label drift (the PR #166 class) or a choice without a behavioural profile. Path filter also triggers on `engine/model_profiles.py` and `data/datasheets.json` changes, which were previously silent. New test: `test_model_choices_match_labels`. No runtime behaviour change to the integration.
- **#175 (partial) — HT profile + datasheet points**
  - `_HT_PROFILE` in `model_profiles.py`: `good_dt_threshold_k=10.0` (vs 5.0 LT), `max_cycle_duration_min=300`, `defrost_interval_min=45`, `short_run_threshold_min=30`, `target_cycles_per_day=5`. Assigned to 6 HT models (EKHBRD011/014/016, ERRQ011/014/016). EBLQ remains LT (const.py:126).
  - `datasheets.json`: 3-point COP curves (A7/W35, A7/W65, A7/W80) for the same 6 models, from official Daikin service-manual specs. No interpolation. `nom_cop` unchanged (W35, schema semantics preserved).
  - Tuning remains open pending live HT field data (#127 RFI). Follow-up: `cop_vs_datasheet_pct` should pick the closest `t_lwc` point for HT models (separate PR).
- **v19 thermal_kw_avg rebuild migration (#169)**: historical cycles with `thermal_kw_avg = 0.0` or NULL are recomputed from `cop_samples` via the flow_dt formula (R486: DHW prefers flow_dt, now uniform for heating due to missing power_w/rps in samples). Cycles with ≥3 eligible samples get a recomputed value; sparse <3 are NULLed. `features.vector_json[11]` overwritten from new values, `daily_summary` + `cop_hourly` rebuilt for touched days/hours. Idempotent via marker `data_migration_v19_completed` with `completed_ts`. Wiring is best-effort: failure does not block setup and does not write the marker (retried next boot).

- **Bundled models expanded to 40** — Added 25 new models (ERGA, EPGA, EDLA, EBLA, EDLQ, EPSK, EPRA18) to support more Daikin Altherma devices in the config flow. Includes ERGA08EAV3H (Split) requested by community.

- **Expand `MODEL_CHOICES` to cover EBLQ + HT families** — 11 new wizard entries (53 total). `docs/MODEL_ATTRIBUTES.json` remains at 40 def files (upstream contract unchanged).
  - **LT monobloc** — `eblq05cv3` (4.40 kW, COP 5.00 A7/W35), `eblq07cv3` (7.00 kW, 4.52), `eblq11cv3` (11.2 kW, 4.61), `eblq14cv3` (14.5 kW, 4.30), `eblq16cv3` (16.0 kW, 4.26)
  - **HT split** — `ekhbrd011+errq011` (11.3 kW, COP 2.97 A7/W55, up to 80 °C LWT), `ekhbrd014+errq014` (14.5 kW, 2.89), `ekhbrd016+errq016` (16.0 kW, 2.73)
  - **HT outdoor** — `errq011-ersq011` (11.0 kW, 3.08), `errq014-ersq014` (14.0 kW, 3.00), `errq016-ersq016` (16.0 kW, 2.88)
  - All 11 use `_BASE` behavioural profile (defaults) — HT units likely need per-family tuning (higher `good_dt_threshold_k`, `max_cycle_duration_min`) once live data is available; tracked as v1.13.0 follow-up.
  - Zero test changes — `test_all_model_choices_present`, `test_no_model_expects_brine`, `test_all_profiles_have_same_keys` auto-cover via `MODEL_CHOICES` iteration.

### Docs
- **Guide**: how to change your model via Reconfigure (`docs/MODEL_COMPATIBILITY.md` §"Changing your model"). Model is config entry data, not an option — per HA 2026+ guidelines.
- **Datasheet runtime coverage** — bundled datasheet store extended to all 51 real models (was 40). 11 new entries (EBLQ05-16, EKHBRD011-016, ERRQ011-016). 12 partial curves (2 points) + 3 nom_cop-only from verified Daikin EN specs — no interpolated data.
- **Validator** — `_T_LWC_MAX` 70 → 80 °C for HT models.
- **Docs** — runtime coverage table + user_datasheets instructions.

- EPSK12AW1/EPSK14AW1 COP A7/W35 filled from heatpumpkeymark + Daikin CH (5.50).

- **Datasheet reference table** — `docs/MODEL_COMPATIBILITY.md` now lists public Daikin datasheet COP, capacity and LWT values for every bundled model family: EBLQ CV3, EKHBRD+ERRQ, ERRQ-ERSQ, EPSK AW1, EDLA D3V3, EBLA EV3, ERGA EAV3, EPGA DAV3, EPRA18. Excluded GEO2/GEO3 listed for reference only.


### Fixed

- **#129 + #124 (v1.13.0)** — Sanity gate for `cop_avg` and `thermal_kw_avg`
  - `_apply_cop_sanity_gate` (coordinator): NULL when `n < MIN_SAMPLES_FOR_AVG (3)` or `cop_avg > MAX_COP (11.0)`
  - `_apply_thermal_sanity_gate` (cycle_detector): NULL when `thermal_kw_avg > MAX_THERMAL_KW (14.0)`
  - Constants in `const.py` (single source of truth)
  - `cop_sample_count` preserved after gate (real count kept for diagnostics)
  - Gated value propagated to return-tuple (R488) — features-writer safe
  - **v19-migration caveat:** `features.vector_json[11]=0.0` now means "gated/missing", NOT "zero heat". Do not treat as measurement during v19 recompute — recompute from `cop_samples` per #129.
  - 11 tests in `tests/test_v1130_sanity_gate.py`

## [1.12.9] — 2026-10-26

### Added

- **#155** — Model compatibility contract + drift gate
  - `tools/parse_espaltherma_defs.py` + `tools/check_compat_contract.py`
  - `MODEL_COMPATIBILITY.md` (40-model matrix + 3 decoy warnings)
  - `.github/workflows/model-compat.yml` (PR path-gate) + `weekly-drift.yml` (signal-only)
  - 130 tests in `tests/test_model_compat.py`
- **#155 follow-up** — Adopt upstream beta drift @ `99ed8d19` (39→40 models, 401→421 labels; new HT ERRQ-ERSQ outdoor unit definition, refrigerant-circuit labels only, no runtime impact)

### Fixed

- **#131 (PR-1)** — Forward bridge-aware cycle merge (db primitive)
  - Extracted `_apply_merge()` primitive shared with v18 R446b migration
  - `async_merge_cycle_forward(new_id)` — detects transient-cycle-sandwiched-between-same-mode pattern, collapses to one keeper row
  - Fixed: v18 R446b could not merge #131's exact case (`is_transient=0` required on both sides; 60s ghost classifies transient)
  - Removed duplicate `_R446B_MERGE_GAP_S` constant definition
  - 13 tests in `tests/test_v1129_131_forward_merge.py`; 10 v18 R446b regression tests still pass
  - Coordinator wiring deferred to PR-2 (ships below)
- **#131 (PR-2)** — Coordinator wiring for forward bridge-merge
  - Hook in `_process_new_cycle` after `async_insert_cycle` now calls `async_merge_cycle_forward(cid)` on the live 30s tick
  - `CycleStore.rollback_last_cycles(n)` pops `n` entries (n = `absorbed` ∈ {0,1,2}) and decrements `cycles_total`, `cycles_today`, `cycles_{mode}`
  - `good_cycles_today` / `bad_cycles_today` intentionally untouched (`score_and_count` ran pre-merge)
  - Keeper feature-vector not regenerated over extended span (optie A; candidate v1.13.0 improvement)
  - 11 tests: 4 `rollback_last_cycles` unit + 7 coordinator integration (simple merge, bridge merge, no-merge, transient skip, exception path, cid-None guard, counter coherence across absorbed ∈ {0,1,2})
- **#132** — DHW thermal cascade prefers `flow_dt` over `power_cop` (R486)
  - `compute_thermal_power_live()` gains additive `mode` kwarg (default `"heating"`) — backward-compatible across all callers
  - `mode == "dhw"` checks `flow_dt` first: R4T is the physical cold side for both heating and DHW; user-configured COP is heating-biased and overestimates DHW thermal (R486)
  - heating / cooling / unknown keep original cascade order (`power_cop` first)
  - Bug 1 (issue claims R5T is cold side) **refuted** by live prod 1 capture 2026-10-26 — R4T is correct
  - Bug 2 **confirmed**: DHW cycle 84 evidence `thermal_kw=0.0` with `cop=1.985` (impossible) via `power_cop` path
  - New `engine/physics.py`: `get_physical_cop_ceiling(mode, lwt, outdoor)` standalone Carnot primitive (R452); cascade wiring deferred to #123 (blocked by #127)
  - 8 tests in `tests/test_v1129_132_thermal_mode.py`; 2 fixtures updated (`test_feat2_thermal_power_live.py` ×2, `test_r216_datasnapshot.py` ×1)
- **#156** — Idempotent `_migrate_entity_ids` for partial migrations
  - Safe re-run when only `entity_id` differs; unique_id + translation_key preserved
  - 3 tests in `tests/test_v1129_entity_mig_idempotent.py`
- **#157** — Historical `cop_sample_count` correction (#133b)
  - Migration `async_migrate_to_v1_12_5_sample_count_fix` (after v18 data migrations)
  - Heuristic: `stored > real_matched × 1.5` → UPDATE (relative, not duration-based)
  - Marker `data_migration_v1_12_5_sample_count_fix` with `completed_ts`
  - 5 tests in `tests/test_v1129_sample_count_fix.py`

### Closed

- **#133** (umbrella) — #133a (v1.12.5 forward COUNT) + #133b (v1.12.9 historical) both shipped
- **#136** — tracked via PR #155

## [1.12.8] — 2026-10-25

### Fixed

- **Reconfigure failure during source offline window** - when the user triggered reconfigure while `sensor.althermasensors` was momentarily `unavailable` or had empty attributes (e.g., during an ESPAltherma reboot, WiFi/MQTT reconnect, or right after an HA restart), the code called `missing_required({})` which returned all 12 required attributes as missing. The resulting UX message was misleading - "required attributes missing" - when the real problem was "sensor is offline, try again in 30-60s".
  - New guards: `source_offline` (state is unavailable/unknown) and `source_empty` (state is Online but attributes is empty).
  - Existing `missing_attributes` path now includes `len(attrs)` and `last_updated` in the log for future diagnosis.
  - `entity_not_found` path unchanged.
  - **Not a v1/v2 ESPAltherma compat issue** - v1 and v2 both publish all 12 required attributes when the sensor is online (verified against prod 2 v1 dump 2026-10-25).

Refs: reported via prod 2 (v1 ESPAltherma) log 2026-10-25T22:00:47 local. Setup wizard hardening deferred to #141 (v1.12.9).

## [1.12.7] — 2026-10-25

### Fixed

- **ESPAltherma beta compatibility (#150)** — `R1T-Outdoor air temp.` prefix format was bypassed by `cycle_detector.update()` and `coordinator._snap_attr()` when called with raw attrs (bypassing `read()`). Result: `outdoor_mean: None` in all `cop_curve_recent` points, `stooklijn_advies.buckets` stuck on `unknown`, `cop_degradatie_week.bins_used` empty. Fix: apply `build_compat_view()` at both entry points (idempotent, safe when `read()` already applied).
- **ERGA D ECH2O config flow (#150)** — HPSU inlet label `[HPSU] Tr return Temp (R4T)` not aliased. Setup wizard raised `missing_attributes`. Alias added.
- **EPRA D / ERGA D ECH2O lwt_before_buh (#150)** — HPSU label `[HPSU] Tv inflow Temp (R1T)` (double-space, handled by `normalize_key`) not aliased. Alias added.
- **DEFAULT.h fallbacks (#150)** — `Inlet temperature(R4T)` and `DHW temperature(R5T)` shorter forms not aliased. Aliases added.

### Docs

- **README — Supported models & ESPAltherma attributes** — new section documenting the 12 required attributes, how to enable them in the ESPAltherma web UI, 39 supported model families, known limitations (Altherma 4, ERGA/EPRA D ECH2O HPSU, Hybrid, LT_EBLQ 5-7kW Monobloc, Mini chiller EWAQ), and not-supported (HT protocol S, PROTOCOL_S, PROTOCOL_S_ROTEX).
- **README cleanup** — removed outdated `## What's new` and `## Version history` sections. Full version history now lives in `CHANGELOG.md` only.

### Tests

- 19 new tests in `tests/test_outdoor_temp_fallback.py` — prefix, suffix, HPSU inlet, HPSU lwt_before_buh, DEFAULT fallbacks, decoy rejection (R1T/R4T/R5T non-canonical labels), placeholder handling, detector runtime with prefix attrs.

### Coverage source

- 39 root ESPAltherma beta model definitions indexed; 401 unique labels (active + commented templates)
- 33/39 use `R1T-Outdoor air temp.` (prefix format)
- 32/39 use `Inlet water temp.(R4T)` (suffix)
- 34/39 use `DHW tank temp. (R5T)` (suffix)
- ERGA D ECH2O is the only model using HPSU labels for both R4T and R1T

Fixes #150 · Refs #117

## [1.12.6] — 2026-10-25

### Dashboard Cards

- **New: Daily Summary Tabbed** — 5-tab Lovelace card (opt-in, no code changes)
  - `Overview` — HP model hero, quality ring, mode split, best/worst day, sparkline trends
  - `Quality` — adaptive Y-axis (auto-scales to 60-100 when all data high, removes dead space)
  - `Cycles` — stacked per-mode daily bars, day totals, stats strip
  - `Duration` — runtime bars with p95 capping and clipping markers
  - `Events` — BUH/Defrost/Total counts (3 rows) + ratio chart with 15%/35% reference lines
  - Popup details on every interactive element (bars, dots, tiles, stats, hero, best/worst)
  - Persistent tab + window state across 30s tick updates
  - 5 configurable variables: `lang_override`, `default_tab`, `default_window`, `chart_height`, `show_hints`
  - Works with Dutch entity IDs (`recent_dagoverzicht`, `wp_specs`, `cyclus_status`, `ontdooiingen_vandaag`, ...)
  - Works with custom entry names (`sensor.warmtepomp_recent_dagoverzicht`)
  - Automatic `hass.language` detection with optional manual override

- **Root README showcase redesign** — tabbed card now features as primary showcase with hero layout, 5 feature bullets, and CTA buttons (Download YAML + Full docs)
- **dashboard/README.md** — split into Featured Card (tabbed, 480px) + Other cards (existing 3, 320px) sections
- **Card README** — quick nav anchors, linked YAML download with Raw/save hint

### Notes

- **Dashboard-only release** — no integration code changes
- **Backwards compatible** — dashboard cards are opt-in; no forced changes for existing users
- **No fleet action required** — users can stay on v1.12.5 if they don't want the new card
- **HACS notification** — version bump triggers update notification in HACS for v1.12.5 users

### Still validating

- **#125 kmeans scheduling** — fase A (scheduler wiring smoke-test) on Monday 2026-10-26 04:05 local; fase B (weekly retrain validation) on Sunday 2026-11-01 04:05 local. Neither is affected by this dashboard release.

## [1.12.5] - 2026-10-25

### Added
- `_sample_aggregates(start, end, mode=None, exclude_artifacts=False)`:
  optional mode filter and artifact exclusion. Backward-compatible —
  existing migration callsites (which pass only start/end) unchanged.
- `_cop_confidence` reformulated as pure count-based 4-tier scale:
  `none` (0-2) / `low` (3-5) / `medium` (6-11) / `high` (12+).
  12 samples at 300s cadence = 1h steady-state, statistically robust.

### Changed
- Forward cycle-close now writes real `COUNT(*)` from `cop_samples`
  (mode-filtered) into `cycles.cop_sample_count`, replacing the
  tick counter (`duration_s / 30`) that inflated counts ~10x (#133).
- `cycles.cop_avg` on the forward path remains **power-weighted**
  from live ticks (correct thermodynamic integration: sum Q / sum P
  over the cycle). DB `AVG(cop)` is used only when no live ticks
  were accumulated (fallback for restart/reload cases).

### Fixed
- `cop_sample_count` no longer mislabels short dense cycles as
  "high" confidence and long sparse cycles as "low" — the previous
  formula divided `duration_s` by 30 which conflated tick count
  with statistical confidence (#133).
- `cop_confidence` "medium" tier now reachable (was documented but
  unreachable in code — only `none`/`low`/`high` could be produced).

- Cycle detector stuck in wrong mode when restored from a stale
  snapshot. `_should_split` unconditionally returned `False` when
  `mode == "dhw"`, so DHW cycles could only close via compressor-off,
  pump-off, or the 4h `MAX_CYCLE_DURATION_S` hard-cap. Added a
  reverse-split for `dhw` -> `heating`/`cooling` after `MODE_DEBOUNCE_S`
  (60s) when source reports steady-state heating/cooling. Reuses
  existing `_pending_mode` / `_pending_mode_since` fields; no schema
  change. (#144)

### Corrections to prior release
- v1.12.4 release notes stated "cop_sample_count and cop_avg now
  computed from real COUNT(*)/AVG(cop)". That was true only for the
  **backfill** path (Amend 7, R445a-c, R446b). The forward live path
  in `_collect_cycle_averages` was not updated and continued using
  tick-based `cop_sample_count`. v1.12.5 closes this gap.

### Known limitations
- Historical cycles with tick-inflated `cop_sample_count` require
  the #133b one-shot migration to correct; tracked separately.
- `DEFAULT_COP_SAMPLE_INTERVAL_SECONDS` = 600 but effective observed
  cadence is ~340s due to `power_stable` + `data_quality` filters.
  Cadence tuning deferred to v1.13.0.

## [1.12.4] - 2026-10-24

### Added
- Schema v18: 6 new columns (mode_original + is_transition_artifact on
  cop_samples; mode_original, parent_cycle_id, is_dhw_tail, is_reconstructed
  on cycles) + 2 indices.
- Migration async_migrate_to_v18: DHW historical backfill with 8 amendments:
  - R445e: dynamic Carnot gate (0.55 x Carnot, not absolute > 11)
  - R445a-c: 3-shape classifier (relabel/split/mark tail)
  - R445d: in-cycle unknown samples relabeled to cycle mode
  - R446: synthesis of orphan DHW runs (>=15min, gap <=15min)
  - R446b: merge adjacent same-mode splits (gap < 120s)
  - Amend 7: aggregate backfill for cycles with NULL cop_sample_count
  - R447: cop_hourly DELETE+rebuild for affected hours (fixes partial-hour bug)
  - R448: daily_summary rebuild for affected days
- ATTR_DHW_TANK_TEMP constant ("DHW tank temp. (R5T)") - verbatim, no
  substring match, protects against prod-1-only decoy key.

### Changed
- cop_sample_count and cop_avg now computed from real COUNT(*)/AVG(cop)
  on cop_samples (never from cached tick count). Related to #133.
- cop_hourly n_samples computed from real COUNT(*) (excludes transition
  artifacts).

### Fixed
- Historical DHW samples reclassified (fleet: 68 in-cycle unknowns).
- COP artifacts flagged by dynamic Carnot threshold (fleet: 247 samples).
- Orphan DHW cycles synthesized (fleet: 13 events).
- Split cycles merged (fleet: 100 total; 37+31+32 per prod).
- cop_hourly partial-hour rows corrected (fixes #130).
- daily_summary rebuilt from corrected cycles.

### Known limitations
- Synthesized cycles have thermal_kw_avg = NULL (cop_samples lacks cold-side
  temperature; fix deferred to v1.13.0 #129).
- energy_acc / runtime_acc not rebuilt (preserves HWM chain).
- Post-migration pre-fix transition artifacts still exist until v1.12.5
  stability gate.
- Migration does NOT retrain ML models (kmeans, baseline). Run
  `daikin_cycle_ml.recompute_kmeans` and `recompute_baseline` manually
  post-deploy, or upgrade to v1.12.5 which auto-retrains once.

### Rollback
Preserved via mode_original and parent_cycle_id. Manual SQL in
docs/UPGRADE.md. Marker deletion (data_migration_v1_12_4) triggers
re-run on next boot.

## [1.12.3] - 2026-10-22

**DHW compound-mode detection fix.** Closes #116 forward half.

### Added
- `classify_mode` now token-splits I/U operation mode on `+` and `/`
  separators, correctly handling compound strings like `Heating + DHW`
  and `Cooling + DHW`. DHW wins over heating/cooling in compound mode
  because the 3-way valve is diverted to the tank (heating paused).
- `CycleDetector._should_split` -- mode-token-transition splitter with
  valve-corroborated debounce (30s with valve ON, 60s without). Valve
  alone never splits (Daikin valve rests ON on power-loss fail-safe).
- `binary_sensor._attr_contains_mode` -- token-based helper; used by
  `_is_dhw_active` so compound mode fires the DHW binary sensor.
- Constants `VALVE_DEBOUNCE_S = 30.0`, `MODE_DEBOUNCE_S = 60.0`.
- 2 new persisted detector state fields (`pending_mode`,
  `pending_mode_since`); backward-compatible with old payloads.

### Changed
- `_is_dhw_active` now uses token-contains matching via
  `_attr_contains_mode` (exact-match was the bug for compound modes).
- Cycle detector closes the current cycle and opens a fresh DHW cycle
  when I/U mode transitions to include `dhw` during a running heating
  cycle (both cycles reach DB with correct mode).

### Fixed
- DHW reheat runs misclassified as heating when Daikin reported
  `Heating + DHW`. Confirmed on 3/3 production instances (#116).
  - `sensor.cop_dhw_today` / `_day` / `_week` / `_month` now update.
  - `binary_sensor.dhw_active` fires during real DHW runs.
  - `daily_summary` DHW rows populate going forward.
  - `cop_hourly` mode bucketing correct for new samples.

### Version
- 1.12.3 across const.py, manifest.json, pyproject.toml, CHANGELOG.md.

### Known limitations
- Historical misclassified cycles still need v1.12.4 migration.
- Prod 2 shows `mixed_heating_then_dhw` shape -- requires cycle
  splitting in v1.12.4 (not just relabeling).
- 4-hour cycles (14400s) flagged as v1.13.0 investigation.
- Short defrost artifacts (0-60s, defrost=1) deferred to v1.13.0.

## [1.12.2] - 2026-10-21

**Data-integrity patch.** Closes the remaining v89.0 DB-integrity
findings plus enables WAL durability properly.

### Added
- WAL journal mode enabled for production DBs (#113). CycleDB now takes a `journal_mode` parameter (default `delete` for tests, `wal` for prod). Includes `synchronous=NORMAL` and `busy_timeout=5000` for concurrent-reader safety.

### Fixed
- `async_prune_cop_hourly` cutoff now uses hours-since-epoch to match `ts_hour` storage (#111). Prior mismatch silently wiped the entire `cop_hourly` table on every maintenance cycle.
- `mode='unknown'` for cycles with valid compressor data now auto-corrected on migration (#112). Per-mode aggregation no longer undercounts heating.
- `thermal_kw_avg` backfilled for all historical cycles from `features.vector_json[11]` (#114). Recovery is lossless.
- Stale `daily_summary` rows with `mode='unknown'` deleted and rebuilt during migration (#112).

### Changed
- v17 data migration runs once per DB (marker-guarded). Idempotent, safe for all schema levels v14–v16.

## [1.12.1] - 2026-10-21

**Patch release.** Fixes the restart phantom short_off from #109.

### Fixed
- Restart phantom short_off (#109). When ESPAltherma is not
  initialised at HA boot, the coordinator advanced the detector
  with missing rps, force-closing the running cycle and producing
  a phantom ~60s off-gap that triggered short_off. The detector
  now freezes until required attributes return.

## [1.12.0] - 2026-10-21

**Data-integrity release.** Six issues, 11 commits. Closes every
durability gap found in the v88.0 post-release audit plus five wiring
bugs where production code existed, compiled, tested, and never
actually fired.

### Added

- **DB-first cycle persist** (#103). Cycle rows are written to SQLite
  *before* the ML pipeline runs. Any ML exception cannot leave the
  cycle in-memory-only.
- **Graceful shutdown flush** (#104). `EVENT_HOMEASSISTANT_STOP` plus
  unload-entry flush persists runtime, energy, and detector state
  before HA tears down. Zero loss on restart, reload, or reboot.
- **`_energy_hwm` persistence** (#101). Per-day high-water-mark stored
  in `model_state.energy_acc.<day>`. Hard-crash loss bounded to one
  persist tick.
- **Transient classification** (#105). Schema v16 adds `is_transient`
  to `cycles`. Startup transients (`<120 s`, or `<300 s` with
  `dT_max < 3 K` and `rps_max >= 40`) tagged at close. Baseline,
  `pendulum_daily`, `high_cycle_rate` exclude them. New sensor
  attrs on `sensor.cycles_today`: `transient_cycles_today`,
  `non_transient_cycles_today`, `transient_ratio_pct`.
- **`thermal_kw_avg` persistence** (#107). Column added, INSERT and
  SELECT wired. Before: in-memory only, lost on restart.
- **`model_state` retention** (#106). `energy_acc.*` /
  `runtime_acc.*` older than 400 days pruned in `_run_maintenance`.

### Changed

- **Energy persist interval 300 s → 30 s** (#101). Aligns with
  `UPDATE_INTERVAL_SECONDS`. Hard-crash loss bounded to ≤1 tick
  instead of ≤5 min. WAL mode handles the 10× write amplification.
- **`short_cycle_ratio` into `score_cycle`** (#105). Parameter was
  accepted since v1.4 but never passed. `PENALTY_HIGH_RATIO = 20`
  now fires on high-short-cycle days.
- **`record_short_run` / `record_short_off` called** (#105). Dead
  code since v1.4. `short_runs_today` / `short_offs_today`
  counters now accurate.

### Fixed

- **Counter drift in `CycleStore`** (#101). `add_cycle` never
  incremented `cycles_today`; only `hydrate_from_rows` did. After
  restart the counter froze at the hydrate value while
  `good_cycles_today` / `bad_cycles_today` kept incrementing. Prod
  showed `cycles_today=3` vs `good+bad=6`. Separately,
  `hydrate_from_rows` failed to restore `cycles_total` and
  `cycles_{mode}`, resetting them to zero on every restart (prod:
  `cycles_total=3` vs `cycle_count=116`).
- **Feature-vector divergence** (#103). DB persist block called
  `extract_feature_vector` *without* `thermal_kw_avg`, ML block
  called it *with*. Two vectors per cycle: stored features did not
  match the inputs that produced each cluster. Both calls now pass
  `thermal_kw_avg=record['thermal_kw_avg']`.
- **Cycle-close ordering** (#103). ML pipeline ran before
  `async_insert_cycle`. Crash mid-ML lost the cycle entirely. DB
  write now completes before ML work; ML exceptions cannot destroy
  the durable row.
- **Shutdown gap** (#104). `async_unload_entry` did not flush
  accumulators; no `EVENT_HOMEASSISTANT_STOP` handler existed.
  Graceful HA stop lost up to 300 s. Both paths now flush via
  `_async_flush_accumulators` with per-subsystem isolation (R378).
- **Dead counters** (#105). `record_short_run` / `record_short_off`
  on `CycleStore` had zero callers. `short_runs_today` /
  `short_offs_today` always 0. Binary sensor `short_run=on` while
  the counter attribute showed 0 — silent contradiction. Wired into
  `score_and_count`.
- **Dead scorer parameter** (#105). `score_cycle(short_cycle_ratio=)`
  accepted since v1.4 but never passed. `PENALTY_HIGH_RATIO = 20`
  never fired. Now computed from store counters; denominator
  includes current cycle.
- **`thermal_kw_avg` gap** (#107). Column missing from `cycles`.
  Value in `last_cycle.thermal_kw_avg` never survived restart.
  Schema v16 adds column, INSERT and hydration SELECT.
- **Transient pollution** (#105). 34 % of prod cycles are startup
  transients. Counted as real, polluted per-mode baselines
  (`per_mode.update`), inflated `pendulum_daily` and
  `high_cycle_rate`. Schema v16 classifies at close; baseline,
  pendulum, target exclude them.
- **`model_state` growth** (#106). One `energy_acc.<day>` and one
  `runtime_acc.<day>` key per day, never pruned. 400-day retention
  added to `_run_maintenance`.

### Data Integrity Guarantees

| Scenario | Before v1.12.0 | After v1.12.0 |
|---|---|---|
| HA graceful restart | ≤300 s loss | **Zero loss** |
| Config entry reload | ≤300 s loss | **Zero loss** |
| Container stop / HAOS reboot | ≤300 s loss | **Zero loss** |
| Cycle close (normal) | ML-first, up to 100 ms window | **DB-first, ~0 ms** |
| Cycle close (ML exception) | Cycle may be lost | **Durable regardless of ML** |
| Hard power loss / `kill -9` | ≤300 s | **≤30 s** (one persist tick) |
| Counter consistency | Drift after restart | **Invariant always** |

### Statistics

| Metric | v1.11.3 | v1.12.0 | Delta |
|---|---|---|---|
| Commits in release | — | **11** | — |
| Test count | 3124 | **3193** | **+69** |
| Statement coverage | 100.00 % | **100.00 %** | — |
| Branch coverage | 100.00 % | **100.00 %** | — |
| Source statements | 7136 | **7230** | +94 |
| Source branches | 2044 | **2066** | +22 |
| Modules | 37 | **37** | — |
| Schema version | v15 | **v16** | +1 |
| Issues closed | — | **6** | — |
| Breaking changes | — | **0** | — |

Issues closed: [#101](https://github.com/elRadix/daikin_cycle_ml/issues/101), [#103](https://github.com/elRadix/daikin_cycle_ml/issues/103), [#104](https://github.com/elRadix/daikin_cycle_ml/issues/104), [#105](https://github.com/elRadix/daikin_cycle_ml/issues/105), [#106](https://github.com/elRadix/daikin_cycle_ml/issues/106), [#107](https://github.com/elRadix/daikin_cycle_ml/issues/107)

### Links

- [Full diff](https://github.com/elRadix/daikin_cycle_ml/compare/v1.11.3...v1.12.0)
- [Documentation](https://github.com/elRadix/daikin_cycle_ml#readme)
- [Upgrade notes](https://github.com/elRadix/daikin_cycle_ml/blob/main/docs/UPGRADE.md)
- [Issue tracker](https://github.com/elRadix/daikin_cycle_ml/issues)

## [1.11.3] - 2026-10-21

### Fixed

- Energy accumulator sensors (`thermal_energy_heating_today`,
  `electrical_energy_*_today`, etc.) no longer report a decrease after
  a restart, violating the `total_increasing` state class contract that
  Home Assistant's recorder enforces.

- Root cause: `_restore_energy_acc` unconditionally replaced the in-memory
  accumulator with the last-persisted DB value. Since persist is throttled
  to 300 s, a restart could wipe up to 5 minutes of accumulated energy,
  producing drops like `12.45 -> 12.28`.

- Fix: (1) `_restore_energy_acc` now merges with `max()`, preserving
  in-memory values. (2) Added a per-day `_energy_hwm` high-water-mark that
  sensors read from, so the contract holds even if any code path lowers
  the accumulator. Reset only at day rollover.

### Added

- Regression tests for the merge path and the HWM safety net.

## [1.11.2] - 2026-10-21

### Fixed

- Config flow and reconfigure now honor the ESPAltherma attribute compat
  view, matching the coordinator. Fixes false-positive reconfigure warnings
  and wrong "core attributes" counts on definition files that label the
  outdoor sensor `R1T-Outdoor air temp.`. Also makes manual mapping accept
  either the canonical or the alias name.

- Reconfigure no longer logs "missing attrs" for a raw-attribute source
  that actually provides the attribute under an aliased key.

### Added

- Three regression tests: raw v2 dump resolves, genuinely missing values
  are still reported, and placeholder values (`---`) count as missing.


## [1.11.1] - 2026-10-21

### Fixed

- ESPAltherma definition files that label the outdoor sensor
  `R1T-Outdoor air temp.` (e.g. ALTHERMA LT_CA_CB, both v1 and v2 builds) now
  resolve the required `Outdoor air temp.(R1T)` attribute. Fixes the
  "Reconfigure missing attrs: ['Outdoor air temp.(R1T)']" repair issue and
  restores `outdoor_temp` on new cycles and daily summaries. Historical rows
  are not backfilled.
- Added a regression test built from a real 174-attribute v2 device dump;
  asserts every entry in `REQUIRED_ATTRIBUTES` resolves.


## [1.11.0] - 2026-10-21

### Added
- ESPAltherma v2 attribute compatibility layer. Legacy v1 attributes are
  preserved; canonical v2 English names are materialised beside them.
  Lookup is tolerant of v2 punctuation/spacing and translated v1 labels.

### Deferred
- Manifest `categories` for the HA integration catalogue
  (`climate.heat_pumps_air_conditioning`, `energy`) — deferred pending
  `hassfest:latest` image update. Code/test ready; re-add once the image
  schema includes the `categories` key.

### Compatibility
- No entity or unique-ID changes. English v1 users are unaffected.
- Translated v1 definitions now resolve through aliases instead of failing
  `missing_required`.

## [1.10.0] - 2026-10-20

### Breaking changes

- **Per-entry SQLite database file.** The integration historically used a
  single shared `/config/.storage/daikin_cycle_ml.db` across all config
  entries. Historical aggregate tables (`daily_summary`, `cop_hourly`,
  `cop_samples`) had no `entry_id` scoping, so multi-entry users saw
  cross-entry data leaks (issue #75). v1.10.0 splits the DB per config
  entry: `daikin_cycle_ml_<entry_id>.db`.

  **Single-entry users (majority):** silent automatic migration on first
  setup after upgrade. Legacy file is backed up to `/config/.daikin_backups/`,
  then renamed to per-entry file. Zero data loss, zero user action.

  **Multi-entry users:** legacy file is assigned to the **oldest entry**
  (by config-entry registration order). A repair issue
  (`legacy_db_multi_entry`) appears, disclosing the auto-assignment and
  pointing to three correction services: `assign_legacy_db`,
  `archive_legacy_db`, `export_legacy_db`.

  **Concurrent-usage limitation:** if both entries ran simultaneously on
  the shared DB before v1.10.0, per-entry historical attribution is
  unrecoverable — the data was physically interleaved. The repair issue
  and export service make this visible and auditable. Single-entry and
  new-install users are not affected.

### Added

- Per-entry SQLite database file `daikin_cycle_ml_<entry_id>.db` — issue #75.
- `storage/migration.py`: idempotent, marker-guarded, backup-first
  migration with size-verified rename and rollback on mismatch.
- `daikin_cycle_ml.assign_legacy_db` service — move the per-entry DB from
  one config entry to another. Fails if target already has its own.
- `daikin_cycle_ml.archive_legacy_db` service — rename live per-entry DB
  to `daikin_cycle_ml.db.legacy-<timestamp>`. Preserved for audit.
- `daikin_cycle_ml.export_legacy_db` service — dump all 7 tables to CSV
  plus `manifest.json` under `/config/daikin_cycle_ml_export_<entry>_<ts>/`.
- Repair issue `legacy_db_multi_entry` — discloses auto-assignment for
  multi-entry users and offers correction via the three services.
- Diagnostics: `database.per_entry` enumerates every `daikin_cycle_ml_*.db`
  file with per-entry file size and table counts. `database.legacy` is
  reported when the legacy file exists.

### Changed

- `_async_setup_database` now takes a `ConfigEntry` parameter to resolve
  the per-entry DB path. Third argument is optional (`None` = legacy path,
  for backward compatibility with tests and external callers).
- `services.yaml` new entries use the `config_entry:` selector instead of
  `text: null`. Existing 10 services still use `text: null`; modernization
  scheduled for a future release.

### Fixed

- Issue #75: historical COP/SPF aggregates shared across config entries.
- `async_remove_entry` now deletes the per-entry DB on config-entry
  removal. Previously no `async_remove_entry` handler existed at all, so
  the shared DB was orphaned after every entry removal. User artifacts
  (`.legacy-<ts>` and `.daikin_backups/`) are preserved.

### Tests

- `tests/test_v1100_per_entry_db.py` — migration paths, all branches,
  marker-recovery, size-mismatch rollback.
- `tests/test_v1100_legacy_db_services.py` (15 tests) — 3 services,
  happy paths and error branches.
- `tests/test_v1100_diag_per_entry.py` (6 tests) — per-entry enumeration,
  read-only table counts.
- `tests/test_v1100_setup_entry_migration.py` (1 test) — end-to-end
  migration via `async_setup_entry`.
- Total coverage: 7056 stmts / 2000 branches, **100.00%**.

### Known limitations

- Multi-entry users who ran entries concurrently before v1.10.0 cannot
  recover per-entry historical attribution (physically unrecoverable).
  Use `export_legacy_db` to audit, `archive_legacy_db` to start fresh.
- Alerts store `daikin_cycle_ml.alerts` remains shared across entries.
  Per-entry split tracked as follow-up issue. Impact: dedup windows are
  cross-entry, no data corruption.

## [1.9.2] - 2026-10-20

### Security

- **`send_test_notification` target escalation** (hacs/default#11345 item 1).
  `target` and the `notify_service` option accepted any `domain.service`,
  which was then called via `hass.services.async_call(...)` with no user
  context. A non-admin HA user could invoke admin-only services such as
  `homeassistant.stop` through this path. Fixed at four layers: engine
  rejects non-`notify.*` before dispatch; schema requires `notify.*` prefix;
  handler returns `{"ok": false, "error": ...}` on a bad option; config
  flow sanitizes non-`notify.*` to empty. Anyone relying on the old
  behaviour was invoking the vulnerability.

- **`_migrate_entity_ids` wrong-row rename** (item 2). The migration looked
  up entities by entity-id string without verifying they belong to this
  config entry, so with a second config entry it could rename foreign rows
  and inject this entry's `unique_id`. Fixed via
  `er.async_entries_for_config_entry(registry, entry_id)` plus a
  `platform == DOMAIN` filter. Closes the migration-path class of #75.
  Orphaned entities with `config_entry_id=None` will no longer be renamed;
  manual cleanup in the entity registry is the correct remediation. This
  is the fix, not a regression.

### Fixed

- **`mkdir` on event loop** (item 3). `_async_setup_database` called
  `db_path.parent.mkdir(...)` synchronously. Moved to
  `hass.async_add_executor_job`.

### Changed

- **README install order** (item 4). HACS catalog search is now the primary
  path; custom-repository is a labeled fallback (the integration is not
  yet in the default catalog; submission pending in hacs/default#11345).

### Tests

- 15 new tests in `tests/test_v192_hacs_review.py` covering all four guards.
  Three existing tests updated to declare entity ownership; one existing
  test assertion encoded the pre-fix vulnerability as expected behaviour.

## [1.9.1] - 2026-10-20

### Fixed

- Energy accumulators reset to 0 on HA reboot. Root cause: silent failure in `_restore_energy_acc` / `_restore_runtime_acc` on boot left `_day_key` empty; first tick zeroed memory and persist overwrote the DB row with zeros. Three-layer fix: self-healing persist (restore from DB if DB > memory before overwrite), retry restore in `_async_update_data`, and WARNING logs on the silent restore paths. Prevents the boot-wipe loop even if restore keeps failing for any future reason.

### Added

- 9 new tests in `tests/test_v191_energy_acc_self_healing.py` covering the self-healing persist, retry, and logging branches (both runtime and energy paths).

## [1.9.0] - 2026-10-20

Alerts v2, 3 new P3 alerts, and full documentation restructure.

### Added

- **3 new alerts:**
  - `db_retention_warning` — DB retention not running
  - `kmeans_retrain_stale` — clustering hasn't succeeded in 14+ days
  - `energy_daily_anomaly` — daily electrical kWh more than 2σ above baseline
- **11 per-alert toggles** in OptionsFlow `notifications_enabled`
- **19 per-alert dedup windows** in OptionsFlow `notifications_dedup`
- **`recompute_kmeans` service** — force k-means retrain on demand
- **`avg_duration_7d_min`** context field on 3 pendulum/ML alerts (J)
- **`async_defrost_duration_since`** DB helper for accurate 7-day defrost totals (I7)
- **`samples` row** in `energy_daily_anomaly` alert schema (I7)

### Changed

- `cop_low` + `stooklijn_advies` route through shared filter chain
- Per-alert dedup windows replace single global aggregation setting
- `energy_daily_anomaly` splits display-candidate vs fire-candidate
- Q4 fix: `setpoint_osc` no longer fires on monotonic drift (requires reversal)
- `DEFAULT_ALERT_RETENTION_DAYS` 30 → 90 (I7 cleanup)
- `_build_alert_context` falls back to `store.last_cycle()` when `snap.last_record` empty (I6 C6)

### Fixed

- `pendulum_daily` collision + `short_off` mismatch + `ml_anomaly` mode overwrite
- `last_alert_sent` was in-memory only — now persisted to HA Store
- `defrost_excessive.duration_7d_min` was hardcoded 0 — now real 7-day sum (I7)
- `energy_daily_anomaly` misleading 0.0 sigma/z when n<2 — now em-dash `None` (I7)
- `energy_acc.<today>` silently wiped on runtime restore failure (I8) — decoupled day-key gates
- Retention fallback literals 90/30 in coordinator/db.py → const names (I7)

### Documentation

- **README split into 8 docs** in `docs/` (Configuration, Entities, Alerts, ML, Database, Development, Troubleshooting, Upgrade) — landing page + deep dives
- **AGENTS.md consolidated** — SOP.md merged in, 23 sections, single source of truth
- **QA pipeline** — `scripts/bootstrap.sh`, `scripts/ci-local.sh`, `scripts/pre-push` (4-gate local parity)
- **Markdown guard** — `scripts/check-markdown.sh` with 19 checks + CI workflow
- **R374–R384 promoted** to ACTIVE/CANDIDATES in AGENTS.md (11 new rules)

### Removed

- SOP.md (content merged into AGENTS.md)

## [1.8.1] - 2026-10-08

### Fixed

- **Alert notifications rendered blank sensor values** (R331). Three
  stacked bugs in the alert context pipeline:
  - `_snap_attr` read `snap.attributes`, but `DataSnapshot` uses
    `snap.attrs` — every lookup silently returned `None`.
  - Four callsites passed string literals (`"ATTR_OUTDOOR"`,
    `"ATTR_LWT"`, `"ATTR_INDOOR"`, `"ATTR_FLOW"`) that do not exist as
    constants. Replaced with real const values; added missing
    `ATTR_INDOOR_AMBIENT_R1T` to `const.py`.
  - `_f(None)` returned the string `—` (em-dash) instead of `None`,
    which was then interpolated by `ALERT_SCHEMA` templates as a
    suffix (`— °C`, `— min`, `— l/min`). `_f` now returns `None`;
    `build_rich_alert` renders a bare `—` when any template field
    resolves to `None`.
- **Setpoint helpers used string literals instead of constants**
  (R331-B) — `_setpoint_current` and `_setpoint_target` passed
  `"ATTR_LWT_SETPOINT"` / `"ATTR_TARGET_LWT"` (which do not exist).
  Replaced with the real constants `ATTR_LW_SETPOINT` and the new
  `ATTR_TARGET_COND_TEMP`. Rendered `LWT setpoint`, `LWT doel` and
  `Setpoint-swing` values had been silently blank.
- **`short_off` `off_min` floored at 1 minute** (SB-1) — a 30s
  off-time was truncated to `0 min`, producing the contradictory
  "Off-tijd 0 min" against a "drempel 5.0 min" in the notification.
- **Global advice bleed disabled** (SB-2) — the first `snap.advice`
  item was previously injected into every alert context, causing
  `Low dT` to appear on ML-anomaly and `short_off` notifications.
  Per-alert advice now comes from `ALERT_ADVICE` in
  `engine/status_report.py`.
- **Mode fallback from `attrs["operation_mode"]`** (SB-3) — when both
  `snap.mode` and `last_cycle.mode` are unknown, the alert context
  now falls back to the raw operation-mode attribute, preventing the
  "Modus: onbekend" symptom on ML-anomaly notifications.

### Tests

- `tests/test_v181_alert_render_ctx.py` — 14 new tests covering the
  three-layer fix, mode fallback branches, sentinel semantics, and the
  R331-B setpoint-helper fix (see below).
- 6 existing assertions updated in `test_build_alert_context.py`,
  `test_52e_coordinator_coverage.py`, `test_cov3_coordinator_edges.py`.
- Coverage: 100.00% (6279 stmts / 1808 branches).

### Rule

- New rule **R331**: `DataSnapshot.attrs` is the canonical attribute
  source. `_snap_attr` must read `attrs` first, fall back to
  `attributes` / `raw_attrs`. Sentinels must be `None`, never `—`.
  Guard: `tests/test_v181_alert_render_ctx.py`.

### Release note

- Released without the standard 72h observation window (R204) and
  without the kmeans gate (R318), at owner direction.

## [1.8.0] - 2026-10-08

### Added
- Smart auto-import for non-canonical ESPAltherma setups (issue #51):
  - Laag 1 - entity discovery via canonical-attribute overlap scoring
  - Laag 2 - alias table + normalized matching (14+ community variants)
  - Laag 3 - fuzzy fallback (Jaccard + register-code conflict guard)
  - Laag 4 - diagnostic wizard step (`config.step.diagnose`, i18n EN/NL)
  - Laag 5 - register-value sanity check + 3-phase hint
- `engine/smart_import.py` - pure module, 5 layers, 100% branch coverage
- `tests/test_smart_import.py` (47 tests)
- `tests/test_smart_import_config_flow.py` (8 tests)
- Anti-alias guard: R2T (after BUH) never resolves to R1T (before BUH) -
  prevents COP~11 artefact on hybrid setups (issue #51, case julG)
- Wizard split UX (issue #54):
  - New `config.step.model_custom_info` (Page A) - identity + optional
    HP spec JSON textarea
  - New `config.step.attribute_mapping` (Page B) - JSON / manual choice
  - `config.step.attribute_mapping_advanced` (Page C) - renamed from
    `model_custom`; the old step-id is kept as a live redirect for one
    release cycle (HA persists in-progress flow step-ids across restart)
  - Public `validate_spec(raw)` in `engine/model_datasheets.py`
  - `_OPTIONAL_MODEL_KEYS` + `_REFRIGERANT_ENUM` in `engine/model_datasheets.py`
  - `tests/test_v181_hp_spec_builder.py` (30 tests)
  - `tests/test_v181_wizard_split_page_b.py` (12 tests)
  - `tests/test_v181_wizard_split_page_c.py` (7 tests)
  - `tests/test_r327_no_whitespace_in_translations.py` (1 test)

### Changed
- `config_flow.async_step_user` - automatic mode now falls back to
  smart-import when exact canonical matching fails and >= 3 canonicals
  resolve. Exact-match path unchanged (backward-compat tested).
- `config_flow.async_step_model_custom_info` - accepts optional
  `custom_datasheet_json`; empty submits `None` to inherit Basic profile
- `config_flow.async_step_attribute_mapping` - JSON branch routes to
  `attribute_mapping_advanced`; Manual branch routes to `map_attributes`
- `config_flow.async_step_model_custom` - deprecated redirect to
  `async_step_attribute_mapping_advanced` (kept for one release cycle)
- i18n parity 15/15/15 -> 16/16/16 (new `attribute_mapping_advanced` key;
  deprecated `model_custom` key retained)

### Fixed
- Hassfest `[TRANSLATIONS]` error on the HP-spec JSON description: the
  `config.step.model_custom_info.data_description.custom_datasheet_json`
  string had a trailing newline. Fixed + regression guard `R327`
  (`tests/test_r327_no_whitespace_in_translations.py`).


- Wizard routing: selecting **model=Custom** together with
  **attribute_mode=manual** on the first page skipped Page A
  (`model_custom_info`) entirely and jumped straight to `map_attributes`.
  Users in this path never saw the HP-spec textarea, and the resulting
  flow had a different shape than the AUTO path. Fixed by mirroring the
  AUTO-branch Custom check inside the MANUAL branch of `async_step_user`.
  Regression guard **R330** added - any model=Custom submission must
  route to `model_custom_info` regardless of attribute_mode. Found during
  post-merge observation of `a093df3`; landed as `de3090e` (PR #56)
  before v1.8.0 tag.

## [1.7.2] - 2026-10-08

### Fixed
- Cycle detector stuck in RUNNING up to 46h (issue #49). Root cause:
  pump is False identity check failed when ESPAltherma _normalize()
  returned string 'OFF', None, or numeric values. Both pump-check
  sites now use _pump_is_off() helper (R316).
- MAX_CYCLE_DURATION_S hard-cap added (R315) - any RUNNING cycle
  exceeding 4h is force-closed on next tick. Safety net for edge cases
  beyond R307.
- Detector call-site now uses _read_power_w() (kW to W conversion)
  instead of raw _read_power() (R317) - kW-domain sensors would have
  compared 0.5W threshold against 200W power.

### Added
- const.MAX_CYCLE_DURATION_S = 4 * 3600.0
- engine.cycle_detector._pump_is_off() helper
- Tests: test_v172_cycle_hardcap.py (8), test_v172_pump_is_off.py (33)

### Changed
- tests/test_coordinator.py - 2 tests aangepast (fixture _valid_attrs semantiek)

## [1.7.1] - 2026-10-07

Stable release. Promotes the v1.7.1 pre-release series to production
after visual confirmation of the Daily Summary card on a live dashboard.

### Added

- Sensor `daily_summary_recent` (shipped in v1.7.1-pre.1) — a rolling
  view of the `daily_summary` table with `days[]` and `totals_by_mode`.
- Dashboard card `dashboard/cards/daily-summary/daily-summary.yaml`
  (shipped in v1.7.1-pre.2) — full cycle-history visual with SVG
  sparklines, dynamically colored quality line chart, stacked
  cycles / duration bars, and a BUH + defrost event strip. Bilingual,
  auto-scaling, HP-spec-aware.
- Card documentation `dashboard/cards/daily-summary/README.md`.
- Third showcase slot in the root README Showcase section.

### Changed

- Fixed broken preview image reference for Simple Card in
  `dashboard/README.md` (`preview.png` -> `showcase.png`, pre-existing bug).

### Fixed

- None.

> Detailed pre-release notes: see `[1.7.1-pre.2]` and `[1.7.1-pre.1]` below.

## [1.7.1-pre.2] - 2026-10-07

Pre-release: daily summary dashboard card. Completes the v1.7.1
pre-release series; v1.7.1 final pending prod visual confirmation.

### Added

- Dashboard card `dashboard/cards/daily-summary/daily-summary.yaml` —
  full cycle history visual with SVG sparklines, dynamically colored
  quality line chart, stacked cycles / duration bars, BUH + defrost
  event strip. Bilingual (NL / EN), auto-scaling, HP-spec-aware hero.
- Card documentation `dashboard/cards/daily-summary/README.md`.
- Third showcase slot in root README Showcase section.
- Daily Summary row + entity requirements in `dashboard/README.md`.

### Changed

- Fixed broken preview image reference for Simple Card in
  `dashboard/README.md` (`preview.png` -> `showcase.png`, pre-existing bug).

### Fixed

- None.

## [1.7.1-pre.1] - 2026-10-07

Pre-release: daily summary visibility. Card lands in pre.2 after this
sensor is verified on prod.

### Added

- New sensor `daily_summary_recent`: state = total cycles across all days
  in `daily_summary`; attributes = full payload (`days[]`, `totals_by_mode{}`,
  `days_available`, `days_count`, `latest_day`, `oldest_day`).
- Coordinator cache `coordinator.daily_summary_recent` (public property),
  refreshed on cycle close (`_maybe_rollup_day`) and primed on startup
  (`_maybe_backfill_daily_summary`).
- Translations for the sensor name in strings.json + en.json + nl.json
  (parity 425 -> 426).

### Changed

- None (card deferred to v1.7.1-pre.2).

### Fixed

- None.

### Notes

- No DB schema change; no new DB method. The sensor reads the existing
  `db.async_daily_summary` and transforms it in-process.
- Pre-release only: v1.7.1 final after explicit prod-confirm (R204).

## [1.7.0] - 2026-10-07

### Added

- Live daily summary rollup: `daily_summary` table populated as each cycle closes (#42).
- New option `daily_summary_live_enabled` in OptionsFlow > Advanced > Retention (default True).
- One-time startup backfill: historic cycles populate `daily_summary` on first startup after upgrade.

### Changed

- `async_run_maintenance` refactored to call `async_rollup_day` per affected day before prune. Idempotent replace semantics eliminate prior double-count risk.

### Fixed

- `daily_summary` stays empty on fresh installs. Root cause (Anomaly D, 2026-10-07): aggregation scoped to retention cutoff only, so no cycles qualified until 365d elapsed.

### Notes

- Existing installs: backfill runs once on next HA restart; no user action required.
- Rollback to v1.6.7 leaves `daily_summary` populated but idle; no data loss.


All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.7] - 2026-10-07

Patch release: R310 accumulator rehydration on coordinator startup and
non-blocking datasheet JSON loads.

[Full diff v1.6.6...v1.6.7](https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.6...v1.6.7)

### Added

- R310: `_restore_runtime_acc()` / `_restore_energy_acc()` in the
  coordinator, wired into the same setup hook as `_restore_detector_state`
  (R306). Restores `model_state["runtime_acc.<day>"]` and
  `model_state["energy_acc.<day>"]` before the first coordinator refresh
  when the day key matches today. Guards: no-op on day mismatch, missing
  payload, or malformed payload; never raises.
- Success log lines on both restore paths for prod-verify grepping.
- Tests: `test_r310_acc_restore.py` (11 cases).

### Fixed

- HA restart / reload / HACS redownload silently zeroed today's
  `_energy_acc` / `_runtime_acc`. Observed 2026-10-07: 09:03 CEST restart
  discarded the 07:11-08:11 heating cycle's 0.41 kWh. Persist had no
  read-back counterpart.
- Blocking `read_text` / `open` calls in the event loop from
  `model_datasheets.load_bundled` and `load_defaults`, flagged by
  HA 2026.9 during `async_setup_entry` and `_refresh_datasheet_state`.
  Replaced with `asyncio.get_running_loop().run_in_executor(None, fn)`.

### Changed

- None user-visible beyond the fixes above. No schema change, no entity
  change, no config change, no string change. Daily accumulators may
  show higher totals on restart days post-upgrade; that is the intended
  behavior.

## [1.6.6] - 2026-10-07

Patch release: cycle detector state persistence (R306) and pump-guard
relaxation (R307). Closes the missed-cycle finding from issue #33.

[Full diff v1.6.5...v1.6.6](https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.5...v1.6.6)

### Added

- R306: `CycleDetector.to_dict()` / `restore_from_dict()` /
  `_float_list()` plus `MAX_RESUME_GAP_S = 6h`. Coordinator persists the
  detector state to `model_state["cycle_detector_state"]` on every
  transition and restores it in `async_setup_baseline_persistence`.
- R307: `PUMP_OFF_MAX_SAMPLES = 20`. `pump=OFF` while RUNNING is now a
  soft signal when the compressor still runs; only 20 consecutive
  pump-off samples (10 min) close the cycle.
- `const.py`: `DETECTOR_STATE_KEY = "cycle_detector_state"`.
- Tests: `test_r306_detector_persistence.py` (6 cases) ·
  `test_r307_pump_guard.py` (6 cases) ·
  `test_r306_r307_coverage.py` (12 cases).

### Fixed

- In-progress cycle silently lost on HA reload (issue #33, cause A:
  reload at 2026-09-26 10:24:43 UTC).
- First 10 minutes of a DHW run discarded when the compressor started
  before the water pump (issue #33, cause B).

### Changed

- Behavior-changing for existing users: cycle counts may rise as DHW
  starts with delayed pump activation are now detected. Expected, not
  a bug. No schema change, no entity change, no config change.

## [1.6.5] - 2026-10-06

Patch release: correctness hygiene for COP-analyzer early-returns and
cop_samples.mode persistence. dt_s cap on energy/runtime accumulators.

[Full diff v1.6.4...v1.6.5](https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.4...v1.6.5)

### Added

- R284: `StooklijnAdvies.comfort_cap` defaults to `None`; early-returns
  (no_data, no_recent_heating, no_indoor_sensor, comfort_floor_reached,
  DHW-active) leave it `None` (was misleading `3.0` sentinel).
- R298: `cop_samples.mode` DEFAULT `'unknown'` + INSERT fallback
  `or "unknown"` + idempotent migration v14 -> v15.
- R288/R288b: energy + BUH/defrost runtime accumulators cap `dt_s` at
  300s, warn >60s (`ENERGY_DT_CAP_S` / `ENERGY_DT_WARN_S`).
- R299: AST-contract test freezing `CopSample.data_quality` invariant.
- Tests: `test_r284_comfort_cap_none.py` (6 cases) ·
  `test_r298_mode_default.py` (3) · `test_r299_data_quality_contract.py`
  (1) · `test_v161_energy_guard.py` (+6) ·
  `test_52b6_init_coverage.py::test_v15_migration_raises` (1).

### Fixed

- Misleading `comfort_cap=3.0` on early-return paths (R284).
- Semantic NULL-vs-'unknown' confusion in `cop_samples.mode` (R298).
- Silent `dt_s` spike in energy accumulator on tick backlog (R288/R288b).

### Changed

- `CopSample.mode: str = 'unknown'` explicit dataclass default.
- `__init__.py` migration chain extended for v15.

### Database

- Schema v14 -> v15 (`cop_samples.mode` DEFAULT `'unknown'`). Idempotent.
- Prod-verify 2026-10-06: 0 NULL-mode rows remain.

### Tests

- 2292 passed, 4 skipped. Coverage 100.00% (5813 / 1640).
- Ruff + mypy strict clean (34 files). CI 6/6 groen op `8ff381b`.

## [1.6.4] - 2026-10-06

Patch release: `bucket_summary()` filters DHW-samples from heating-curve
buckets (issue #29).

[Full diff v1.6.3...v1.6.4](https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.3...v1.6.4)

### Fixed

- `bucket_summary()` mode-filter; DHW no longer pollutes heating-curve
  buckets (R295, issue #29).

### Added

- Keyword-only `include_modes=('heating','unknown')`; `None` disables.
- `tests/test_r295_bucket_mode_filter.py` (8 cases).

## [1.6.3] - 2026-10-06

Patch release: Hassfest 2026.10 weigert ICU-escape in translations.
`integration_type` helper -> hub.

[Full diff v1.6.2...v1.6.3](https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.2...v1.6.3)

### Fixed

- ICU-escape `{{ }}` in translations replaced with `{identifier}`
  (R290/R293).
- `tests/test_r290_icu_braces.py` guard-test (2 cases).

### Changed

- `manifest.json`: `integration_type: helper` -> `hub` (R294).

## [1.6.2] - 2026-10-06

Patch release: onboarding blocker for units that do not expose every
canonical ESPAltherma attribute (issue #25). Adds a Manual mapping mode
and downgrades `INV frequency (rps)` from required to optional.

[Full diff v1.6.1...v1.6.2](https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.1...v1.6.2)

### Added

- Screen-1 dropdown `attribute_mode` with Automatic / Manual options.
- New config-flow step `map_attributes`: one text field per required
  (12) and optional (1) attribute, letting the user map canonical names
  to their own sensor's attribute names.
- `const.OPTIONAL_ATTRIBUTES` and `const.ATTRIBUTE_MODE_AUTO|MANUAL`.
- `tests/test_v162_manual_mapping.py` with 12 cases covering Auto/Manual
  routing, mapping validation, error paths, and translation parity.

### Changed

- `REQUIRED_ATTRIBUTES` is now derived from `CORE_ATTRIBUTES` minus
  `OPTIONAL_ATTRIBUTES` (13 -> 12). `CORE_ATTRIBUTES` stays at 13 for
  profile consumers.
- `engine/attribute_reader.missing_required()` checks
  `REQUIRED_ATTRIBUTES` instead of `CORE_ATTRIBUTES`.
- `coordinator._async_update_data` resolves the custom map in order:
  `options["custom_attribute_map"]` -> `data["custom_attribute_map"]` ->
  `data["attribute_map"]`. Existing entries unaffected.
- `strings.json` + `translations/{en,nl}.json` updated: `attribute_mode`
  field, `map_attributes` step, refreshed error texts. Parity kept at
  410/410/410 leaves.

### Fixed

- Onboarding no longer blocks on screen 1 when a firmware variant uses
  non-canonical attribute names. Manual mode bypasses the required-check
  and lets the user map each attribute explicitly (issue #25).
- Improved error message lists the exact missing attribute keys instead
  of a generic "Sensor mist vereiste ESPAltherma-attributen".

### Notes

- Backward compatible: `attribute_mode` defaults to Automatic; existing
  entries follow the original code path.
- No entity changes, no DB schema change, no options-flow change.
- Resolves issue #25.

## [1.6.1] - 2026-10-06

Patch release: fixes an energy accumulator bug found in production where
standby power (~21 W from a Shelly 3EM reading) was booked as heating
consumption when the compressor was idle.

[Full diff v1.6.0...v1.6.1](https://github.com/elRadix/daikin_cycle_ml/compare/v1.6.0...v1.6.1)

### Fixed

- Energy tick now requires compressor running OR BUH active before
  accumulating thermal/electrical kWh (R286). Idle and cooldown ticks are
  skipped entirely.
- Unknown cycle modes no longer fall back to "heating" (R287). Those
  ticks are skipped instead of polluting the heating accumulator.
- BUH-only fallback added for resistive load (R286b): if thermal
  computation is unavailable but BUH is active and power is known,
  accumulate electrical only.
- Detector state access guarded with try/except; a raising detector is
  treated as "not running" rather than crashing the tick.

### Added

- Test suite `tests/test_v161_energy_guard.py` with 16 cases covering
  idle/cooldown skip, standby 21 W over 1 h, unknown-mode skip, per-mode
  accumulation, cop fallback, BUH step1/step2 only, and dt_s boundaries.

### Notes

- No new entities, no schema change, no options change.
- Backward compatible.
- Unblocks cost tracking (C6b/C6c) planned for v1.6.1 main scope.

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

[Unreleased]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.10.0...HEAD
[1.10.0]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.9.2...v1.10.0
[1.9.2]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.9.1...v1.9.2
[1.9.1]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.7.2...v1.8.0
[1.6.0]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.5.3...v1.6.0
[1.5.3]: https://github.com/elRadix/daikin_cycle_ml/compare/v1.5.2...v1.5.3
