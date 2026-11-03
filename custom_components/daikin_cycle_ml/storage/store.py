"""In-memory cycle store. SQLite lands in Batch 6."""
from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAXLEN = 500


def _is_transient_int(v: object) -> int:
    """v1.19.6 FASE 5: safe parse of is_transient flag.

    Cycle records can carry is_transient from DB-imports, oude schema-
    versies or manual SQL edits. These may be non-numeric strings, and
    ``int("x")`` raises ValueError. Combined with the R580 fix (no
    silent-except), one corrupt record would crash cycles_in_window /
    cycles_in_window_mode / alert dispatch.

    Policy: unknown / unparseable -> treat as non-transient (0). This
    matches the backward-compat rule used elsewhere (missing key == 0).
    Booleans and ints keep their existing semantics.
    """
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return 0
    return 0


@dataclass
class CycleStore:
    """Bounded deque of cycle records + named counters."""

    maxlen: int = DEFAULT_MAXLEN
    _cycles: deque[dict[str, Any]] = field(default_factory=deque)
    _counters: dict[str, int] = field(default_factory=dict)

    def add_cycle(self, record: Mapping[str, Any]) -> dict[str, Any]:
        stored = dict(record)
        self._cycles.append(stored)
        while len(self._cycles) > self.maxlen:
            self._cycles.popleft()
        self._counters["cycles_total"] = self._counters.get("cycles_total", 0) + 1
        self._counters["cycles_today"] = self._counters.get("cycles_today", 0) + 1
        mode = stored.get("mode")
        if isinstance(mode, str):
            key = f"cycles_{mode}"
            self._counters[key] = self._counters.get(key, 0) + 1
        return stored

    def rollback_last_cycles(self, n: int) -> int:
        """Undo last n add_cycle calls (v1.12.9 #131 PR-2). Bridge merges
        absorb 2, simple merges 1. good/bad_cycles_today are NOT touched
        (score_and_count ran pre-merge). Returns #actually rolled back.
        """
        if n <= 0 or not self._cycles:
            return 0
        rolled = 0
        for _ in range(n):
            if not self._cycles:
                break
            popped = self._cycles.pop()
            _mode = popped.get("mode")
            self._counters["cycles_total"] = max(
                0, self._counters.get("cycles_total", 0) - 1)
            self._counters["cycles_today"] = max(
                0, self._counters.get("cycles_today", 0) - 1)
            if isinstance(_mode, str):
                _key = f"cycles_{_mode}"
                self._counters[_key] = max(
                    0, self._counters.get(_key, 0) - 1)
            rolled += 1
        return rolled

    def cycles(self) -> list[dict[str, Any]]:
        return list(self._cycles)

    def last_cycle(self) -> dict[str, Any] | None:
        if not self._cycles:
            return None
        return dict(self._cycles[-1])

    def count(self) -> int:
        return len(self._cycles)

    def increment(self, key: str, delta: int = 1) -> int:
        self._counters[key] = self._counters.get(key, 0) + int(delta)
        return self._counters[key]

    def get(self, key: str, default: int = 0) -> int:
        return self._counters.get(key, default)

    def counters_snapshot(self) -> dict[str, int]:
        return dict(self._counters)

    def reset(self, keys: Iterable[str] | None = None) -> None:
        if keys is None:
            self._counters.clear()
            return
        for key in keys:
            self._counters.pop(key, None)

    def off_time_since_last(self, now: float) -> float | None:
        last = self.last_cycle()
        if last is None:
            return None
        end_ts = last.get("end_ts")
        if not isinstance(end_ts, (int, float)):
            return None
        return max(0.0, float(now) - float(end_ts))

    # --- Batch 5b-1 additions ---

    def daily_reset_if_needed(self, now: float) -> bool:
        day = time.strftime("%Y-%m-%d", time.localtime(float(now)))
        counters: dict[str, Any] = self._counters
        prev = counters.get("_day_key")
        if prev == day:
            return False
        counters["_day_key"] = day
        for key in list(counters.keys()):
            if key.endswith("_today"):
                counters.pop(key, None)
        return True

    def record_short_run(self) -> int:
        return self.increment("short_runs_today")

    def record_short_off(self) -> int:
        return self.increment("short_offs_today")

    def hydrate_from_rows(
        self,
        rows: list[Mapping[str, Any]],
        *,
        good_threshold: int = 70,
    ) -> int:
        # v1.4.2: preload cycles + recompute today counters.
        if not rows:
            return 0
        for r in rows:
            self._cycles.append(dict(r))
        while len(self._cycles) > self.maxlen:
            self._cycles.popleft()
        today = time.strftime("%Y-%m-%d", time.localtime())
        self._counters["cycles_total"] = len(self._cycles)
        for _m in ("heating", "dhw", "cooling"):
            self._counters[f"cycles_{_m}"] = sum(
                1 for c in self._cycles if c.get("mode") == _m
            )
        # v1.4.4: mark day so daily_reset_if_needed is a no-op today.
        # Uses Any-alias to satisfy mypy (matches daily_reset_if_needed).
        _any: dict[str, Any] = self._counters
        _any["_day_key"] = today
        good = 0
        bad = 0
        cycles_today = 0
        for c in self._cycles:
            ts = c.get("start_ts")
            if not isinstance(ts, (int, float)) or isinstance(ts, bool):
                continue
            if time.strftime(
                "%Y-%m-%d", time.localtime(float(ts))
            ) != today:
                continue
            cycles_today += 1
            qs = c.get("quality_score")
            if isinstance(qs, bool) or not isinstance(qs, int):
                continue
            if qs >= good_threshold:
                good += 1
            else:
                bad += 1
        self._counters["cycles_today"] = cycles_today
        self._counters["good_cycles_today"] = good
        self._counters["bad_cycles_today"] = bad
        return len(self._cycles)

    def cycles_in_window(
        self,
        now: float,
        window_s: float,
        *,
        exclude_transient: bool = True,
        exclude_future: bool = True,
    ) -> int:
        """v1.19.6: parity with v1.14.0 cycles_today clock-skew guard.

        Before v1.19.6 this function had no upper bound on start_ts,
        so records far in the future (HA reboot + NTP drift, DB-import
        corruption, multi-device skew) inflated the count. cycles_today
        already skipped start_ts > now+60s since v1.14.0; the window
        helper was missed. Same bug family as v1.12.0 / #245 / #246.
        """
        cutoff = float(now) - float(window_s)
        future_cutoff = float(now) + 60.0
        return sum(
            1
            for c in self._cycles
            if isinstance(c.get("start_ts"), (int, float))
            and c["start_ts"] >= cutoff
            and (not exclude_future or c["start_ts"] <= future_cutoff)
            and (not exclude_transient or _is_transient_int(c.get("is_transient")) == 0)
        )

    def count_short_in_window_mode(
        self, now_ts: float, window_s: float, duration_threshold_s: int, mode: str,
    ) -> int:
        """v1.19.7 #11: count non-transient cycles < threshold in window+mode."""
        cutoff = float(now_ts) - float(window_s)
        future = float(now_ts) + 60.0
        return sum(
            1 for c in self._cycles
            if isinstance(c.get("start_ts"), (int, float))
            and c["start_ts"] >= cutoff and c["start_ts"] <= future
            and c.get("mode") == mode
            and _is_transient_int(c.get("is_transient")) == 0
            and isinstance(c.get("duration_s"), (int, float))
            and float(c["duration_s"]) < duration_threshold_s
        )

    def short_runs_in_window_mode(
        self, now_ts: float, window_s: float, duration_threshold_s: int,
        mode: str, limit: int = 10,
    ) -> list[dict[str, Any]]:
        """v1.19.7 #11: recent short runs for diagnostics (newest first)."""
        cutoff = float(now_ts) - float(window_s)
        future = float(now_ts) + 60.0
        rows = [
            c for c in self._cycles
            if isinstance(c.get("start_ts"), (int, float))
            and c["start_ts"] >= cutoff and c["start_ts"] <= future
            and c.get("mode") == mode
            and _is_transient_int(c.get("is_transient")) == 0
            and isinstance(c.get("duration_s"), (int, float))
            and float(c["duration_s"]) < duration_threshold_s
        ]
        rows.sort(key=lambda r: r["start_ts"], reverse=True)
        return [
            {"start_ts": r["start_ts"], "duration_s": int(r["duration_s"])}
            for r in rows[:limit]
        ]

    def cycles_in_window_mode(
        self,
        now: float,
        window_s: float,
        mode: str,
        *,
        exclude_transient: bool = True,
        exclude_future: bool = True,
    ) -> int:
        """v1.19.6: parity with v1.14.0 cycles_today clock-skew guard.

        See cycles_in_window for rationale. Same upper-bound fix so that
        pendulum_hourly / dhw_pendulum / high_cycle_rate are not inflated
        by distant-future timestamps.
        """
        cutoff = float(now) - float(window_s)
        future_cutoff = float(now) + 60.0
        return sum(
            1
            for c in self._cycles
            if isinstance(c.get("start_ts"), (int, float))
            and c["start_ts"] >= cutoff
            and c["start_ts"] <= future_cutoff
            and c.get("mode") == mode
            and (not exclude_transient or _is_transient_int(c.get("is_transient")) == 0)
        )

    def cycles_today(self, now: float) -> list[dict[str, Any]]:
        day = time.strftime("%Y-%m-%d", time.localtime(float(now)))
        now_f = float(now)
        # v1.14.0: skip cycles whose start_ts is >60s in the future
        # (clock skew tolerance; blocks DB-import corruption).
        future_cutoff = now_f + 60.0
        out: list[dict[str, Any]] = []
        for c in self._cycles:
            ts = c.get("start_ts")
            if not isinstance(ts, (int, float)):
                continue
            ts_f = float(ts)
            if ts_f > future_cutoff:
                continue
            if time.strftime("%Y-%m-%d", time.localtime(ts_f)) == day:
                out.append(dict(c))
        return out

    def non_transient_today(self, now: float) -> list[dict[str, Any]]:
        """v1.12.0 (#105): today's cycles excluding startup transients.

        v1.19.6 FASE 5C: numeric parse via _is_transient_int (was truthy
        check; string "0"/"false"/"x" silently EXCLUDED all records feeding
        _is_pendulum_daily -> false negatives on corrupt DB-imports).
        """
        return [
            c
            for c in self.cycles_today(now)
            if _is_transient_int(c.get("is_transient")) == 0
        ]

    def non_transient_in_window(self, now: float, window_s: float) -> int:
        """v1.12.0 (#105): cycles in window excluding startup transients.

        v1.19.6: delegates to cycles_in_window so future-cutoff and
        transient rules stay in sync (was drifting before).
        """
        return self.cycles_in_window(
            now, window_s, exclude_transient=True, exclude_future=True
        )
