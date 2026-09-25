# Daikin Cycle ML - Technical

## Architecture

config_entry -> DaikinCycleMLCoordinator -> CycleDetector
                      |
                      +-> AttributeReader (engine/)
                      +-> CycleStore (memory deque)
                      +-> CycleDB (aiosqlite)
                      +-> MultiBaseline (per-mode EWMA)   <-- wired
                      +-> anomaly_engine + action_engine
                      +-> notification_engine + repairs
                      +-> sensor / binary_sensor platforms
                      +-> async_setup_maintenance   (03:00 daily)
                      +-> async_setup_baseline_save (every 6h)
                      +-> async_setup_kmeans        (Sunday 04:00)

## Data flow (every 30s)

1. Read source attrs.
2. AttributeReader normalizes mixed types.
3. CycleDetector accumulates dT / RPS.
4. On cycle close, on_new_cycle -> _process_new_cycle:
   a. extract_feature_vector(record)
   b. MultiBaseline.update(mode, vector)
   c. MultiBaseline.zscore(mode, vector)
   d. evaluate_anomaly(vector, zscore) -> severity
   e. generate_advice(record, anomaly, quality)
   f. DB insert cycle + features
   g. Alert dispatch (quiet hours + aggregation)
5. Repairs: source-stale + missing-attrs.

## ML flow (per closed cycle)

  record --+-> extract_feature_vector -> 8-dim vector
           |
           +-> MultiBaseline.update(mode, vector)
           |     mode in {heating,dhw,cooling,defrost,unknown}
           |
           +-> MultiBaseline.zscore(mode, vector) -> z_max
           |
           +-> evaluate_anomaly -> severity
           |
           +-> generate_advice -> ActionAdvice list

## Quality score

score = 100
duration < good_run_min:  -30
dT_max < good_dt_k:       -20
off_time < good_off_min:  -20
short_cycle_ratio > 50:   -20
buh_used:                 -10
result = max(0, score)

## Feature vector (8 dims)

0. duration_s
1. dT_max
2. dT_avg
3. rps_max
4. rps_avg
5. outdoor_temp
6. buh_used
7. defrost_used

is_valid() filters NaN/Inf.

## Anomaly severity mapping

z = (x - mean) / std
z < 2.0    -> normal
z 2 - 3    -> watch
z 3 - 4.5  -> warn
z >= 4.5   -> critical
Zero-variance dims give z = 0 and never alert.

## Baseline layers

AdaptiveBaseline (EWMA, active):

  mean_t = (1 - alpha) * mean_(t-1) + alpha * x_t
  var_t  = (1 - alpha) * (var_(t-1) + alpha * (x_t - mean_(t-1))^2)

Parameters:
- alpha (default 0.05): ~14-day half-life at 30s sampling
- outlier_skip_z (default 5.0): skip after warm-up
- min_samples_before_skip (default 20)

Baseline (Welford) is legacy, kept for backward-compat tests only.
baseline_from_dict() dispatches on type: welford -> Baseline,
ewma -> AdaptiveBaseline.

## MultiBaseline (per-mode)

Dict of AdaptiveBaseline, one per mode.
Routes each vector to the correct sub-baseline so a single baseline
does not blur Heating vs DHW vs Cooling at mode switches.

API:
- update(mode, vector)
- zscore(mode, vector)
- is_anomaly(mode, vector, threshold=3.0)
- to_dict() / from_dict(data)  (model_state persistence)

## Adaptive thresholds (12a)

Pure percentile self-learning, per mode. ml/adaptive_thresholds.py.

Learned values:
- learn_short_run_min(mode) = p20 of run durations (min)
- learn_good_off_min(mode)   = p50 of off durations (min)
- learn_target_cycles_per_day() = p50 of daily counts

Clamps: run 2-240, off 0-240, target 1-100.

Config: adaptive_thresholds_enabled (default False), adaptive_min_samples=20.

Coordinator: _effective_threshold(key, default) overrides static short_run,
good_off and target_cycles_per_day in _alert_binary_states when enabled.
Values with fewer samples than adaptive_min_samples return None.

Exposed as 3 sensors: learned_short_run_min, learned_good_off_min,
learned_target_cycles_per_day (return unknown below min_samples).

## Persistence

Coordinator methods:
- async_save_baseline_state() -> db.async_set_model_state('baseline_state', ...)
- async_load_baseline_state() -> MultiBaseline.from_dict(...) at startup

Coordinator methods (adaptive, 12a):
- async_save_adaptive_state() -> db.async_set_model_state(adaptive_thresholds, ...)
- async_load_adaptive_state() -> AdaptiveThresholds.from_dict(...) at startup

Both baseline and adaptive persist on the same 6h hook.

Scheduled via async_track_time_interval (6h). _baseline_save_unsub tracked
for unload.

## k-means (weekly)

async_run_kmeans() runs Sunday 04:00:
1. Query last 7 days cycles
2. extract_many -> filter is_valid
3. kmeans(vectors, k=3, max_iter=100)
4. Save model_state['kmeans_state'] = {centroids, counts, ts}

Goal: discover 3 natural clusters (short pendulum / normal / DHW+defrost).
_kmeans_unsub tracked.

## Cluster assignment (12b)

Per-cycle: after DB insert, coordinator calls
nearest_centroid(vector, _kmeans_centroids) and stores the result
in cycles.cluster_id (lazy ALTER TABLE for old DBs).

Auto-labeling (classify_clusters on centroids):
- Sorted by mean duration (dim 0): shortest -> "pendulum"
- Highest dT_max (dim 1) among the rest -> "dhw_like"
- Remaining -> "normal"

Centroids loaded at startup from model_state[kmeans_state].
Exposed as 3 binary sensors: cluster_pendulum, cluster_normal,
cluster_dhw_like.

## recompute_baseline service

Real (no longer stub):
1. db.async_export_cycles(days)
2. extract_feature_vector per record -> filter is_valid
3. baseline = MultiBaseline(); update per record mode
4. async_save_baseline_state()
Returns {computed, samples, days}.

## Scheduled jobs

Job              | When             | Effect
-----------------|------------------|------------------------------
poll             | every 30s        | read, detect, dispatch
baseline save    | every 6h         | model_state['baseline_state']
maintenance      | daily 03:00      | rollup + prune + VACUUM
k-means          | Sunday 04:00     | model_state['kmeans_state']
status updates   | configurable     | opt-in, persistent + notify (12c)

## DB

Path: /config/.storage/daikin_cycle_ml.db
Tables: cycles, features, model_state, alerts, daily_summary, cop_samples

model_state keys:
- last_maintenance_ts  (float, written by async_run_maintenance)
- baseline_state       (dict, written by async_save_baseline_state)
- kmeans_state         (dict, written by async_run_kmeans)
- adaptive_thresholds  (dict, written by async_save_adaptive_state)

## Retention

async_run_maintenance(cycle_retention_days, alert_retention_days, vacuum):
1. Rollup cycles -> daily_summary (atomic, before prune)
2. Prune features (children first, R28)
3. Prune cycles
4. Delete orphan features
5. Prune alerts
6. VACUUM via fresh connection, isolation_level=None (R27)

daily_summary is ONLY filled by this method.
async_daily_summary() reads from it.

## COP analysis (batch 14)

engine/cop_analyzer.py parses sensor.altherma_global_cop attributes
(string -> float with unit stripping), buckets samples by 2C outdoor
temperature, and produces stooklijn advice:
- verlaag_lwt_2c: current LWT above bucket average, comfort-safe
- verhoog_lwt_2c: current LWT below bucket average
- behoud: within +/- 1.5C or comfort-guard triggered

Samples are collected every 10 min while COP > 0, quality=Good,
power_stable, no defrost. Retention 365 days (~2 MB/year).
Analysis uses last 30 days, min 5 samples/bucket.

2 sensors expose results:
- sensor.daikin_cycle_ml_stooklijn_advies (state + bucket table attrs)
- sensor.daikin_cycle_ml_cop_vandaag (state + samples/min/max attrs)

Daily scheduler at 04:00 evaluates alerts:
- cop_low: day COP < 2.5 with >= 3 samples (20h dedup)
- stooklijn_advies: saving >= 5% COP, confidence >= 0.7 (20h dedup)

## Known limitations (v0.3)

- COP / cost are out of scope (v0.3)
- Cluster sensors not yet exposed (11e optional)
- Adaptive thresholds default off (opt-in after real-data validation)
- K-means and cluster sensors require >=7 days of cycles
- Weather-compensation advisor not implemented (v0.4 idea)

## Testing

export PYTHONPATH=/workspace
cd /workspace/daikin_cycle_ml
pytest -q
