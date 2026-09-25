"""Tests for 12c scheduler + options constants."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    DEFAULT_NOTIFY_EMOJI_ENABLED,
    DEFAULT_STATUS_UPDATE_ENABLED,
    DEFAULT_STATUS_UPDATE_INTERVAL_HOURS,
    NOTIF_ID_STATUS,
)


def test_status_update_default_off():
    assert DEFAULT_STATUS_UPDATE_ENABLED is False


def test_status_interval_default_24h():
    assert DEFAULT_STATUS_UPDATE_INTERVAL_HOURS == 24


def test_notify_emoji_default_on():
    assert DEFAULT_NOTIFY_EMOJI_ENABLED is True


def test_notif_id_status_format():
    assert NOTIF_ID_STATUS == "daikin_cycle_ml_status"

