"""Behaviour baseline for the ML anomaly alert (#443, ML v2). Pure Python.

The v1 baseline (``MultiBaseline``) scored the full 12-dimension feature
vector per mode with a slow EWMA. The 3-month winter simulation
(docs/design/ml-winter-simulation.md) showed why it alerted 19 times a
week on a healthy heat pump:

- the warm-up was biased (EWMA alpha 0.01 from the first cycle), so the
  first week alerted on almost every cycle;
- context dimensions (outdoor temperature, BUH / defrost flags, dT_max,
  rps_max) carried most of the z-scores: weather is not a fault;
- every z > 5 cycle was skipped from the update, so a new normal (colder
  week) was never learned and the std stayed locked.

This baseline scores only how the heat pump behaves (run length, dT,
compressor speed, COP, leaving water, thermal power), per mode and per
4 K outdoor band, with:

- unbiased warm-up: ``alpha_eff = max(alpha, 1 / n)``;
- a std floor per dimension (a stable install never gets z = 40 for a
  0.2 K change);
- a Huber-clipped update (an outlier moves the mean by at most 3 sigma
  times alpha, instead of being skipped or pulling it fully);
- persistence: an alert needs z >= 4 on two consecutive cycles of the
  mode, or z >= 6 once.

Missing values (no COP sensor, no LWT) are skipped per dimension. The
caller keeps transients and boiler co-fire cycles out (see coordinator).
"""
from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .features import FEATURE_NAMES

_LOGGER = logging.getLogger(__name__)

ML_VERSION = 2

BEHAVIOUR_DIMS: tuple[str, ...] = (
    "duration_s",       # scored as log(minutes): 10 -> 20 min == 40 -> 80 min
    "dT_avg",
    "rps_avg",
    "cop_avg",
    "lwt_avg",
    "thermal_kw_avg",
)
# std floor per dimension (duration in log units: 0.15 ~ 15 %)
STD_FLOOR: dict[str, float] = {
    "duration_s": 0.15,
    "dT_avg": 0.4,
    "rps_avg": 3.0,
    "cop_avg": 0.15,
    "lwt_avg": 0.8,
    "thermal_kw_avg": 0.3,
}

DEFAULT_ALPHA = 0.02          # ~50 cycles memory once warmed up
READY_SAMPLES = 25            # samples before a dimension is scored
HUBER_AFTER = 30              # clip updates once the stats are settled
HUBER_C = 3.0
BAND_K = 4.0                  # outdoor band width
PERSIST_Z = 4.0               # z on two consecutive cycles
SINGLE_Z = 6.0                # z once

_FEATURE_INDEX = {name: i for i, name in enumerate(FEATURE_NAMES)}
_POSITIVE_ONLY = frozenset({"duration_s", "rps_avg", "cop_avg", "lwt_avg", "thermal_kw_avg"})


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def behaviour_values(
    record: Mapping[str, Any],
    *,
    cop_avg: float | None = None,
    lwt_avg: float | None = None,
    thermal_kw_avg: float | None = None,
) -> dict[str, float | None]:
    """Raw behaviour values of a cycle. ``None`` = not measured.

    0.0 means "no data" for every dimension except dT (the accumulators
    and the DB default to 0.0 when a sensor is absent).
    """
    over = {"cop_avg": cop_avg, "lwt_avg": lwt_avg, "thermal_kw_avg": thermal_kw_avg}
    out: dict[str, float | None] = {}
    for name in BEHAVIOUR_DIMS:
        ov = over.get(name)
        v = _num(ov) if ov is not None else _num(record.get(name))
        if v is not None and (v <= 0.0 if name in _POSITIVE_ONLY else v == 0.0):
            v = None
        out[name] = v
    return out


def scaled_value(name: str, value: float) -> float:
    if name == "duration_s":
        return math.log(max(1.0, value / 60.0))
    return value


def outdoor_band(outdoor: Any) -> int | None:
    """Lower edge of the 4 K outdoor band (-3.0 -> -4, 5.9 -> 4)."""
    v = _num(outdoor)
    if v is None:
        return None
    return int(math.floor(v / BAND_K) * BAND_K)


class _Stat:
    """EWMA mean / variance of one dimension (warm-up, floor, Huber)."""

    __slots__ = ("mean", "n", "var")

    def __init__(self, n: int = 0, mean: float = 0.0, var: float = 0.0) -> None:
        self.n, self.mean, self.var = n, mean, var

    def std(self, floor: float) -> float:
        return max(floor, math.sqrt(max(0.0, self.var)))

    def z(self, x: float, floor: float) -> float:
        return (x - self.mean) / self.std(floor)

    def update(self, x: float, floor: float, alpha: float) -> None:
        self.n += 1
        if self.n == 1:
            self.mean, self.var = x, 0.0
            return
        a = max(alpha, 1.0 / self.n)
        d = x - self.mean
        if self.n > HUBER_AFTER:
            s = HUBER_C * self.std(floor)
            d = max(-s, min(s, d))
        self.mean += a * d
        self.var = (1.0 - a) * (self.var + a * d * d)

    def to_list(self) -> list[float]:
        return [self.n, round(self.mean, 6), round(self.var, 8)]

    @classmethod
    def from_list(cls, raw: Any) -> _Stat:
        try:
            n, mean, var = raw
            return cls(int(n), float(mean), float(var))
        except (TypeError, ValueError):
            return cls()


@dataclass(frozen=True)
class BehaviourScore:
    """z-scores of one cycle against its group."""

    z: dict[str, float]
    group: str               # "heating|-4" (band) or "heating" (mode fallback)

    @property
    def max_abs_z(self) -> float:
        return max((abs(v) for v in self.z.values()), default=0.0)

    @property
    def top(self) -> str | None:
        if not self.z:
            return None
        return max(self.z, key=lambda k: abs(self.z[k]))


def _mode_key(mode: str | None) -> str:
    return mode if isinstance(mode, str) and mode else "unknown"


class BehaviourBaseline:
    """Per mode x outdoor-band behaviour statistics + persistence rule."""

    # R52: class-level defaults (stub coordinators, from_dict)
    _migrated_from_dim: int | None = None
    version: int = ML_VERSION

    def __init__(self, alpha: float = DEFAULT_ALPHA) -> None:
        self._alpha = min(1.0, max(0.001, float(alpha)))
        # group key -> dim -> stat; group is "<mode>" or "<mode>|<band>"
        self._groups: dict[str, dict[str, _Stat]] = {}
        self._streak: dict[str, int] = {}

    # ---------- MultiBaseline-compatible surface ----------

    @property
    def dim(self) -> int:
        return len(BEHAVIOUR_DIMS)

    @property
    def alpha(self) -> float:
        return self._alpha

    def modes(self) -> list[str]:
        return sorted(k for k in self._groups if "|" not in k)

    def sample_count(self, mode: str | None) -> int:
        g = self._groups.get(_mode_key(mode), {})
        return max((s.n for s in g.values()), default=0)

    def total_samples(self) -> int:
        return sum(self.sample_count(m) for m in self.modes())

    def bands(self, mode: str | None) -> dict[int, int]:
        """{band: samples} for a mode (diagnostics)."""
        prefix = _mode_key(mode) + "|"
        out: dict[int, int] = {}
        for key, g in self._groups.items():
            if key.startswith(prefix):
                out[int(key[len(prefix):])] = max((s.n for s in g.values()), default=0)
        return dict(sorted(out.items()))

    def reset(self, mode: str | None = None) -> None:
        if mode is None:
            self._groups.clear()
            self._streak.clear()
            return
        key = _mode_key(mode)
        for k in [k for k in self._groups if k == key or k.startswith(key + "|")]:
            del self._groups[k]
        self._streak.pop(key, None)

    # ---------- scoring ----------

    def _group_for(self, mode: str, band: int | None, name: str) -> tuple[str, _Stat] | None:
        """Band stats once ready, else the mode stats, else None."""
        if band is not None:
            key = f"{mode}|{band}"
            st = self._groups.get(key, {}).get(name)
            if st is not None and st.n >= READY_SAMPLES:
                return key, st
        st = self._groups.get(mode, {}).get(name)
        if st is not None and st.n >= READY_SAMPLES:
            return mode, st
        return None

    def score(
        self, mode: str | None, values: Mapping[str, float | None], outdoor: Any = None,
    ) -> BehaviourScore:
        """z per measured, ready dimension (empty during warm-up)."""
        m = _mode_key(mode)
        band = outdoor_band(outdoor)
        z: dict[str, float] = {}
        groups: set[str] = set()
        for name in BEHAVIOUR_DIMS:
            raw = values.get(name)
            if raw is None:
                continue
            hit = self._group_for(m, band, name)
            if hit is None:
                continue
            groups.add(hit[0])
            z[name] = hit[1].z(scaled_value(name, raw), STD_FLOOR[name])
        group = f"{m}|{band}" if f"{m}|{band}" in groups else m
        return BehaviourScore(z=z, group=group)

    def update(
        self, mode: str | None, values: Mapping[str, float | None], outdoor: Any = None,
    ) -> bool:
        """Learn one cycle (mode stats and its band stats)."""
        m = _mode_key(mode)
        band = outdoor_band(outdoor)
        keys = [m] if band is None else [m, f"{m}|{band}"]
        learned = False
        for name in BEHAVIOUR_DIMS:
            raw = values.get(name)
            if raw is None:
                continue
            x = scaled_value(name, raw)
            for key in keys:
                self._groups.setdefault(key, {}).setdefault(name, _Stat()).update(
                    x, STD_FLOOR[name], self._alpha,
                )
            learned = True
        return learned

    def observe(
        self,
        mode: str | None,
        values: Mapping[str, float | None],
        outdoor: Any = None,
        *,
        learn: bool = True,
    ) -> tuple[BehaviourScore, bool]:
        """Score first, then learn. Returns (score, persistent alert)."""
        m = _mode_key(mode)
        sc = self.score(m, values, outdoor)
        zmax = sc.max_abs_z
        self._streak[m] = self._streak.get(m, 0) + 1 if zmax >= PERSIST_Z else 0
        alert = zmax >= SINGLE_Z or self._streak[m] >= 2
        if learn:
            self.update(m, values, outdoor)
        return sc, alert

    # ---------- persistence ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "behaviour",
            "version": ML_VERSION,
            "dim": self.dim,
            "dims": list(BEHAVIOUR_DIMS),
            "alpha": self._alpha,
            "groups": {
                k: {n: s.to_list() for n, s in g.items()} for k, g in self._groups.items()
            },
            "streak": dict(self._streak),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> BehaviourBaseline:
        """Restore; a v1 MultiBaseline payload yields an empty v2 baseline."""
        if (
            not isinstance(data, Mapping)
            or data.get("type") != "behaviour"
            or data.get("version") != ML_VERSION
        ):
            bb = cls()
            dim = data.get("dim") if isinstance(data, Mapping) else None
            bb._migrated_from_dim = dim if isinstance(dim, int) else 0
            return bb
        bb = cls(alpha=float(data.get("alpha", DEFAULT_ALPHA)))
        for key, g in (data.get("groups") or {}).items():
            if isinstance(g, Mapping):
                bb._groups[str(key)] = {
                    str(n): _Stat.from_list(v) for n, v in g.items() if n in STD_FLOOR
                }
        for key, v in (data.get("streak") or {}).items():
            if isinstance(v, int) and not isinstance(v, bool):
                bb._streak[str(key)] = v
        return bb

    def summary(self) -> dict[str, Any]:
        """Diagnostics view: per mode samples, bands, mean / std per dim.

        duration_s is stored as log(minutes): its mean is shown in minutes
        and its std in log units (0.15 ~ 15 %).
        """
        out: dict[str, Any] = {"version": ML_VERSION, "dims": list(BEHAVIOUR_DIMS), "modes": {}}
        for m in self.modes():
            g = self._groups.get(m, {})
            out["modes"][m] = {
                "samples": self.sample_count(m),
                "bands": self.bands(m),
                "streak": self._streak.get(m, 0),
                "dims": {
                    n: {
                        "n": s.n,
                        "mean": round(math.exp(s.mean) if n == "duration_s" else s.mean, 3),
                        "std": round(s.std(STD_FLOOR[n]), 3),
                    }
                    for n, s in g.items()
                },
            }
        return out


def feature_index(name: str | None) -> int | None:
    """Index of a behaviour dimension in FEATURE_NAMES (alerts, advice)."""
    return _FEATURE_INDEX.get(name) if name else None
