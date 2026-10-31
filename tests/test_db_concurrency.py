import asyncio
import time

import pytest

from tests.test_rollup_concurrency import _mk_db, _sample


@pytest.mark.asyncio
async def test_simultaneous_writes(tmp_path):
    db = await _mk_db(tmp_path)
    now = time.time()
    async def write_batch(offset):
        for i in range(5):
            await db.async_insert_cop_sample(_sample(now - i * 60 - offset, "heating", 5.0))

    await asyncio.gather(write_batch(0), write_batch(1), write_batch(2))
    count = await db.async_count_cop_samples()
    assert count == 15
