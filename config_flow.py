"""Config flow for Daikin Cycle ML."""
from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (

    DOMAIN,
    NAME,
    SOURCE_SENSOR_ENTITY,
    REQUIRED_ATTRIBUTES,
    MODEL_CHOICES,
    MODEL_CUSTOM,
    MODEL_EPRA12EAV3,
    MODEL_LABELS,
    DEFAULT_COMPRESSOR_RPS_THRESHOLD,
    DEFAULT_FALLBACK_POWER_THRESHOLD_W,
    DEFAULT_SHORT_RUN_MIN,
    DEFAULT_SHORT_OFF_MIN,
    DEFAULT_PENDULUM_CPD,
    DEFAULT_DHW_PENDULUM_CPH,
    DEFAULT_GOOD_RUN_MIN,
    DEFAULT_GOOD_DT_K,
    DEFAULT_GOOD_OFF_MIN,
    DEFAULT_TARGET_CYCLES_PER_DAY,
    DEFAULT_PERSISTENT_ENABLED,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_QUIET_HOURS_ENABLED,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_INDOOR_TEMP_SENSOR,
    DEFAULT_SETPOINT_OSC_THRESHOLD,
    DEFAULT_SETPOINT_OSC_WINDOW_MIN,
    DEFAULT_SETPOINT_OSC_MIN_DELTA,
    DEFAULT_NOTIFICATION_LANGUAGE,
    LANG_EN,
    LANG_NL,
    DEFAULT_PENDULUM_CPH,
    DEFAULT_ALERT_AGGREGATION_MIN,
    DEFAULT_ACTION_ADVICE_ENABLED,
    DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED,
    DEFAULT_ADAPTIVE_MIN_SAMPLES,
    DEFAULT_NOTIFY_EMOJI_ENABLED,
    DEFAULT_STATUS_UPDATE_ENABLED,
    DEFAULT_STATUS_UPDATE_INTERVAL_HOURS,
    DEFAULT_RETENTION_ENABLED,
    DEFAULT_CYCLE_RETENTION_DAYS,
    DEFAULT_ALERT_RETENTION_DAYS,
    DEFAULT_VACUUM_ENABLED,
    CORE_ATTRIBUTES,
)

_LOGGER = logging.getLogger(__name__)

_MODEL_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=m, label=MODEL_LABELS[m])
            for m in MODEL_CHOICES
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)


def _num(min_v: float, max_v: float, step: float, unit: str | None = None):
    kwargs = {
        "min": min_v,
        "max": max_v,
        "step": step,
        "mode": selector.NumberSelectorMode.BOX,
    }
    if unit is not None:
        kwargs["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**kwargs))


def _build_language_selector() -> selector.SelectSelector:
    """Dropdown: EN / NL. Default EN."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=LANG_EN, label="English"),
                selector.SelectOptionDict(value=LANG_NL, label="Nederlands"),
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _legacy_notify_options(hass) -> list:
    """List legacy notify services (excludes generic send_message)."""
    try:
        svcs = hass.services.async_services().get("notify", {})
    except Exception:  # noqa: BLE001
        svcs = {}
    return sorted(
        f"notify.{svc}" for svc in svcs if svc != "send_message"
    )


def _build_notify_selector(hass) -> selector.SelectSelector:
    """Dropdown of notify targets with free-text fallback."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_legacy_notify_options(hass),
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
        )
    )


def _default_notify_choice(hass, current):
    """Return current notify target as a plain string, or None."""
    if not current:
        return None
    return str(current)


def _flatten_notify_choice(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        active = value.get("active_choice")
        if active in ("entity", "service"):
            inner = value.get(active)
            return inner if isinstance(inner, str) else ""
        for k in ("entity", "service"):
            inner = value.get(k)
            if isinstance(inner, str):
                return inner
    return ""

class DaikinCycleMLConfigFlow(ConfigFlow, domain=DOMAIN):
    """8-step config wizard. Supports fresh setup + full reconfigure."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._reconfigure_entry: ConfigEntry | None = None

    # ---------- initial setup ----------

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input["source_sensor"]
            state = self.hass.states.get(entity_id)
            if state is None:
                errors["source_sensor"] = "entity_not_found"
            else:
                missing = [
                    k for k in REQUIRED_ATTRIBUTES if k not in state.attributes
                ]
                if missing:
                    _LOGGER.warning("Missing required attrs: %s", missing)
                    errors["source_sensor"] = "missing_attributes"
                else:
                    self._data.update(user_input)
                    if user_input["model"] == MODEL_CUSTOM:
                        return await self.async_step_model_custom()
                    return await self.async_step_attributes()
        schema = vol.Schema({
            vol.Required(
                "source_sensor",
                default=self._data.get("source_sensor", SOURCE_SENSOR_ENTITY),
            ): _ENTITY_SELECTOR,
            vol.Required(
                "model",
                default=self._data.get("model", MODEL_EPRA12EAV3),
            ): _MODEL_SELECTOR,
        })
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_model_custom(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            raw = user_input.get("custom_attribute_map") or ""
            try:
                mapping = json.loads(raw) if raw else None
                if mapping is not None and not isinstance(mapping, dict):
                    raise ValueError("not a dict")
            except (ValueError, json.JSONDecodeError):
                errors["custom_attribute_map"] = "invalid_json"
            else:
                self._data["custom_attribute_map"] = mapping
                return await self.async_step_attributes()
        schema = vol.Schema({
            vol.Optional(
                "custom_attribute_map",
                default=self._data.get("custom_attribute_map", "") or "",
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        })
        return self.async_show_form(
            step_id="model_custom", data_schema=schema, errors=errors
        )

    async def async_step_attributes(self, user_input=None) -> FlowResult:
        """Show core attribute status. Warning-only, does not block."""
        if user_input is not None:
            return await self.async_step_cycle()

        source_id = (
            self._data.get("source_sensor")
            or self._options.get("source_sensor")
        )
        cmap = self._data.get("custom_attribute_map") or {}
        state = self.hass.states.get(source_id) if source_id else None

        present: list[str] = []
        missing: list[str] = []
        if state is None:
            missing = list(CORE_ATTRIBUTES)
        else:
            attrs = state.attributes
            normalized = {cmap.get(k, k): v for k, v in attrs.items()}
            for key in CORE_ATTRIBUTES:
                if normalized.get(key) is None:
                    missing.append(key)
                else:
                    present.append(key)

        return self.async_show_form(
            step_id="attributes",
            data_schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
            description_placeholders={
                "present": str(len(present)),
                "total": str(len(CORE_ATTRIBUTES)),
                "missing_list": (
                    "\n".join(f"\u2022 {m}" for m in missing)
                    if missing else "none"
                ),
                "present_list": (
                    "\n".join(f"\u2022 {m}" for m in present)
                    if present else "none"
                ),
            },
        )

    async def async_step_cycle(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_pendulum()
        pse_key = vol.Optional("power_sensor_entity")
        pse_val = self._options.get("power_sensor_entity")
        if pse_val:
            pse_key = vol.Optional(
                "power_sensor_entity",
                description={"suggested_value": pse_val},
            )
        schema = vol.Schema({
            vol.Required(
                "compressor_rps_threshold",
                default=self._options.get(
                    "compressor_rps_threshold",
                    DEFAULT_COMPRESSOR_RPS_THRESHOLD,
                ),
            ): _num(0, 100, 1, "rps"),
            pse_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(
                "indoor_temp_sensor",
                description={
                    "suggested_value": self._options.get(
                        "indoor_temp_sensor"
                    ) or None
                },
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                "fallback_power_threshold_w",
                default=self._options.get(
                    "fallback_power_threshold_w",
                    DEFAULT_FALLBACK_POWER_THRESHOLD_W,
                ),
            ): _num(0, 10000, 10, "W"),
        })
        return self.async_show_form(step_id="cycle", data_schema=schema)

    async def async_step_pendulum(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_quality()
        schema = vol.Schema({
            vol.Required(
                "short_run_threshold_min",
                default=self._options.get(
                    "short_run_threshold_min", DEFAULT_SHORT_RUN_MIN
                ),
            ): _num(1, 240, 1, "min"),
            vol.Required(
                "short_off_threshold_min",
                default=self._options.get(
                    "short_off_threshold_min", DEFAULT_SHORT_OFF_MIN
                ),
            ): _num(1, 120, 1, "min"),
            vol.Required(
                "pendulum_cycles_per_day",
                default=self._options.get(
                    "pendulum_cycles_per_day", DEFAULT_PENDULUM_CPD
                ),
            ): _num(1, 200, 1),
            vol.Required(
                "dhw_pendulum_cycles_per_hour",
                default=self._options.get(
                    "dhw_pendulum_cycles_per_hour", DEFAULT_DHW_PENDULUM_CPH
                ),
            ): _num(1, 20, 1),
        })
        return self.async_show_form(step_id="pendulum", data_schema=schema)

    async def async_step_quality(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_notifications()
        schema = vol.Schema({
            vol.Required(
                "good_run_threshold_min",
                default=self._options.get(
                    "good_run_threshold_min", DEFAULT_GOOD_RUN_MIN
                ),
            ): _num(1, 240, 1, "min"),
            vol.Required(
                "good_dt_threshold_k",
                default=self._options.get(
                    "good_dt_threshold_k", DEFAULT_GOOD_DT_K
                ),
            ): _num(0.0, 20.0, 0.5, "K"),
            vol.Required(
                "good_off_threshold_min",
                default=self._options.get(
                    "good_off_threshold_min", DEFAULT_GOOD_OFF_MIN
                ),
            ): _num(1, 240, 1, "min"),
            vol.Required(
                "target_cycles_per_day",
                default=self._options.get(
                    "target_cycles_per_day", DEFAULT_TARGET_CYCLES_PER_DAY
                ),
            ): _num(1, 100, 1),
        })
        return self.async_show_form(step_id="quality", data_schema=schema)

    async def async_step_notifications(self, user_input=None) -> FlowResult:
        if user_input is not None:
            if "notify_service" in user_input:
                user_input["notify_service"] = _flatten_notify_choice(
                    user_input["notify_service"]
                )
            self._options.update(user_input)
            return await self.async_step_finalize()
        _current_ns = (
            self._options.get("notify_service") or DEFAULT_NOTIFY_SERVICE
        )
        _default_ns = _default_notify_choice(self.hass, _current_ns)
        if _default_ns is not None:
            _ns_key = vol.Optional(
                "notify_service", default=_default_ns
            )
        else:
            _ns_key = vol.Optional("notify_service")
        schema = vol.Schema({
            vol.Required(
                "persistent_enabled",
                default=self._options.get(
                    "persistent_enabled", DEFAULT_PERSISTENT_ENABLED
                ),
            ): bool,
            _ns_key: _build_notify_selector(self.hass),
            vol.Required(
                "quiet_hours_enabled",
                default=self._options.get(
                    "quiet_hours_enabled", DEFAULT_QUIET_HOURS_ENABLED
                ),
            ): bool,
            vol.Optional(
                "quiet_hours_start",
                default=self._options.get(
                    "quiet_hours_start", DEFAULT_QUIET_HOURS_START
                ),
            ): str,
            vol.Optional(
                "quiet_hours_end",
                default=self._options.get(
                    "quiet_hours_end", DEFAULT_QUIET_HOURS_END
                ),
            ): str,
        })
        return self.async_show_form(
            step_id="notifications", data_schema=schema
        )

    async def async_step_finalize(self, user_input=None) -> FlowResult:
        if user_input is not None:
            if self._reconfigure_entry is not None:
                return self.async_update_reload_and_abort(
                    self._reconfigure_entry,
                    data_updates=self._data,
                    options=self._options,
                    reason="reconfigure_successful",
                )
            model = self._data.get("model", "")
            source = self._data.get("source_sensor", "")
            return self.async_create_entry(
                title=f"{NAME} - {model} ({source})",
                data=self._data,
                options=self._options,
            )
        return self.async_show_form(
            step_id="finalize",
            data_schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
            description_placeholders={
                "model": str(self._data.get("model", "?")),
                "source": str(self._data.get("source_sensor", "?")),
            },
        )

    # ---------- reconfigure menu ----------

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_basic", "reconfigure_full"],
        )

    async def async_step_reconfigure_basic(
        self, user_input=None
    ) -> FlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input["source_sensor"]
            state = self.hass.states.get(entity_id)
            if state is None:
                errors["source_sensor"] = "entity_not_found"
            else:
                missing = [
                    k for k in REQUIRED_ATTRIBUTES
                    if k not in state.attributes
                ]
                if missing:
                    _LOGGER.warning(
                        "Reconfigure missing attrs: %s", missing
                    )
                    errors["source_sensor"] = "missing_attributes"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=dict(user_input),
                        reason="reconfigure_successful",
                    )
        current = entry.data or {}
        schema = vol.Schema({
            vol.Required(
                "source_sensor",
                default=current.get(
                    "source_sensor", SOURCE_SENSOR_ENTITY
                ),
            ): _ENTITY_SELECTOR,
            vol.Required(
                "model",
                default=current.get("model", MODEL_EPRA12EAV3),
            ): _MODEL_SELECTOR,
        })
        return self.async_show_form(
            step_id="reconfigure_basic", data_schema=schema, errors=errors
        )

    async def async_step_reconfigure_full(
        self, user_input=None
    ) -> FlowResult:
        entry = self._get_reconfigure_entry()
        self._reconfigure_entry = entry
        self._data = dict(entry.data)
        self._options = dict(entry.options or {})
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DaikinCycleMLOptionsFlow()


class DaikinCycleMLOptionsFlow(OptionsFlow):
    """Menu-driven options editor (batch 18)."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "device",
                "pendulum",
                "quality",
                "notifications",
                "ml",
                "maintenance",
                "test_notification",
            ],
        )

    def _save(self, user_input):
        merged = {**(self.config_entry.options or {}), **user_input}
        return self.async_create_entry(title="", data=merged)

    async def async_step_device(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self._save(user_input)
        c = self.config_entry.options or {}
        d = self.config_entry.data or {}
        schema = vol.Schema({
            vol.Required(
                "compressor_rps_threshold",
                default=c.get("compressor_rps_threshold",
                    DEFAULT_COMPRESSOR_RPS_THRESHOLD),
            ): _num(0, 100, 1, "rps"),
            vol.Optional(
                "power_sensor_entity",
                description={"suggested_value": c.get("power_sensor_entity")},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                "fallback_power_threshold_w",
                default=c.get("fallback_power_threshold_w",
                    DEFAULT_FALLBACK_POWER_THRESHOLD_W),
            ): _num(0, 10000, 10, "W"),
            vol.Optional(
                "indoor_temp_sensor",
                description={"suggested_value": c.get("indoor_temp_sensor")},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(
                "cop_sensor_entity",
                description={"suggested_value": c.get("cop_sensor_entity")},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })
        return self.async_show_form(
            step_id="device",
            data_schema=schema,
            description_placeholders={
                "source_sensor": str(d.get("source_sensor", "?")),
                "model": str(d.get("model", "?")),
            },
        )

    async def async_step_pendulum(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self._save(user_input)
        c = self.config_entry.options or {}
        schema = vol.Schema({
            vol.Required("short_run_threshold_min",
                default=c.get("short_run_threshold_min", DEFAULT_SHORT_RUN_MIN)
            ): _num(1, 240, 1, "min"),
            vol.Required("short_off_threshold_min",
                default=c.get("short_off_threshold_min", DEFAULT_SHORT_OFF_MIN)
            ): _num(1, 120, 1, "min"),
            vol.Required("pendulum_cycles_per_hour",
                default=c.get("pendulum_cycles_per_hour", DEFAULT_PENDULUM_CPH)
            ): _num(1, 100, 1),
            vol.Required("pendulum_cycles_per_day",
                default=c.get("pendulum_cycles_per_day", DEFAULT_PENDULUM_CPD)
            ): _num(1, 200, 1),
            vol.Required("dhw_pendulum_cycles_per_hour",
                default=c.get("dhw_pendulum_cycles_per_hour",
                    DEFAULT_DHW_PENDULUM_CPH),
            ): _num(1, 20, 1, "cyc/h"),
            vol.Required("setpoint_oscillation_threshold",
                default=c.get("setpoint_oscillation_threshold",
                    DEFAULT_SETPOINT_OSC_THRESHOLD),
            ): _num(1, 100, 1, "changes"),
            vol.Required("setpoint_osc_window_min",
                default=c.get("setpoint_osc_window_min",
                    DEFAULT_SETPOINT_OSC_WINDOW_MIN),
            ): _num(5, 180, 1, "min"),
            vol.Required("setpoint_osc_min_delta",
                default=c.get("setpoint_osc_min_delta",
                    DEFAULT_SETPOINT_OSC_MIN_DELTA),
            ): _num(0.1, 2.0, 0.1, "\u00b0C"),
        })
        return self.async_show_form(step_id="pendulum", data_schema=schema)

    async def async_step_quality(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self._save(user_input)
        c = self.config_entry.options or {}
        schema = vol.Schema({
            vol.Required("good_run_threshold_min",
                default=c.get("good_run_threshold_min", DEFAULT_GOOD_RUN_MIN)
            ): _num(1, 240, 1, "min"),
            vol.Required("good_dt_threshold_k",
                default=c.get("good_dt_threshold_k", DEFAULT_GOOD_DT_K)
            ): _num(0.0, 20.0, 0.5, "K"),
            vol.Required("good_off_threshold_min",
                default=c.get("good_off_threshold_min", DEFAULT_GOOD_OFF_MIN)
            ): _num(1, 240, 1, "min"),
            vol.Required("target_cycles_per_day",
                default=c.get("target_cycles_per_day", DEFAULT_TARGET_CYCLES_PER_DAY)
            ): _num(1, 100, 1),
        })
        return self.async_show_form(step_id="quality", data_schema=schema)

    async def async_step_notifications(self, user_input=None) -> FlowResult:
        if user_input is not None:
            if "notify_service" in user_input:
                user_input["notify_service"] = _flatten_notify_choice(
                    user_input["notify_service"]
                )
            return self._save(user_input)
        c = self.config_entry.options or {}
        _cur_ns = c.get("notify_service") or DEFAULT_NOTIFY_SERVICE
        _def_ns = _default_notify_choice(self.hass, _cur_ns)
        if _def_ns is not None:
            _ns_key = vol.Optional("notify_service", default=_def_ns)
        else:
            _ns_key = vol.Optional("notify_service")
        schema = vol.Schema({
            vol.Required("persistent_enabled",
                default=c.get("persistent_enabled", DEFAULT_PERSISTENT_ENABLED)
            ): bool,
            _ns_key: _build_notify_selector(self.hass),
            vol.Required("notify_emoji_enabled",
                default=c.get("notify_emoji_enabled", DEFAULT_NOTIFY_EMOJI_ENABLED)
            ): bool,
            vol.Required("action_advice_enabled",
                default=c.get("action_advice_enabled", DEFAULT_ACTION_ADVICE_ENABLED)
            ): bool,
            vol.Required("quiet_hours_enabled",
                default=c.get("quiet_hours_enabled", DEFAULT_QUIET_HOURS_ENABLED)
            ): bool,
            vol.Optional("quiet_hours_start",
                default=c.get("quiet_hours_start", DEFAULT_QUIET_HOURS_START)
            ): str,
            vol.Optional("quiet_hours_end",
                default=c.get("quiet_hours_end", DEFAULT_QUIET_HOURS_END)
            ): str,
            vol.Required("alert_aggregation_minutes",
                default=c.get("alert_aggregation_minutes", DEFAULT_ALERT_AGGREGATION_MIN)
            ): _num(1, 1440, 1, "min"),
            vol.Required("status_update_enabled",
                default=c.get("status_update_enabled", DEFAULT_STATUS_UPDATE_ENABLED)
            ): bool,
            vol.Required("status_update_interval_hours",
                default=c.get("status_update_interval_hours",
                    DEFAULT_STATUS_UPDATE_INTERVAL_HOURS),
            ): _num(1, 168, 1, "h"),
            vol.Required("notification_language",
                default=c.get("notification_language", DEFAULT_NOTIFICATION_LANGUAGE)
            ): _build_language_selector(),
            vol.Required("alert_group_pendulum",
                default=c.get("alert_group_pendulum", True)
            ): bool,
            vol.Required("alert_group_short_cycle",
                default=c.get("alert_group_short_cycle", True)
            ): bool,
            vol.Required("alert_group_ml",
                default=c.get("alert_group_ml", True)
            ): bool,
            vol.Required("alert_group_setpoint",
                default=c.get("alert_group_setpoint", True)
            ): bool,
            vol.Required("alert_group_cop_stooklijn",
                default=c.get("alert_group_cop_stooklijn", True)
            ): bool,
        })
        return self.async_show_form(step_id="notifications", data_schema=schema)

    def _get_coordinator_handle(self):
        """Resolve coordinator across runtime_data and hass.data patterns."""
        from .const import DOMAIN
        entry = self.config_entry
        coord = getattr(entry, "runtime_data", None)
        if coord is not None and hasattr(coord, "async_emit_status_update"):
            return coord
        data = self.hass.data.get(DOMAIN)
        if isinstance(data, dict):
            coord = data.get(entry.entry_id)
            if coord is not None and hasattr(coord, "async_emit_status_update"):
                return coord
            for v in data.values():
                if hasattr(v, "async_emit_status_update"):
                    return v
        if data is not None and hasattr(data, "async_emit_status_update"):
            return data
        return None

    async def async_step_test_notification(self, user_input=None) -> FlowResult:
        """Send current daily summary to the configured notify target."""
        if user_input is not None:
            return await self.async_step_init()
        status = "unknown"
        preview = ""
        try:
            coord = self._get_coordinator_handle()
            if coord is None:
                status = "no_coordinator"
                preview = "Integration is not loaded. Reload the entry first."
            else:
                msg = await coord.async_emit_status_update()
                status = "sent"
                preview = (msg or "")[:500]
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            preview = str(exc)[:500]
        return self.async_show_form(
            step_id="test_notification",
            data_schema=vol.Schema({
                vol.Optional("back", default=True): bool,
            }),
            description_placeholders={
                "status": status,
                "preview": preview,
            },
        )

    async def async_step_ml(self, user_input=None) -> FlowResult:

        if user_input is not None:
            return self._save(user_input)
        c = self.config_entry.options or {}
        schema = vol.Schema({
            vol.Required("adaptive_thresholds_enabled",
                default=c.get("adaptive_thresholds_enabled",
                    DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED),
            ): bool,
            vol.Required("adaptive_min_samples",
                default=c.get("adaptive_min_samples", DEFAULT_ADAPTIVE_MIN_SAMPLES)
            ): _num(5, 500, 1),
        })
        return self.async_show_form(step_id="ml", data_schema=schema)

    async def async_step_maintenance(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self._save(user_input)
        c = self.config_entry.options or {}
        schema = vol.Schema({
            vol.Required("retention_enabled",
                default=c.get("retention_enabled", DEFAULT_RETENTION_ENABLED)
            ): bool,
            vol.Required("cycle_retention_days",
                default=c.get("cycle_retention_days", DEFAULT_CYCLE_RETENTION_DAYS)
            ): _num(1, 3650, 1, "d"),
            vol.Required("alert_retention_days",
                default=c.get("alert_retention_days", DEFAULT_ALERT_RETENTION_DAYS)
            ): _num(1, 365, 1, "d"),
            vol.Required("vacuum_enabled",
                default=c.get("vacuum_enabled", DEFAULT_VACUUM_ENABLED)
            ): bool,
        })
        return self.async_show_form(step_id="maintenance", data_schema=schema)
