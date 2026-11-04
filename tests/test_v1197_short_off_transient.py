"""v1.19.7 RED: _is_short_off must skip when last_cycle is transient.

Pre-fix: no is_transient guard, so pump-only LWT pulses fire a spurious
short_off alert (same bug pattern as #246 for short_run).

Post-fix: guard added via _is_transient_int, matching #246 semantics.

Fixture tests inject off_s (from DB gaps) to simulate live coordinator
state (coordinator.py:318-322). Without injection, hydrated records have
no off_s and _is_short_off short-circuits before reaching the transient
check — a false-pass trap (R594).
"""
import pathlib
import sqlite3
import time

import pytest

from custom_components.daikin_cycle_ml import binary_sensor as bs
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _mk_coordinator(cycles=None, threshold_min=5):
    s = CycleStore(maxlen=100)
    if cycles:
        s.hydrate_from_rows(cycles, good_threshold=70)
    return type("C", (), {"store": s, "options": {"short_off_threshold_min": threshold_min}})()


def _mk_snap(mode="heating"):
    return type("S", (), {"mode": mode})()


def _mk_cycle(*, dur=60, mode="heating", is_transient=0, off_s=None, ts=None):
    if ts is None:
        # v1.19.7 #259: realistic recent timestamp (end_ts = now-100).
        ts = time.time() - dur - 100
    r = {
        "start_ts": ts,
        "end_ts": ts + dur,
        "duration_s": dur,
        "mode": mode,
        "dT_max": 2.0,
        "rps_max": 30.0,
        "is_transient": is_transient,
    }
    if off_s is not None:
        r["off_s"] = off_s
    return r


# ---------- NEW BEHAVIOR (RED pre-fix) ----------

def test_transient_current_cycle_silent():
    """Transient last cycle + off_s<300: must be silent post-fix."""
    c = _mk_coordinator([_mk_cycle(dur=29, is_transient=1, off_s=30)])
    assert bs._is_short_off(_mk_snap(), c) is False


def test_transient_corrupt_string_1_silent():
    """is_transient='1' must be treated as transient via _is_transient_int."""
    c = _mk_coordinator([_mk_cycle(dur=29, is_transient="1", off_s=30)])
    assert bs._is_short_off(_mk_snap(), c) is False


# ---------- PRESERVED BEHAVIOR (green pre-fix) ----------

def test_real_short_off_fires():
    """Real cycle + off_s<300 still fires."""
    c = _mk_coordinator([_mk_cycle(dur=600, is_transient=0, off_s=30)])
    assert bs._is_short_off(_mk_snap(), c) is True


def test_corrupt_string_0_treated_as_real():
    """is_transient='0' -> int 0 -> real -> still fires."""
    c = _mk_coordinator([_mk_cycle(dur=600, is_transient="0", off_s=30)])
    assert bs._is_short_off(_mk_snap(), c) is True


def test_dhw_mode_silent():
    """DHW-mode still silent (existing behavior)."""
    c = _mk_coordinator([_mk_cycle(dur=600, mode="dhw", is_transient=0, off_s=30)])
    assert bs._is_short_off(_mk_snap(mode="dhw"), c) is False


def test_off_s_above_threshold_silent():
    """off_s >= threshold -> silent."""
    c = _mk_coordinator([_mk_cycle(dur=600, is_transient=0, off_s=600)])
    assert bs._is_short_off(_mk_snap(), c) is False


def test_missing_off_s_silent():
    """No off_s key -> silent (post-reboot safety invariant, unchanged)."""
    c = _mk_coordinator([_mk_cycle(dur=600, is_transient=0, off_s=None)])
    assert bs._is_short_off(_mk_snap(), c) is False


def test_empty_store_silent():
    """Empty store -> last_cycle() is None -> silent."""
    c = _mk_coordinator([])
    assert bs._is_short_off(_mk_snap(), c) is False


# ---------- FIXTURE PARAMETRIZE (inject live off_s) ----------

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "_prod1_20261103.db"


def _load_rows():
    con = sqlite3.connect(f"file:{FIXTURE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM cycles ORDER BY start_ts")]
    con.close()
    return rows


def _transient_short_off_cases():
    """Return (idx, label) for each real transient + short gap case.

    Injects off_s so the test exercises the transient decision path
    (R594: without injection, hydrated records short-circuit at the
    missing off_s guard and pass for the wrong reason).
    """
    if not FIXTURE.exists():
        return []
    rows = _load_rows()
    cases = []
    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]
        if not (prev.get("end_ts") and cur.get("start_ts") and cur.get("end_ts")):
            continue
        try:
            tr = int(cur.get("is_transient") or 0)
        except (ValueError, TypeError):
            continue
        if tr != 1:
            continue
        if str(cur.get("mode", "")).lower() == "dhw":
            continue
        off = cur["start_ts"] - prev["end_ts"]
        if not (0 <= off < 300):
            continue
        label = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(cur["start_ts"]))
        cases.append((i, label))
    return cases


_CASES = _transient_short_off_cases()
_PARAMS = (
    [pytest.param(idx, label, id=label) for idx, label in _CASES]
    if _CASES
    else [pytest.param(None, None, id="no-fixture")]
)


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture absent")
@pytest.mark.parametrize("idx,label", _PARAMS)
def test_fixture_transient_short_off_silent(idx, label):
    """Real Prod 1 transient + short gap, with live off_s: silent post-fix."""
    if idx is None:
        pytest.skip("fixture absent")
    rows = _load_rows()
    # Build subset with live off_s injected (simulates coordinator.py:318-322)
    subset = []
    for j in range(idx + 1):
        r = dict(rows[j])
        if j > 0:
            prev = rows[j - 1]
            if prev.get("end_ts") and r.get("start_ts"):
                r["off_s"] = float(r["start_ts"] - prev["end_ts"])
        subset.append(r)
    c = _mk_coordinator(subset, threshold_min=5)
    assert bs._is_short_off(_mk_snap(mode="heating"), c) is False, (
        f"{label} - transient last cycle should not fire short_off"
    )


# ---------- FIXTURE SAFETY (unchanged post-reboot invariant) ----------

@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture absent")
def test_hydrated_store_no_off_s_silent():
    """Hydrated store (no live off_s): silent, regardless of transient.

    Documents the post-reboot safety invariant: off_s is not persisted,
    so _is_short_off returns False for all hydrated records. This is a
    deliberate behaviour (no false positive post-reboot), not a bug.
    """
    rows = _load_rows()
    c = _mk_coordinator(rows, threshold_min=5)
    last = c.store.last_cycle()
    assert "off_s" not in last
    assert bs._is_short_off(_mk_snap(mode="heating"), c) is False
