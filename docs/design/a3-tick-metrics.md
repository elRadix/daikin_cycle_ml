# A3 Design Memo — Coordinator Tick Metrics

**Status:** Decision record (retroactive — A3a+A3b merged in #361)
**Date:** 2026-11-16
**Scope:** A3a (sample-rate label), A3b (tick-duration), A3c (residual)
**Related:** Issue #353, PR #361, handoff v137.4 §3

## 1. Probleem

Prod-1 diagnostics (v1.22.7, uptime 6210s) exposed three A3 issues:

**A3a — Sample-rate label misleading.** `sampling.samples_last_24h = 198` vs `samples_expected_24h = 2880` reads as 6.9%. Real rate for 6210s uptime = 198/207 = 95.7%. Root cause: `_samples_last_24h = len(_tick_timestamps)` after 24h prune — with uptime < 24h, count == tick_count, not 24h window.

**A3b — p95=6963ms, max=25215ms, p50=124ms.** ~5% of ticks block HA Core event loop 7-25s.

**A3c — Regression unknown.** Priority P2 until v1.22.5→v1.22.6 diagnostics prove or refute regression.

## 2. Opties

### A3a — Sample-rate
- **Fix A (rename):** `_samples_since_start` + `_samples_expected_since_start` + `_sample_rate_pct` from uptime. No persistence. ~10 LOC.
- **Fix B (persist):** `tick_timestamps_v1` in `model_state`, load on restart, 24h prune. Reuses shutdown hook. ~40 LOC.

### A3b — Tick-duration
1. `asyncio.create_task(self._refresh_7d_rollups())` — fire-and-forget
2. Dedicated write queue (single worker owns all DB writes)
3. `asyncio.to_thread(self._do_db_write)` on heavy awaits
4. Batch writes every N ticks

### A3c — Regression gate
- Proceed at P2 with instrumentation, OR block release for prod-1 data.

## 3. Afweging

**Recon refuted the issue hypothesis:** `_refresh_7d_rollups` and `_refresh_daily_summary_recent` are NOT in the tick hot-path (`_async_update_data`). They are called from `_maybe_backfill_daily_summary` (startup) and `_maybe_rollup_day`.

Real unthrottled caller identified: **`_refresh_cop_today`** — 2 awaited DB queries per tick (days=1 + days=7), no cache-timestamp guard. Impact: 2×2880=5760 queries/day from one function.

- **Optie 1:** fire-and-forget — failures vanish silently.
- **Optie 2:** queue — 14 call sites to reroute.
- **Optie 3:** to_thread — surgical, no new failure mode.
- **Optie 4:** batch — doesn't help WAL-checkpoint stalls.

## 4. Aanbeveling

- **A3a:** Fix A — truthful labels, no persistence. Simpler than B; hourly-window semantics deferred to future work if needed.
- **A3b:** 60s throttle on `_refresh_cop_today`. Cuts query load 50% (2880→1440/day). `asyncio.to_thread` deferred pending v1.22.8 prod-1 metrics.
- **A3c:** P2 with instrumentation deferred to follow-up PR.

## 5. Instrumentatie-plan (deferred)

Follow-up PR adds per-section timing to `_instrument_tick` wrapper (coordinator.py:519-554). ~10 LOC.

## 6. Metric-definitie

- **p95:** over `_tick_durations_ms` (maxlen=200). Algorithm: linear-interpolation per `db._percentile` (db.py:2855), NOT index-based (current `diagnostics.py:378`). Unify in follow-up.
- **sample_rate_pct:** `len(tick_timestamps) / ceil(uptime_s / update_interval_s)`.

## 7. Test-plan

11 tests in `tests/test_v1228_a3_reproduction.py`:
- A3a repro + 3 branch arms (primed=True, expected=0, non-int last)
- A3b throttle active (5 windows × 2 queries = 10)
- A3b P4 regression guard (empty rows still set ts)
- A3b db-None early return
- Refute-hypothesis guard

## 8. Impact

- Files: `coordinator.py`, `diagnostics.py`, `tests/test_v1228_a3_reproduction.py`
- Migration: none (reuses existing `model_state` schema)
- Breakage: none for sensors (zero tick refs)
- Diagnostics p95 may shift by few ms (linear-interp)

## Residual — A3c open

25s max-tick origin needs prod-1 `iostat -x 5` + log grep. Not closable in-container. Tracked on #353.
