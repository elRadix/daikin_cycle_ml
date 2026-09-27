"""Batch 52b10: AlertSpec context + notify payload enrichment."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    AlertSpec,
)


def _mk(options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c.options = dict(options or {"notify_service": "notify.x"})
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._kmeans_centroids = []
    c._cluster_labels = {0: "normal", 1: "abnormal"}
    return c


# --- AlertSpec dataclass ---

def test_alertspec_context_default_none():
    spec = AlertSpec(
        alert_type="t", severity="warning", message="m",
        notif_id="nid", dedupe_key="dk",
    )
    assert spec.context is None


def test_alertspec_context_explicit():
    spec = AlertSpec(
        alert_type="t", severity="warning", message="m",
        notif_id="nid", dedupe_key="dk",
        context={"mode": "heating", "cluster": 0},
    )
    assert spec.context == {"mode": "heating", "cluster": 0}


# --- _emit_alert context forwarding ---

def test_emit_alert_forwards_context_to_notify():
    c = _mk(options={"notify_service": "notify.telegram"})
    spec = AlertSpec(
        alert_type="t", severity="warning", message="hello",
        notif_id="nid", dedupe_key="dk", persistent=False,
        context={"mode": "heating", "cop": 2.1},
    )
    asyncio.run(c._emit_alert(spec))
    calls = c.hass.services.async_call.await_args_list
    notify_call = [x for x in calls if x.args[0] == "notify"][0]
    payload = notify_call.args[2]
    assert payload["message"] == "hello"
    assert payload["mode"] == "heating"
    assert payload["cop"] == 2.1


def test_emit_alert_no_context_still_works():
    c = _mk(options={"notify_service": "notify.telegram"})
    spec = AlertSpec(
        alert_type="t", severity="warning", message="hello",
        notif_id="nid", dedupe_key="dk", persistent=False,
    )
    asyncio.run(c._emit_alert(spec))
    calls = c.hass.services.async_call.await_args_list
    notify_call = [x for x in calls if x.args[0] == "notify"][0]
    payload = notify_call.args[2]
    assert payload == {"message": "hello"}


def test_emit_alert_context_none_explicit():
    c = _mk(options={"notify_service": "notify.telegram"})
    spec = AlertSpec(
        alert_type="t", severity="warning", message="hello",
        notif_id="nid", dedupe_key="dk", persistent=False,
        context=None,
    )
    asyncio.run(c._emit_alert(spec))
    calls = c.hass.services.async_call.await_args_list
    notify_call = [x for x in calls if x.args[0] == "notify"][0]
    assert notify_call.args[2] == {"message": "hello"}


def test_emit_alert_persistent_ignores_context():
    c = _mk(options={"notify_service": "notify.telegram"})
    spec = AlertSpec(
        alert_type="t", severity="warning", message="hello",
        notif_id="nid", dedupe_key="dk", persistent=True,
        context={"mode": "heating"},
    )
    asyncio.run(c._emit_alert(spec))
    calls = c.hass.services.async_call.await_args_list
    pn_call = [x for x in calls if x.args[0] == "persistent_notification"][0]
    payload = pn_call.args[2]
    assert set(payload.keys()) == {"title", "message", "notification_id"}

