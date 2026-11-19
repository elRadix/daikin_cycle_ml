#!/usr/bin/env python3
"""#368 Phase 2: simulate the Energy Balance Engine + Adaptive Floor Buffer.

House model (2 nodes: floor screed + room) heated by a modulating heat pump on
a weather curve, calibrated to prod-1 (ETVX12S23 12 kW, underfloor heating;
v1.23.3 diagnostics + SQL of 2026-11-19):

* 2.55 kW heat at 16 rps (minimum modulation) at 9.6 C outdoor, room 20 C,
  LW setpoint 28.6 C, LWT 29.6 / RWT 27.5 at 18.3 l/min (dT 2.1 K);
* COP per outdoor bucket 4.8 (-1 C) ... 6.3 (9 C) at LWT ~30 C;
* 22-24 h compressor time on cold days, single 9-12 h pauses on mild days
  (room thermostat active: RT setpoint 20 C).

The engine of #368 (as specified) and an enhanced engine (proposed) run on
what the integration measures: flow x dT from 0.1 K sensors, the rounded
indoor temperature, day / night. Both are compared with the model's truth.

Scenarios: mild (9-17 C, sunny), shoulder (5-11 C), cold (-6-0 C), weather
curve only (#368 scope 2), each with V0 no automation, V1 #368 automation
(-5 K on "saturated", restore on "empty"), V2 the same automation on the
enhanced screed signals, V3 advisory curve trim above the turnover point.
A calibration run uses prod-1's control (weather curve + room thermostat).

Usage: python3 tools/sim_energy_balance.py --out DIR   (PNGs + results.json)
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DT = 30.0                       # s, coordinator tick
CP = 4186.0
H_TRUE = 260.0                  # W/K envelope
GAIN_BASE = 250.0               # W internal (+250 W 18-23 h)
C_FLOOR = 4.0 * 3.6e6           # J/K screed (4.0 kWh/K)
C_ROOM = 6.0 * 3.6e6            # J/K room, furniture, inner walls
UA_PIPE, UA_FLOOR = 1100.0, 600.0
MCP0 = 18.3 / 60.0 * CP
P_MAX = 9000.0
ROOM_SET = 20.0


def p_min(t_out: float) -> float:
    """Minimum modulation heat (16 rps): 2.55 kW at 9.6 C."""
    return max(1900.0, 2200.0 + 36.0 * t_out)


def lwt_curve(t_out: float) -> float:
    """prod-1 weather curve: 28.6 C at 9.6 C, floor 25 C."""
    return min(45.0, max(25.0, 28.6 + 0.85 * (9.6 - t_out)))


def cop(lwt: float, t_out: float) -> float:
    """0.612 x Carnot, fitted to prod-1's COP per outdoor bucket."""
    return 0.612 * (lwt + 273.15) / max(8.0, lwt - t_out + 8.0)


@dataclass
class Weather:
    name: str
    t_mean: float
    t_amp: float
    sun_w: float
    days: int = 3


SCENARIOS = {
    "mild": Weather("Mild & sunny 9-17 C (overshoot)", 13.0, 4.0, 1500.0),
    "shoulder": Weather("Shoulder 5-11 C (prod-1 November)", 8.0, 3.0, 700.0),
    "cold": Weather("Cold -6-0 C (defrost, full load)", -3.0, 3.0, 400.0),
}
LEARN = [Weather("learn", t, 3.0, s, 2) for t, s in ((6, 300), (1, 900), (11, 200), (-2, 600), (8, 1200),
                                                      (3, 100), (13, 700), (-5, 1000), (9, 400), (4, 1300))]


def outdoor(w: Weather, t: float) -> float:
    return w.t_mean + w.t_amp * math.cos(((t / 3600.0) % 24 - 15.0) / 24.0 * 2 * math.pi)


def sun_frac(t: float) -> float:
    h = (t / 3600.0) % 24
    return max(0.0, math.sin(math.pi * (h - 8.0) / 9.0)) if 8 <= h <= 17 else 0.0


def gains(w: Weather, t: float) -> float:
    h = (t / 3600.0) % 24
    return GAIN_BASE + (250.0 if 18 <= h < 23 else 0.0) + w.sun_w * sun_frac(t)


@dataclass
class Engine:
    """#368 as specified (u, pmin, buffer, dT saturation) + enhanced signals."""
    u_num: float = 0.0
    u_den: float = 0.0
    u_pts: list = field(default_factory=list)
    pmin: dict = field(default_factory=dict)
    pmin_rps: dict = field(default_factory=dict)          # enhanced: hours at minimum rps only
    day_pts: list = field(default_factory=list)          # (degree-h, sun-h, heat kWh) per day
    acc: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    emit_pts: list = field(default_factory=list)         # (Tw_mean - Tin, P) steady hours
    win: list = field(default_factory=list)
    e_buf: float = 0.0
    sat_ticks: int = 0
    tau_pts: list = field(default_factory=list)          # screed decay time constants (h)
    off_track: list = field(default_factory=list)
    screed_est: float | None = None

    # --- #368 as specified ---------------------------------------------------------
    @property
    def u(self) -> float | None:
        return self.u_num / self.u_den if self.u_den > 0 and len(self.u_pts) >= 6 else None

    def pmin_fit(self) -> tuple[float, float] | None:
        if len(self.pmin) < 3:
            return None
        x = np.array(sorted(self.pmin)) + 1.0
        return tuple(float(v) for v in np.polyfit(x, [self.pmin[k] for k in sorted(self.pmin)], 1))

    def pmin_rps_fit(self) -> tuple[float, float] | None:
        if len(self.pmin_rps) < 2:
            return None
        x = np.array(sorted(self.pmin_rps)) + 1.0
        return tuple(float(v) for v in np.polyfit(x, [self.pmin_rps[k] for k in sorted(self.pmin_rps)], 1))

    def turnover(self, enhanced: bool = False) -> float | None:
        pm = self.pmin_rps_fit() if enhanced else self.pmin_fit()
        if pm is None:
            return None
        if enhanced and self.house():
            u, g0, _ = self.house()                       # loss_net = u*dT - g0
            return (ROOM_SET * u - g0 - pm[1]) / (u + pm[0])
        if self.u is None:
            return None
        return (ROOM_SET * self.u - pm[1]) / (self.u + pm[0])

    # --- enhanced ------------------------------------------------------------------
    def house(self) -> tuple[float, float, float] | None:
        """Daily energy balance: heat = U*degree_h - g0*24h - s*sun_h  (least squares)."""
        if len(self.day_pts) < 4:
            return None
        a = np.array([[p[0], -24.0, -p[1]] for p in self.day_pts])
        b = np.array([p[2] * 1000.0 for p in self.day_pts])
        sol, *_ = np.linalg.lstsq(a, b, rcond=None)
        return float(sol[0]), float(sol[1]), float(sol[2])

    def emitter(self) -> float | None:
        if len(self.emit_pts) < 6:
            return None
        x = np.array([p[0] for p in self.emit_pts])
        y = np.array([p[1] for p in self.emit_pts])
        return float((x * y).sum() / (x * x).sum())

    def tau(self) -> float | None:
        return float(np.median(self.tau_pts)) if len(self.tau_pts) >= 2 else None

    def net_loss(self, t_in: float, t_out: float, sunf: float) -> float | None:
        hs = self.house()
        if not hs:
            return None
        u, g0, s = hs
        return max(0.0, u * (t_in - t_out) - g0 - s * sunf)

    def tick(self, m: dict) -> dict:
        self.win.append(m)
        if len(self.win) > 120:
            self.win.pop(0)
        if m["mode"] == "heating":
            self.acc[0] += (m["t_in"] - m["t_out"]) * DT / 3600.0
            self.acc[1] += m["sunf"] * DT / 3600.0
            self.acc[2] += m["p_meas"] * DT / 3.6e6
        if int(m["t"]) % 86400 == 0:                       # day end
            if self.acc[0] > 0:
                self.day_pts.append(tuple(self.acc))
            self.acc = [0.0, 0.0, 0.0]
        if len(self.win) == 120 and int(m["t"]) % 3600 == 0:
            on = all(x["on"] and x["mode"] == "heating" and not x["defrost"] for x in self.win)
            p = sum(x["p_meas"] for x in self.win) / 120.0
            d_t = sum(x["t_in"] - x["t_out"] for x in self.win) / 120.0
            steady = abs(self.win[-1]["t_in"] - self.win[0]["t_in"]) <= 0.1
            if on and steady and m["night"] and d_t > 3:
                self.u_pts.append((d_t, p))
                self.u_num += p * d_t
                self.u_den += d_t * d_t
            if on:
                br = int(math.floor(sum(x["t_out"] for x in self.win) / 240.0) * 2)
                self.pmin[br] = min(self.pmin.get(br, 1e9), p)
                if sum(1 for x in self.win if x["at_min"]) >= 96:          # >= 80 % at minimum rps
                    self.pmin_rps[br] = min(self.pmin_rps.get(br, 1e9), p)
                tw = sum((x["lwt"] + x["rwt"]) / 2 - x["t_in"] for x in self.win) / 120.0
                if tw > 1:
                    self.emit_pts.append((tw, p))
        # screed temperature: RWT while the pump runs and the compressor is off
        if not m["on"] and m["mode"] == "heating" and m["flow"] > 5:
            self.screed_est = m["rwt"]
            self.off_track.append((m["t"], m["rwt"] - m["t_in"]))
        else:
            if len(self.off_track) >= 120:                 # >= 1 h of decay: tau from log-slope
                t0, x0 = self.off_track[0]
                t1, x1 = self.off_track[-1]
                if x0 > 1.0 and x1 > 0.3 and x1 < x0:
                    self.tau_pts.append((t1 - t0) / 3600.0 / math.log(x0 / x1))
            self.off_track = []
            if m["on"] and not m["defrost"] and self.emitter():
                # screed = mean water - P / UA_pipe ; UA_pipe ~ 2x emitter (series pipe + floor)
                self.screed_est = (m["lwt"] + m["rwt"]) / 2 - m["p_meas"] / (2.0 * self.emitter())
        out = {"loss_est": None, "status": None, "e_buf": None, "sat": False, "empty": True,
               "sat2": False, "empty2": True, "excess_k": None, "status2": None}
        u = self.u
        if u is not None:
            loss = u * (m["t_in"] - m["t_out"])
            p60 = sum(x["p_meas"] for x in self.win) / len(self.win)
            l60 = sum(u * (x["t_in"] - x["t_out"]) for x in self.win) / len(self.win)
            tol = max(150.0, 0.1 * l60)
            out["status"] = "BALANCED" if abs(p60 - l60) <= tol else ("OVERPRODUCING" if p60 > l60 else "UNDERPRODUCING")
            if m["mode"] == "heating":
                self.e_buf = max(0.0, self.e_buf + (m["p_meas"] - loss) * DT / 3.6e6)
            self.sat_ticks = self.sat_ticks + 1 if (m["on"] and m["dt"] < 2.0 and m["flow"] > 15) else 0
            out.update(loss_est=loss, e_buf=self.e_buf, sat=self.sat_ticks >= 20, empty=self.e_buf <= 0.05)
        nl = self.net_loss(m["t_in"], m["t_out"], m["sunf"])
        em = self.emitter()
        if nl is not None and em and self.screed_est is not None:
            need = ROOM_SET + nl / (2.0 * em)               # screed temperature that covers the loss
            exc = self.screed_est - need
            out["excess_k"] = exc
            out["sat2"] = exc > 1.0 and m["t_in"] > ROOM_SET
            out["empty2"] = exc < 0.0 or m["t_in"] < ROOM_SET - 0.3
            p60 = sum(x["p_meas"] for x in self.win) / len(self.win)
            tol = max(150.0, 0.1 * nl)
            out["status2"] = "BALANCED" if abs(p60 - nl) <= tol else ("OVERPRODUCING" if p60 > nl else "UNDERPRODUCING")
        return out


def run(w: Weather, variant: str, eng: Engine, *, control: str = "war", flow_lpm: float = 18.3,
        seed: int = 1, record: bool = True) -> dict:
    rng = np.random.default_rng(seed)
    mcp = flow_lpm / 60.0 * CP
    eps = 1.0 - math.exp(-UA_PIPE / mcp)
    t_floor, t_room = 24.0, 20.2
    on, off_s, hot_s, start_s = True, 0.0, 0.0, 0.0
    offset, run_since_df, df_left, rt_off = 0.0, 0.0, 0.0, False
    starts, comp_s, e_el, e_th = 0, 0.0, 0.0, 0.0
    hist_p: list = []
    ts: dict[str, list] = {k: [] for k in ("h", "t_out", "t_in", "p", "loss_true", "loss_est", "e_est", "e_true",
                                          "excess", "sat", "sat2", "dt", "on", "status", "status2", "true_state")}
    for i in range(int(w.days * 86400 / DT)):
        t = i * DT
        h = (t / 3600.0) % 24
        t_out, g, sf = outdoor(w, t), gains(w, t), sun_frac(t)
        mode = "dhw" if 6.0 <= h < 7.5 else "heating"
        lwt_set = lwt_curve(t_out) + offset
        defrost, p = False, 0.0
        if control == "rt":                                 # prod-1: room thermostat on top of the curve
            rt_off = t_room > ROOM_SET + 0.5 if not rt_off else t_room > ROOM_SET - 0.2
        if mode == "heating":
            if on:
                if t_out < 4.0 and run_since_df > 75 * 60 and df_left <= 0:
                    df_left = 6 * 60
                if df_left > 0:
                    df_left -= DT
                    defrost = True
                    run_since_df = 0.0
                    p = -2500.0
                else:
                    run_since_df += DT
                    p = min(P_MAX, max(p_min(t_out), mcp * eps * (lwt_set - t_floor)))
                    if t - start_s < 600:
                        p = min(p, p_min(t_out) + (P_MAX - p_min(t_out)) * (t - start_s) / 600.0)
                lwt = t_floor + p / (mcp * eps)
                hot_s = hot_s + DT if lwt > lwt_set + 2.0 else 0.0
                if hot_s >= 180 or (control == "rt" and rt_off and not defrost):
                    on, off_s, hot_s = False, 0.0, 0.0
            else:
                off_s += DT
                lwt = t_floor
                if off_s >= 600 and t_floor < lwt_set - 1.0 and not (control == "rt" and rt_off):
                    on, start_s, starts = True, t, starts + 1
        else:
            lwt = t_floor
        rwt = lwt - eps * (lwt - t_floor) if p != 0 else lwt
        q_fr = UA_FLOOR * (t_floor - t_room)
        loss = H_TRUE * (t_room - t_out)
        t_floor += (p - q_fr) / C_FLOOR * DT
        t_room += (q_fr - loss + g) / C_ROOM * DT
        if p > 0:
            comp_s += DT
            e_th += p * DT
            e_el += p / (cop(lwt, t_out) * (0.7 if t - start_s < 600 else 1.0)) * DT
        elif defrost:
            comp_s += DT
            e_el += 1200.0 * DT
        lwt_m = round(lwt + rng.normal(0, 0.03), 1)
        rwt_m = round(rwt + rng.normal(0, 0.03), 1)
        dt_m = lwt_m - rwt_m
        m = {"t": t + DT, "on": p > 0 or defrost, "mode": mode, "defrost": defrost,
             "p_meas": dt_m * mcp if (p > 0 or defrost) else 0.0, "lwt": lwt_m, "rwt": rwt_m,
             "t_in": round(t_room + rng.normal(0, 0.03), 1), "t_out": round(t_out, 1), "dt": dt_m,
             "flow": flow_lpm, "night": not (8 <= h < 17), "sunf": sf,
             "at_min": p > 0 and abs(p - p_min(t_out)) < 1.0}
        r = eng.tick(m)
        if t_out > 3 and variant in ("V1", "V2"):            # #368 automation (V2: enhanced signals)
            sat, emp = (r["sat"], r["empty"]) if variant == "V1" else (r["sat2"], r["empty2"])
            if sat and offset == 0.0:
                offset = -5.0
            elif emp and offset != 0.0 and m["t_in"] < 21.5:
                offset = 0.0
        if variant == "V3" and int(t) % 1800 == 0:            # advisory curve trim above turnover
            to = eng.turnover(enhanced=True)
            if to is not None and t_out > to - 1.0 and m["t_in"] > ROOM_SET + 0.3:
                offset = max(offset - 1.0, -4.0)
            elif m["t_in"] < ROOM_SET - 0.1 or (to is not None and t_out < to - 3.0):
                offset = min(offset + 1.0, 0.0)
        hist_p.append((max(p, 0.0), loss - g))
        if len(hist_p) > 120:
            hist_p.pop(0)
        if record and i % 10 == 0:
            net = loss - g
            tf_eq = t_room + max(0.0, net) / UA_FLOOR
            e_true = C_FLOOR * (t_floor - tf_eq) / 3.6e6
            pw = sum(a for a, _ in hist_p) / len(hist_p)
            nw = sum(b for _, b in hist_p) / len(hist_p)
            tstate = "BALANCED" if abs(pw - nw) <= max(150.0, 0.1 * abs(nw)) else ("OVERPRODUCING" if pw > nw else "UNDERPRODUCING")
            for k, v in (("h", t / 3600.0), ("t_out", t_out), ("t_in", t_room), ("p", p), ("loss_true", net),
                         ("loss_est", r["loss_est"]), ("e_est", r["e_buf"]), ("e_true", e_true),
                         ("excess", r["excess_k"]), ("sat", r["sat"]), ("sat2", r["sat2"]),
                         ("dt", dt_m if p > 0 else None), ("on", p > 0), ("status", r["status"]),
                         ("status2", r["status2"]), ("true_state", tstate)):
                ts[k].append(v)
    t_in = np.array(ts["t_in"]) if record else np.array([0.0])
    n_rec = max(1, len(ts["h"]))
    hrs = lambda c: round(float(c) * DT * 10 / 3600 / w.days, 1)  # noqa: E731
    kpi = {"starts_per_day": round(starts / w.days, 1), "compressor_h_per_day": round(comp_s / 3600 / w.days, 1),
           "heat_kwh_per_day": round(e_th / 3.6e6 / w.days, 1), "elec_kwh_per_day": round(e_el / 3.6e6 / w.days, 2),
           "cop": round(e_th / e_el, 2) if e_el else None,
           "room_mean": round(float(t_in.mean()), 2), "room_min": round(float(t_in.min()), 2),
           "room_max": round(float(t_in.max()), 2), "h_above_21": hrs((t_in > 21.0).sum()),
           "h_below_19_5": hrs((t_in < 19.5).sum())}
    if record:
        on_dt = [d for d in ts["dt"] if d is not None]
        kpi["dt_below_2k_pct_of_on"] = round(100 * sum(1 for d in on_dt if d < 2.0) / max(1, len(on_dt)), 1)
        kpi["sat_pct"] = round(100 * sum(ts["sat"]) / n_rec, 1)
        kpi["sat2_pct"] = round(100 * sum(ts["sat2"]) / n_rec, 1)
        pairs = [(a, b) for a, b in zip(ts["e_est"], ts["e_true"]) if a is not None]
        kpi["buffer_corr"] = round(float(np.corrcoef(*zip(*pairs))[0, 1]), 2) if len(pairs) > 10 else None
        pairs2 = [(a, b) for a, b in zip(ts["excess"], ts["e_true"]) if a is not None]
        kpi["excess_corr"] = round(float(np.corrcoef(*zip(*pairs2))[0, 1]), 2) if len(pairs2) > 10 else None
        for key, name in (("status", "status_ok_pct"), ("status2", "status2_ok_pct")):
            ok = [a == b for a, b in zip(ts[key], ts["true_state"]) if a is not None]
            kpi[name] = round(100 * sum(ok) / max(1, len(ok)), 1)
    return {"kpi": kpi, "ts": ts}


def learn(seed: int = 7, control: str = "war") -> tuple[Engine, list]:
    e, hist = Engine(), []
    for k, w in enumerate(LEARN):
        run(w, "V0", e, control=control, seed=seed + k, record=False)
        hs = e.house()
        hist.append({"day": (k + 1) * w.days, "u_spec": e.u and round(e.u, 1), "n_u": len(e.u_pts),
                     "u_enh": hs and round(hs[0], 1), "gains_enh": hs and round(hs[1], 0),
                     "solar_enh": hs and round(hs[2], 0), "emitter": e.emitter() and round(e.emitter(), 0),
                     "tau_h": e.tau() and round(e.tau(), 1),
                     "turnover_spec": e.turnover() and round(e.turnover(), 1),
                     "turnover_enh": e.turnover(True) and round(e.turnover(True), 1),
                     "pmin": {k2: round(v) for k2, v in sorted(e.pmin.items())},
                     "pmin_at_min_rps": {k2: round(v) for k2, v in sorted(e.pmin_rps.items())}})
    return e, hist


def clone(e: Engine) -> Engine:
    return Engine(u_num=e.u_num, u_den=e.u_den, u_pts=list(e.u_pts), pmin=dict(e.pmin), pmin_rps=dict(e.pmin_rps),
                  day_pts=list(e.day_pts),
                  emit_pts=list(e.emit_pts), tau_pts=list(e.tau_pts))


def plots(out: Path, runs: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    col = {"V0": "#1565C0", "V1": "#E65100", "V2": "#8E24AA", "V3": "#2E7D32"}
    for name, by_v in runs.items():
        ts = by_v["V0"]["ts"]
        h = ts["h"]
        fig, ax = plt.subplots(4, 1, figsize=(11, 11.5), sharex=True)
        ax[0].plot(h, ts["t_out"], color="#90A4AE", label="outdoor")
        for v in ("V0", "V1", "V2", "V3"):
            ax[0].plot(by_v[v]["ts"]["h"], by_v[v]["ts"]["t_in"], color=col[v], lw=1.2, label=f"room {v}")
        ax[0].axhline(ROOM_SET, ls=":", color="k")
        ax[0].set_ylabel("C")
        ax[0].legend(ncol=5, fontsize=8)
        ax[0].set_title(f"{SCENARIOS[name].name}  (V0 none, V1 #368 automation, V2 #368 on enhanced signals, V3 curve trim)")
        ax[1].plot(h, [p / 1000 for p in ts["p"]], color="#E60012", lw=0.7, label="HP heat (V0)")
        ax[1].plot(h, [x / 1000 for x in ts["loss_true"]], color="k", label="true net loss (incl. sun + gains)")
        ax[1].plot(h, [x / 1000 if x is not None else None for x in ts["loss_est"]], color="#E65100", ls="--", label="#368 loss = U x dT")
        ax[1].set_ylabel("kW")
        ax[1].legend(fontsize=8)
        ax[2].plot(h, ts["e_true"], color="k", label="true excess in screed (kWh)")
        ax[2].plot(h, ts["e_est"], color="#E65100", label="#368 buffer_energy_kwh")
        ax[2].plot(h, [x * C_FLOOR / 3.6e6 if x is not None else None for x in ts["excess"]], color="#8E24AA",
                   label="enhanced: screed excess (via RWT) x C")
        ax[2].axhline(0, color="#90A4AE", lw=0.6)
        ax[2].set_ylabel("kWh")
        ax[2].legend(fontsize=8)
        ax[3].plot(h, ts["dt"], color="#00539F", lw=0.7, label="measured dT, compressor on")
        ax[3].axhline(2.0, color="#E65100", ls="--", label="#368 saturation rule dT < 2 K")
        ax[3].set_ylabel("K")
        ax[3].set_xlabel("hours")
        ax[3].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / f"sim368_{name}.png", dpi=85)
        plt.close(fig)
    fig, ax = plt.subplots(1, 4, figsize=(14, 3.6))
    names = list(runs)
    x = np.arange(len(names))
    for j, (k, lab) in enumerate((("starts_per_day", "starts / day"), ("h_above_21", "h/day room > 21 C"),
                                   ("elec_kwh_per_day", "kWh electricity / day"), ("cop", "COP"))):
        for vi, v in enumerate(("V0", "V1", "V2", "V3")):
            ax[j].bar(x + (vi - 1.5) * 0.2, [runs[n][v]["kpi"][k] for n in names], 0.2, color=col[v], label=v)
        ax[j].set_xticks(x)
        ax[j].set_xticklabels(names)
        ax[j].set_title(lab)
    ax[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "sim368_kpi.png", dpi=85)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base, hist = learn()
    true_turn = (ROOM_SET * H_TRUE - GAIN_BASE - 2200.0) / (H_TRUE + 36.0)
    res: dict = {"truth": {"H_w_per_k": H_TRUE, "gains_night_w": GAIN_BASE, "turnover_c": round(true_turn, 1),
                           "emitter_w_per_k": round(1 / (1 / UA_PIPE + 1 / UA_FLOOR)), "tau_h": round(C_FLOOR / UA_FLOOR / 3600, 1)},
                 "learning": hist, "runs": {}}
    runs = {}
    for name, w in SCENARIOS.items():
        runs[name] = {v: run(w, v, clone(base), seed=11) for v in ("V0", "V1", "V2", "V3")}
    # prod-1 calibration: weather curve + room thermostat, shoulder and mild
    cal = {n: run(SCENARIOS[n], "V0", clone(base), control="rt", seed=5)["kpi"] for n in ("shoulder", "mild")}
    # flow sensitivity of the dT < 2 K rule (mild, V0)
    flow = {f: run(SCENARIOS["mild"], "V0", clone(base), flow_lpm=f, seed=3)["kpi"]["dt_below_2k_pct_of_on"]
            for f in (12.0, 15.0, 18.3, 22.0, 25.0)}
    plots(args.out, runs)
    res["runs"] = {n: {v: r["kpi"] for v, r in by.items()} for n, by in runs.items()}
    res["prod1_calibration_rt"] = cal
    res["dt_rule_vs_flow_pct_on_time_below_2k"] = flow
    (args.out / "results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
