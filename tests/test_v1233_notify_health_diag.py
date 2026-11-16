"""Tests for diagnostics notify_health emit (issue #384)."""
import inspect
from typing import Any

from custom_components.daikin_cycle_ml import diagnostics


def test_helper_exists() -> None:
    assert hasattr(diagnostics, "_notify_health_snapshot")

def test_emit_call_in_main_builder() -> None:
    src = inspect.getsource(
        diagnostics.async_get_config_entry_diagnostics
    )
    assert "_notify_health_snapshot" in src

def test_helper_returns_empty_when_coord_none() -> None:
    assert diagnostics._notify_health_snapshot(None) == {}

def test_helper_returns_dict_snapshot() -> None:
    class FakeCoord:
        @property
        def notify_health(self) -> dict[str, Any]:
            return {"fail_streak": 3,
                    "fail_target_configured": True,
                    "fail_logged_count": 1,
                    "currently_failing": True}
    expected = {"fail_streak": 3,
                "fail_target_configured": True,
                "fail_logged_count": 1,
                "currently_failing": True}
    assert diagnostics._notify_health_snapshot(FakeCoord()) == expected

def test_helper_returns_empty_when_notify_health_not_dict() -> None:
    class WeirdCoord:
        @property
        def notify_health(self) -> Any:
            return "not a dict"
    assert diagnostics._notify_health_snapshot(WeirdCoord()) == {}
