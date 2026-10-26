"""v1.12.9 (#131 PR-2): store.rollback_last_cycles unit tests."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _rec(mode: str, start: float = 0.0, end: float = 60.0) -> dict:
    return {"mode": mode, "start_ts": start, "end_ts": end}


class TestRollbackLastCycles:
    def test_rollback_two_heating_cycles(self) -> None:
        """Bridge merge case: absorbed=2 → both heating entries removed."""
        s = CycleStore(maxlen=10)
        s.add_cycle(_rec("heating", 0, 60))
        s.add_cycle(_rec("heating", 70, 130))
        assert s.get("cycles_total") == 2
        assert s.get("cycles_heating") == 2
        assert len(s.cycles()) == 2

        n = s.rollback_last_cycles(2)

        assert n == 2
        assert s.get("cycles_total") == 0
        assert s.get("cycles_today") == 0
        assert s.get("cycles_heating") == 0
        assert len(s.cycles()) == 0
        assert s.last_cycle() is None

    def test_rollback_mixed_modes_decrements_per_mode(self) -> None:
        """Per-mode counter only decrements for the mode actually popped."""
        s = CycleStore(maxlen=10)
        s.add_cycle(_rec("heating", 0, 60))
        s.add_cycle(_rec("dhw", 70, 130))

        n = s.rollback_last_cycles(1)  # pops dhw

        assert n == 1
        assert s.get("cycles_total") == 1
        assert s.get("cycles_dhw") == 0
        assert s.get("cycles_heating") == 1  # untouched
        assert len(s.cycles()) == 1
        assert s.last_cycle()["mode"] == "heating"

    def test_rollback_underflow_and_zero(self) -> None:
        """n>size: rollback what's there, return actual. Empty/n<=0: 0."""
        s = CycleStore(maxlen=10)
        assert s.rollback_last_cycles(2) == 0  # empty
        assert s.rollback_last_cycles(0) == 0  # no-op
        assert s.rollback_last_cycles(-1) == 0  # guard

        s.add_cycle(_rec("heating"))
        assert s.rollback_last_cycles(5) == 1  # only 1 present
        assert s.get("cycles_total") == 0
        assert len(s.cycles()) == 0

    def test_rollback_does_not_touch_good_bad_counters(self) -> None:
        """score_and_count ran pre-merge; its counters are NOT undone."""
        s = CycleStore(maxlen=10)
        s.increment("good_cycles_today", 1)
        s.increment("bad_cycles_today", 1)
        s.add_cycle(_rec("heating"))
        s.add_cycle(_rec("heating"))

        s.rollback_last_cycles(2)

        assert s.get("good_cycles_today") == 1
        assert s.get("bad_cycles_today") == 1
        assert s.get("cycles_total") == 0


class TestRollbackMissingMode:
    def test_rollback_with_missing_mode_skips_per_mode_counter(self) -> None:
        """Cycle without 'mode' key: per-mode counter untouched, total dropped."""
        s = CycleStore(maxlen=10)
        s.add_cycle({"start_ts": 0, "end_ts": 60})  # no mode key
        s.increment("cycles_heating", 5)  # sentinel — must remain
        n = s.rollback_last_cycles(1)
        assert n == 1
        assert s.get("cycles_total") == 0
        assert s.get("cycles_today") == 0
        assert s.get("cycles_heating") == 5  # untouched
        assert len(s.cycles()) == 0
