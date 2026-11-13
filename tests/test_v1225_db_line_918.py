"""Explicit coverage for db.py line 918 (gaps list comprehension)."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.mark.asyncio
async def test_median_dhw_gap_line_918():
    """Force execution of line 918: gaps = [r[0] for r in rows if r[0] is not None]."""
    db = CycleDB.__new__(CycleDB)
    
    # Mock the database cursor to return rows with None gaps
    # This ensures 'rows' is non-empty, but 'gaps' becomes empty
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[(None,), (None,)])
    
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    
    db._require = MagicMock(return_value=mock_conn)
    
    # Call the function
    res = await db.async_get_median_dhw_gap()
    
    # Should fallback to 300.0 because gaps is empty
    assert res == 300.0
