"""In-memory cycle store. SQLite lands in Batch 6."""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAXLEN = 500


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
        mode = stored.get("mode")
        if isinstance(mode, str):
            key = f"cycles_{mode}"
            self._counters[key] = self._counters.get(key, 0) + 1
        return stored

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
        prev = self._counters.get("_day_key")
        if prev == day:
            return False
        self._counters["_day_key"] = day
        for key in list(self._counters.keys()):
            if key.endswith("_today"):
                self._counters.pop(key, None)
        return True

    def record_short_run(self) -> int:
        return self.increment("short_runs_today")

    def record_short_off(self) -> int:
        return self.increment("short_offs_today")

    def cycles_in_window(self, now: float, window_s: float) -> int:
        cutoff = float(now) - float(window_s)
        return sum(
            1 for c in self._cycles
            if isinstance(c.get("start_ts"), (int, float)) and c["start_ts"] >= cutoff
        )

    def cycles_in_window_mode(
        self, now: float, window_s: float, mode: str
    ) -> int:
        cutoff = float(now) - float(window_s)
        return sum(
            1 for c in self._cycles
            if isinstance(c.get("start_ts"), (int, float))
            and c["start_ts"] >= cutoff
            and c.get("mode") == mode
        )

    def cycles_today(self, now: float) -> list[dict[str, Any]]:
        day = time.strftime("%Y-%m-%d", time.localtime(float(now)))
        out: list[dict[str, Any]] = []
        for c in self._cycles:
            ts = c.get("start_ts")
            if isinstance(ts, (int, float)) and time.strftime(
                "%Y-%m-%d", time.localtime(float(ts))
            ) == day:
                out.append(dict(c))
        return out
