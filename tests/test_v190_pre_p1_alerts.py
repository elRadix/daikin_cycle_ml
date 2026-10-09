"""v1.9.0 PR E — new P1 alerts.

Covers cop_degradation, defrost_excessive, buh_excessive, source_stale,
missing_attributes end-to-end: trigger predicates, context builders,
pipeline routing, schema render, advice strings, config flow, i18n.

Refs #66.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import const
from custom_components.daikin_cycle_ml.const import (
    ALERT_GROUP_COMPONENT_HEALTH,
    ALERT_GROUP_DATA_QUALITY,
    ALERT_GROUP_COP_STOOKLIJN,
    BUH_7D_RATIO_THRESHOLD_DEFAULT,
    COP_DEGRADATION_WEEK_PCT_THRESHOLD,
    DEFROST_7D_COUNT_THRESHOLD_DEFAULT,
    DOMAIN,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    NOTIF_ID_BY_TYPE,
    evaluate_alerts,
)
from custom_components.daikin_cycle_ml.engine.status_report import (
    ALERT_ADVICE,
    ALERT_EMOJI,
    ALERT_SCHEMA,
    ALERT_TITLES,
    build_rich_alert,
)

_ROOT = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"

_PR_E_NEW = (
    "cop_degradation",
    "defrost_excessive",
    "buh_excessive",
    "source_stale",
    "missing_attributes",
)


def _bare_coord(
    options: dict[str, Any] | None = None,
    store: Any = None,
    db: Any = None,
) -> DaikinCycleMLCoordinator:
    """Coordinator shell for PR E unit tests (pattern from PR D tests)."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = dict(options or {})
    c.store = store if store is not None else MagicMock()
    c.db = db
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._alert_store = None
    c._alert_save_unsub = None
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._setpoint_history = []
    c._defrost_7d_sum = 0
    c._buh_7d_ratio = 0.0
    return c


def _fake_db_7d(defrost: int = 0, buh: int = 0, cycles: int = 0) -> Any:
    """Fake db returning a single 7d daily_summary row."""
    row = {
        "defrost_count": defrost,
        "buh_count": buh,
        "cycles": cycles,
    }
    db = MagicMock()
    db.async_daily_summary = AsyncMock(return_value=[row])
    return db


# ============================================================
# const wiring — new IDs / groups / emojis / dedup defaults
# ============================================================


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_notif_id_present(alert_type: str) -> None:
    assert alert_type in NOTIF_ID_BY_TYPE
    assert NOTIF_ID_BY_TYPE[alert_type].startswith(DOMAIN)


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_binary_alert_map_entry(alert_type: str) -> None:
    assert alert_type in BINARY_ALERT_MAP
    entry = BINARY_ALERT_MAP[alert_type]
    assert entry[0] == alert_type
    assert entry[1] in ("warning", "critical")
    assert "{advice}" in entry[2]


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_group_map_entry(alert_type: str) -> None:
    assert alert_type in const.ALERT_GROUP_MAP


def test_groups_extended() -> None:
    assert ALERT_GROUP_COMPONENT_HEALTH in const.ALERT_GROUPS
    assert ALERT_GROUP_DATA_QUALITY in const.ALERT_GROUPS


def test_group_mapping() -> None:
    assert const.ALERT_GROUP_MAP["cop_degradation"] == ALERT_GROUP_COP_STOOKLIJN
    assert const.ALERT_GROUP_MAP["defrost_excessive"] == ALERT_GROUP_COMPONENT_HEALTH
    assert const.ALERT_GROUP_MAP["buh_excessive"] == ALERT_GROUP_COMPONENT_HEALTH
    assert const.ALERT_GROUP_MAP["source_stale"] == ALERT_GROUP_DATA_QUALITY
    assert const.ALERT_GROUP_MAP["missing_attributes"] == ALERT_GROUP_DATA_QUALITY


def test_dedup_defaults_extended() -> None:
    for alert_type in _PR_E_NEW:
        assert alert_type in const.ALERT_DEDUP_DEFAULTS


def test_thresholds_defined() -> None:
    assert COP_DEGRADATION_WEEK_PCT_THRESHOLD == -15.0
    assert DEFROST_7D_COUNT_THRESHOLD_DEFAULT == 30
    assert BUH_7D_RATIO_THRESHOLD_DEFAULT == 0.15


# ============================================================
# _refresh_7d_rollups — happy, no-db, exception
# ============================================================


async def test_refresh_7d_rollups_happy() -> None:
    c = _bare_coord(db=_fake_db_7d(defrost=40, buh=5, cycles=20))
    await c._refresh_7d_rollups()
    assert c._defrost_7d_sum == 40
    assert c._buh_7d_ratio == 0.25


async def test_refresh_7d_rollups_zero_cycles() -> None:
    c = _bare_coord(db=_fake_db_7d(defrost=10, buh=0, cycles=0))
    await c._refresh_7d_rollups()
    assert c._defrost_7d_sum == 10
    assert c._buh_7d_ratio == 0.0


async def test_refresh_7d_rollups_no_db() -> None:
    c = _bare_coord(db=None)
    await c._refresh_7d_rollups()
    assert c._defrost_7d_sum == 0


async def test_refresh_7d_rollups_swallows_exception() -> None:
    db = MagicMock()
    db.async_daily_summary = AsyncMock(side_effect=RuntimeError("boom"))
    c = _bare_coord(db=db)
    c._defrost_7d_sum = 99  # pre-existing value
    await c._refresh_7d_rollups()
    # cache unchanged on exception
    assert c._defrost_7d_sum == 99


# ============================================================
# _alert_binary_states — 5 new trigger predicates
# ============================================================


def _mk_store(**overrides: Any) -> MagicMock:
    st = MagicMock()
    st.last_cycle.return_value = {"duration_s": 3600}
    st.off_time_since_last.return_value = 999
    st.cycles_in_window.return_value = 0
    st.cycles_today.return_value = []
    for k, v in overrides.items():
        setattr(st, k, v)
    return st


def test_binary_states_cop_degradation_true() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    snap.cop_degradation_week_pct = -20.0
    assert c._alert_binary_states(snap)["cop_degradation"] is True


def test_binary_states_cop_degradation_false() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    snap.cop_degradation_week_pct = -5.0
    assert c._alert_binary_states(snap)["cop_degradation"] is False


def test_binary_states_cop_degradation_none() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    assert c._alert_binary_states(snap)["cop_degradation"] is False


def test_binary_states_defrost_excessive_true() -> None:
    c = _bare_coord(options={"defrost_7d_count_threshold": 10}, store=_mk_store())
    c._defrost_7d_sum = 20
    assert c._alert_binary_states(DataSnapshot())["defrost_excessive"] is True


def test_binary_states_defrost_excessive_false() -> None:
    c = _bare_coord(options={"defrost_7d_count_threshold": 30}, store=_mk_store())
    c._defrost_7d_sum = 20
    assert c._alert_binary_states(DataSnapshot())["defrost_excessive"] is False


def test_binary_states_buh_excessive_true() -> None:
    c = _bare_coord(options={"buh_7d_ratio_threshold": 0.1}, store=_mk_store())
    c._buh_7d_ratio = 0.2
    assert c._alert_binary_states(DataSnapshot())["buh_excessive"] is True


def test_binary_states_buh_excessive_false() -> None:
    c = _bare_coord(options={"buh_7d_ratio_threshold": 0.15}, store=_mk_store())
    c._buh_7d_ratio = 0.1
    assert c._alert_binary_states(DataSnapshot())["buh_excessive"] is False


def test_binary_states_source_stale_true() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    import time as _t
    snap.last_success_ts = _t.time() - 999
    assert c._alert_binary_states(snap)["source_stale"] is True


def test_binary_states_source_stale_false() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    import time as _t
    snap.last_success_ts = _t.time()
    assert c._alert_binary_states(snap)["source_stale"] is False


def test_binary_states_source_stale_zero_ts() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    snap.last_success_ts = 0.0
    assert c._alert_binary_states(snap)["source_stale"] is False


def test_binary_states_missing_attributes_true() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    snap.missing_attrs = ["foo", "bar"]
    assert c._alert_binary_states(snap)["missing_attributes"] is True


def test_binary_states_missing_attributes_false() -> None:
    c = _bare_coord(store=_mk_store())
    assert c._alert_binary_states(DataSnapshot())["missing_attributes"] is False


# ============================================================
# _build_alert_context — 5 new sub-dicts
# ============================================================


def test_context_has_5_new_subdicts() -> None:
    c = _bare_coord(store=_mk_store())
    ctx = c._build_alert_context(DataSnapshot())
    for alert_type in _PR_E_NEW:
        assert alert_type in ctx
        assert isinstance(ctx[alert_type], dict)
        assert "mode" in ctx[alert_type]
        assert "advice" in ctx[alert_type]


def test_context_cop_degradation_fields() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    snap.cop_degradation_week_pct = -22.5
    ctx = c._build_alert_context(snap)
    assert ctx["cop_degradation"]["week_pct"] == "-22.5"


def test_context_defrost_uses_cached_sum() -> None:
    c = _bare_coord(store=_mk_store())
    c._defrost_7d_sum = 42
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["defrost_excessive"]["count_7d"] == 42


def test_context_buh_uses_cached_ratio() -> None:
    c = _bare_coord(store=_mk_store())
    c._buh_7d_ratio = 0.33
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["buh_excessive"]["buh_ratio_7d"] == 0.33


def test_context_source_stale_fields() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    import time as _t
    snap.last_success_ts = _t.time() - 120
    ctx = c._build_alert_context(snap)
    assert float(ctx["source_stale"]["age_s"]) > 100
    assert ctx["source_stale"]["threshold_s"] > 0


def test_context_missing_attributes_list() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    snap.missing_attrs = ["a", "b", "c", "d", "e"]
    ctx = c._build_alert_context(snap)
    assert ctx["missing_attributes"]["missing_count"] == 5
    # only first 3 + ellipsis
    assert "a, b, c" in ctx["missing_attributes"]["missing_list"]
    assert "\u2026" in ctx["missing_attributes"]["missing_list"]


def test_context_missing_attributes_short_list() -> None:
    c = _bare_coord(store=_mk_store())
    snap = DataSnapshot()
    snap.missing_attrs = ["x"]
    ctx = c._build_alert_context(snap)
    assert ctx["missing_attributes"]["missing_list"] == "x"


# ============================================================
# evaluate_alerts — pipeline routing for 5 new types
# ============================================================


def test_evaluate_routes_cop_degradation() -> None:
    out = evaluate_alerts({"cop_degradation": True}, {}, now=1e9)
    assert len(out) == 1
    assert out[0].alert_type == "cop_degradation"


def test_evaluate_routes_defrost_excessive() -> None:
    out = evaluate_alerts({"defrost_excessive": True}, {}, now=1e9)
    assert out[0].alert_type == "defrost_excessive"


def test_evaluate_routes_buh_excessive() -> None:
    out = evaluate_alerts({"buh_excessive": True}, {}, now=1e9)
    assert out[0].alert_type == "buh_excessive"


def test_evaluate_routes_source_stale_critical() -> None:
    out = evaluate_alerts({"source_stale": True}, {}, now=1e9)
    assert len(out) == 1
    assert out[0].alert_type == "source_stale"
    assert out[0].severity == "critical"


def test_evaluate_routes_missing_attributes() -> None:
    out = evaluate_alerts({"missing_attributes": True}, {}, now=1e9)
    assert out[0].alert_type == "missing_attributes"


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_group_gating_applies(alert_type: str) -> None:
    group = const.ALERT_GROUP_MAP[alert_type]
    out = evaluate_alerts(
        {alert_type: True},
        {f"alert_group_{group}": False},
        now=1e9,
    )
    assert out == []


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_quiet_hours_suppresses_except_critical(alert_type: str) -> None:
    # 23:00 UTC during quiet hours 22:00-07:00
    opts = {
        "quiet_hours_enabled": True,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
    }
    out = evaluate_alerts({alert_type: True}, opts, now=1e9)
    if alert_type == "source_stale":
        # critical severity bypasses quiet hours
        assert len(out) == 1
    else:
        assert out == []


# ============================================================
# status_report — schema, titles, emojis, advice
# ============================================================


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_schema_entry_present(alert_type: str) -> None:
    assert alert_type in ALERT_SCHEMA
    rows = ALERT_SCHEMA[alert_type]
    assert len(rows) >= 4
    for emoji, key, tpl in rows:
        assert isinstance(key, str) and key
        assert "{" in tpl and "}" in tpl


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_titles_present_both_langs(alert_type: str) -> None:
    assert alert_type in ALERT_TITLES["en"]
    assert alert_type in ALERT_TITLES["nl"]


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_emoji_present(alert_type: str) -> None:
    assert alert_type in ALERT_EMOJI
    assert ALERT_EMOJI[alert_type]


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_advice_present_both_langs(alert_type: str) -> None:
    assert alert_type in ALERT_ADVICE["en"]
    assert alert_type in ALERT_ADVICE["nl"]
    assert len(ALERT_ADVICE["en"][alert_type]) > 10
    assert len(ALERT_ADVICE["nl"][alert_type]) > 10


@pytest.mark.parametrize("alert_type", _PR_E_NEW)
def test_build_rich_alert_renders(alert_type: str) -> None:
    ctx = {
        "mode": "heating",
        "advice": ALERT_ADVICE["en"][alert_type],
        "week_pct": -20.0, "threshold_pct": "-15", "trend_30d": -3.5,
        "outdoor": 5.0,
        "count_7d": 40, "threshold": 30, "duration_7d_min": 0,
        "buh_ratio_7d": 0.25, "threshold_ratio": 0.15, "buh_count_7d": 12,
        "age_s": 999.0, "threshold_s": 60.0, "source_sensor": "sensor.x",
        "missing_count": 3, "missing_list": "a, b, c",
    }
    msg = build_rich_alert(alert_type, "warning", ctx, language="en")
    assert ALERT_TITLES["en"][alert_type] in msg
    # at least one schema row renders with a real value
    assert "\u2501" in msg


# ============================================================
# config_flow — notifications_enabled step
# ============================================================


@pytest.fixture(autouse=True)
def _disable_options_reload(hass):
    with patch.object(
        hass.config_entries, "async_reload",
        new=AsyncMock(return_value=True),
    ), patch.object(
        hass.config_entries, "async_schedule_reload",
        new=lambda *a, **k: None,
    ):
        yield


async def _start(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": "sensor.x", "model": "epra12eav3"},
        options={},
    )
    entry.add_to_hass(hass)
    return await hass.config_entries.options.async_init(entry.entry_id)


async def test_notifications_enabled_renders(hass) -> None:
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    assert "notifications_enabled" in r["menu_options"]
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications_enabled"}
    )
    assert r["type"] == "form"
    assert r["step_id"] == "notifications_enabled"
    field_names = {str(k) for k in r["data_schema"].schema}
    for alert_type in _PR_E_NEW:
        assert f"alert_enabled_{alert_type}" in field_names


async def test_notifications_enabled_submits(hass) -> None:
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications_enabled"}
    )
    payload = {f"alert_enabled_{a}": True for a in _PR_E_NEW}
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input=payload
    )
    assert r["type"] == "create_entry"


# ============================================================
# i18n parity — new step + extended groups + dedup entries
# ============================================================


@pytest.mark.parametrize(
    "rel",
    ["strings.json", "translations/en.json", "translations/nl.json"],
)
def test_i18n_notifications_enabled_block(rel: str) -> None:
    d = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
    step = d["options"]["step"]["notifications_enabled"]
    assert step["title"]
    assert step["description"]
    for alert_type in _PR_E_NEW:
        assert f"alert_enabled_{alert_type}" in step["data"]
        assert f"alert_enabled_{alert_type}" in step["data_description"]


@pytest.mark.parametrize(
    "rel",
    ["strings.json", "translations/en.json", "translations/nl.json"],
)
def test_i18n_menu_has_notifications_enabled(rel: str) -> None:
    d = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
    menu = d["options"]["step"]["notifications"]["menu_options"]
    assert "notifications_enabled" in menu


@pytest.mark.parametrize(
    "rel",
    ["strings.json", "translations/en.json", "translations/nl.json"],
)
def test_i18n_content_has_new_groups(rel: str) -> None:
    d = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
    content = d["options"]["step"]["notifications_content"]["data"]
    assert "alert_group_component_health" in content
    assert "alert_group_data_quality" in content


@pytest.mark.parametrize(
    "rel",
    ["strings.json", "translations/en.json", "translations/nl.json"],
)
def test_i18n_dedup_has_new_alerts(rel: str) -> None:
    d = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
    dedup = d["options"]["step"]["notifications_dedup"]["data"]
    for alert_type in _PR_E_NEW:
        assert f"alert_agg_{alert_type}_min" in dedup
