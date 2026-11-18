"""#408: prod-1 v1.23.2 diagnostics follow-ups (2026-11-18 22:05).

A. learned short-run threshold 2 min (configured 20) -> short_run never fires
B. legacy cop_hourly hours with means 0.47 / 16.49 (pre-#391/#394 samples)
C. daily_summary duration_min (full length) > duration_max (within-day)
D. external COP sensor 7.59 vs measured ~6.1 vs ESPAltherma 5.61, invisible
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.diagnostics import _cop_cross_check, _num
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds,
)
from custom_components.daikin_cycle_ml.sensor import _attrs_learned
from custom_components.daikin_cycle_ml.storage.db import CycleDB

# --- A. learned short-run floor -------------------------------------------------


def _adaptive_with_short_runs() -> AdaptiveThresholds:
    at = AdaptiveThresholds(min_samples=20)
    # prod-1 pattern: a quarter of the runs last ~1-2 min, the rest are long
    for i in range(40):
        dur_min = 1.5 if i % 4 == 0 else 300.0 + i
        at.observe_cycle("heating", dur_min * 60.0, 600.0)
    return at


class _Coord(DaikinCycleMLCoordinator):
    options: dict[str, Any] = {}  # type: ignore[assignment]


def _coord(options: dict[str, Any], at: AdaptiveThresholds) -> _Coord:
    c = object.__new__(_Coord)
    c.options = options
    c.adaptive = at
    c._resolve_adaptive_mode = lambda: "heating"  # type: ignore[method-assign]
    return c


def test_learner_collapses_to_2_min():
    assert _adaptive_with_short_runs().learn_short_run_min("heating") == 2


def test_effective_short_run_bounded_at_half_of_configured():
    c = _coord({"adaptive_thresholds_enabled": True}, _adaptive_with_short_runs())
    assert c._effective_threshold("short_run_threshold_min", 20) == 10
    assert c._effective_threshold("short_run_threshold_min", 7) == 4


def test_effective_short_run_learned_higher_is_kept():
    at = AdaptiveThresholds(min_samples=20)
    for _ in range(30):
        at.observe_cycle("heating", 45 * 60.0, None)
    c = _coord({"adaptive_thresholds_enabled": True}, at)
    assert c._effective_threshold("short_run_threshold_min", 20) == 45


def test_adaptive_off_uses_configured():
    c = _coord({}, _adaptive_with_short_runs())
    assert c._effective_threshold("short_run_threshold_min", 20) == 20


def test_other_keys_not_bounded():
    at = AdaptiveThresholds(min_samples=20)
    for _ in range(30):
        at.observe_cycle("heating", None, 60.0)          # 1 min off
    c = _coord({"adaptive_thresholds_enabled": True}, at)
    assert c._effective_threshold("good_off_threshold_min", 20) == 1


def test_learned_sensor_exposes_effective_value():
    c = _coord(
        {"adaptive_thresholds_enabled": True, "short_run_threshold_min": 20},
        _adaptive_with_short_runs(),
    )
    attrs = _attrs_learned(None, c)  # type: ignore[arg-type]
    assert attrs["short_run_effective_min"] == 10


def test_learned_sensor_effective_error_is_none():
    c = _coord({"adaptive_thresholds_enabled": True}, _adaptive_with_short_runs())

    def boom(*_a: Any) -> int:
        raise RuntimeError("x")

    c._effective_threshold = boom  # type: ignore[method-assign]
    assert _attrs_learned(None, c)["short_run_effective_min"] is None  # type: ignore[arg-type]


# --- B/C. migration v30 + daily min/max -----------------------------------------

D0, D1 = "2026-11-16", "2026-11-17"


def _ts(day: str, h: int, m: int = 0) -> float:
    return time.mktime(time.strptime(f"{day} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M"))


async def _mk_db(tmp_path) -> CycleDB:
    db = CycleDB(str(tmp_path / "v30.db"))
    await db.async_open()
    await db.async_initialize()
    await db.async_ensure_cop_samples_table()
    await db.async_create_cop_hourly_v14()
    return db


async def _close(db: CycleDB) -> None:
    await db.async_close()
    await asyncio.sleep(0.05)


async def _hourly(db: CycleDB) -> dict[tuple[int, str], float]:
    async with db._require().execute(
        "SELECT ts_hour, mode, cop_mean FROM cop_hourly"
    ) as cur:
        return {(int(r[0]), r[1]): float(r[2]) for r in await cur.fetchall()}


async def test_v30_flags_legacy_outliers_and_rebuilds_hours(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        h = int(_ts(D1, 10) // 3600)
        legacy = [  # (hour offset, cop, mode) as stored before the gates
            (0, 16.486, "heating"),          # only sample > MAX_COP
            (1, 0.47, "heating"),            # only sample < floor
            (2, 3.5, "heating"), (2, 16.0, "heating"),   # mixed hour
            (3, 0.9, "dhw"),                 # DHW below floor
            (4, 0.5, "cooling"),             # cooling: floor does not apply
        ]
        for off, cop, mode in legacy:
            await conn.execute(
                "INSERT INTO cop_samples (ts, cop, mode, source, "
                "is_transition_artifact) VALUES (?, ?, ?, 'interval', 0)",
                ((h + off) * 3600 + 60, cop, mode),
            )
        await conn.commit()
        await db._rebuild_cop_hourly_for_hours([h + i for i in range(5)])
        before = await _hourly(db)
        assert before[(h, "heating")] == pytest.approx(16.486)
        assert before[(h + 1, "heating")] == pytest.approx(0.47)

        stats = await db.async_migrate_to_v30()
        assert stats["flagged_samples"] == 4 and stats["completed"] is True
        after = await _hourly(db)
        assert (h, "heating") not in after           # only outlier -> gone
        assert (h + 1, "heating") not in after
        assert (h + 3, "dhw") not in after
        assert after[(h + 2, "heating")] == pytest.approx(3.5)
        assert after[(h + 4, "cooling")] == pytest.approx(0.5)
        assert await db.async_migrate_to_v30() == {"skipped": 1}
    finally:
        await _close(db)


async def test_v30_rebuilds_daily_summary_min_le_max(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        for st, en in ((_ts(D0, 23), _ts(D1, 2)), (_ts(D1, 10), _ts(D1, 10, 30))):
            await db.async_insert_cycle({
                "start_ts": st, "end_ts": en, "duration_s": int(en - st),
                "mode": "heating", "quality_score": 80, "is_transient": 0,
            })
        stats = await db.async_migrate_to_v30()
        assert stats["days_rebuilt"] == 2
        rows = {r["day"]: r for r in await db.async_daily_summary(days=36500)}
        d0, d1 = rows[D0], rows[D1]
        assert d0["duration_min"] == d0["duration_max"] == 3600   # 23:00-24:00
        assert d1["duration_min"] == 1800                          # 10:00-10:30
        assert d1["duration_max"] == 7200                          # 00:00-02:00 tail
        for r in (d0, d1):
            assert r["duration_min"] <= r["duration_max"] <= r["total_duration_s"]
    finally:
        await _close(db)


async def test_v30_on_empty_db(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        stats = await db.async_migrate_to_v30()
        assert stats == {"flagged_samples": 0, "hours_rebuilt": 0,
                         "days_rebuilt": 0, "completed": True}
    finally:
        await _close(db)


# --- D. COP cross-check in diagnostics -----------------------------------------

PROD1_ATTRS = {
    "Flow sensor (l/min)": 11.6,
    "Leaving water temp. before BUH (R1T)": 32.3,
    "Leaving water temp. after BUH (R2T)": 32.2,
    "Inlet water temp.(R4T)": 29.0,
    "Stats: COP estimated": 5.61,
}


def _diag(cop: Any, attrs: dict[str, Any], power: Any) -> dict[str, Any]:
    snap = SimpleNamespace(cop=cop, cop_source="cop_sensor", attrs=attrs)
    coord = SimpleNamespace(_read_power_w=power)
    return _cop_cross_check(coord, snap)


def test_cross_check_prod1_sensor_reads_high():
    out = _diag(7.59, PROD1_ATTRS, lambda: 435.47)
    assert out["cop_used"] == 7.59 and out["cop_source"] == "cop_sensor"
    assert 5.5 < out["cop_measured_flow_dt_power"] < 6.5
    assert out["cop_espaltherma_estimate"] == 5.61
    assert out["used_vs_measured_pct"] > 15


@pytest.mark.parametrize(
    "cop,attrs,power",
    [
        (7.59, PROD1_ATTRS, lambda: None),          # no power meter
        (7.59, {}, lambda: 435.47),                 # no flow / dT
        (7.59, PROD1_ATTRS, None),                  # coordinator without reader
        (None, PROD1_ATTRS, lambda: 435.47),        # no COP used
    ],
)
def test_cross_check_partial(cop, attrs, power):
    out = _diag(cop, attrs, power)
    assert out["used_vs_measured_pct"] is None


def test_cross_check_reader_error():
    def boom() -> float:
        raise RuntimeError("x")

    out = _diag(7.59, PROD1_ATTRS, boom)
    assert out["cop_measured_flow_dt_power"] is None


def test_num_helper():
    assert _num(True) is None and _num("1") is None and _num(2) == 2.0
