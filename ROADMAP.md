# Roadmap — Daikin Cycle ML

**Current version:** 1.2.1 (released 2026-09-28)
**Last updated:** 2026-09-28
**Maintainer:** elRadix

This file tracks what shipped, what is being built, and what is
deliberately deferred. It is *not* a changelog (see `CHANGELOG.md`)
and *not* a task list (see the active handoff).

---

## 1. Where we are

| Dimension | Status |
|---|---|
| Detection + classification | ✅ 8 pendulum patterns, RPS + power fallback, water-pump guard |
| Quality score | ✅ 0–100, 5 penalties |
| Local ML | ✅ 12-dim vector, MultiBaseline (per-mode EWMA), AdaptiveThresholds, k-means (k=4) |
| COP analysis | ✅ DHW-aware, 48 h recency window, stooklijn advice |
| Entities | ✅ 10 sensors + 15 binary sensors |
| Services | ✅ 6 |
| Repairs | ✅ 5 |
| HA compliance | ✅ ConfigFlowResult, OptionsFlowWithReload, IQS Bronze+Silver+Gold |
| HACS layout | ✅ `custom_components/<domain>/`, PR #11345 open for default store |
| Coverage | ✅ 100.00 % branch (4092 stmts / 1166 branches, 0 miss) |
| Tests | ✅ 1615 passed, 4 skipped |
| Tooling | ✅ ruff, pylint 10.00/10, mypy `--strict` 0 errors, Hypothesis |
| Live features | ✅ FEAT-1 `configured_*` attrs, FEAT-2 `thermal_power_live` |

**Next milestone:** Phase A of the state-space binning programme
(see §3).

---

## 2. Version timeline

Condensed. Full notes in `CHANGELOG.md`.

| Version | Date | Summary |
|---|---|---|
| v0.2.0 | 2026-09-25 | Cycle detection, 8-step wizard, quality score, base ML |
| v0.3.0 | 2026-09-25 | Adaptive thresholds (12a), cluster assignment (12b), diagnostics v2 (12c) |
| v0.4.0 | 2026-09-25 | COP analysis (14a), `cop_samples` table, stooklijn advice, 2 sensors |
| v0.5.0 | 2026-09-26 | ML 8 → 11 dims, i18n basis, menu OptionsFlow |
| v0.6.0 | 2026-09-26 | `setpoint_osc`, EN/NL i18n, alert groups |
| v0.7.0 | 2026-09-26 | Core attrs, water-pump guard, `VECTOR_LEN = 12` |
| v0.8.0 | 2026-09-26 | `OptionsFlowWithReload`, HA compliance, test-notify dropdown |
| v0.9.0 | 2026-09-26 | Rich alerts EN/NL, all-alerts test, import smoke, ruff |
| v1.0.0 | 2026-09-26 | HA compliance release, IQS Bronze + Silver |
| v1.0.1 | 2026-09-27 | DHW gating, stooklijn mode, `AlertSpec` context, IQS Gold |
| v1.0.2 | 2026-09-27 | mypy `--strict` 219 → 0, `py.typed`, CI Mypy |
| v1.1.0 | 2026-09-27 | HACS-compliant layout (**breaking** — integration moved to `custom_components/`) |
| v1.1.1 | 2026-09-28 | Docs-only: `dashboard/` folder + showcase + HANDOFF_SOP |
| v1.2.0 | 2026-09-28 | FEAT-1 + FEAT-2 + COV-0/1/2 + mypy fixes. ⚠️ Tagged with stale version strings. Marked pre-release after the fact |
| **v1.2.1** | **2026-09-28** | **Fix version strings to 1.2.1** (commit `2b9063e`) |

---

## 3. Phase A/B/C — State-space binning

**Goal.** Replace the statistical ML baseline with per-(outdoor-temp ×
mode) bins that collect cycle statistics directly. The current EWMA /
Welford stack blurs modes and short cycles; bins make "is this cycle
normal for these conditions?" a lookup instead of a z-score.

### Phase A — Parallel signal (`v1.3.x` → `v1.4.x`)

Run bins **alongside** existing ML. No user-visible change.

- [ ] Bin key: `(mode, outdoor_temp_bucket)` — bucket width 2 °C
- [ ] Per-bin accumulators: cycle count, duration, dT, RPS, COP
- [ ] Bin Welford update on every closed cycle
- [ ] Persist bin state in `model_state['bins_state']` on the 6 h hook
- [ ] Diagnostics section: bin table with sample counts
- [ ] **Prerequisite:** resolve §4.1 (COP sampling resolution) — see below

Gate to Phase B: 30 days of stable bin data, ≥ 20 samples in the
modal bins, COP confidence ≥ medium.

### Phase B — Promote bins to primary (`v1.5.0`)

- [ ] `bin_is_anomaly(cycle, bins)` becomes the primary anomaly signal
- [ ] ML z-score demoted to advisory (kept in diagnostics, not in alerts)
- [ ] New binary sensor: `bin_out_of_range` per mode
- [ ] Migration: `model_state['baseline_state']` kept for one release as rollback safety
- [ ] Backtest: bins vs ML on the historical `cycles` table, measure false-positive / false-negative rates
- [ ] Document bin semantics in `DOCUMENTATION.md`

Gate to Phase C: bins outperform ML on backtest and on 30 days of live alerts.

### Phase C — Retire ML (`v2.0.0`)

- [ ] Remove `ml/baseline.py`, `ml/multi_baseline.py`, `ml/adaptive_thresholds.py`
- [ ] Drop `features.vector_json` storage (archive — see §4.2)
- [ ] Drop k-means (`ml/clustering.py`)
- [ ] Drop `model_state['baseline_state']` and `['kmeans_state']`
- [ ] Breaking change: document in `CHANGELOG.md` with a migration note
- [ ] Reduce `ml/features.py` to bin keys only (or remove entirely)

---

## 4. Open questions

Resolve before the phase that depends on them.

### 4.1 COP sampling resolution mismatch — **BLOCKS Phase A**

`cop_samples` fires every 10 min. Cycles are variable-length. An 8-min
cycle can produce **zero** COP samples → `avg_cop` is `NULL` in the bin
→ Welford drift → bins biased toward long healthy cycles → **false
negatives** on degradation alerts.

This is worse than missing data: it silently corrupts the baseline.

Required resolution:

1. [ ] Sample-on-cycle-close hook in coordinator (fallback, min 1 sample)
2. [ ] **30 s-tick power + flow integration as PRIMARY** (physically
       correct — this is the preferred path)
3. [ ] Store per-cycle `cop_sample_count` and `cop_sample_stdev` in `cycles`
4. [ ] Bin Welford weights contributions by `sample_count`
5. [ ] Reject a cycle's contribution to `avg_cop` if `sample_count < 2`
       (bin still accumulates duration / RPS / dT from that cycle)

If power + flow sensors are absent: fall back to (1) + (4) + (5) and
mark bin COP as `confidence: low` until density improves.

### 4.2 `features` table — archive or drop?

`features.vector_json` holds the 12-dim vector per cycle. Phase C
removes its consumer.

- [ ] Decision: **archive** (`features_archive`, compressed, 180 d
      retention) — current recommendation
- [ ] Alternative: drop entirely, rely on `cycles` columns

### 4.3 Verify `features.vector_json[9] == lwt_avg`

- [ ] Confirm dim-9 slot actually stores LWT average
- [ ] **BLOCKING** for any backtest that reads historical vectors

---

## 5. Backlog (ideas, not committed)

Grouped by theme. No target release.

### 5.1 Analytics

- Per-zone analysis (multiple indoor sensors)
- Weather-compensation advisor (uses forecast + outdoor trend)
- Cost tracking (€) — currently out of scope by design
- Export to InfluxDB / Prometheus

### 5.2 ML

- ML 12 → 14 dims (candidate: weather-forecast temp, humidity)
- Cluster-based dynamic advice tuning (adjust advice per cluster)
- Supervised ML — explicitly out of scope, listed for completeness

### 5.3 Operations

- Multi-instance support (multiple Daikin units, one HA instance)
- `async_set_unique_id` single-instance enforcement
- Mutation testing (mutmut)
- `pytest-benchmark` for tick-latency tracking
- Pre-commit hook: `ruff --no-fix`
- Fine-grained GitHub PAT (replacing the classic PAT)
- Automatic deploy pipeline: GitHub webhook → HACS → restart

### 5.4 UI / integrations

- Web UI cycle-explorer
- Extra dashboard cards (mobile variant)
- MQTT publish — **confirmed not needed** (2026-09-27)
- Brine circuits (EPRA12 is split air-water) — different hardware, out of scope

### 5.5 Empirical validation

- [ ] Verify `RPS_KW_FACTOR = 0.20` against real heating-season data
      (currently an assumption; EPRA12 air-water)
- [ ] Verify FEAT-2 cascade `power_cop` path with a real compressor-on
      cycle (runtime smoke so far only exercised `idle`)

---

## 6. Explicitly out of scope

Not planned. Listed so the boundary is visible.

- Setpoint writes (integration reads, does not control)
- Cloud ML / external inference
- Proprietary Daikin cloud API
- Supervised ML
- Cost / tariff modelling
- Web frontend beyond Lovelace cards

---

## 7. Programme-level blockers

Things that gate any phase:

- HACS default-store merge (PR #11345) — weeks to months, not blocking
  development
- Real heating-season data — required for §5.5, not blocking Phase A
  development but blocking Phase A **graduation**

---

## Appendix — deprecated version labels

Historical entries retained for traceability. Do not act on these.

- `v0.5.0-dev` — shipped as `v0.7.0` (ML 12-dim, not 11)
- `v0.4.0 (duplicate heading in old roadmap)` — same release as the
  first v0.4.0 entry