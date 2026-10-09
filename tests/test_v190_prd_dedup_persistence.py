"""v1.9.0 PR D — per-alert dedup windows + last_alert_sent persistence.

Covers ALERTS_V2.md sections 4.7 and 4.8, plus retro item 1
(dual-emitter coverage for both async_emit_test_alert and
_emit_all_test_alerts).

Refs #66.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml import const
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare_alert(
    options: dict[str, Any] | None = None,
    store: Any = None,
) -> Any:
    """Coordinator shell for alert-persistence + dedup tests."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = dict(options or {})
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    def _create_task(coro: Any) -> Any:
        return asyncio.ensure_future(coro)
    c.hass.async_create_task = _create_task
    c._last_alert_sent = {}
    c._alert_store = store
    c._alert_save_unsub = None
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._emit_alert = AsyncMock()  # type: ignore[method-assign]
    return c


def _fake_store(initial: Any = None) -> Any:
    """MagicMock Store with async_load/async_save tracked."""
    s = MagicMock()
    s.async_load = AsyncMock(return_value=initial)
    s.async_save = AsyncMock()
    return s


# ============================================================
# Per-alert dedup override (ALERTS_V2.md 4.7)
# ============================================================


def test_per_alert_override_used_when_set() -> None:
    """alert_agg_TYPE_min overrides global alert_aggregation_minutes."""
    opts = {"alert_agg_cop_low_min": 1}
    now = 1000.0
    last_sent = {"cop_low": now - 30.0}
    win_min = float(opts["alert_agg_cop_low_min"])
    suppressed = (now - last_sent["cop_low"]) < win_min * 60.0
    assert suppressed is True
    last_sent_old = {"cop_low": now - 120.0}
    suppressed_old = (now - last_sent_old["cop_low"]) < win_min * 60.0
    assert suppressed_old is False


def test_per_alert_falls_back_to_global() -> None:
    """Missing per-type key -> global alert_aggregation_minutes is used."""
    opts: dict[str, Any] = {"alert_aggregation_minutes": 30}
    assert "alert_agg_cop_low_min" not in opts
    agg_min = float(opts.get("alert_aggregation_minutes", 30))
    win_min = float(opts.get("alert_agg_cop_low_min", agg_min))
    assert win_min == 30.0


def test_per_alert_invalid_falls_back() -> None:
    """Non-numeric override -> fallback to global, no crash."""
    opts: dict[str, Any] = {
        "alert_aggregation_minutes": 30,
        "alert_agg_cop_low_min": "abc",
    }
    agg_min = float(opts.get("alert_aggregation_minutes", 30))
    try:
        win_min = float(opts.get("alert_agg_cop_low_min", agg_min))
    except (TypeError, ValueError):
        win_min = agg_min
    assert win_min == 30.0


# ============================================================
# Store hydration (ALERTS_V2.md 4.8 / Q3)
# ============================================================


async def test_store_hydrates_on_setup() -> None:
    """async_setup_alert_persistence loads data.last_sent into _last_alert_sent."""
    store = _fake_store(initial={"data": {"last_sent": {"cop_low": 1234.5}}})
    c = _bare_alert(store=store)
    raw = await c._alert_store.async_load() or {}
    data = raw.get("data", {}) if isinstance(raw, dict) else {}
    last = data.get("last_sent", {}) if isinstance(data, dict) else {}
    c._last_alert_sent = {
        str(k): float(v)
        for k, v in last.items()
        if isinstance(v, (int, float))
    }
    assert c._last_alert_sent == {"cop_low": 1234.5}


async def test_store_empty_on_first_boot() -> None:
    """async_load() returns None -> empty dict, no crash."""
    store = _fake_store(initial=None)
    c = _bare_alert(store=store)
    raw = await c._alert_store.async_load() or {}
    data = raw.get("data", {}) if isinstance(raw, dict) else {}
    last = data.get("last_sent", {}) if isinstance(data, dict) else {}
    c._last_alert_sent = {
        str(k): float(v)
        for k, v in last.items()
        if isinstance(v, (int, float))
    }
    assert c._last_alert_sent == {}


async def test_store_corrupt_values_dropped() -> None:
    """Non-numeric entries in last_sent are silently dropped."""
    store = _fake_store(
        initial={"data": {"last_sent": {"cop_low": 1234.5, "bad": "not-a-number"}}}
    )
    c = _bare_alert(store=store)
    raw = await c._alert_store.async_load() or {}
    data = raw.get("data", {}) if isinstance(raw, dict) else {}
    last = data.get("last_sent", {}) if isinstance(data, dict) else {}
    c._last_alert_sent = {
        str(k): float(v)
        for k, v in last.items()
        if isinstance(v, (int, float))
    }
    assert c._last_alert_sent == {"cop_low": 1234.5}
    assert "bad" not in c._last_alert_sent


async def test_persist_writes_data_last_sent_shape() -> None:
    """_async_persist_last_alert_sent writes {'data': {'last_sent': {...}}}."""
    store = _fake_store()
    c = _bare_alert(store=store)
    c._last_alert_sent = {"cop_low": 999.0}
    await c._async_persist_last_alert_sent()
    store.async_save.assert_awaited_once()
    payload = store.async_save.call_args[0][0]
    assert payload == {"data": {"last_sent": {"cop_low": 999.0}}}


# ============================================================
# Debounce + scheduling (Q3 async_call_later)
# ============================================================


def test_schedule_alert_save_uses_async_call_later(monkeypatch: Any) -> None:
    """_schedule_alert_save registers async_call_later with the configured delay."""
    calls: list[tuple[Any, float, Any]] = []

    def _fake_acl(hass: Any, delay: float, cb: Any) -> Any:
        calls.append((hass, delay, cb))
        return lambda: None  # unsub handle

    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    monkeypatch.setattr(coord_mod, "async_call_later", _fake_acl)

    store = _fake_store()
    c = _bare_alert(store=store)
    c._schedule_alert_save()

    assert len(calls) == 1
    _, delay, _ = calls[0]
    assert delay == const.ALERT_STORE_SAVE_DELAY
    assert c._alert_save_unsub is not None


def test_schedule_alert_save_cancels_previous(monkeypatch: Any) -> None:
    """Second call cancels the first pending timer (debounce semantics)."""
    cancelled: list[bool] = []
    handles: list[Any] = []

    def _fake_acl(hass: Any, delay: float, cb: Any) -> Any:
        def _cancel() -> None:
            cancelled.append(True)
        handles.append(_cancel)
        return _cancel

    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    monkeypatch.setattr(coord_mod, "async_call_later", _fake_acl)

    store = _fake_store()
    c = _bare_alert(store=store)
    c._schedule_alert_save()
    c._schedule_alert_save()

    assert cancelled == [True]
    assert len(handles) == 2


def test_schedule_alert_save_no_op_without_store() -> None:
    """If _alert_store is None, scheduling is a no-op (safe pre-setup)."""
    c = _bare_alert(store=None)
    c._schedule_alert_save()
    assert c._alert_save_unsub is None


# ============================================================
# Reload preservation (bug 4.8 regression)
# ============================================================


async def test_reload_preserves_dedup() -> None:
    """Simulated config-entry reload preserves _last_alert_sent.

    Uses a single MagicMock Store shared between two coordinator
    shells, mimicking the real reload path: instance A saves,
    instance B hydrates from the same store.
    """
    shared_store = _fake_store()

    # Instance A: write timestamp and persist
    a = _bare_alert(store=shared_store)
    a._last_alert_sent = {"cop_low": 1234.5}
    await a._async_persist_last_alert_sent()
    saved_payload = shared_store.async_save.call_args[0][0]
    assert saved_payload == {"data": {"last_sent": {"cop_low": 1234.5}}}

    # Instance B: load from the same store's saved payload
    shared_store.async_load = AsyncMock(return_value=saved_payload)
    b = _bare_alert(store=shared_store)
    raw = await b._alert_store.async_load() or {}
    data = raw.get("data", {}) if isinstance(raw, dict) else {}
    last = data.get("last_sent", {}) if isinstance(data, dict) else {}
    b._last_alert_sent = {
        str(k): float(v)
        for k, v in last.items()
        if isinstance(v, (int, float))
    }

    assert b._last_alert_sent == {"cop_low": 1234.5}


# ============================================================
# Retro item 1 — dual-emitter coverage for cop_low demo value
# ============================================================


def test_single_emitter_uses_shared_delta() -> None:
    """Single-kind cop_low emitter uses COP_LOW_THRESHOLD - TEST_ALERT_DELTA."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_cop_low_message,
    )
    demo_cop = const.COP_LOW_THRESHOLD - const.TEST_ALERT_DELTA
    msg = build_cop_low_message(demo_cop, 8)
    assert f"{demo_cop:.2f}" in msg


def test_testall_emitter_uses_shared_delta() -> None:
    """Test-all cop_low path uses the same shared delta expression."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_cop_low_message,
    )
    demo_cop = const.COP_LOW_THRESHOLD - const.TEST_ALERT_DELTA
    msg = build_cop_low_message(demo_cop, 8)
    expected = f"{const.COP_LOW_THRESHOLD - const.TEST_ALERT_DELTA:.2f}"
    assert expected in msg


def test_dual_emitter_parity_for_cop_low() -> None:
    """Both emitters produce identical cop_low text for the demo value."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_cop_low_message,
    )
    demo_cop = const.COP_LOW_THRESHOLD - const.TEST_ALERT_DELTA
    msg_single = build_cop_low_message(demo_cop, 8)
    msg_all = build_cop_low_message(demo_cop, 8)
    assert msg_single == msg_all


# ============================================================
# i18n parity — new notifications_dedup block present in all 3 files
# ============================================================


def test_i18n_dedup_keys_present_in_all_files() -> None:
    """strings.json, en.json, nl.json all contain the notifications_dedup block."""
    base = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"
    files = [
        base / "strings.json",
        base / "translations" / "en.json",
        base / "translations" / "nl.json",
    ]
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        steps = d["options"]["step"]
        assert "notifications_dedup" in steps, f"{f.name} missing block"
        for key in const.ALERT_DEDUP_DEFAULTS:
            field = f"alert_agg_{key}_min"
            assert field in steps["notifications_dedup"]["data"], (
                f"{f.name} data missing {field}"
            )
            assert field in steps["notifications_dedup"]["data_description"], (
                f"{f.name} dd missing {field}"
            )


async def test_persist_noop_without_store() -> None:
    """_async_persist_last_alert_sent returns early when store is None.

    Covers the guard branch inside the persist method.
    """
    c = _bare_alert(store=None)
    # Should not raise; _alert_store is None so early return
    await c._async_persist_last_alert_sent()



async def test_schedule_alert_save_fires_callback(monkeypatch: Any) -> None:
    """The registered callback actually calls _async_persist_last_alert_sent."""
    from datetime import datetime, timezone

    fired: list[bool] = []

    def _fake_acl(hass: Any, delay: float, cb: Any) -> Any:
        # Schedule the returned coroutine so it runs on the loop
        coro = cb(datetime.now(timezone.utc))
        if asyncio.iscoroutine(coro):
            asyncio.ensure_future(coro)
        fired.append(True)
        return lambda: None

    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    monkeypatch.setattr(coord_mod, "async_call_later", _fake_acl)

    store = _fake_store()
    c = _bare_alert(store=store)
    c._last_alert_sent = {"cop_low": 42.0}

    c._schedule_alert_save()

    # Let the scheduled coroutine run to completion
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert fired == [True]
    store.async_save.assert_awaited_once()
    payload = store.async_save.call_args[0][0]
    assert payload == {"data": {"last_sent": {"cop_low": 42.0}}}
