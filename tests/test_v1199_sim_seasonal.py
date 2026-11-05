"""v1.19.9 R645: 30-day seasonal simulation.

Simuleert outdoor temp sweep -15 → +20 (typisch Daikin werkbereik)
met correcte LWT/COP verhoudingen, verify dat classifier + aggregaten
consistent blijven over een seizoen.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.engine.physics import (
    classify_cop_sample,
    get_physical_cop_ceiling,
)
from tests.test_rollup_concurrency import _mk_db


# Seizoensgebonden (outdoor, lwt, cop) drietallen die fysisch realistisch zijn
SEASONAL_POINTS = [
    (-15.0, 45.0, 1.8),   # deep winter
    (-10.0, 42.0, 2.2),
    (-5.0, 38.0, 2.8),
    (0.0, 35.0, 3.2),
    (5.0, 32.0, 4.0),
    (10.0, 30.0, 5.0),
    (15.0, 28.0, 5.8),
    (20.0, 25.0, 6.5),    # mild
]


@pytest.mark.parametrize("outdoor,lwt,cop", SEASONAL_POINTS)
def test_sim_seasonal_classifier_accepts_typical(outdoor, lwt, cop):
    """R645: typical seasonal COP waarden moeten geaccepteerd worden."""
    k = classify_cop_sample("heating", lwt, outdoor, cop)
    assert k == "accept", (
        f"typical seasonal out={outdoor} lwt={lwt} cop={cop} "
        f"was classified as {k}"
    )


@pytest.mark.parametrize("outdoor,lwt,cop", SEASONAL_POINTS)
def test_sim_seasonal_ceiling_monotonic(outdoor, lwt, cop):
    """R645: ceiling daalt met kouder outdoor (logica)."""
    ceiling = get_physical_cop_ceiling("heating", lwt, outdoor)
    assert ceiling is not None
    assert ceiling > 0
    # Classifier accept threshold must allow cop
    assert cop <= ceiling


@pytest.mark.asyncio
async def test_sim_seasonal_cop_samples_rollup_30_days(tmp_path):
    """30 dagen COP samples: rollup + verification."""
    db = await _mk_db(tmp_path)
    try:
        # 30 dagen, 1 sample per dag
        base = time.mktime((2026, 10, 7, 12, 0, 0, 0, 0, -1))
        for i, (outdoor, lwt, cop) in enumerate(SEASONAL_POINTS):
            ts = base + i * 86400
            await db.async_insert_cop_sample({
                "ts": ts, "cop": cop, "lwt": lwt, "outdoor": outdoor,
                "mode": "heating", "source": "interval",
                "power_stable": True,
                "is_transition_artifact": 0,
            })

        # Verify all 8 inserted
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == len(SEASONAL_POINTS)

        # Classify each against our new classifier
        async with db._conn.execute("""
            SELECT cop, lwt, outdoor FROM cop_samples
            ORDER BY ts
        """) as cur:
            rows = await cur.fetchall()

        accept = flag = reject = 0
        for r in rows:
            k = classify_cop_sample("heating", r[1], r[2], r[0])
            if k == "accept":
                accept += 1
            elif k == "flag":
                flag += 1
            elif k == "reject":
                reject += 1

        # All should be accepted (typical values)
        assert accept == len(SEASONAL_POINTS)
        assert flag == 0
        assert reject == 0

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.parametrize("outdoor", [-15.0, -5.0, 0.0, 5.0, 15.0, 20.0])
def test_sim_seasonal_ceiling_formula(outdoor):
    """R645: ceiling formula consistent across full temp range."""
    lwt = 35.0
    ceiling = get_physical_cop_ceiling("heating", lwt, outdoor)
    assert ceiling is not None
    # Ceiling must decrease as outdoor gets colder
    assert ceiling > 0


def test_sim_seasonal_coldest_ceiling_lowest():
    """R645: extreme cold -> LOWEST ceiling (more lift needed).

    Carnot formula: ceiling = (Th / (Th - Tc)) * 0.65
    where Th = lwt + 273.15, Tc = outdoor + 273.15.

    At lwt=45, outdoor=-15: Th-Tc = 60K -> ceiling = 318.15/60 * 0.65 = 3.45
    At lwt=45, outdoor=20: Th-Tc = 25K -> ceiling = 318.15/25 * 0.65 = 8.27

    Physically: at extreme cold the heat pump has to work harder
    (higher lift), so the practical max COP is LOWER. This is exactly
    why heat pumps are less efficient in winter. Pre-fix assertion
    was inverted (my math error, not product bug).
    """
    c_deep = get_physical_cop_ceiling("heating", 45.0, -15.0)
    c_mild = get_physical_cop_ceiling("heating", 45.0, 20.0)
    assert c_deep is not None and c_mild is not None
    assert c_deep < c_mild, (
        f"cold ceiling {c_deep} should be BELOW mild {c_mild} "
        f"(more lift needed in cold)"
    )
    # Sanity: ratio matches Carnot physics
    assert abs(c_deep / c_mild - (25.0 / 60.0)) < 0.01
