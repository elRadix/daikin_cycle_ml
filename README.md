# Daikin Cycle ML

Home Assistant integration that detects compressor cycles and advises on
pendulum behaviour for Daikin Altherma heat pumps. Local-only ML, no cloud.

## Features

- RPS-based cycle detection with power-sensor fallback
- 8 pendulum patterns per mode (Heating / Cooling / DHW)
- Quality score 0-100 per cycle
- Per-mode adaptive ML baseline (EWMA) with persistent state
- Adaptive thresholds: percentile-based self-learning per mode (opt-in)
- Weekly k-means clustering + per-cycle cluster assignment
- 11-dim feature-vector: duration, dT, RPS, outdoor, BUH,
  defrost + cop_avg, lwt_avg, indoor_temp_avg (batch 14c)
- Actionable advice per pattern
- 31 sensors + 19 binary sensors
- COP stooklijn analysis (batch 14): daily advice + bucket table
- SQLite persistence with retention + daily rollups + auto-migration

IoT class: calculated.

## Install

1. Copy custom_components/daikin_cycle_ml/ to the HA config tree.
2. Restart Home Assistant.
3. Add integration, follow the 8-step wizard.

## Services

- daikin_cycle_ml.reset_counters - reset daily counters
- daikin_cycle_ml.export_cycles - export cycles (json/csv)
- daikin_cycle_ml.label_cycle - label a cycle (analytics)
- daikin_cycle_ml.recompute_baseline - rebuild MultiBaseline from history
- daikin_cycle_ml.run_maintenance - retention prune + VACUUM

## ML pipeline

Every closed cycle becomes an 8-dimensional feature vector:

  duration_s, dT_max, dT_avg, rps_max, rps_avg,
  outdoor_temp, buh_used, defrost_used

The vector feeds three self-learning layers:

1. MultiBaseline (per-mode EWMA) - anomaly scoring per mode
2. AdaptiveThresholds (per-mode percentile) - learned short_run/good_off
3. K-means clusters (weekly retrain) - per-cycle cluster assignment

All self-learning, no labels, no supervised training.

## Clustering

Weekly k-means over the last 7 days produces 3 centroids.
New cycles are assigned via nearest-centroid and stored as cluster_id.

Cluster labels are auto-derived from centroid properties:

- shortest mean duration -> cluster_pendulum
- highest dT_max        -> cluster_dhw_like
- rest                  -> cluster_normal

Three binary sensors expose membership for the latest cycle.

## Scheduled jobs

- Every 30s: poll, detect, dispatch alerts
- Every 6h: save baseline + adaptive state to model_state
- Daily 03:00: retention rollup + prune + optional VACUUM
- Sunday 04:00: k-means clustering over last 7 days
- Every N hours (opt-in): status update via build_status_message()

## Retention

- cycle_retention_days (default 90)
- alert_retention_days (default 30)
- vacuum_enabled (default true)
- daily_summary rollup runs before prune so aggregates survive

## Out of scope (v0.3+)

- COP calculation
- Cost tracking
- HACS publication
- Supervised ML (label-based training)
- Brine circuits (EPRA12 is split air-water)
