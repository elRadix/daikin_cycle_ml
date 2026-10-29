# Machine Learning

How Daikin Cycle ML learns what "normal" looks like for your heat pump, and how it detects anomalies, pendelen, and degradation.

- **Covers:** feature extraction, baseline learning (EWMA), adaptive thresholds, k-means clustering, IsolationForest anomaly detection, energy anomaly, retrain schedules
- **For:** end users who want to understand what the ML does, developers reading the pipeline, admins tuning sensitivity
- **Version:** v1.14.0

Cross-references: [CONFIGURATION.md](CONFIGURATION.md) (ML options), [ENTITIES.md](ENTITIES.md) (ML-powered sensors), [DATABASE.md](DATABASE.md) (`model_state` persistence), [ALERTS.md](ALERTS.md) (ML alerts).

---

## Contents

- [1. Philosophy](#1-philosophy)
- [2. Feature vector](#2-feature-vector)
- [3. Per-mode baseline](#3-per-mode-baseline)
- [4. Anomaly detection](#4-anomaly-detection)
- [5. Adaptive thresholds](#5-adaptive-thresholds)
- [6. K-means clustering](#6-k-means-clustering)
- [7. Energy anomaly detection](#7-energy-anomaly-detection)
- [8. Retrain schedule](#8-retrain-schedule)
- [9. Interpretation guide](#9-interpretation-guide)
- [10. Tuning sensitivity](#10-tuning-sensitivity)
- [11. Limitations](#11-limitations)

---

## 1. Philosophy

### 1.1 Why per-installation ML

Every heat pump installation is different: house size, insulation, radiator vs underfloor, outdoor climate, thermostat behaviour. A heat pump cycling 15 times per hour on one installation can be completely normal on another.

The ML in this integration learns **your** installation's normal behaviour. There are no hardcoded thresholds that say "X cycles per hour is bad" — instead, the model establishes a statistical baseline and flags cycles that deviate from it.

### 1.2 What is learned

| Model | What it learns | Timescale |
|---|---|---|
| **Baseline (EWMA)** | Per-mode means and variances of the 12-dim feature vector | Continuous, per cycle |
| **Adaptive thresholds** | Percentile-based `short_run` and `good_off` per mode | On every completed cycle |
| **K-means clusters** | 3 archetype cycles (pendulum / normal / dhw_like) | Weekly retrain |
| **Energy baseline** | Per-mode daily electrical kWh distribution | Daily (Welford) |

### 1.3 What is NOT learned

- **Hard thresholds** (short_run_min, pendulum_cph, etc.) — you set these
- **Cycle detection** — deterministic based on RPS
- **Quality score** — fixed formula, not learned
- **Heat-curve advice** — deterministic from bucket data, not ML

ML is only for **anomaly detection** and **adaptive fallback**, not for the primary alert triggers.

---

## 2. Feature vector

### 2.1 The 12 dimensions

Every completed cycle is converted to a 12-dimensional float vector. All dimensions are stored in the `features` table with one column per dimension.

| Dim | Feature | Unit | Rationale |
|---|---|---|---|
| `v0` | `duration_s` | seconds | Absolute cycle length |
| `v1` | `dT_max` | Kelvin | Max water-side delta-T (efficiency) |
| `v2` | `dT_avg` | Kelvin | Average dT (efficiency sustained) |
| `v3` | `rps_max` | RPM | Max compressor rotation |
| `v4` | `rps_avg` | RPM | Average compressor rotation |
| `v5` | `outdoor_temp` | °C | Context (outdoor conditions) |
| `v6` | `buh_used` | 0/1 | Binary — was backup heater used |
| `v7` | `defrost_used` | 0/1 | Binary — was defrost triggered |
| `v8` | `cop_avg` | ratio | Average COP during cycle |
| `v9` | `lwt_avg` | °C | Average leaving water temperature |
| `v10` | `indoor_temp_avg` | °C | Average indoor temp (if sensor configured) |
| `v11` | `thermal_kw_avg` | kW | Average thermal power |

### 2.2 Missing values

Every dimension can be `None` (source attribute missing, or sensor not configured). `None` values are substituted with `0.0` in the feature vector — the vector is always 12 elements.

**Consequence:** if a critical feature like `cop_avg` is always `None` (no COP sensor), that dimension contributes nothing to anomaly detection. This is fine — the model just works with 11 effective dimensions.

### 2.3 Vector construction

`extract_feature_vector(cycle)` in `ml/features.py`:

1. Reads each field from the `Cycle` dataclass
2. Converts `None` to `0.0`
3. Returns `list[float]` of length 12

`extract_many(cycles)` batches this for k-means and baseline training.

`is_valid_record(vec)` validates a vector is usable for training (e.g. not all zeros, duration > 0).

---

## 3. Per-mode baseline

### 3.1 Why per-mode

A heating cycle, a DHW cycle, and a cooling cycle have completely different characteristics:
- Heating: typically 30-120 min, moderate dT, moderate RPS
- DHW: shorter, higher dT, higher RPS
- Cooling: different seasonal behaviour

Mixing them in one baseline would produce meaningless z-scores (a DHW cycle would always flag as anomalous when the baseline is heating-heavy).

**Solution:** three independent baselines — heating, cooling, DHW. Each learns from its own cycles only.

### 3.2 EWMA with Welford variance

The baseline uses **Exponentially Weighted Moving Average** (EWMA) for the mean, and a Welford-style accumulator for variance. This gives:

- **Recency bias:** recent cycles weigh more than old ones
- **Constant memory:** O(1) state per mode per dimension
- **Robust to old outliers:** an unusual cycle from 6 months ago is gradually forgotten

Parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `alpha` | 0.01 | EWMA smoothing factor. Lower = slower adaptation |
| `outlier_skip_z` | 5.0 | Skip cycles with z-score > this from mean update |
| `min_samples_before_skip` | 20 | Don't skip until baseline has at least N samples |

### 3.3 Update rule

For each new cycle, per dimension:

```
if n < min_samples_before_skip:
    update mean/m2 with Welford (no skip)
else:
    z = abs((x - mean) / std)
    if z > outlier_skip_z:
        skip this dimension's update
    else:
        Welford update (with exponential weight alpha)
```

The outlier skip prevents a single very unusual cycle (e.g. after a heating outage) from corrupting the baseline.

### 3.4 Persistence

Baseline is persisted to `model_state.baseline_state` every 6 h. On startup:

1. Load `baseline_state` from model_state
2. Deserialize into `MultiBaseline` instance
3. **Dimension guard**: if stored vector length != current `VECTOR_LEN` (12), reset to empty

The dimension guard handles the case where a previous version had 8 or 11 dims. On upgrade, the baseline is reset and relearned. This happens once per major vector change.

### 3.5 Cold start

Baseline needs at least **20 cycles per mode** before anomaly detection is meaningful. Before that:

- `ml_anomaly` alert does not fire (would produce noise)
- Baseline exists but z-scores are unreliable
- Samples counter on the baseline is exposed in diagnostics

**Time to ready:** with 20 cycles/day for heating, baseline is usable after ~1 day. With 5 cycles/day (summer), it may take 4 days.

---

## 4. Anomaly detection

### 4.1 Method

Anomaly detection uses a **z-score threshold** against the per-mode baseline. It is not IsolationForest despite the module name (see §11.2 for historical note).

For each new cycle:

1. Compute the feature vector (12 dims)
2. For each dimension, compute z-score: `z_d = |(x_d - mean_d) / std_d|`
3. Take `z_max = max(z_d)` across dimensions
4. Flag as anomaly if `z_max >= threshold`

The `top_dim` attribute (dimension with highest z-score) tells you **which dimension** triggered the flag.

### 4.2 Thresholds

| z-score | Severity | Action |
|---|---|---|
| < 2.0 | Normal | No alert |
| 2.0 – 3.0 | Watch | Considered but not alerted in v1.9 |
| ≥ 3.0 | Warning | `ml_anomaly` alert fires (warning) |
| ≥ 5.0 | Critical | `ml_anomaly` alert fires (critical) |

The 2.0 threshold matches the ~95% confidence interval for normal distributions. Real cycles are not normal distributions, so a strict 2.0 would produce too many alerts. v1.9 uses **2.0 as "watch"** and **3.0 as actual fire threshold**.

### 4.3 Dimension weighting

Not all dimensions are equally important. In v1.9, all dimensions are weighted equally in the z-score maximum. This is a design decision that trades off:
- **Simplicity:** no per-dimension weights to tune
- **Sensitivity:** a small dimension's variance can dominate if its std is very small

If you see the same dimension flagging repeatedly with tiny deviations, it means that dimension has a very tight baseline (e.g. `defrost_used` might be near-zero std during summer). Per-dimension minimum variance floor is a candidate for a future version.

### 4.4 Interpreting `top_dim`

The `top_dim` attribute on `ml_anomaly` alerts tells you which feature caused the flag:

| `top_dim` | What it usually means |
|---|---|
| `v0` (duration) | Cycle unusually long or short |
| `v1` (dT_max) | Max water delta unusually high or low |
| `v2` (dT_avg) | Sustained water delta unusual |
| `v3` (rps_max) | Compressor max RPM unusual |
| `v4` (rps_avg) | Sustained compressor RPM unusual |
| `v5` (outdoor) | Outdoor temp very unusual (weather outlier) |
| `v6` (buh_used) | BUH usage flagged when baseline expects 0 |
| `v7` (defrost_used) | Defrost flagged when baseline expects 0 |
| `v8` (cop_avg) | COP unusually high or low |
| `v9` (lwt_avg) | LWT unusually hot or cold |
| `v10` (indoor) | Indoor temp unusual (comfort issue) |
| `v11` (thermal) | Thermal power unusual (efficiency) |

If `top_dim = v5`, it's likely a weather outlier — not something to fix. If `top_dim = v8` (COP), it's more actionable.

### 4.5 Per-mode z-scores

Anomaly detection uses the baseline of the **same mode** as the cycle. A DHW cycle is scored against the DHW baseline, not heating or cooling.

If a cycle's mode is `unknown`, it is scored against the mode that has the most samples (fallback). This is rare — most cycles have a clear mode.

---

## 5. Adaptive thresholds

### 5.1 What it is

An **opt-in** feature (default off) that learns `short_run_threshold_min` and `good_off_threshold_min` from your actual cycle history, rather than using the hardcoded defaults.

When enabled, the thresholds are recalculated after each completed cycle, using percentile-based statistics.

### 5.2 Why opt-in

The hardcoded defaults (short_run = 20 min, good_off = 20 min) work well for most installations. Adaptive thresholds are useful when:

- Your heat pump is a low-mass system (fast response, shorter cycles are normal)
- You live in a climate with wild swings (short cycles during shoulder seasons are expected)
- You want the integration to "learn" what normal looks like rather than imposing a rule

They are not the default because:
- They can be surprising — behaviour changes as the model matures
- They mask real issues if the model has learned bad behaviour
- They need ~20 cycles to be meaningful

### 5.3 How it learns

Per mode, after each completed cycle:

```
short_run_threshold = percentile(durations, p20)
good_off_threshold = percentile(off_times, p50)
```

Meaning:
- `short_run`: the 20th percentile of your cycle durations. Cycles shorter than this are in the bottom 20% → "short run"
- `good_off`: the median off-time between cycles. Off-times longer than this are "good"

This means **20% of your cycles will always be flagged as short_run** if adaptive is on and you use the default percentile. That is intentional — it is a relative threshold, not an absolute one.

### 5.4 Safety bounds

Adaptive thresholds are clamped to a safe range:

| Threshold | Min | Max |
|---|---|---|
| `short_run_threshold_min` | 5 | 60 |
| `good_off_threshold_min` | 3 | 120 |

This prevents the model from learning absurd values (e.g. a 1-minute short_run threshold during a heat wave, or a 200-minute one during a cold snap).

### 5.5 Activation

Requires `adaptive_min_samples` cycles per mode (default 20) before kicking in. Until then, hardcoded thresholds are used.

`sensor.daikin_cycle_ml_learned_thresholds` exposes the current learned values as attributes. Empty until the minimum sample count is reached.

### 5.6 Turning it off

Set `adaptive_thresholds_enabled = false`. The sensor stops updating but retains its last values. Cycle detection reverts to hardcoded thresholds on the next tick.

---

## 6. K-means clustering

### 6.1 What it does

Groups your cycles into **3 archetypes** (clusters) based on the 12-dim feature vectors. Each cluster gets an auto-derived label:

| Label | Meaning |
|---|---|
| `pendulum` | Shortest mean duration — pendelen |
| `dhw_like` | Highest dT_max — DHW-style cycles |
| `normal` | Everything else — typical heating cycles |

These labels are **descriptive**, not prescriptive. A cluster being labelled "pendulum" doesn't mean every cycle in it is a problem — it just means this cluster has the shortest durations relative to the other two.

### 6.2 Why 3 clusters

The choice of k=3 is a trade-off:
- k=2: too coarse — DHW and heating get mixed
- k=4+: harder to label meaningfully, more fragile to noise
- k=3: maps well to "short, medium, long" or "pendulum, normal, DHW"

You can inspect the actual cluster centroids via diagnostics download. Changing k is not exposed as an option in v1.9.

### 6.3 The algorithm

Standard k-means with:
- **Initialization:** k-means++ for centroid seeding
- **Iterations:** max 100
- **Convergence:** stop when centroids move < 1e-4 or 100 iterations reached
- **Features:** all 12 dimensions, unweighted

Performed by `ml/clustering.py::kmeans(vectors, k=3)`.

### 6.4 Weekly retrain

Retrained **every Sunday at 04:00 local** over the last 7 days of cycles.

Requires:
- At least 30 cycles in the last 7 days (else skips this week)
- At least 3 distinct cycles per cluster

On success:
- New centroids persisted to `model_state.kmeans_state`
- Cluster labels recalculated
- `last_ok_ts` updated

On failure:
- `consecutive_failures` incremented
- `last_failure_reason` set
- `last_ok_ts` unchanged (stays at previous success)

### 6.5 Cluster assignment for new cycles

Every new cycle is assigned to a cluster via **nearest centroid** of the current model. This happens in `_assign_cluster(vector)`:

```python
if not self._kmeans_centroids:
    return None
return nearest_centroid(vector, self._kmeans_centroids)
```

If k-means has never run (no centroids), `cluster_id` is `None` on the cycle record.

### 6.6 When kmeans_retrain_stale fires

If the last successful retrain was more than **14 days ago**, the `kmeans_retrain_stale` alert fires.

Common causes:
- Not enough cycles (< 30 in a 7-day window) — normal for summer/DHW-only homes
- Retrain kept failing (DB issue, corruption)
- HA was off during the Sunday 04:00 window

Fix: call `daikin_cycle_ml.recompute_kmeans` service manually. It runs immediately regardless of schedule.

### 6.7 Auto-derived labels

Labels are assigned by inspecting the centroids after training:

```python
# Order clusters by mean duration (v0)
sorted_by_duration = sorted(range(k), key=lambda i: centroids[i][0])

# Shortest = pendulum
labels[sorted_by_duration[0]] = "pendulum"

# Highest dT_max = dhw_like
sorted_by_dt = sorted(range(k), key=lambda i: -centroids[i][1])
labels[sorted_by_dt[0]] = "dhw_like"

# The rest = normal
for i in range(k):
    if i not in labels:
        labels[i] = "normal"
```

If the highest-dT cluster is also the shortest-duration cluster, there is a conflict — pendulum wins. This is rare but produces "2 pendulum + 1 normal + 1 dhw_like" instead of the expected 1+1+1. The exact rules are in `labels_to_dict` in `ml/clustering.py`.

---

## 7. Energy anomaly detection

### 7.1 Purpose

Independent from cycle anomaly detection. Flags days where **total electrical energy consumption** is unusually high compared to the recent baseline.

Catches problems that cycle anomaly misses:
- Stuck valves (compressor runs longer than needed)
- Unexpected extra demand (someone set the thermostat to 30 °C)
- Defrost runaway
- BUH misbehaviour

### 7.2 Method

Per mode (heating, DHW, cooling):

1. Yesterday's total electrical kWh is added to the baseline via Welford update
2. Today's total electrical kWh is compared to the baseline
3. If `today > mean + 2 * sigma` AND `today > 2.0 kWh above mean`, alert fires

Requires at least **7 daily samples** before firing. First week after install: no alert possible.

### 7.3 Welford baseline

The energy baseline uses **Welford update**, not EWMA:
- Simpler update rule (mean and m2 accumulator)
- Adapts naturally as data grows
- Does not decay — an old normal day still contributes

In v1.9 the energy baseline does not have EWMA recency bias. This means the baseline becomes very stable over time (harder to flag anomalies) but also cannot "forget" old behaviour. For a yearly seasonal cycle, this is mostly fine because it averages across seasons.

### 7.4 The 2.0 kWh floor

The 2.0 kWh floor prevents alerts when:
- Baseline is very low (summer DHW-only usage at 1-2 kWh/day)
- Sigma is very small (stable usage)
- A tiny deviation is still 2 sigma above mean

Without the floor, a 0.5 kWh day after 0.3 kWh days would flag. That is noise, not a problem.

The floor ensures the alert only fires when **both**:
- Statistically anomalous (2 sigma)
- Practically anomalous (2 kWh above baseline)

### 7.5 Weather normalization

**The energy baseline is NOT weather-normalized** in v1.9. This means:
- If winter arrives suddenly, daily energy jumps → alert may fire
- If a cold snap hits, energy jumps → alert may fire

This is intentional — cold snaps ARE when problems are most visible, and flagging "unusually high usage" during a cold snap is informative even if "expected" for the weather.

**Consequence:** expect `energy_daily_anomaly` to fire several times during seasonal transitions. Not a bug.

Weather normalization is a candidate for a future version.

### 7.6 Today vs yesterday semantics

Two different concepts:
- **Display candidate**: today's running total vs baseline (what appears in the alert message)
- **Fire candidate**: yesterday's total vs baseline (what actually triggers the alert, after a full day is complete)

Reason: today's total is partial. A day at 10:00 is not comparable to a full day. Firing only on complete days prevents "early morning false positives".

This split was introduced in v1.9 (I6). Before v1.9, the alert could not fire correctly.

---

## 8. Retrain schedule

| Model | When | Frequency | Trigger |
|---|---|---|---|
| Baseline (EWMA) | Per cycle | Continuous | On every completed cycle |
| Adaptive thresholds | Per cycle | Continuous | If enabled |
| K-means | Sunday 04:00 local | Weekly | Scheduler |
| Energy baseline | Per day | Daily | On 1h tick after midnight |
| `recompute_baseline` | On demand | Manual | Service call |
| `recompute_kmeans` | On demand | Manual | Service call |

### 8.1 Timezone

All schedule times are **local timezone**, not UTC. If your HA is set to Europe/Brussels, Sunday 04:00 means 04:00 Brussels time.

This is standard HA behaviour for scheduled jobs.

### 8.2 HA restart behaviour

- **Baseline state**: loaded from disk on restart, no retrain needed
- **Adaptive thresholds**: loaded from disk, no retrain needed
- **K-means**: loaded from disk, no retrain needed (next scheduled retrain continues as normal)
- **Energy baseline**: loaded from disk, no retrain needed
- **In-progress cycle**: **lost** on restart (coordinator memory is not persisted mid-cycle)

Lost in-progress cycles are rare (only if HA restarts during a running cycle). They produce a gap in the history but no corruption.

---

## 9. Interpretation guide

### 9.1 Reading `ml_anomaly` alerts

The message shows:
- Severity (warning / critical)
- Mode (heating / cooling / dhw)
- z-score (how far from baseline)
- Top dimension (what triggered the flag)
- Last cycle duration, average duration (7d), outdoor temp

**Decision tree:**

1. **`top_dim` is `v5` (outdoor)**: weather outlier. No action needed.
2. **`top_dim` is `v7` (defrost)**: the cycle had a defrost when baseline didn't expect one. Check outdoor humidity.
3. **`top_dim` is `v8` (COP)**: efficiency dropped or rose. If dropped, investigate. If rose, maybe a good thing.
4. **`top_dim` is `v0` (duration)**: cycle is unusually short or long. Combined with low `quality_score`, investigate.
5. **`top_dim` is `v1`/`v2` (dT)**: water-side efficiency changed. Check flow, check for air in the system.
6. **Severity is critical and z-score > 5**: strongly anomalous. Cross-reference with other alerts (`cop_degradation`, `defrost_excessive`).

### 9.2 Reading cluster labels

- **`cluster_pendulum`**: shortest cycles. Look at quality scores — if they are mostly 60-80, they are acceptable but not optimal.
- **`cluster_normal`**: typical heating cycles. This is your baseline.
- **`cluster_dhw_like`**: highest dT cycles, usually DHW. If heating cycles are clustered here, it means your heating dT is unusually high.

Cluster membership alone is not a problem. It becomes actionable when combined with:
- Low quality scores in the "normal" cluster (deterioration)
- High pendulum cluster share (> 30% of cycles in "pendulum" cluster)
- Sudden cluster shift (yesterday you were 80% normal, today 80% pendulum)

### 9.3 Reading energy anomaly alerts

The message shows today's kWh, baseline mean, baseline sigma, z-score, samples, mode.

- **`samples < 7`**: baseline is very new. Ignore alerts in the first week.
- **`samples >= 7, z-score 2-3`**: mild anomaly. May be weather or a one-off.
- **`samples >= 7, z-score > 3`**: strong anomaly. Investigate.
- **`today_kwh > mean + 2.0` but `samples < 7`**: should not happen — this is a bug.

Cross-reference with the daily cycle count for that day. If cycles are also high, it's probably demand-driven. If cycles are normal but energy is high, it's efficiency-driven (investigate).

### 9.4 Reading adaptive threshold changes

If `sensor.daikin_cycle_ml_learned_thresholds` shows values very different from defaults (e.g. `short_run_threshold_min: 45` when default is 20):

- Your installation cycles longer than average
- This might be correct (large radiators) or a sign of oversizing
- Compare with cluster distribution — if most cycles are in "normal" cluster with high duration, the adaptive threshold is correct
- If most cycles are in "pendulum" cluster, the adaptive threshold is masking a problem

### 9.5 When to disable ML

Disable adaptive thresholds if:
- You want deterministic behaviour
- You are debugging a specific issue and want a stable reference
- The learned thresholds are masking a real problem

**Do not disable** the baseline or k-means — they have no direct alert consequences and disabling would require code changes.

---

## 10. Tuning sensitivity

### 10.1 Making anomaly detection more sensitive

Currently, `ml_anomaly` fires at z-score >= 3.0. To make it more sensitive, you would need to:

1. Edit `ml/baseline.py` to change the threshold
2. Or add a config option (candidate for future)

In v1.9, the threshold is hardcoded. Adjust via:
- Reducing `outlier_skip_z` (currently 5.0) → more cycles counted, tighter baseline
- Reducing `adaptive_min_samples` → baseline ready faster

### 10.2 Making it less sensitive

- Increase `alert_enabled_...` for `ml_anomaly` is not available (no per-alert toggle for ml)
- Disable `alert_group_ml` in Options → Notifications → Content
- Increase `ml_anomaly` dedup window from 60 min to a longer value

### 10.3 Resetting ML state

To fully reset ML and start learning from scratch:

1. Delete the DB (see [DATABASE.md §8.4](DATABASE.md#84-full-reset))
2. Restart HA
3. All ML state is relearned

**Warning:** this deletes ALL historical data (cycles, alerts, everything), not just ML. There is no way to reset just the ML state in v1.9.

To reset only the baseline:
```sql
DELETE FROM model_state WHERE key = 'baseline_state';
```
Then restart HA. Baseline relearns from future cycles. K-means and adaptive thresholds are unaffected.

To reset only k-means:
```sql
DELETE FROM model_state WHERE key = 'kmeans_state';
```
Then either wait for Sunday 04:00 or call `daikin_cycle_ml.recompute_kmeans`.

To reset only energy baseline:
```sql
DELETE FROM model_state WHERE key = 'thermal_daily_baseline';
```
Then wait 7 days for it to rebuild.

### 10.4 Cold start optimisation

To speed up baseline learning:

1. Lower `adaptive_min_samples` to 10 (default 20)
2. Lower `min_samples_before_skip` in code (advanced)
3. Wait at least 3-4 days for baseline to have meaningful data

Even with tuning, minimum time to a useful baseline is ~2 days.

---

## 11. Limitations

### 11.1 Not a diagnostic tool

ML flags **anomalies**, not **problems**. A flagged cycle might be:
- A real problem (compressor wear)
- A weather outlier (sudden cold snap)
- A legitimate change (you opened a window, thermostat changed)
- Noise (in-progress baseline, sensor glitch)

ML is a **starting point for investigation**, not a conclusion. Always cross-reference with other data before acting.

### 11.2 Historical note: IsolationForest

The module is named `anomaly_engine.py` and older documentation (including v1.8 README) mentioned IsolationForest. **In v1.9, the actual algorithm is z-score based**, not IsolationForest.

Why:
- IsolationForest needs many samples to train reliably (>1000)
- z-score works well with 20+ samples per mode
- z-score produces interpretable scores (z=3.5 is meaningful)
- IsolationForest produces uninterpretable "anomaly scores"

The class name `AnomalyResult` and the module name are unchanged for backwards compatibility. The actual computation is in `ml/baseline.py::MultiBaseline.score_z()`.

**IsolationForest is planned for a future version** if the sample count grows enough to justify it. That is a candidate for v1.10+.

### 11.3 No supervised learning

The integration does not learn from labeled data. `label_cycle` service attaches labels to cycles, but they are not used for training (yet). Label collection is for a future supervised model.

If you label cycles, they are stored but not used. This is documented behavior, not a bug.

### 11.4 No cross-installation learning

Every installation trains its own model in isolation. There is no federated learning, no cloud model, no pooling across users.

Trade-off:
- **Pro:** privacy (no data leaves your HA)
- **Pro:** relevance (the model learns YOUR installation)
- **Con:** every new installation starts from zero
- **Con:** no way to benefit from aggregate patterns

Local-only learning is a core design decision of this integration.

### 11.5 No seasonal model

The EWMA baseline does not model seasons. It treats a January cycle and a July cycle with equal recency weight (at alpha=0.01, "recent" means ~100 cycles, which is ~1 month at 20 cycles/day).

Consequence: as seasons change, the baseline lags behind actual conditions. Anomalies spike during seasonal transitions, then settle.

Per-season baselines (winter/summer/shoulder) are a candidate for a future version.

### 11.6 Energy baseline not weather-normalized

See §7.5. This is intentional for v1.9 but acknowledged as a limitation.

Weather normalization (correlating energy with heating degree days) is a candidate for a future version.

### 11.7 No `defrost_used` variance modelling

`defrost_used` and `buh_used` are binary (0/1) features. Their variance in the baseline can be very low (e.g. 0.05 during summer). This means a single defrost cycle produces a huge z-score, even if it is completely normal for that season.

Consequence: in summer, `ml_anomaly` may fire on a single defrost when baseline expected none. This is a false positive.

Workaround: ignore `ml_anomaly` alerts with `top_dim` `v6` or `v7` (BUH or defrost) during shoulder seasons.

Binary feature variance floor is a candidate for a future version.

### 11.8 K-means fragility at low sample counts

K-means needs enough cycles to produce stable clusters. With fewer than 30 cycles in a 7-day window, clusters can vary wildly between weeks.

Consequence: the `cluster` label on a cycle might change between retrains even if the cycle characteristics didn't change.

This is a mathematical limitation of k-means at low N, not a bug.

### 11.9 No anomaly detection for `unknown` mode

Cycles with `mode = unknown` do not have a baseline to score against. They fall back to the mode with most samples, but this is a guess, not a real baseline.

Consequence: `ml_anomaly` is less reliable for `unknown` cycles. If you see a lot of `unknown` cycles, check the source sensor's mode attributes — likely one of `Operation Mode` or `I/U operation mode` is missing.

### 11.10 No time-of-day modelling

The baseline does not distinguish between a cycle at 03:00 and one at 15:00. If your installation behaves differently at night (e.g. setback mode), that behaviour gets averaged into the baseline.

Consequence: night cycles may be slightly more likely to be flagged as anomalies because they differ from the average.

Time-of-day buckets are a candidate for a future version.

---

## Appendix A — Key files

| File | Purpose |
|---|---|
| `ml/features.py` | Feature extraction, `VECTOR_LEN = 12`, `FEATURE_NAMES` |
| `ml/baseline.py` | `MultiBaseline` (EWMA), `Baseline` (Welford for energy) |
| `ml/adaptive_thresholds.py` | Percentile-based threshold learning |
| `ml/clustering.py` | `kmeans`, `nearest_centroid`, `labels_to_dict`, `classify_clusters` |
| `ml/multi_baseline.py` | `MultiBaseline` deserialization |
| `engine/anomaly_engine.py` | Public anomaly detection entrypoint (z-score) |
| `coordinator.py` | `_refresh_kmeans`, `_assign_cluster`, baseline persist/load |

## Appendix B — Constants

| Constant | Value | Where | Meaning |
|---|---|---|---|
| `VECTOR_LEN` | 12 | `ml/features.py` | Number of feature dimensions |
| `FEATURE_NAMES` | list of 12 | `ml/features.py` | Human-readable names |
| `alpha` (EWMA) | 0.01 | `ml/baseline.py` | EWMA smoothing |
| `outlier_skip_z` | 5.0 | `ml/baseline.py` | Outlier skip threshold |
| `min_samples_before_skip` | 20 | `ml/baseline.py` | Skip only after N samples |
| `KMEANS_STALE_AFTER_DAYS` | 14 | `const.py` | Days before `kmeans_retrain_stale` |
| `ENERGY_ANOMALY_SIGMA_THRESHOLD` | 2.0 | `const.py` | Sigma for energy alert |
| `ENERGY_ANOMALY_FLOOR_KWH` | 2.0 | `const.py` | kWh floor for energy alert |
| `ENERGY_ANOMALY_MIN_DAYS` | 7 | `const.py` | Min samples before energy alert |
| `DEFAULT_ADAPTIVE_MIN_SAMPLES` | 20 | `const.py` | Min samples for adaptive |
| `SHORT_RUN_P20` | 20 | `ml/adaptive_thresholds.py` | Short-run percentile |
| `GOOD_OFF_P50` | 50 | `ml/adaptive_thresholds.py` | Good-off percentile |

## Appendix C — Tuning cheat sheet

**"I get too many ml_anomaly alerts"**
1. Disable `alert_group_ml` in Options → Notifications → Content
2. Or increase the `ml_anomaly` dedup window from 60 min to 720+ min

**"I never get ml_anomaly alerts"**
1. Check baseline has ≥ 20 samples per mode (diagnostics → baseline section)
2. Verify `alert_enabled_ml` is `true` (Options → Notifications → Content)
3. Verify quiet hours are not active (if baseline fires at night)

**"ml_anomaly fires on defrost cycles"**
Known limitation (see §11.7). Ignore alerts with `top_dim = v7`.

**"cluster labels keep changing"**
K-means instability at low sample counts (see §11.8). Reduce `recompute_kmeans` frequency or wait for more cycles to accumulate.

**"energy_daily_anomaly fires every week"**
Likely weather-driven. If z-score is 2-3 and cycles also high that day, ignore. If z-score > 3 without high cycles, investigate.

**"Adaptive thresholds make short_run alert every 5 cycles"**
Expected — adaptive learns p20 (20% flag rate). Disable adaptive thresholds to return to hardcoded 20 min.
