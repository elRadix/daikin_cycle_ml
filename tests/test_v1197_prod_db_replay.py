"""v1.19.7: replay 4 confirmed Prod 1 false-positive incidents.

Fixture: tests/fixtures/_prod1_20261103.db (gitignored — copy from a live
HA host via `docker cp`). Skipped when fixture absent (e.g. CI).
"""
import pathlib
import sqlite3
import time

import pytest

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "_prod1_20261103.db"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Prod 1 fixture absent (gitignored at tests/fixtures/)",
)


@pytest.fixture(scope="module")
def prod_rows():
    con = sqlite3.connect(f"file:{FIXTURE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM cycles ORDER BY start_ts")]
    con.close()
    return rows


@pytest.fixture(scope="module")
def prod_store(prod_rows):
    from custom_components.daikin_cycle_ml.storage.store import CycleStore
    s = CycleStore(maxlen=1000)
    s.hydrate_from_rows(prod_rows, good_threshold=70)
    return s


def _iso(iso):
    return time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone


INCIDENTS = [
    ("2026-10-07T15:35:18Z", "heating", 4, 3),
    ("2026-10-16T07:55:26Z", "dhw",     3, 1),
    ("2026-10-16T08:24:16Z", "dhw",     3, 1),
    ("2026-10-26T11:48:09Z", "heating", 4, 1),
]


@pytest.mark.parametrize("iso,mode,pre_count,post_count", INCIDENTS)
def test_incident_window(prod_store, iso, mode, pre_count, post_count):
    ts = _iso(iso)
    pre = prod_store.cycles_in_window_mode(ts, 3600, mode, exclude_transient=False)
    post = prod_store.cycles_in_window_mode(ts, 3600, mode, exclude_transient=True)
    thr = 4 if mode == "heating" else 3
    assert pre == pre_count, f"pre-fix count mismatch on real data: {pre} != {pre_count}"
    assert post == post_count, f"post-fix count mismatch on real data: {post} != {post_count}"
    assert pre >= thr, "pre-fix should have fired"
    assert post < thr, "post-fix must be silent"


def test_short_run_suppressed_20261026(prod_rows):
    ts = _iso("2026-10-26T11:48:09Z")
    cand = [r for r in prod_rows if r.get("end_ts") and r["end_ts"] <= ts]
    last = max(cand, key=lambda r: r["end_ts"])
    assert last["duration_s"] < 1200
    assert last["mode"] != "dhw"
    assert int(last.get("is_transient") or 0) == 1


def test_classifier_self_consistent(prod_rows):
    from custom_components.daikin_cycle_ml.coordinator import _classify_transient
    trans_kw = [
        r for r in prod_rows
        if int(r.get("is_transient") or 0) == 1
        and (r.get("thermal_kw_avg") or 0) > 0
    ]
    assert len(trans_kw) > 0, "fixture should contain transients with kw>0"
    for r in trans_kw:
        assert _classify_transient(r), (
            f"classifier drift: dur={r['duration_s']} "
            f"dT_max={r.get('dT_max')} rps_max={r.get('rps_max')}"
        )
