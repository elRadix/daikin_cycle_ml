"""Adaptive thresholds: learn per-mode limits from cycle history.

Pure Python, no HA imports. Percentile-based, no supervised training.
Each threshold adapts to the actual behaviour of this heat pump.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Mapping

_LOGGER = logging.getLogger(__name__)

MIN_RUN_MIN = 2
MAX_RUN_MIN = 240
MIN_OFF_MIN = 0
MAX_OFF_MIN = 240
MIN_TARGET_CPD = 1
MAX_TARGET_CPD = 100


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile. pct in [0, 100]."""
    if not values:
        raise ValueError('empty')
    if pct <= 0:
        return float(min(values))
    if pct >= 100:
        return float(max(values))
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def _clamp_int(value: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, round(value))))


class AdaptiveThresholds:
    """Learn per-mode run/off/target thresholds from observed cycles.

    Thread-safety: single-threaded (called from coordinator event loop).
    Memory: O(modes * samples). Bounded by caller via periodic reset.
    """

    def __init__(self, min_samples: int = 20) -> None:
        self.min_samples = max(1, int(min_samples))
        self._run_min: dict[str, list[float]] = defaultdict(list)
        self._off_min: dict[str, list[float]] = defaultdict(list)
        self._daily_cycles: list[int] = []

    # --- observation ---

    def observe_cycle(
        self,
        mode: str | None,
        duration_s: float | None,
        off_s: float | None = None,
    ) -> bool:
        """Record one cycle. Returns True if stored."""
        m = (mode or 'unknown').strip() or 'unknown'
        stored = False
        if duration_s is not None:
            try:
                dur_min = float(duration_s) / 60.0
            except (TypeError, ValueError):
                dur_min = None
            if dur_min is not None and dur_min > 0:
                self._run_min[m].append(dur_min)
                stored = True
        if off_s is not None:
            try:
                off_m = float(off_s) / 60.0
            except (TypeError, ValueError):
                off_m = None
            if off_m is not None and off_m >= 0:
                self._off_min[m].append(off_m)
                stored = True
        return stored

    def observe_day(self, cycles: int | None) -> bool:
        """Record end-of-day cycle count."""
        if cycles is None:
            return False
        try:
            c = int(cycles)
        except (TypeError, ValueError):
            return False
        if c < 0:
            return False
        self._daily_cycles.append(c)
        return True

    # --- learned thresholds ---

    def learn_short_run_min(self, mode: str | None) -> int | None:
        """p20 of run durations (minutes). None if not enough samples."""
        vals = self._run_min.get(mode or 'unknown', [])
        if len(vals) < self.min_samples:
            return None
        p20 = _percentile(vals, 20.0)
        return _clamp_int(p20, MIN_RUN_MIN, MAX_RUN_MIN)

    def learn_good_off_min(self, mode: str | None) -> int | None:
        """p50 of off durations (minutes). None if not enough samples."""
        vals = self._off_min.get(mode or 'unknown', [])
        if len(vals) < self.min_samples:
            return None
        p50 = _percentile(vals, 50.0)
        return _clamp_int(p50, MIN_OFF_MIN, MAX_OFF_MIN)

    def learn_target_cycles_per_day(self) -> int | None:
        """p50 of daily cycle counts. None if not enough days."""
        if len(self._daily_cycles) < max(3, self.min_samples // 4):
            return None
        p50 = _percentile([float(x) for x in self._daily_cycles], 50.0)
        return _clamp_int(p50, MIN_TARGET_CPD, MAX_TARGET_CPD)

    def suggest(self, mode: str | None = None) -> dict[str, int]:
        """Return all currently-learned values for a mode (may be empty)."""
        out: dict[str, int] = {}
        sr = self.learn_short_run_min(mode)
        if sr is not None:
            out['short_run_threshold_min'] = sr
        go = self.learn_good_off_min(mode)
        if go is not None:
            out['good_off_threshold_min'] = go
        tgt = self.learn_target_cycles_per_day()
        if tgt is not None:
            out['target_cycles_per_day'] = tgt
        return out

    # --- introspection ---

    def sample_count(self, mode: str | None = None) -> dict[str, int]:
        """Return per-kind sample counts."""
        m = mode or 'unknown'
        return {
            'run': len(self._run_min.get(m, [])),
            'off': len(self._off_min.get(m, [])),
            'days': len(self._daily_cycles),
        }

    def modes(self) -> list[str]:
        keys = set(self._run_min) | set(self._off_min)
        return sorted(keys)

    def total_samples(self) -> int:
        n = sum(len(v) for v in self._run_min.values())
        n += sum(len(v) for v in self._off_min.values())
        return n

    # --- persistence ---

    def to_dict(self) -> dict[str, Any]:
        return {
            'min_samples': self.min_samples,
            'run_min': {k: list(v) for k, v in self._run_min.items()},
            'off_min': {k: list(v) for k, v in self._off_min.items()},
            'daily_cycles': list(self._daily_cycles),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> 'AdaptiveThresholds':
        if not data:
            return cls()
        ms = int(data.get('min_samples', 20) or 20)
        inst = cls(min_samples=ms)
        for k, v in (data.get('run_min') or {}).items():
            if isinstance(v, list):
                inst._run_min[k] = [float(x) for x in v]
        for k, v in (data.get('off_min') or {}).items():
            if isinstance(v, list):
                inst._off_min[k] = [float(x) for x in v]
        dc = data.get('daily_cycles') or []
        if isinstance(dc, list):
            inst._daily_cycles = [int(x) for x in dc]
        return inst

    def reset(self, mode: str | None = None) -> None:
        """Clear data. If mode given, only that mode's run/off lists."""
        if mode is None:
            self._run_min.clear()
            self._off_min.clear()
            self._daily_cycles.clear()
        else:
            self._run_min.pop(mode, None)
            self._off_min.pop(mode, None)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f'AdaptiveThresholds(min_samples={self.min_samples}, '
            f'modes={len(self.modes())}, samples={self.total_samples()})'
        )

