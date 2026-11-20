"""Three-month winter simulation of the Daikin Cycle ML ML pipeline.

Drives the integration's real ML code with synthetic cycles of an 8 kW
split heat pump (ERGA-class, radiators + underfloor) from 1 Dec to 28 Feb:

- ml.multi_baseline.MultiBaseline + engine.anomaly_engine.evaluate
  (ml_anomaly alert, 60 min dedup as ALERT_DEDUP_DEFAULTS)
- ml.adaptive_thresholds.AdaptiveThresholds (observe_cycle / observe_day)
- ml.clustering.kmeans + classify_clusters + nearest_centroid (weekly,
  last 7 days, as async_run_kmeans / _assign_cluster)
- engine.quality_scorer.score_cycle
- coordinator._classify_transient

in the order of coordinator._process_new_cycle. Two faults are injected
so the alerts can be scored: a clogging filter (flow 17 -> 10 l/min,
4-14 Feb) and a slow COP loss (-15 %, 15-28 Feb).

A second pipeline ("v2", shipped with #443: ml.behaviour_baseline +
engine.anomaly_engine.evaluate_behaviour) runs on the same cycles for
comparison; "current" is the v1 path (MultiBaseline, kept as a module).

Usage:  python tools/sim_ml_winter.py [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.daikin_cycle_ml.coordinator import _classify_transient  # noqa: E402
from custom_components.daikin_cycle_ml.engine.anomaly_engine import (  # noqa: E402
    evaluate,
    evaluate_behaviour,
)
from custom_components.daikin_cycle_ml.engine.quality_scorer import score_cycle  # noqa: E402
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import AdaptiveThresholds  # noqa: E402
from custom_components.daikin_cycle_ml.ml.behaviour_baseline import (  # noqa: E402
    BehaviourBaseline,
    behaviour_values,
)
from custom_components.daikin_cycle_ml.ml.clustering import (  # noqa: E402
    classify_clusters,
    kmeans,
    nearest_centroid,
)
from custom_components.daikin_cycle_ml.ml.features import (  # noqa: E402
    FEATURE_NAMES,
    VECTOR_LEN,
    extract_feature_vector,
    extract_many,
)
from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline  # noqa: E402

DAY = 86400.0
DAYS = 90
T0 = 1796083200.0  # 2026-12-01 00:00 UTC
FILTER_FAULT = (65, 75)   # day index 65..74 = 4-13 Feb: flow 17 -> 10 l/min
COP_FAULT = (76, 90)      # 15-28 Feb: COP -15 % (slow)
DEDUP_S = 3600.0          # ALERT_DEDUP_DEFAULTS["ml_anomaly"] = 60 min
SHORT_RUN_MIN = 20


# ---------------------------------------------------------------- weather

def weather(rng: random.Random) -> list[float]:
    """Hourly outdoor temperature, 90 days (Dutch / Belgian winter)."""
    daily, x = [], 0.0
    for d in range(DAYS):
        x = 0.8 * x + rng.gauss(0, 1.6)
        base = 6.5 - 2.5 * math.sin(math.pi * d / DAYS)  # coldest mid-winter
        if 40 <= d < 47:      # cold snap 10-16 Jan
            base -= 9.0 * math.sin(math.pi * (d - 39) / 8)
        if 71 <= d < 76:      # mild spell 10-14 Feb
            base += 6.0
        daily.append(base + x)
    hourly = []
    for d in range(DAYS):
        for h in range(24):
            hourly.append(daily[d] + 3.0 * math.sin(2 * math.pi * (h - 9) / 24) + rng.gauss(0, 0.4))
    return hourly


# ---------------------------------------------------------------- house + heat pump

H_W_K, GAINS_W, T_IN = 150.0, 400.0, 20.5


def load_kw(t: float) -> float:
    return max(0.0, (H_W_K * (T_IN - t) - GAINS_W) / 1000.0)


def p_min(t: float) -> float:
    return 2.3 + 0.03 * t


def p_max(t: float) -> float:
    return min(8.5, 7.6 + 0.12 * t)


def lwt_curve(t: float) -> float:
    return max(26.0, min(42.0, 33.0 - 0.6 * t))


def cop(lwt: float, t: float, factor: float) -> float:
    tc, te = lwt + 3.0 + 273.15, t - 6.0 + 273.15
    return 0.48 * tc / (tc - te) * factor


def defrost_rate(t: float) -> float:
    """Defrosts per hour of runtime (humid -2..+4 worst)."""
    if t > 6:
        return 0.0
    return 0.9 * math.exp(-((t - 1.0) / 4.0) ** 2) + (0.3 if t < -3 else 0.0)


# ---------------------------------------------------------------- cycle generator

def generate(seed: int = 7) -> tuple[list[dict], list[float]]:
    rng = random.Random(seed)
    temps = weather(rng)
    cycles: list[dict] = []
    t = T0
    end = T0 + DAYS * DAY
    last_end = None

    dhw_times = [T0 + dd * DAY + hh * 3600 for dd in range(DAYS) for hh in (6.5, 18.25)]

    def temp_at(ts: float) -> float:
        i = int((ts - T0) // 3600)
        return temps[min(max(i, 0), len(temps) - 1)]

    while t < end:
        d = int((t - T0) // DAY)
        to = temp_at(t)
        flow = 17.0
        if FILTER_FAULT[0] <= d < FILTER_FAULT[1]:
            flow = 17.0 - 7.0 * (d - FILTER_FAULT[0] + 1) / (FILTER_FAULT[1] - FILTER_FAULT[0])
        elif d >= FILTER_FAULT[1]:
            flow = 17.0  # filter cleaned
        cop_f = 1.0
        if COP_FAULT[0] <= d:
            cop_f = 1.0 - 0.15 * (d - COP_FAULT[0] + 1) / (COP_FAULT[1] - COP_FAULT[0])

        while dhw_times and dhw_times[0] < t - 3 * 3600:
            dhw_times.pop(0)  # missed by more than 3 h: skip
        due = dhw_times[0] if dhw_times else None
        if due is not None and due <= t + 1800:
            dhw_times.pop(0)
            # DHW run 40-55 min, tank 45 -> 50 °C
            start = max(t, due)
            dur = rng.uniform(40, 55) * 60
            cycles.append(_record("dhw", start, dur, temp_at(start), 5.5, 52.0, 58,
                                  flow, cop_f, rng, last_end))
            last_end = start + dur
            t = last_end + rng.uniform(60, 240)
            continue

        ld = load_kw(to)
        pm = p_min(to)
        nxt = dhw_times[0] if dhw_times else None
        horizon = (nxt - t) if nxt and nxt > t else 8 * 3600
        if ld >= pm:
            # continuous modulating run until the next DHW (or 8 h)
            dur = max(1800.0, min(horizon - 60, 8 * 3600 * rng.uniform(0.6, 1.0)))
            p = min(ld, p_max(to))
            buh = (ld > p_max(to) + 0.3 and rng.random() < 0.7) or (to < -5 and rng.random() < 0.25)
            rps = 18 + 60 * (p - pm) / max(0.1, p_max(to) - pm)
            cycles.append(_record("heating", t, dur, to, p, lwt_curve(to), rps,
                                  flow, cop_f, rng, last_end, buh=buh))
            last_end = t + dur
            t = last_end + rng.uniform(60, 600)
        else:
            duty = max(0.08, ld / pm)
            if duty < 0.3 and rng.random() < 0.5:  # mild: pendulum
                run = rng.uniform(8, 18) * 60
            else:
                run = max(600.0, rng.gauss(42, 10) * 60 * min(1.6, 0.5 + duty))
            off = run * (1 - duty) / duty
            cycles.append(_record("heating", t, run, to, pm, lwt_curve(to) + 1.5, 24,
                                  flow, cop_f, rng, last_end))
            last_end = t + run
            # start transient (1-2 min false start) on some mild restarts
            if duty < 0.5 and rng.random() < 0.15:
                ts = last_end + off * 0.5
                cycles.append(_record("heating", ts, rng.uniform(50, 110), to, pm, lwt_curve(to),
                                      45, flow, cop_f, rng, last_end, transient=True))
            t = last_end + off
    return cycles, temps


def _record(mode, start, dur, to, p_kw, lwt, rps, flow, cop_f, rng, last_end,
            buh=False, transient=False):
    cp = flow * 4.186 / 60.0  # kW/K
    dt_avg = p_kw / cp * rng.uniform(0.92, 1.08)
    runtime_h = dur / 3600.0
    n_def = 0
    if mode == "heating" and not transient:
        lam = defrost_rate(to) * runtime_h
        n_def = sum(1 for _ in range(int(lam * 3) + 1) if rng.random() < lam / (int(lam * 3) + 1))
    c = cop(lwt if mode == "heating" else 50.0, to, cop_f) * (0.93 if n_def else 1.0)
    if mode == "dhw":
        c *= 0.85
    c *= rng.uniform(0.96, 1.04)
    rec = {
        "start_ts": start, "end_ts": start + dur, "duration_s": int(dur), "mode": mode,
        "dT_max": round(dt_avg * rng.uniform(1.15, 1.45) + (1.5 if transient else 0), 2),
        "dT_avg": round(dt_avg, 2),
        "rps_max": int(min(110, rps * rng.uniform(1.1, 1.3))),
        "rps_avg": round(rps * rng.uniform(0.95, 1.05), 1),
        "outdoor_temp": round(to, 1),
        "buh_used": 1 if buh else 0, "buh_s": dur * rng.uniform(0.1, 0.4) if buh else None,
        "defrost_used": 1 if n_def else 0, "defrost_s": n_def * rng.uniform(240, 420) if n_def else None,
        "cop_avg": round(c, 2),
        "lwt_avg": round(lwt + rng.gauss(0, 0.4), 1),
        "indoor_temp_avg": round(T_IN + rng.gauss(0, 0.25), 2),
        "thermal_kw_avg": round(p_kw * rng.uniform(0.95, 1.05), 2),
        "off_s": None if last_end is None else max(0.0, start - last_end),
        "_flow": flow, "_cop_f": cop_f,
    }
    if transient:
        rec["rps_max"] = 48
        rec["dT_max"] = 1.2
    return rec


# ---------------------------------------------------------------- pipeline: current code

def run_current(cycles: list[dict]) -> dict:
    mb = MultiBaseline(VECTOR_LEN)
    adaptive = AdaptiveThresholds(min_samples=20)
    centroids: list[list[float]] = []
    labels: dict[int, str] = {}
    last_alert = -1e18
    out = defaultdict(list)
    next_kmeans = T0 + 6 * DAY + 4 * 3600  # first Sunday 04:00
    day_cycles = Counter()
    for rec in cycles:
        while rec["start_ts"] >= next_kmeans:
            window = [c for c in cycles if next_kmeans - 7 * DAY <= c["end_ts"] < next_kmeans]
            rows = [{k: v for k, v in c.items() if k not in ("lwt_avg", "indoor_temp_avg")} for c in window]
            vecs = extract_many(rows)  # DB rows: no lwt_avg / indoor_temp_avg columns
            if len(vecs) >= 3:
                res = kmeans(vecs, k=3)
                centroids = res.centroids
                labels = classify_clusters(centroids)
                out["kmeans"].append({
                    "day": int((next_kmeans - T0) // DAY),
                    "centroid_min": [round(c[0] / 60, 1) for c in centroids],
                    "labels": [labels[i] for i in range(len(centroids))],
                    "n": len(vecs),
                    "transients_in_training": sum(1 for c in window if _classify_transient(c)),
                    "modes_in_training": dict(Counter(c["mode"] for c in window)),
                })
            next_kmeans += 7 * DAY
        rec["is_transient"] = int(_classify_transient(rec))
        rec["quality_score"] = score_cycle(rec, {}, off_time_s=rec["off_s"])
        vec = extract_feature_vector(rec, cop_avg=rec["cop_avg"], lwt_avg=rec["lwt_avg"],
                                     indoor_temp_avg=rec["indoor_temp_avg"],
                                     thermal_kw_avg=rec["thermal_kw_avg"])
        cl = nearest_centroid(vec, centroids) if centroids else None
        rec["cluster"] = labels.get(cl) if cl is not None else None
        mode = rec["mode"]
        if not rec["is_transient"]:
            adaptive.observe_cycle(mode, rec["duration_s"], rec["off_s"])
        per_mode = mb.get(mode)
        updated = None
        if not rec["is_transient"] and not rec.get("boiler_contribution_samples"):
            updated = per_mode.update(vec)  # co-fire cycles are not learned (v1.17.2)
        res = evaluate(vec, per_mode, {})  # ... but are evaluated
        rec["z"] = res.max_abs_z
        rec["top"] = FEATURE_NAMES[res.top_dim] if res.top_dim is not None else None
        rec["anomaly"] = res.is_anomaly
        rec["skipped_update"] = updated is False
        if res.is_anomaly and rec["end_ts"] - last_alert >= DEDUP_S:
            rec["alert"] = True
            last_alert = rec["end_ts"]
        else:
            rec["alert"] = False
        day_cycles[int((rec["start_ts"] - T0) // DAY)] += 0 if rec["is_transient"] else 1
        d = int((rec["start_ts"] - T0) // DAY)
        if d >= 1 and d - 1 in day_cycles and not out.get("_day_done_" + str(d - 1)):
            adaptive.observe_day(day_cycles[d - 1])
            out["_day_done_" + str(d - 1)] = True
            out["adaptive"].append({"day": d - 1, **adaptive.suggest("heating")})
    out["final_baseline"] = {m: {"n": mb.get(m).sample_count,
                                 "std": dict(zip(FEATURE_NAMES, [round(x, 3) for x in mb.get(m).std], strict=True)),
                                 "mean": dict(zip(FEATURE_NAMES, [round(x, 2) for x in mb.get(m).mean], strict=True))}
                             for m in mb.modes()}
    return out


# ---------------------------------------------------------------- pipeline: v2 (#443, shipped)

def run_v2(cycles: list[dict]) -> None:
    """The shipped ML v2 path: BehaviourBaseline + evaluate_behaviour.

    Same rules as coordinator._ml_score_cycle: transients and co-fire
    cycles are not scored, a short run drops its run length.
    """
    bb = BehaviourBaseline()
    last_alert = -1e18
    for rec in cycles:
        rec["v2_alert"] = False
        rec["v2_z"] = 0.0
        if rec["is_transient"] or rec.get("boiler_contribution_samples"):
            continue
        vals = behaviour_values(rec, cop_avg=rec["cop_avg"], lwt_avg=rec["lwt_avg"],
                                thermal_kw_avg=rec["thermal_kw_avg"])
        if rec["duration_s"] < SHORT_RUN_MIN * 60:
            vals["duration_s"] = None
        res = evaluate_behaviour(bb, rec["mode"], vals, rec["outdoor_temp"])
        rec["v2_z"] = res.max_abs_z
        rec["v2_top"] = res.details.get("top_dim_name")
        if res.is_anomaly and rec["end_ts"] - last_alert >= DEDUP_S:
            rec["v2_alert"] = True
            last_alert = rec["end_ts"]


# ---------------------------------------------------------------- report

def summarize(cycles, cur):
    real = [c for c in cycles if not c["is_transient"]]
    weeks = defaultdict(lambda: Counter())
    for c in cycles:
        w = int((c["start_ts"] - T0) // (7 * DAY))
        weeks[w]["cycles"] += 0 if c["is_transient"] else 1
        weeks[w]["transients"] += c["is_transient"]
        weeks[w]["anomaly_cur"] += c["anomaly"]
        weeks[w]["alert_cur"] += c["alert"]
        weeks[w]["alert_v2"] += c["v2_alert"]
        weeks[w]["alert_cur_on_transient"] += c["alert"] and c["is_transient"]

    def in_fault(c):
        d = int((c["start_ts"] - T0) // DAY)
        return FILTER_FAULT[0] + 3 <= d < FILTER_FAULT[1] or d >= COP_FAULT[0] + 5

    def faultless(c):
        d = int((c["start_ts"] - T0) // DAY)
        return d < FILTER_FAULT[0] or (FILTER_FAULT[1] <= d < COP_FAULT[0])

    top = Counter(c["top"] for c in cycles if c["alert"])
    top_v2 = Counter(c.get("v2_top") for c in cycles if c["v2_alert"])
    pendulum_long = [c for c in real if c.get("cluster") == "pendulum" and c["duration_s"] >= SHORT_RUN_MIN * 60]
    pendulum_all = [c for c in real if c.get("cluster") == "pendulum"]
    short_real = [c for c in real if c["duration_s"] < SHORT_RUN_MIN * 60 and c["mode"] == "heating"]
    first20 = {m: [c for c in real if c["mode"] == m][:20] for m in ("heating", "dhw")}

    def det(key, lo, hi):
        hit = [c for c in cycles if lo <= int((c["start_ts"] - T0) // DAY) < hi and c[key]]
        return len(hit), (min(int((c["start_ts"] - T0) // DAY) for c in hit) - lo) if hit else None

    return {
        "cycles": len(real), "transients": sum(c["is_transient"] for c in cycles),
        "per_day": round(len(real) / DAYS, 1),
        "current": {
            "anomaly_cycles": sum(c["anomaly"] for c in cycles),
            "alerts": sum(c["alert"] for c in cycles),
            "alerts_fault_free_days": sum(c["alert"] for c in cycles if faultless(c)),
            "alerts_per_week_fault_free": round(sum(c["alert"] for c in cycles if faultless(c)) / ((FILTER_FAULT[0] + COP_FAULT[0] - FILTER_FAULT[1]) / 7), 1),
            "alerts_on_transients": sum(c["alert"] and c["is_transient"] for c in cycles),
            "alerts_first_20_heating": sum(c["alert"] for c in first20["heating"]),
            "alerts_first_20_dhw": sum(c["alert"] for c in first20["dhw"]),
            "updates_skipped_as_outlier": sum(c["skipped_update"] for c in cycles),
            "top_dims": dict(top.most_common()),
            "filter_fault_alerts_and_delay_days": det("alert", *FILTER_FAULT),
            "cop_fault_alerts_and_delay_days": det("alert", COP_FAULT[0], DAYS),
        },
        "v2": {
            "alerts": sum(c["v2_alert"] for c in cycles),
            "alerts_fault_free_days": sum(c["v2_alert"] for c in cycles if faultless(c)),
            "alerts_per_week_fault_free": round(sum(c["v2_alert"] for c in cycles if faultless(c)) / ((FILTER_FAULT[0] + COP_FAULT[0] - FILTER_FAULT[1]) / 7), 1),
            "top_dims": dict(top_v2.most_common()),
            "filter_fault_alerts_and_delay_days": det("v2_alert", *FILTER_FAULT),
            "cop_fault_alerts_and_delay_days": det("v2_alert", COP_FAULT[0], DAYS),
            "in_fault_share": round(sum(c["v2_alert"] for c in cycles if in_fault(c)) / max(1, sum(c["v2_alert"] for c in cycles)), 2),
        },
        "clusters": {
            "labelled_pendulum": len(pendulum_all),
            "pendulum_but_ge_20min": len(pendulum_long),
            "true_short_heating_runs": len(short_real),
            "kmeans_runs": cur["kmeans"],
        },
        "weeks": {w: dict(v) for w, v in sorted(weeks.items())},
        "adaptive_last": cur["adaptive"][-1] if cur["adaptive"] else {},
        "adaptive_first": next((a for a in cur["adaptive"] if len(a) > 1), {}),
        "final_baseline": cur["final_baseline"],
    }


def plots(cycles, temps, summary, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    days = [(c["start_ts"] - T0) / DAY for c in cycles]
    fig, ax = plt.subplots(4, 1, figsize=(11, 11), sharex=True)
    ax[0].plot([i / 24 for i in range(len(temps))], temps, lw=0.6, color="#1E88E5")
    ax[0].set_ylabel("Outdoor °C")
    ax[0].axvspan(*FILTER_FAULT, color="#FB8C00", alpha=0.15, label="filter clogging")
    ax[0].axvspan(COP_FAULT[0], DAYS, color="#E53935", alpha=0.12, label="COP loss")
    ax[0].legend(loc="upper right", fontsize=8)
    ax[0].set_title("Three-month winter: ML anomaly score per cycle")
    for i, (key, lab) in enumerate((("z", "current max |z|"), ("v2_z", "v2 max |z| (proposal)"))):
        a = ax[i + 1]
        col = ["#9E9E9E" if c["is_transient"] else ("#E53935" if c["mode"] == "dhw" else "#3949AB") for c in cycles]
        a.scatter(days, [min(30, c[key]) for c in cycles], s=4, c=col)
        alert_key = "alert" if key == "z" else "v2_alert"
        a.scatter([d for d, c in zip(days, cycles, strict=True) if c[alert_key]],
                  [min(30, c[key]) for c in cycles if c[alert_key]], s=18, facecolors="none", edgecolors="#000", lw=0.8)
        a.axhline(3.0 if key == "z" else 4.0, color="#FB8C00", ls="--", lw=1)
        a.set_ylabel(lab)
        a.set_ylim(0, 31)
        a.axvspan(*FILTER_FAULT, color="#FB8C00", alpha=0.15)
        a.axvspan(COP_FAULT[0], DAYS, color="#E53935", alpha=0.12)
    weeks = summary["weeks"]
    w = sorted(weeks)
    ax[3].bar([x * 7 + 2 for x in w], [weeks[x].get("alert_cur", 0) for x in w], width=3, label="alerts current", color="#8E24AA")
    ax[3].bar([x * 7 + 5 for x in w], [weeks[x].get("alert_v2", 0) for x in w], width=3, label="alerts v2", color="#43A047")
    ax[3].set_ylabel("ml_anomaly alerts / week")
    ax[3].set_xlabel("Day (1 Dec → 28 Feb)")
    ax[3].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "sim_ml_winter_z.png", dpi=110)
    plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    top = summary["current"]["top_dims"]
    ax[0].barh(list(top), list(top.values()), color="#8E24AA")
    ax[0].set_title("Current: top dimension of each alert")
    real = [c for c in cycles if not c["is_transient"] and c["mode"] == "heating" and c.get("cluster")]
    for lab, col in (("pendulum", "#E53935"), ("normal", "#43A047"), ("long_cycle", "#1E88E5")):
        xs = [c["duration_s"] / 60 for c in real if c["cluster"] == lab]
        ax[1].hist(xs, bins=60, range=(0, 600), alpha=0.6, label=lab, color=col)
    ax[1].axvline(SHORT_RUN_MIN, color="#000", ls="--", lw=1)
    ax[1].set_title("Current k-means label vs run length (heating)")
    ax[1].set_xlabel("run (min)")
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "sim_ml_winter_dims_clusters.png", dpi=110)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs/design/img"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cycles, temps = generate(args.seed)
    cur = run_current(cycles)
    run_v2(cycles)
    summary = summarize(cycles, cur)
    (out / "sim_ml_winter_results.json").write_text(json.dumps(summary, indent=1, default=str))
    plots(cycles, temps, summary, out)
    print(json.dumps({k: summary[k] for k in ("cycles", "transients", "per_day", "current", "v2")}, indent=1, default=str))


if __name__ == "__main__":
    main()
