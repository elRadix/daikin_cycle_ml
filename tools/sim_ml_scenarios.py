"""Scenario runs on top of tools/sim_ml_winter.py (#443).

For three winters (mild, normal, cold) and three systems (heat pump only,
hybrid EVLQ + gas boiler, bivalent heat pump + external boiler):

1. Pendulum detection: heating (mild and cold) and DHW short-cycling
   episodes are injected; the integration's real ``_alert_binary_states``
   (short_run, short_off, short_cycling_pattern, pendulum_hourly,
   pendulum_daily, dhw_pendulum, high_cycle_rate) is evaluated after every
   cycle on a real ``CycleStore``. Each episode must be detected; time to
   first detection and alerts outside episodes are reported.
2. ML: ml_anomaly alerts of the current code and of the v2 proposal, per
   scenario, and on boiler co-fire cycles.
3. Hybrid / bivalent COP: per-minute COP samples with boiler flags go into
   a real ``CycleDB``; the pure-HP paths (async_fetch_cop_samples with
   include_boiler=False + _aggregate_cop_rows) and the per-cycle fallback
   (_sample_aggregates) are compared with the true heat-pump COP.

Usage:  python tools/sim_ml_scenarios.py [--out DIR]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import tempfile
import time as _time
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sim_ml_winter as base  # noqa: E402

from custom_components.daikin_cycle_ml import coordinator as co  # noqa: E402
from custom_components.daikin_cycle_ml.ml import kmeans_v2  # noqa: E402
from custom_components.daikin_cycle_ml.storage.db import CycleDB  # noqa: E402
from custom_components.daikin_cycle_ml.storage.store import CycleStore  # noqa: E402

WEATHER = {"mild": +4.0, "normal": 0.0, "cold": -5.0}
SYSTEMS = ("hp", "hybrid", "bivalent")
OPTIONS = {
    "short_run_threshold_min": 20, "short_off_threshold_min": 5,
    "pendulum_cycles_per_hour": 4, "pendulum_cycles_per_day": 40,
    "dhw_pendulum_cycles_per_hour": 3, "short_cycling_min_cycles": 3,
    "short_cycling_window_min": 60,
}
PEND_KEYS = ("short_run", "short_off", "short_cycling_pattern", "pendulum_hourly",
             "pendulum_daily", "high_cycle_rate")


# ---------------------------------------------------------------- scenario data

def make_cycles(weather: str, system: str, seed: int) -> tuple[list[dict], list[dict]]:
    orig = base.weather
    base.weather = lambda rng: [t + WEATHER[weather] for t in orig(rng)]
    try:
        cycles, _ = base.generate(seed)
    finally:
        base.weather = orig
    rng = random.Random(seed + 1)
    for c in cycles:
        c["true_cop"] = c["cop_avg"]
        c["boiler_contribution_samples"] = 0
    if system != "hp":
        cycles = apply_boiler(cycles, system, rng)
    cycles, episodes = inject_pendulum(cycles, rng)
    _recompute_off(cycles)
    return cycles, episodes


def apply_boiler(cycles: list[dict], system: str, rng: random.Random) -> list[dict]:
    """Hybrid: co-fire below 4 °C, boiler only below -2 °C.
    Bivalent: parallel below -2 °C, alternative (boiler only) below -6 °C."""
    co_below, only_below = (4.0, -2.0) if system == "hybrid" else (-2.0, -6.0)
    out = []
    for c in cycles:
        t = c["outdoor_temp"]
        if c["mode"] == "heating" and t < only_below:
            continue  # heat pump off, boiler alone
        if c["mode"] == "heating" and t < co_below and rng.random() < 0.6:
            frac = min(0.8, 0.25 + 0.08 * (co_below - t))  # boiler share of the heat
            n = max(1, int(c["duration_s"] / 60 * frac))
            c["boiler_contribution_samples"] = n
            c["boiler_frac"] = frac
            # what the live tick average sees: flow x dT includes boiler heat
            c["thermal_kw_avg"] = round(c["thermal_kw_avg"] / (1 - frac), 2)
            c["dT_avg"] = round(c["dT_avg"] / (1 - frac), 2)
            c["cop_avg"] = round(c["true_cop"] / (1 - frac), 2)
        out.append(c)
    return out


def inject_pendulum(cycles: list[dict], rng: random.Random) -> tuple[list[dict], list[dict]]:
    """6 heating episodes (3 at the mildest, 3 at the coldest afternoons) of
    2 h with 6-12 min runs, and 3 DHW episodes of 4 starts in 1 h."""
    by_day: dict[int, list[float]] = {}
    for c in cycles:
        by_day.setdefault(int((c["start_ts"] - base.T0) // base.DAY), []).append(c["outdoor_temp"])
    days = sorted((d for d in by_day if 5 <= d < base.DAYS - 2), key=lambda d: sum(by_day[d]) / len(by_day[d]))
    chosen = [("heating_cold", d) for d in days[:3]] + [("heating_mild", d) for d in days[-3:]]
    chosen += [("dhw", d) for d in rng.sample(days[len(days) // 3: 2 * len(days) // 3], 3)]
    episodes = []
    for kind, d in chosen:
        start = base.T0 + d * base.DAY + (14.0 if kind != "dhw" else 20.5) * 3600
        end = start + (2 * 3600 if kind != "dhw" else 3600)
        cycles = [c for c in cycles if c["end_ts"] <= start or c["start_ts"] >= end]
        t, n = start, 0
        while t < end - 300:
            run = rng.uniform(6, 12) * 60 if kind != "dhw" else rng.uniform(5, 9) * 60
            to = rng.choice(by_day[d])
            rec = base._record("heating" if kind != "dhw" else "dhw", t, run, to, base.p_min(to),
                               base.lwt_curve(to) if kind != "dhw" else 48.0, 30, 17.0, 1.0, rng, None)
            rec["true_cop"] = rec["cop_avg"]
            rec["boiler_contribution_samples"] = 0
            rec["episode"] = len(episodes)
            cycles.append(rec)
            n += 1
            t += run + (rng.uniform(4, 10) * 60 if kind != "dhw" else rng.uniform(6, 9) * 60)
        episodes.append({"id": len(episodes), "kind": kind, "day": d, "start": start, "end": end,
                         "cycles": n, "outdoor": round(sum(by_day[d]) / len(by_day[d]), 1)})
    cycles.sort(key=lambda c: c["start_ts"])
    return cycles, episodes


def _recompute_off(cycles: list[dict]) -> None:
    last = None
    for c in cycles:
        c["off_s"] = None if last is None else max(0.0, c["start_ts"] - last)
        last = c["end_ts"]


# ---------------------------------------------------------------- pendulum detectors

def detector_states(cycles: list[dict]) -> None:
    """Real _alert_binary_states after every cycle (clock pinned at close)."""
    store = CycleStore(maxlen=200)
    clock = {"now": 0.0}
    fake_time = types.SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time) if not k.startswith("_")})
    fake_time.time = lambda: clock["now"]
    stub = types.SimpleNamespace(
        store=store, options=OPTIONS, _effective_threshold=lambda k, d: d,
        _compute_setpoint_oscillating=lambda: False, _db_retention_stale={"fired": False},
        _kmeans_stale={"fired": False}, _energy_daily_anomaly={"fired": False},
        _defrost_7d_sum=0, _buh_7d_ratio=0.0,
    )
    snap = types.SimpleNamespace(mode="heating", anomaly=None, cop_degradation_week_pct=None,
                                 cop_vs_datasheet_pct=None, last_success_ts=0.0,
                                 missing_attrs=[], advice=[])
    real_time = co.time
    co.time = fake_time
    try:
        for c in cycles:
            store.add_cycle({k: c[k] for k in ("start_ts", "end_ts", "duration_s", "mode", "off_s",
                                                "is_transient", "dT_max", "rps_max")})
            clock["now"] = c["end_ts"] + 30
            snap.last_success_ts = clock["now"]
            st = co.DaikinCycleMLCoordinator._alert_binary_states(stub, snap)
            c["det"] = {k: bool(st.get(k)) for k in (*PEND_KEYS, "dhw_pendulum")}
    finally:
        co.time = real_time


def pendulum_report(cycles: list[dict], episodes: list[dict]) -> dict:
    out = []
    for ep in episodes:
        keys = ("dhw_pendulum",) if ep["kind"] == "dhw" else PEND_KEYS
        hits = [c for c in cycles if ep["start"] <= c["end_ts"] <= ep["end"] + 600
                and any(c["det"].get(k) for k in keys)]
        fired = sorted({k for c in hits for k in keys if c["det"].get(k)})
        first = min((c["end_ts"] for c in hits), default=None)
        out.append({**{k: ep[k] for k in ("kind", "day", "outdoor", "cycles")},
                    "detected": bool(hits),
                    "minutes_to_detect": None if first is None else round((first - ep["start"]) / 60),
                    "detectors": fired})
    # false positive = a detector on while the last hour holds no short run
    thr = OPTIONS["short_run_threshold_min"] * 60
    normal = [c for c in cycles if "episode" not in c and not c["is_transient"]]
    fp: Counter = Counter()
    for c in normal:
        recent = [x for x in cycles if c["end_ts"] - 3600 <= x["end_ts"] <= c["end_ts"]
                  and not x["is_transient"]]
        short_recent = any(x["duration_s"] < thr for x in recent)
        dhw_recent = sum(1 for x in recent if x["mode"] == "dhw") >= OPTIONS["dhw_pendulum_cycles_per_hour"]
        for k in (*PEND_KEYS, "dhw_pendulum"):
            if c["det"].get(k) and not (dhw_recent if k == "dhw_pendulum" else short_recent or k == "pendulum_daily"):
                fp[k] += 1
    real_short = sum(1 for c in normal if c["duration_s"] < thr and c["mode"] == "heating")
    return {"episodes": out, "false_positive_cycles": dict(fp), "normal_cycles": len(normal),
            "real_short_runs_outside_episodes": real_short}


# ---------------------------------------------------------------- hybrid / bivalent COP

async def sample_level(cycles: list[dict]) -> dict:
    """Per-minute COP samples (boiler-flagged) through the real DB paths."""
    co_cycles = [c for c in cycles if c.get("boiler_contribution_samples")][:12]
    hp_cycles = [c for c in cycles if not c.get("boiler_contribution_samples")
                 and c["mode"] == "heating" and not c["is_transient"]][:12]
    if not co_cycles:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        db = CycleDB(str(Path(tmp) / "s.db"))
        await db.async_open()
        await db.async_initialize()
        truth, fallback, true_samples = [], [], []
        for c in co_cycles + hp_cycles:
            n = int(c["duration_s"] // 60)
            nb = int(c.get("boiler_contribution_samples") or 0)
            for i in range(n):
                boiler = i >= n - nb  # boiler joins in the second part of the run
                cop = c["true_cop"] / (1 - c.get("boiler_frac", 0.0)) if boiler else c["true_cop"]
                true_samples.append(c["true_cop"])
                await db.async_insert_cop_sample({
                    "ts": c["start_ts"] + 60 * i + 30, "cop": round(cop, 3), "lwt": c["lwt_avg"],
                    "outdoor": c["outdoor_temp"], "flow_lmin": 17.0, "mode": c["mode"],
                    "boiler_active": boiler, "boiler_mode": "heat" if boiler else "",
                })
        for c in co_cycles:
            avg, _n = await db._sample_aggregates(c["start_ts"], c["end_ts"], mode=c["mode"])
            truth.append(c["true_cop"])
            fallback.append(avg)
        pure = await db.async_fetch_cop_samples(days=36500, include_boiler=False, include_artifacts=False)
        alls = await db.async_fetch_cop_samples(days=36500, include_boiler=True, include_artifacts=False)
        stats_pure, _ = co.DaikinCycleMLCoordinator._aggregate_cop_rows(pure, since_ts=0.0)
        stats_all, _ = co.DaikinCycleMLCoordinator._aggregate_cop_rows(alls, since_ts=0.0)
        await db.async_close()
    true_mean = sum(true_samples) / len(true_samples)  # sample-weighted, like the DB paths
    return {
        "true_hp_cop_mean": round(true_mean, 2),
        "pure_hp_path_cop_mean": round(stats_pure["cop_mean"] or 0, 2),
        "all_samples_cop_mean": round(stats_all["cop_mean"] or 0, 2),
        "boiler_samples_excluded": len(alls) - len(pure),
        "cycle_fallback_cop_vs_true_pct": round(100 * (sum(f for f in fallback if f) / sum(truth) - 1), 1),
    }


# ---------------------------------------------------------------- run

def kmeans_v2_report(cycles: list[dict]) -> dict:
    """Shipped per-mode k-means (#443) on the last 28 days, every cycle assigned."""
    window = [c for c in cycles if c["end_ts"] >= base.T0 + (base.DAYS - 28) * base.DAY]
    state = kmeans_v2.train(window, short_run_min=base.SHORT_RUN_MIN)
    lbl = kmeans_v2.labels(state)
    tally: Counter = Counter()
    for c in window:
        cid = None if c["is_transient"] or c.get("boiler_contribution_samples") else kmeans_v2.assign(
            state, c["mode"], kmeans_v2.behaviour_values(c, lwt_avg=c["lwt_avg"]))
        name = lbl.get(cid) if cid is not None else None
        short = c["duration_s"] < base.SHORT_RUN_MIN * 60
        tally[f"{name}_{'short' if short else 'ge20'}"] += 1
    return {
        "modes": {m: {"labels": v["labels"], "sizes": v["sizes"], "n": v["n"]}
                  for m, v in state["modes"].items()},
        "assigned": dict(tally),
    }


def run(weather: str, system: str, seed: int = 7) -> dict:
    cycles, episodes = make_cycles(weather, system, seed)
    cur = base.run_current(cycles)
    base.run_v2(cycles)
    detector_states(cycles)
    cofire = [c for c in cycles if c.get("boiler_contribution_samples")]
    healthy = [c for c in cycles if "episode" not in c]
    weeks = base.DAYS / 7
    res = {
        "cycles": sum(1 for c in cycles if not c["is_transient"]),
        "pendulum": pendulum_report(cycles, episodes),
        "ml": {
            "alerts_current_per_week": round(sum(c["alert"] for c in healthy) / weeks, 1),
            "alerts_v2_per_week": round(sum(c["v2_alert"] for c in healthy) / weeks, 1),
            "pendulum_episodes_with_ml_alert_current": sum(
                1 for e in episodes if any(c["alert"] for c in cycles if c.get("episode") == e["id"])),
            "pendulum_episodes_with_ml_alert_v2": sum(
                1 for e in episodes if any(c["v2_alert"] for c in cycles if c.get("episode") == e["id"])),
        },
        "kmeans_last": cur["kmeans"][-1] if cur["kmeans"] else None,
        "kmeans_v2": kmeans_v2_report(cycles),
    }
    if cofire:
        res["boiler"] = {
            "cofire_cycles": len(cofire),
            "cofire_cycle_cop_avg_vs_true_pct": round(100 * (sum(c["cop_avg"] for c in cofire) / sum(c["true_cop"] for c in cofire) - 1), 1),
            "ml_alerts_current_on_cofire": sum(c["alert"] for c in cofire),
            "ml_anomaly_current_on_cofire": sum(c["anomaly"] for c in cofire),
            "ml_alerts_v2_on_cofire": sum(c["v2_alert"] for c in cofire),
            "cofire_cycles_in_last_kmeans_window": sum(
                1 for c in cofire if c["end_ts"] >= base.T0 + (base.DAYS - 7) * base.DAY),
            "samples": asyncio.run(sample_level(cycles)),
        }
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs/design/img"))
    args = ap.parse_args()
    results = {}
    for w in WEATHER:
        for s in SYSTEMS:
            results[f"{w}/{s}"] = run(w, s)
            r = results[f"{w}/{s}"]
            det = sum(e["detected"] for e in r["pendulum"]["episodes"])
            print(f"{w:6} {s:8} cycles {r['cycles']:5}  pendulum {det}/{len(r['pendulum']['episodes'])}"
                  f"  fp {r['pendulum']['false_positive_cycles']}  ml cur {r['ml']['alerts_current_per_week']}"
                  f"/wk v2 {r['ml']['alerts_v2_per_week']}/wk"
                  + (f"  cofire {r['boiler']['cofire_cycles']} cop {r['boiler']['cofire_cycle_cop_avg_vs_true_pct']:+}%"
                     f" ml-on-cofire {r['boiler']['ml_alerts_current_on_cofire']}/{r['boiler']['ml_alerts_v2_on_cofire']}"
                     if "boiler" in r else ""))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "sim_ml_scenarios_results.json").write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
