"""v1.4.3 regression: setup order backfill before hydrate."""
from __future__ import annotations

import inspect

from custom_components.daikin_cycle_ml import async_setup_entry


def test_setup_entry_backfill_runs_before_hydrate():
    """v1.4.3: backfill must execute before hydrate so hydrated
    records carry quality_score."""
    src = inspect.getsource(async_setup_entry)
    idx_back = src.find("_async_backfill_quality(coordinator)")
    idx_hyd = src.find("_async_hydrate_store(coordinator)")
    assert idx_back != -1, "backfill call missing"
    assert idx_hyd != -1, "hydrate call missing"
    assert idx_back < idx_hyd, (
        "backfill must run BEFORE hydrate; found hydrate at "
        + str(idx_hyd) + " backfill at " + str(idx_back)
    )
