# Roadmap - Daikin Cycle ML

### Open questions (must resolve before Phase A)

- [ ] Verify `features.vector_json[9]` is actually `lwt_avg`. **BLOCKING.**
- [ ] `features` table: archive (`features_archive`, compressed, 180d) or drop?
      Current recommendation: **archive**.
- [ ] **BLOCKING — COP sampling resolution mismatch.** `cop_samples` fires
      every 10 min; cycles are variable-length. An 8-min cycle can produce
      ZERO samples → `avg_cop = NULL` in bin → Welford drift → bins biased
      toward long healthy cycles → **false negatives** on degradation alert.
      This is worse than missing data: it silently corrupts the baseline.

      Required resolution before Phase A:
      1. Sample-on-cycle-close hook in coordinator (fallback, min 1 sample)
      2. 30s-tick power+flow integration as PRIMARY (physically correct)
      3. Store per-cycle `cop_sample_count` + `cop_sample_stdev` in `cycles`
      4. Bin Welford weights contributions by `sample_count`
      5. Reject cycle contribution to `avg_cop` if `sample_count < 2`
         (bin still accumulates duration/rps/dT from that cycle)

      Without (2), Phase A COP data is unreliable. If power+flow sensors
      absent, fall back to (1)+(4)+(5) and mark bin COP as `confidence: low`
      until sample density improves.
## v0.5.0-dev (in progress, 2026-09-26)

Scope: ML feature-vector expansion (COP + LWT + indoor).
No version bump to 0.5.0 until runtime verified in production.

- [x] 14c-1 - ml/features.py 8 -> 11 dims (FEATURE_NAMES, VECTOR_LEN)
- [x] 14c-2 - coordinator wiring (accumulators + cop_avg post-hoc)
- [x] 14c-3 - DB migration + MultiBaseline/kmeans state reset
- [x] 14c-4 - version bump 0.5.0-dev + docs sync
- [ ] 14c-runtime - verify 11-dim vectors in production DB

## v0.4.0 (released 2026-09-25)

## v0.2.0 (current)

Released 2026-09-25. Highlights:

- [x] 8-step config wizard + OptionsFlow + 2-path reconfigure
- [x] Cycle detection (RPS + power fallback), 8 pendulum patterns
- [x] Quality score 0-100 per cycle
- [x] Local ML: MultiBaseline (per-mode EWMA) + k-means + anomaly engine
- [x] Baseline persistence in model_state (every 6h)
- [x] Weekly k-means (Sunday 04:00)
- [x] Daily maintenance hook (03:00): rollup + prune + VACUUM
- [x] Retention: cycles 90d, alerts 30d (configurable)
- [x] 5 services incl. recompute_baseline + run_maintenance
- [x] Notification v2: dynamic messages + emoji + status updates (opt-in)
- [x] Diagnostics extended: daily_summary, kmeans_state, baseline_state
- [x] SOP.md (install + troubleshoot + release)
- [x] Branding (Daikin icon + logo)

## v0.4.0 (released 2026-09-25)

Scope: COP analysis + stooklijn advice. No cost tracking,
no setpoint writes.

- [x] 14a - cop_analyzer module (pure parser + advice engine)
- [x] 14b-1 - cop_samples table + coordinator sample collector
- [x] 14b-2 - 2 sensors (stooklijn_advies, cop_vandaag) + attrs
- [x] 14b-3 - daily 04:00 scheduler + 2 alerts + diagnostics
- [x] 14c - ML feature-vector 8->11 dims (see v0.5.0-dev below)

## v0.3.0 (released 2026-09-25)

Scope: self-learning only. No COP, no cost tracking, no HACS, no supervised ML.

- [x] 12c - diagnostics extension + notification v2 + status updates
- [x] 12a - adaptive thresholds (self-learning percentile module)
      12a-1 module + const + tests
      12a-2 coordinator wiring + OptionsFlow + diagnostics
      12a-3 sensors (learned_short_run_min, learned_good_off_min,
            learned_target_cycles_per_day) + translations
- [x] 12b - cluster activation
      12b-1 nearest_centroid + classify_clusters + DB column + methods
      12b-2 coordinator _assign_cluster + _load_kmeans_state
      12b-3 3 binary sensors + diagnostics + translations
- [x] 12d - cleanup + coverage
      entity.py name param marked deprecated
      21 additional tests (test_12d_coverage.py), coverage ~96%
- [ ] 12e - extra model profiles (deferred to v0.4)

## v0.4+ (ideas, not committed)

- [ ] Per-zone analysis
- [ ] Weather-compensation advisor
- [ ] Export to InfluxDB / Prometheus
- [ ] Cluster-based dynamic advice tuning

