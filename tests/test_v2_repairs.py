"""RED tests for ESPAltherma v2-specific repair issue (issue #281).

R634: These tests MUST FAIL on current code if the v2-specific repair
issue does not exist. Expected RED failures:
- `ISSUE_V2_MISSING_ATTRS` constant missing
- `_check_v2_missing_attrs` function missing

Regression guards (must remain green before AND after fix):
- `_check_missing_attrs` (monolithic) unchanged
- clear on recovery works
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import repairs


def _snap(missing: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        missing_attrs=list(missing or []),
        last_success_ts=0.0,
    )


def _coord(source_type: str = "individual") -> SimpleNamespace:
    return SimpleNamespace(
        source_type=source_type,
        individual_prefix="sensor.espaltherma_",
        _db_integrity_ok=True,
        _notify_fail_streak=0,
        _notify_fail_target="",
        _migration_error=None,
    )


@pytest.fixture
def fake_ir(monkeypatch):
    """Patch the issue_registry so we can assert create/delete calls."""
    created: list[tuple[str, dict[str, object]]] = []
    deleted: list[str] = []

    def fake_create(hass, domain, issue_id, **kwargs):
        created.append((issue_id, dict(kwargs)))

    def fake_delete(hass, domain, issue_id):
        deleted.append(issue_id)

    monkeypatch.setattr(repairs.ir, "async_create_issue", fake_create)
    monkeypatch.setattr(repairs.ir, "async_delete_issue", fake_delete)

    class Tracker:
        def __init__(self):
            self.created = created
            self.deleted = deleted

    return Tracker()


# ---------- New v2-specific issue behaviour ----------


def test_v2_issue_constant_exists() -> None:
    """RED: ISSUE_V2_MISSING_ATTRS not defined yet."""
    assert hasattr(repairs, "ISSUE_V2_MISSING_ATTRS"), (
        "repairs.py must define ISSUE_V2_MISSING_ATTRS for #281"
    )
    assert repairs.ISSUE_V2_MISSING_ATTRS == "espaltherma_v2_missing_attrs"


def test_v2_issue_created_when_individual_and_missing(fake_ir) -> None:
    """RED: _check_v2_missing_attrs does not exist yet."""
    hass = MagicMock()
    snap = _snap(missing=["BUH Step1", "BUH Step2", "Defrost Operation"])
    coord = _coord(source_type="individual")
    assert hasattr(repairs, "_check_v2_missing_attrs"), (
        "repairs.py must define _check_v2_missing_attrs for #281"
    )
    repairs._check_v2_missing_attrs(hass, "entry_abc", snap, coord)
    ids = [c[0] for c in fake_ir.created]
    assert "espaltherma_v2_missing_attrs_entry_abc" in ids
    # Placeholders must list missing labels
    entry = next(c for c in fake_ir.created if c[0].startswith("espaltherma_v2"))
    ph = entry[1].get("translation_placeholders", {})
    assert ph.get("count") == "3"
    assert "BUH Step1" in ph.get("labels", "")


def test_v2_issue_severity_is_warning(fake_ir) -> None:
    """RED: severity must be WARNING (not ERROR, fixable by user)."""
    hass = MagicMock()
    snap = _snap(missing=["Defrost Operation"])
    coord = _coord(source_type="individual")
    repairs._check_v2_missing_attrs(hass, "e1", snap, coord)
    entry = next(c for c in fake_ir.created if c[0].startswith("espaltherma_v2"))
    assert entry[1].get("severity") == repairs.ir.IssueSeverity.WARNING


def test_v2_issue_not_created_when_complete(fake_ir) -> None:
    """No missing -> delete issue, no create."""
    hass = MagicMock()
    snap = _snap(missing=[])
    coord = _coord(source_type="individual")
    repairs._check_v2_missing_attrs(hass, "e1", snap, coord)
    assert not fake_ir.created
    assert "espaltherma_v2_missing_attrs_e1" in fake_ir.deleted


def test_v2_issue_not_created_in_monolithic(fake_ir) -> None:
    """Monolithic mode -> never touch v2 issue."""
    hass = MagicMock()
    snap = _snap(missing=["X"])
    coord = _coord(source_type="monolithic")
    repairs._check_v2_missing_attrs(hass, "e1", snap, coord)
    assert not fake_ir.created
    assert "espaltherma_v2_missing_attrs_e1" in fake_ir.deleted


def test_v2_issue_deleted_on_recovery(fake_ir) -> None:
    """Missing resolved -> delete issue."""
    hass = MagicMock()
    repairs._check_v2_missing_attrs(
        hass, "e1", _snap(missing=[]), _coord(source_type="individual")
    )
    assert "espaltherma_v2_missing_attrs_e1" in fake_ir.deleted


def test_v2_issue_dispatched_from_async_check_repairs(fake_ir) -> None:
    """RED: async_check_repairs must call the new v2 check."""
    hass = MagicMock()
    snap = _snap(missing=["BUH Step1"])
    coord = _coord(source_type="individual")
    import asyncio
    asyncio.run(
        repairs.async_check_repairs(hass, "e1", snap, coordinator=coord)
    )
    ids = [c[0] for c in fake_ir.created]
    assert any(i.startswith("espaltherma_v2_missing_attrs") for i in ids), (
        f"v2 issue not created via async_check_repairs, got: {ids}"
    )


# ---------- Regression: monolithic stays unchanged ----------


def test_monolithic_missing_attrs_still_works(fake_ir) -> None:
    """Regression: generic missing_attrs repair unchanged for monolithic."""
    hass = MagicMock()
    snap = _snap(missing=["Operation Mode"])
    coord = _coord(source_type="monolithic")
    repairs._check_missing_attrs(hass, "e1", snap)
    ids = [c[0] for c in fake_ir.created]
    assert "missing_attrs_e1" in ids
    assert not any(i.startswith("espaltherma_v2") for i in ids)
