"""v1.19.7 fix #12: thermal_kw_avg requires minimum samples.

Pre-fix: 60s cycle -> 2 samples -> "avg" = (peak1+peak2)/2, not a mean.
Post-fix: cycles with < MIN_THERMAL_SAMPLES samples -> thermal_kw_avg = None.

MAX_THERMAL_KW (existing) catches ABSURD values (>14 kW) at write time.
MIN_THERMAL_SAMPLES gate catches UNRELIABLE values (too few samples).

Coverage strategy:
- Direct gate tests: verify n_samples semantics
- Source inspection: verify caller passes n_samples
- Migration: verify method exists + correct SQL
- Fixture: document dirty baseline

State-machine integration is out of scope here — covered by
test_v1197_hvac_flow_e2e.py and test_v1197_hvac_edge_cases.py which use
real CycleStore + cycle records, not the incremental update() path.
"""
import inspect
import pathlib
import sqlite3

import pytest

from custom_components.daikin_cycle_ml.engine import cycle_detector as cd


FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "_prod1_20261103.db"


def _gate_accepts_n_samples():
    """R602: probe signature before calling."""
    try:
        sig = inspect.signature(cd._apply_thermal_sanity_gate)
        return "n_samples" in sig.parameters
    except (ValueError, TypeError):
        return False


# ============================================================
# NEW BEHAVIOR — RED pre-fix, GREEN post-fix
# ============================================================

def test_min_thermal_samples_constant():
    """MIN_THERMAL_SAMPLES must exist and be >= 2."""
    assert hasattr(cd, "MIN_THERMAL_SAMPLES"), "MIN_THERMAL_SAMPLES missing"
    assert cd.MIN_THERMAL_SAMPLES >= 2


def test_gate_accepts_n_samples_kwarg():
    """Gate signature must accept n_samples kwarg (source verification)."""
    sig = inspect.signature(cd._apply_thermal_sanity_gate)
    assert "n_samples" in sig.parameters, (
        f"gate signature is {sig}, missing n_samples"
    )
    # Must have default None for backward compat
    assert sig.parameters["n_samples"].default is None


def test_gate_nulls_too_few_samples():
    """n_samples < MIN_THERMAL_SAMPLES -> None."""
    assert _gate_accepts_n_samples(), "gate missing n_samples"
    r = cd._apply_thermal_sanity_gate(5.0, n_samples=1)
    assert r is None


def test_gate_nulls_zero_samples():
    """n_samples=0 -> None (no samples collected = no mean)."""
    assert _gate_accepts_n_samples(), "gate missing n_samples"
    r = cd._apply_thermal_sanity_gate(5.0, n_samples=0)
    assert r is None


def test_gate_nulls_two_samples_below_min():
    """n_samples=2 < MIN=3 -> None."""
    assert _gate_accepts_n_samples(), "gate missing n_samples"
    r = cd._apply_thermal_sanity_gate(5.0, n_samples=2)
    assert r is None


def test_gate_keeps_at_min_samples():
    """n_samples=MIN exactly -> value preserved (boundary)."""
    assert _gate_accepts_n_samples(), "gate missing n_samples"
    r = cd._apply_thermal_sanity_gate(5.0, n_samples=cd.MIN_THERMAL_SAMPLES)
    assert r == 5.0


def test_caller_passes_n_samples():
    """Source inspection: the cycle-close caller passes n_samples=len(samples)."""
    src = inspect.getsource(cd.CycleDetector)
    # Find the _apply_thermal_sanity_gate call
    idx = src.find("_apply_thermal_sanity_gate(")
    assert idx >= 0, "caller site not found"
    # Check that n_samples= appears within 200 chars of the call
    snippet = src[idx:idx + 400]
    assert "n_samples=len(self._thermal_kw_samples)" in snippet, (
        "caller does not pass n_samples=len(self._thermal_kw_samples)"
    )


def test_migration_v26_exists():
    """CycleDB must have async_migrate_to_v26."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    assert hasattr(CycleDB, "async_migrate_to_v26"), "async_migrate_to_v26 missing"


def test_migration_v26_sql_correct():
    """Migration SQL nulls short cycles: duration_s < 90."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    if not hasattr(CycleDB, "async_migrate_to_v26"):
        pytest.skip("covered by RED test")
    src = inspect.getsource(CycleDB.async_migrate_to_v26)
    assert "duration_s < 90" in src, "SQL missing duration_s < 90 filter"
    assert "thermal_kw_avg IS NOT NULL" in src, "SQL missing NOT NULL filter"
    assert "SET thermal_kw_avg = NULL" in src, "SQL missing SET NULL"


# ============================================================
# PRESERVATION — green pre AND post
# ============================================================

def test_gate_keeps_plenty_of_samples():
    """n_samples=10 well above MIN: value in range preserved."""
    if _gate_accepts_n_samples():
        r = cd._apply_thermal_sanity_gate(5.0, n_samples=10)
    else:
        r = cd._apply_thermal_sanity_gate(5.0)
    assert r == 5.0


def test_gate_still_nulls_over_max():
    """MAX_THERMAL_KW gate preserved: value > 14 still nulls."""
    if _gate_accepts_n_samples():
        r = cd._apply_thermal_sanity_gate(500.0, n_samples=100)
    else:
        r = cd._apply_thermal_sanity_gate(500.0)
    assert r is None


def test_gate_none_input_passthrough():
    """None input -> None output (post-fix too)."""
    if _gate_accepts_n_samples():
        r = cd._apply_thermal_sanity_gate(None, n_samples=10)
    else:
        r = cd._apply_thermal_sanity_gate(None)
    assert r is None


def test_gate_boundary_at_max():
    """Exactly MAX_THERMAL_KW (14.0): not nulled (uses > not >=)."""
    if _gate_accepts_n_samples():
        r = cd._apply_thermal_sanity_gate(cd.MAX_THERMAL_KW, n_samples=100)
    else:
        r = cd._apply_thermal_sanity_gate(cd.MAX_THERMAL_KW)
    assert r == cd.MAX_THERMAL_KW


# ============================================================
# Fixture baseline
# ============================================================

@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture absent")
def test_fixture_has_dirty_short_cycles():
    """Document baseline: fixture contains short cycles with non-null thermal_kw_avg."""
    con = sqlite3.connect(f"file:{FIXTURE}?mode=ro", uri=True)
    cur = con.execute(
        "SELECT COUNT(*) FROM cycles WHERE duration_s < 90 AND thermal_kw_avg IS NOT NULL"
    )
    pre_count = cur.fetchone()[0]
    con.close()
    assert pre_count > 0, (
        f"fixture expected dirty short cycles (4C found them); got {pre_count}"
    )
