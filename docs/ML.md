# Machine Learning

What the integration scores, what it learns from your installation, and
how to read the results. Everything runs locally in Home Assistant.

## Contents

- [1. Overview](#1-overview)
- [2. Quality score](#2-quality-score)
- [3. Behaviour baseline and `ml_anomaly`](#3-behaviour-baseline-and-ml_anomaly)
- [4. Adaptive thresholds](#4-adaptive-thresholds)
- [5. Clusters](#5-clusters)
- [6. Energy anomaly](#6-energy-anomaly)
- [7. Schedule, restarts and relearning](#7-schedule-restarts-and-relearning)
- [8. Reading the results](#8-reading-the-results)
- [9. Limitations](#9-limitations)
- [10. Files and constants](#10-files-and-constants)

## 1. Overview

| Part | What it does | Learned? |
|---|---|---|
| Quality score | Scores every closed cycle 0-100 | No: a fixed formula with your thresholds |
| Behaviour baseline | Learns how your heat pump usually runs, per mode and outdoor band, and raises `ml_anomaly` | Yes, every cycle |
| Adaptive thresholds | Learns your short-run length, good pause and cycles per day | Yes (opt-in for use) |
| Clusters | Groups cycles per mode into normal, pendulum and long runs | Yes, weekly |
| Energy anomaly | Flags a day with unusually high electricity use per mode | Yes, daily |

Cycle detection, the pendulum alerts and the heating-curve advice are
rule based; the advice learns COP per outdoor band from your samples, not
from a model.

## 2. Quality score

Every closed cycle starts at 100. Each penalty grows with how far the cycle
is from good, up to its maximum; the score is 100 minus the sum, rounded,
0-100. `last_cycle` shows the points per reason in `quality_penalties`.

| Penalty | Max | Formula | Example |
|---|---|---|---|
| Short run | 30 | 30 × (good_run − run) / good_run | good_run 45 min: 40 min → 3.3, 10 min → 23.3 |
| Low ΔT | 20 | 20 × (good_ΔT − ΔT_max) / good_ΔT, ΔT = R1T (before the backup heater) − R4T | good_ΔT 5 K: 4 K → 4, 2.5 K → 10 |
| Short pause | 20 | 20 × (good_off − pause) / good_off | good_off 20 min: 15 min → 5, 2 min → 18 |
| Short-run ratio | 20 | 0 up to threshold / 2, linear to 20 at 1.5 × threshold | threshold 50 %: 25 % → 0, 50 % → 10, 75 % → 20 |
| Backup heater | 20 | 1 point per % of the run time; step 2 counts double | 8 of 300 min → 2.7, 30 of 300 min → 10 |
| Defrost | 10 | 1 point per % of the run time above 5 % | 6 of 300 min → 0, 30 of 300 min → 5 |

- The thresholds are the options `good_run_threshold_min`,
  `good_dt_threshold_k`, `good_off_threshold_min` and
  `short_cycle_ratio_threshold`.
- Missing data costs nothing (no ΔT, no ΔT penalty).
- The backup heater on a legionella run (tank at 60 °C or more) costs
  nothing when *No backup-heater penalty for legionella runs* is on.
- **Segments.** A heating ↔ hot-water switch, or the 48 h cap, closes one
  cycle and opens the next while the compressor keeps running. Those
  segments get no short-run or short-pause penalty and do not count as
  short runs.
- **Live score.** `quality_today` includes the run in progress; its live
  score does not judge length or ΔT, which can only grow.

## 3. Behaviour baseline and `ml_anomaly`

The baseline learns how your heat pump behaves, so a cycle unlike its
usual cycles at that outdoor temperature stands out.

- **Dimensions:** run length (log minutes), ΔT average, compressor speed,
  COP, leaving water temperature and heat output. Outdoor temperature,
  backup heater, defrost, ΔT max and maximum speed are context, not scored:
  weather is not a fault.
- **Groups:** per mode, and per 4 K outdoor band once a band has 25
  cycles (the mode's statistics until then). A dimension is scored after 25
  samples.
- **Learning:** a moving mean and spread with an unbiased warm-up
  (`alpha = max(0.02, 1/n)`, about 50 cycles of memory), a minimum spread
  per dimension so a stable heat pump does not alert on a tiny change
  (run length 15 %, ΔT 0.4 K, speed 3 rps, COP 0.15, water 0.8 K, heat
  0.3 kW), and outliers clipped at 3 σ instead of ignored, so a new normal
  is learned.
- **Not scored:** transients, boiler co-fire cycles; short runs and split
  segments drop their run length.
- **Alert:** z ≥ 4 on two consecutive cycles of the mode, or z ≥ 6 once.
  The alert names the dimension that stood out (`top_dim_name`) and the
  group.

The 12-value feature vector of every cycle is still stored (`features`
table, diagnostics) for analysis and the clusters.

Design and the winter simulation behind it:
[design/ml-winter-simulation.md](design/ml-winter-simulation.md).

## 4. Adaptive thresholds

Learned per mode from your history (up to 1,500 runs and 90 days):

| Value | Learned as | Range |
|---|---|---|
| Short run | 5th percentile of run lengths | 2-240 min |
| Good pause | median pause before a run | 0-240 min |
| Cycles per day | median of daily counts | 1-100 |

They are always learned and shown in `learned_thresholds`; they are
**used** only when `adaptive_thresholds_enabled` is on (Configure → Quality
& ML), after `adaptive_min_samples` runs (default 20). The short-run value
in use never drops below half of the configured one. The pause is measured
from the end of the previous run to the start of this one.

## 5. Clusters

One k-means model per mode (k = 3), trained on the last 28 days of
behaviour values without transients or co-fire, standardised with the
mean and spread stored in the model. Labels are absolute: a centre below
the short-run threshold is `pendulum`, above 180 min `long_cycle`, else
`normal`. A mode needs 12 cycles; a dimension measured in fewer than half
of the runs is left out. Cluster ids are `mode × 10 + i`.

`kmeans_retrain_stale` fires when a retrain is overdue or keeps failing;
its message says why (too few cycles, one mode only, ...).

## 6. Energy anomaly

Per mode, yesterday's electricity is compared with the baseline of earlier
days (Welford mean and spread). `energy_daily_anomaly` fires when a full
day is more than 2 σ **and** more than 2 kWh above the mean, after at
least 7 days of data. Today's running total is shown for context but
never fires. The baseline is not corrected for weather: a cold snap can
fire it.

## 7. Schedule, restarts and relearning

| What | When |
|---|---|
| Quality score, baseline, adaptive values | Every closed cycle |
| Clusters | Sunday 04:00 (local time), or `recompute_kmeans` |
| Energy baseline | Once a day after midnight |
| Database maintenance | Daily 03:00 |
| Full relearn from stored cycles | `recompute_baseline`, and once after an ML version change |

All models are stored in the database and restored on start; the run in
progress is restored as well, so a restart does not lose it. After the
ML v2 update the integration replayed every stored cycle once (marker
`data_migration_ml_v2_completed`).

## 8. Reading the results

**`ml_anomaly`:** read `top_dim_name` and the group in the alert. A low
COP or heat output with normal run length points at the heat pump (flow,
filter, refrigerant); a run length far from usual at that outdoor
temperature points at control (thermostat, curve, hysteresis). One alert
after a settings change is expected: the baseline adapts within about 50
cycles.

**Clusters:** a growing `pendulum` cluster means more short runs at the
same conditions. Few cycles in a mode give unstable clusters.

**Learned thresholds:** compare them with your options. A learned short
run far below the configured one means many short runs are normal for
your system; enabling adaptive thresholds makes the alerts relative.

**Too sensitive or too quiet:** switch `ml_anomaly` off under Configure →
Notifications, or relearn with `recompute_baseline` after a big change
(new heat pump settings, new radiators). Resetting the ML state: see
[Database](DATABASE.md).

## 9. Limitations

- A statistical signal, not a diagnosis: it says a cycle is unusual, not
  why.
- No supervised learning: `label_cycle` stores labels that are not used
  for training.
- No learning across installations; every heat pump starts from scratch.
- No time-of-day model.
- The energy baseline is not weather-normalised.
- Clusters are unstable below a few dozen cycles per mode.
- Cycles in mode `unknown` are not scored.

## 10. Files and constants

| File | Contents |
|---|---|
| `ml/behaviour_baseline.py` | Behaviour baseline (`BEHAVIOUR_DIMS`, `STD_FLOOR`, `READY_SAMPLES` 25, `BAND_K` 4, `PERSIST_Z` 4, `SINGLE_Z` 6) |
| `ml/adaptive_thresholds.py` | Adaptive thresholds (`SHORT_RUN_PCT` 5, `MAX_SAMPLES_PER_MODE` 1500, `MAX_DAYS` 90) |
| `ml/kmeans_v2.py` | Clusters (`DEFAULT_K` 3, `MIN_CYCLES_PER_MODE` 12, `LONG_CYCLE_MIN` 180) |
| `ml/features.py` | The stored 12-value feature vector |
| `engine/quality_scorer.py` | Quality score |
| `docs/cycle-thresholds.json` | All cycle, pendulum and quality defaults |
