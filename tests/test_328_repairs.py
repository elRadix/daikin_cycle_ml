"""#328 Phase 5: Repairs safety net for dhw_missing_suspect.

Behavior matrix:
  dhw_present=True  + any history  -> no issue (normal)
  dhw_present=False + history > 0  -> issue raised (Frans safety net)
  dhw_present=False + history = 0  -> no issue (genuine no-DHW)
  user flips to True               -> issue cleared
  dhw_present=True                 -> DB never queried (perf short-circuit)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.helpers import issue_registry as ir
from custom_components.daikin_cycle_ml.const import DOMAIN
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk_coord(hass, dhw_present, db_count):
    entry = MagicMock(); entry.options = {}; entry.data = {}
    coord = DaikinCycleMLCoordinator(hass, entry)
    coord.dhw_present = dhw_present
    coord.db = MagicMock()
    coord.db.async_get_dhw_cycle_count = AsyncMock(return_value=db_count)
    return coord


def _has_issue(hass, entry_id):
    from custom_components.daikin_cycle_ml.repairs import ISSUE_DHW_MISSING_SUSPECT
    reg = ir.async_get(hass)
    return reg.async_get_issue(DOMAIN, f"{ISSUE_DHW_MISSING_SUSPECT}_{entry_id}") is not None


@pytest.mark.asyncio
async def test_issue_raised_no_dhw_but_historical(hass):
    """#176 Frans: valve disabled + historical DHW -> issue raised."""
    from custom_components.daikin_cycle_ml.repairs import _check_dhw_missing_suspect
    coord = _mk_coord(hass, dhw_present=False, db_count=5)
    await _check_dhw_missing_suspect(hass, "entry_test_1", coord)
    assert _has_issue(hass, "entry_test_1")


@pytest.mark.asyncio
async def test_issue_not_raised_when_dhw_present(hass):
    """Normal users: dhw_present=True -> no issue regardless of DB."""
    from custom_components.daikin_cycle_ml.repairs import _check_dhw_missing_suspect
    coord = _mk_coord(hass, dhw_present=True, db_count=5)
    await _check_dhw_missing_suspect(hass, "entry_test_2", coord)
    assert not _has_issue(hass, "entry_test_2")


@pytest.mark.asyncio
async def test_issue_cleared_when_dhw_true(hass):
    """Once dhw_present becomes True (user sets 'always'), issue cleared."""
    from custom_components.daikin_cycle_ml.repairs import _check_dhw_missing_suspect
    coord = _mk_coord(hass, dhw_present=False, db_count=5)
    await _check_dhw_missing_suspect(hass, "entry_test_3", coord)
    assert _has_issue(hass, "entry_test_3")
    coord.dhw_present = True
    await _check_dhw_missing_suspect(hass, "entry_test_3", coord)
    assert not _has_issue(hass, "entry_test_3")


@pytest.mark.asyncio
async def test_no_historical_dhw_no_issue(hass):
    """Genuine no-DHW installs (never had tank) -> no issue."""
    from custom_components.daikin_cycle_ml.repairs import _check_dhw_missing_suspect
    coord = _mk_coord(hass, dhw_present=False, db_count=0)
    await _check_dhw_missing_suspect(hass, "entry_test_4", coord)
    assert not _has_issue(hass, "entry_test_4")


@pytest.mark.asyncio
async def test_short_circuits_db_when_dhw_present(hass):
    """Perf: dhw_present=True -> DB not queried."""
    from custom_components.daikin_cycle_ml.repairs import _check_dhw_missing_suspect
    coord = _mk_coord(hass, dhw_present=True, db_count=5)
    await _check_dhw_missing_suspect(hass, "entry_test_5", coord)
    coord.db.async_get_dhw_cycle_count.assert_not_awaited()


def test_dhw_check_wired_in_async_check_repairs():
    """AST contract: _check_dhw_missing_suspect must be referenced in async_check_repairs."""
    import ast
    from pathlib import Path
    src = Path("custom_components/daikin_cycle_ml/repairs.py").read_text()
    tree = ast.parse(src)
    fn = next(
        (n for n in tree.body
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_check_repairs"),
        None,
    )
    assert fn is not None, "async_check_repairs missing"
    refs = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Name) and n.id == "_check_dhw_missing_suspect"
    ]
    assert refs, "_check_dhw_missing_suspect not referenced in async_check_repairs"
