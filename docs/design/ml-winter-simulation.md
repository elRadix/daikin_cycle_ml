# ML pipeline: three-month winter simulation

Review of the ML layer (`ml/` + `engine/anomaly_engine.py`), checked with a
simulation of 1 December to 28 February. Tool: `tools/sim_ml_winter.py`;
results: `img/sim_ml_winter_results.json`.

## Setup

The tool generates the cycles of an 8 kW split heat pump in a typical
Dutch / Belgian house and feeds them through the integration's **own
code**, in the order of `coordinator._process_new_cycle`:

| Code | Use |
|---|---|
| `coordinator._classify_transient` | False starts are not learned |
| `ml.multi_baseline.MultiBaseline` + `engine.anomaly_engine.evaluate` | `ml_anomaly` alert, 60 min dedup |
| `ml.adaptive_thresholds.AdaptiveThresholds` | Learned short-run / off / cycles-per-day |
| `ml.clustering.kmeans` + `classify_clusters` + `nearest_centroid` | Weekly clusters (last 7 days), label per cycle |
| `engine.quality_scorer.score_cycle` | Quality per cycle |

The simulated house and weather:

| Quantity | Value |
|---|---|
| Heat loss / internal gains | 150 W/K / 400 W |
| Outdoor temperature | mean 4.2 °C, cold snap to −10 °C in week 6 (10–16 Jan), mild spell 10–14 Feb |
| Behaviour | Modulates down to 2.3 kW, then cycles; DHW 06:30 and 18:15 |
| Defrosts | Most frequent around +1 °C |
| False starts | On mild restarts |
| Data volume | 1,403 cycles (15.6 per day), 180 DHW runs, 20 false starts |

Two faults are injected to score the alerts:
- **Water-flow loss, 4–13 Feb:** flow falls from 17 to 10 l/min, so ΔT rises by 70 %. On a real install this comes from a clogging water filter or dirt separator, air in the system, a partly closed valve or a weak pump.
- **Slow COP loss, 15–28 Feb:** the COP falls by 15 %.

![Anomaly score per cycle](img/sim_ml_winter_z.png)

## Findings

### 1. `ml_anomaly` fires about 19 times a week on a healthy heat pump

| | Current | v2 (proposal below) |
|---|---|---|
| Alerts in 90 days | 233 | 13 |
| Alerts per week, no fault | **19.3** | **0.6** |
| Alerts in week 1 | 52 | 1 |
| Alerts on false starts | 17 | 0 |
| Water-flow loss: alerts / first alert after | 36 / day 0 (buried in noise) | 7 / day 6 |
| COP loss: alerts | 15 (indistinguishable from noise) | 0 (a COP-degradation job, see 7) |

The causes, in order of impact:

- **a. Cold start:**
  - The EWMA (`alpha` 0.01) starts with variance 0. After *n* cycles its variance is roughly `alpha·n` times the true variance, so after 10 cycles the std is about a third of the truth.
  - Every z-score is therefore inflated about 3× for the first ~100 cycles of each mode. 17 of the first 20 heating cycles and 16 of the first 20 DHW cycles raise an alert.
  - DHW (2 cycles a day) needs about 7 weeks to settle.
- **b. Outlier lock:**
  - From cycle 20 on, a cycle with |z| > 5 is not learned. Because the std is still too small at that point (see a), long but normal runs are rejected, and 141 updates are skipped.
  - The variance of `duration_s` never grows: its std ends at 14 min, while heating runs normally range from 30 min to 8 h.
  - Every long run on a cold day then raises an alert. `duration_s` is the top dimension in **121 of 233** alerts.
- **c. Raw duration:** run length is skewed (log-normal); a z-score on seconds treats a 6 h run as a fault.
- **d. Context and binary features are scored too:**
  - `outdoor_temp` is the weather, not the heat pump.
  - `indoor_temp_avg` is the room.
  - `buh_used` and `defrost_used` are 0/1 with a tiny variance.
  - A cold snap or the first defrost of the season therefore reads as an anomaly. Within the 12-dimension max, 12 tests per cycle multiply false positives.
- **e. False starts are scored:** they are kept out of the baseline (#105) but still evaluated against it, and a 90 s run is always an outlier, so 17 alerts are about a cycle the integration already classifies as expected.

### 2. "pendulum" cluster label is relative, not absolute

`classify_clusters` names the cluster with the shortest mean duration "pendulum", whatever that duration is.
- In this winter the shortest centroid is 34–47 min, so **852 cycles are labelled pendulum and 838 of them run 20 min or longer**; only 15 real short runs exist.
- The #436 reporter's diagnostics show the same: a 48 min centroid is labelled `pendulum`.
- `sensor.last_cycle.cluster` therefore says "pendulum" for most normal cycles.

![Alert dimensions and cluster labels](img/sim_ml_winter_dims_clusters.png)

### 3. k-means trains on other vectors than it assigns

- **Different inputs:** `async_run_kmeans` builds vectors from DB rows (`extract_many`). The `cycles` table has no `lwt_avg` or `indoor_temp_avg` column, so these two dimensions are 0 in training. `nearest_centroid` then assigns live vectors in which they are 30–50 °C and ~20 °C.
- **Mixed data:** training also mixes heating with DHW (12–14 DHW cycles per week) and includes false starts. The docstring says clustering finds sub-patterns "within a single mode".
- **No scaling:** features are not scaled, so `duration_s` (thousands of seconds) decides the clusters on its own.

### 4. Adaptive short-run threshold flags 20 % of cycles by design

`learn_short_run_min` is the p20 of run lengths: 38–39 min in this winter.
- If adaptive thresholds are enabled, one cycle in five is "short" by definition, however healthy the heat pump is.
- The learned `good_off` (p50) drops to 13 min.
- Adaptive thresholds are off by default (`adaptive_enabled: false`), so this affects only users who turn them on.

### 5. Other details

- **Self-inclusion:** `evaluate_anomaly` runs after `per_mode.update(vector)`, so a cycle is partly compared with itself (small with `alpha` 0.01, but z = 0 for the first cycle of a mode).
- **Unbounded history:** the adaptive history lists grow without bound (persisted in `model_state`), about 5,000 samples a year.

### 6. Quality score

- **Range:** the scores range from 70 to 100 for healthy cycles in this winter.
- **Penalties:** defrost and backup-heater penalties behave as specified (#421).
- **Fault weeks:** the injected faults barely move the score, which is expected because it scores cycle shape, not efficiency.

### 7. The COP loss is not an ML anomaly

- **v2:** a 15 % loss over two weeks is absorbed by any adaptive baseline, and v2 raises nothing for it.
- **Current code:** its 15 alerts cannot be told apart from the noise around them.
- **Where it belongs:** slow drift is the job of `cop_degradation` (weekly, weather-normalised), not of a per-cycle z-score.

## ML v2 (shipped with #443)

| Change | Effect |
|---|---|
| Unbiased warm-up: `alpha_eff = max(alpha, 1/n)`, alerts only after 25 cycles per baseline | No week-1 burst |
| Score behaviour only: `log(duration)`, `dT_avg`, `rps_avg`, `cop_avg`, `lwt_avg`, `thermal_kw_avg`; outdoor temperature as context, not as a dimension | Weather and defrosts no longer alert |
| Baseline per mode × outdoor band (4 K), falling back to the mode baseline until a band has 25 cycles | A cold-snap run is compared with cold-day runs |
| Std floor per dimension, Huber-clipped update instead of skipping outliers | No variance lock; real faults still stand out |
| Do not evaluate false starts | 17 alerts fewer |
| Alert on z ≥ 4 for 2 cycles in a row, or z ≥ 6 once | One odd cycle is not an alert |
| k-means per mode, on scaled behaviour dimensions, without false starts; vectors built the same way for training and assignment; "pendulum" only for runs below the short-run threshold | Labels mean what they say |
| Adaptive short-run: learn from the user's good-run threshold and the run-length distribution (e.g. p5, floored at half the configured value) instead of p20 | No built-in 20 % "short" rate |

The simulation's v2 path now runs the shipped code (`ml/behaviour_baseline.py`, `engine/anomaly_engine.evaluate_behaviour`, `ml/kmeans_v2.py`), with the coordinator's rules: transients and co-fire cycles are not scored, and a short run drops its run length (short_run and the pendulum detectors already cover it).

Result in this winter: 14 alerts instead of 233, 0.7 per fault-free week, and the water-flow loss found after 6 days (7 alerts).

Migration: on the first start after the update, the integration relearns every model once from the cycles table (marker `data_migration_ml_v2_completed`, rerun when the stored ML version differs or a v1 baseline is restored):
- the baseline replays the stored cycles (LWT from the features rows);
- the adaptive run lengths are rebuilt and bounded;
- the per-mode k-means is retrained and every `cycles.cluster_id` is reassigned;
- co-fire COP is repaired: cop_hourly hours holding boiler samples are rebuilt, and co-fire cycles get their COP from their pure-HP samples.

Still open for tuning on prod-1 data: a lower threshold (z ≥ 3.5) or a CUSUM on `dT_avg` would find the water-flow loss sooner, at the cost of some noise.

## Scenarios: weather, pendulum, hybrid and bivalent

`tools/sim_ml_scenarios.py` reruns the winter for three weathers:
- mild (+4 K, mean about 8 °C);
- normal;
- cold (−5 K, mean about −1 °C, cold snap to −15 °C).

It does so for three systems:
- heat pump only;
- hybrid EVLQ + gas boiler: co-fire below 4 °C, boiler alone below −2 °C;
- bivalent heat pump + external boiler (#288): parallel below −2 °C, boiler alone below −6 °C.

Each run injects 9 pendulum episodes:
- 3 heating episodes on the coldest afternoons;
- 3 heating episodes on the mildest afternoons (2 h of 6–12 min runs);
- 3 DHW episodes (4–5 starts in 1 h).

The integration's real `_alert_binary_states` runs on a real `CycleStore` after every cycle. Results: `img/sim_ml_scenarios_results.json`.

### Pendulum detection: correct everywhere

| | Mild | Normal | Cold |
|---|---|---|---|
| Episodes detected (heat pump / hybrid / bivalent) | 9/9 · 9/9 · 9/9 | 9/9 · 9/9 · 9/9 | 9/9 · 9/9 · 9/9 |
| Heating episode → first alert | 7–11 min | 7–11 min | 7–11 min |
| DHW episode → `dhw_pendulum` | 30–40 min (third start) | 30–37 min | 36–40 min |
| Real short runs outside episodes | 101 (mild days) | 13 | 1 |
| Detector on without a short run in the last hour | 0 | 1 (`short_off`) | 0 |

Heating episodes fire `short_run` at the first short run, then `short_cycling_pattern` and `pendulum_hourly`. DHW pendulum needs 3 DHW starts in an hour, by design.

### ML anomaly per scenario

| ml_anomaly alerts per week (v1 / v2) | Mild | Normal | Cold |
|---|---|---|---|
| Heat pump | 24.0 / 0.1 | 17.9 / 0.5 | 9.4 / 0.2 |
| Hybrid | 25.7 / 0.4 | 26.0 / 0.4 | 19.3 / 0.0 |
| Bivalent | 24.0 / 0.1 | 17.5 / 0.4 | 11.9 / 0.0 |

**Pendulum episodes:** `ml_anomaly` fires in 5–9 of the 9 episodes per scenario with v1, and in 1–3 with v2. A short run no longer feeds its run length to the baseline (the pendulum alerts already catch every episode), so the remaining v2 alerts are on dT / compressor speed during the episode.

**k-means v2** (last 28 days, per mode): no run of 20 min or more is labelled "pendulum" in any scenario (v1: 838 of 852). Heating gets a "pendulum" cluster only when the window holds enough short runs (the hybrid scenarios); short runs elsewhere land in "normal", which the short-run detector covers.

### Hybrid and bivalent: boiler co-fire

| | Mild hybrid | Normal hybrid | Cold hybrid | Normal bivalent | Cold bivalent |
|---|---|---|---|---|---|
| Co-fire cycles | 87 | 193 | 175 | 10 | 64 |
| Cycle `cop_avg` vs the true heat-pump COP | +55 % | +71 % | +94 % | +53 % | +64 % |
| Co-fire cycles flagged `ml_anomaly` (current) | 87 of 87 | 190 of 193 | 172 of 175 | 10 of 10 | 64 of 64 |
| … of which notified (60 min dedup) | 74 | 175 | 161 | 8 | 64 |
| v2 | 0 | 0 | 0 | 0 | 0 |
| Per-cycle DB fallback (`_sample_aggregates`) vs true, v1 → #443 | +18 % → 0 % | +16 % → 0 % | +37 % → 0 % | +19 % → 0 % | +29 % → 0 % |
| Pure-HP sample paths (cop today, SPF, curve, hybrid hourly) vs true | +4 % | +3 % | +1 % | +3 % | +2 % |
| All samples (no boiler filter) vs true | +12 % | +12 % | +41 % | +15 % | +17 % |

What this shows:
- **Sample level is right.** COP today, SPF, the heating-curve fit, the hourly rollup and the hybrid hourly COP all drop boiler samples. They read a few percent high only because they leave out the co-fire periods, which are the colder ones.
- **Cycle level is not.**
  - The per-cycle `cop_avg` is built from every live tick, co-fire included. Flow × ΔT then contains boiler heat, so the cycle COP reads 53–94 % too high, and the DB fallback 16–37 % too high.
  - Co-fire cycles are kept out of the ML baseline (v1.17.2) but are **still evaluated** against it, so nearly every co-fire cycle raises `ml_anomaly`. This is the largest single noise source for hybrid users.
  - k-means trains on them too (20 co-fire cycles in the last cold-hybrid week).
- **Rebuild path:** `_rebuild_cop_hourly_for_hours` (migrations v19 / v30 / v31) has no boiler filter, unlike the live hourly rollup. Hours rebuilt on a hybrid or bivalent install keep co-fire samples.

Fixed in #443:
- the live cycle COP skips ticks with a trusted boiler signal;
- `_sample_aggregates` and `_rebuild_cop_hourly_for_hours` drop boiler samples;
- co-fire cycles are neither scored nor learned by the ML, and k-means leaves them out;
- the relearn repairs stored values once.

The +53–94 % row is the source COP of a co-fire cycle; the integration no longer stores it as the cycle COP.

## Further finding: `lwt_avg` is never filled in production (fixed in #443)

`_accumulate_cycle_samples` looks for the keys `lwt`, `leaving_water_temp`, `leaving_temp` and `R2T`. The source attributes are ESPAltherma labels (`Leaving water temp. after BUH (R2T)`), so `lwt_avg` stays empty and the ML dimension is always 0. The #436 diagnostics confirm it: the baseline mean of `lwt_avg` is exactly 0.0 in both modes. The status report reads `attrs.get('leaving_water_temp')`, so its LWT line is always empty too. Since #443 both read the ESPAltherma labels (R2T, then R1T).

## Reproduce

    python tools/sim_ml_winter.py --out docs/design/img
    python tools/sim_ml_scenarios.py --out docs/design/img

The tool runs on the integration's code at the checked-out version; the
weather, the house and the faults are in the tool (seed 7).
