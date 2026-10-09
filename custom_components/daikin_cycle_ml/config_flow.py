"""Config flow for Daikin Cycle ML."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)

from .const import DEFAULT_DAILY_SUMMARY_LIVE_ENABLED

if TYPE_CHECKING:
    from homeassistant.config_entries import (
        OptionsFlowWithReload as _OPTIONS_FLOW_BASE,
    )
else:
    try:
        from homeassistant.config_entries import (
            OptionsFlowWithReload as _OPTIONS_FLOW_BASE,
        )
    except ImportError:  # pragma: no cover
        from homeassistant.config_entries import (
            OptionsFlow as _OPTIONS_FLOW_BASE,
        )

from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    ALERT_DEDUP_DEFAULTS,
    ATTRIBUTE_MODE_AUTO,
    ATTRIBUTE_MODE_MANUAL,
    DEFAULT_ACTION_ADVICE_ENABLED,
    DEFAULT_ADAPTIVE_MIN_SAMPLES,
    DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED,
    DEFAULT_ALERT_AGGREGATION_MIN,
    DEFAULT_ALERT_RETENTION_DAYS,
    DEFAULT_COMFORT_MAX_C,
    DEFAULT_COMFORT_MIN_C,
    DEFAULT_COMPRESSOR_RPS_THRESHOLD,
    DEFAULT_CYCLE_RETENTION_DAYS,
    DEFAULT_DHW_PENDULUM_CPH,
    DEFAULT_FALLBACK_POWER_THRESHOLD_W,
    DEFAULT_GOOD_DT_K,
    DEFAULT_GOOD_OFF_MIN,
    DEFAULT_GOOD_RUN_MIN,
    DEFAULT_NOTIFICATION_LANGUAGE,
    DEFAULT_NOTIFY_EMOJI_ENABLED,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_PENDULUM_CPD,
    DEFAULT_PENDULUM_CPH,
    DEFAULT_PERSISTENT_ENABLED,
    DEFAULT_QUIET_HOURS_ENABLED,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_RETENTION_ENABLED,
    DEFAULT_SEASON_START_MONTH,
    DEFAULT_SETPOINT_OSC_MIN_DELTA,
    DEFAULT_SETPOINT_OSC_THRESHOLD,
    DEFAULT_SETPOINT_OSC_WINDOW_MIN,
    DEFAULT_SHORT_OFF_MIN,
    DEFAULT_SHORT_RUN_MIN,
    DEFAULT_STATUS_UPDATE_ENABLED,
    DEFAULT_STATUS_UPDATE_INTERVAL_HOURS,
    DEFAULT_TARGET_CYCLES_PER_DAY,
    DEFAULT_VACUUM_ENABLED,
    DOMAIN,
    LANG_EN,
    LANG_NL,
    MODEL_BASISPROFIEL,
    MODEL_CHOICES,
    MODEL_CUSTOM,
    MODEL_EPRA12EAV3,
    MODEL_LABELS,
    NAME,
    OPTIONAL_ATTRIBUTES,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
)
from .engine.model_datasheets import validate_spec
from .engine.model_profiles import expected_attributes
from .engine.smart_import import build_diagnostic, resolve_canonical

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

_ATTRIBUTE_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(
                value=ATTRIBUTE_MODE_AUTO,
                label="Automatic (canonical ESPAltherma names)",
            ),
            selector.SelectOptionDict(
                value=ATTRIBUTE_MODE_MANUAL,
                label="Manual (map each required attribute)",
            ),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


def _num(
    min_v: float, max_v: float, step: float, unit: str | None = None
) -> selector.NumberSelector:
    config: selector.NumberSelectorConfig = {
        "min": min_v,
        "max": max_v,
        "step": step,
        "mode": selector.NumberSelectorMode.BOX,
    }
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


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


def _legacy_notify_options(hass: HomeAssistant) -> list[str]:
    """List legacy notify services (excludes generic send_message)."""
    try:
        svcs = hass.services.async_services().get("notify", {})
    except Exception:
        svcs = {}
    return sorted(
        f"notify.{svc}" for svc in svcs if svc != "send_message"
    )


def _build_notify_selector(hass: HomeAssistant) -> selector.SelectSelector:
    """Dropdown of notify targets with free-text fallback."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_legacy_notify_options(hass),
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
        )
    )


def _default_notify_choice(hass: HomeAssistant, current: Any) -> str | None:
    """Return current notify target as a plain string, or None."""
    if not current:
        return None
    return str(current)


def _flatten_notify_choice(value: Any) -> str:
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

_SPEC_EXAMPLE_MIN = '{"family": "Altherma 3 R", "kw": 8.0, "lwt_min": 25.0, "lwt_max": 55.0, "nom_cop": 4.6}'
_SPEC_EXAMPLE_FULL = '{\n  "family": "Altherma 3 R",\n  "kw": 8.0,\n  "lwt_min": 25.0,\n  "lwt_max": 55.0,\n  "nom_cop": 4.6,\n  "refrigerant": "R32",\n  "buh_kw": 3.0,\n  "max_flow_lmin": 22.0,\n  "noise_db": 58.0,\n  "points": [\n    {"label": "A7/W35", "t_out": 7.0, "t_lwc": 35.0, "cop": 4.60},\n    {"label": "A2/W35", "t_out": 2.0, "t_lwc": 35.0, "cop": 3.85},\n    {"label": "A-7/W35", "t_out": -7.0, "t_lwc": 35.0, "cop": 2.60},\n    {"label": "A7/W45", "t_out": 7.0, "t_lwc": 45.0, "cop": 3.40}\n  ]\n}'

_MAPPING_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="json", label="JSON"),
            selector.SelectOptionDict(value="manual", label="Manual"),
        ],
        mode=selector.SelectSelectorMode.LIST,
    )
)

class DaikinCycleMLConfigFlow(ConfigFlow, domain=DOMAIN):
    """8-step config wizard. Supports fresh setup + full reconfigure."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._reconfigure_entry: ConfigEntry | None = None

    # ---------- initial setup ----------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        missing_list: list[str] = []
        if user_input is not None:
            entity_id = user_input["source_sensor"]
            state = self.hass.states.get(entity_id)
            mode = user_input.get("attribute_mode", ATTRIBUTE_MODE_AUTO)
            if state is None:
                errors["source_sensor"] = "entity_not_found"
            elif mode == ATTRIBUTE_MODE_MANUAL:
                self._data.update(user_input)
                self._data["attribute_mode"] = ATTRIBUTE_MODE_MANUAL
                if user_input["model"] == MODEL_CUSTOM:
                    return await self.async_step_model_custom_info()
                return await self.async_step_map_attributes()
            else:
                available = set(state.attributes.keys())
                missing_exact = [
                    k for k in REQUIRED_ATTRIBUTES if k not in state.attributes
                ]
                if not missing_exact:
                    self._data.update(user_input)
                    self._data["attribute_mode"] = ATTRIBUTE_MODE_AUTO
                    if user_input["model"] == MODEL_CUSTOM:
                        return await self.async_step_model_custom_info()
                    return await self.async_step_attributes()
                # Smart fallback (issue #51, Laag 1-3)
                smart_map: dict[str, str] = {}
                for canonical in REQUIRED_ATTRIBUTES:
                    m = resolve_canonical(canonical, available)
                    if m.actual_key is not None:
                        smart_map[canonical] = m.actual_key
                if len(smart_map) >= 3:
                    self._data.update(user_input)
                    self._data["attribute_mode"] = ATTRIBUTE_MODE_AUTO
                    self._data["attribute_map"] = smart_map
                    self._data["_smart_available"] = sorted(available)
                    return await self.async_step_diagnose()
                _LOGGER.warning("Missing required attrs: %s", missing_exact)
                errors["source_sensor"] = "missing_attributes"
                missing_list = missing_exact
        schema = vol.Schema({
            vol.Required(
                "source_sensor",
                default=self._data.get("source_sensor", SOURCE_SENSOR_ENTITY),
            ): _ENTITY_SELECTOR,
            vol.Required(
                "model",
                default=self._data.get("model", MODEL_EPRA12EAV3),
            ): _MODEL_SELECTOR,
            vol.Required(
                "attribute_mode",
                default=self._data.get("attribute_mode", ATTRIBUTE_MODE_AUTO),
            ): _ATTRIBUTE_MODE_SELECTOR,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "missing_list": (
                    "\n".join("\u2022 " + m for m in missing_list)
                    if missing_list else "none"
                ),
            },
        )

    async def async_step_diagnose(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show smart-import diagnostic report (issue #51, Laag 4+5)."""
        source_id = self._data.get("source_sensor", SOURCE_SENSOR_ENTITY)
        state = self.hass.states.get(source_id) if source_id else None
        available = set(self._data.get("_smart_available") or [])
        attrs: dict[str, Any] = dict(state.attributes) if state is not None else {}
        report = build_diagnostic(
            canonicals=tuple(REQUIRED_ATTRIBUTES),
            available=available,
            attrs=attrs,
        )
        if user_input is not None:
            # Drop internal key before finalize (defensive, mirrors _bad_attrs)
            self._data.pop("_smart_available", None)
            if self._data.get("model") == MODEL_CUSTOM:
                return await self.async_step_model_custom_info()
            return await self.async_step_attributes()
        lines: list[str] = []
        for m in report.matches:
            kind = m.kind.upper().ljust(7)
            target = m.actual_key or "-"
            lines.append(f"{m.canonical}  [{kind}]  {target}")
        report_text = "\n".join(lines) if lines else "none"
        warnings_text = "\n".join(report.warnings) if report.warnings else "none"
        return self.async_show_form(
            step_id="diagnose",
            data_schema=vol.Schema({}),
            description_placeholders={
                "report_lines": report_text,
                "warnings": warnings_text,
                "missing_count": str(len(report.missing)),
            },
        )

    async def async_step_model_custom_info(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Page A (issue #54): custom heat pump identity + optional spec JSON."""
        errors: dict[str, str] = {}
        last_raw = ""
        if user_input is not None:
            last_raw = (user_input.get("custom_datasheet_json") or "").strip()
            if not last_raw:
                self._data["custom_datasheet"] = None
                return await self.async_step_attribute_mapping()
            try:
                parsed = json.loads(last_raw)
            except (ValueError, json.JSONDecodeError):
                errors["custom_datasheet_json"] = "invalid_json"
            else:
                spec, spec_errs = validate_spec(parsed)
                if spec_errs:
                    _LOGGER.warning(
                        "Invalid custom datasheet spec: %s", spec_errs
                    )
                    errors["custom_datasheet_json"] = "invalid_spec"
                else:
                    self._data["custom_datasheet"] = spec
                    return await self.async_step_attribute_mapping()
        schema = vol.Schema({
            vol.Optional(
                "custom_datasheet_json",
                default=last_raw,
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        })
        return self.async_show_form(
            step_id="model_custom_info",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "spec_example_min": _SPEC_EXAMPLE_MIN,
                "spec_example_full": _SPEC_EXAMPLE_FULL,
            },
        )

    async def async_step_attribute_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Page B (issue #54): choose JSON (advanced) vs manual per-attribute."""
        if user_input is not None:
            mode = user_input.get("mapping_mode", "json")
            if mode == "manual":
                return await self.async_step_map_attributes()
            return await self.async_step_attribute_mapping_advanced()
        schema = vol.Schema({
            vol.Required(
                "mapping_mode",
                default="json",
            ): _MAPPING_MODE_SELECTOR,
        })
        return self.async_show_form(
            step_id="attribute_mapping",
            data_schema=schema,
        )

    async def async_step_model_custom(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Deprecated redirect to attribute_mapping_advanced (issue #54, commit 4)."""
        return await self.async_step_attribute_mapping_advanced(user_input)

    async def async_step_attribute_mapping_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Page C (issue #54): advanced JSON attribute map (renamed from model_custom)."""
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
            step_id="attribute_mapping_advanced", data_schema=schema, errors=errors
        )

    async def async_step_map_attributes(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manual mapping of required + optional attributes to user's own names."""
        errors: dict[str, str] = {}
        source_id = self._data.get("source_sensor", SOURCE_SENSOR_ENTITY)
        state = self.hass.states.get(source_id) if source_id else None
        available = set(state.attributes.keys()) if state else set()

        if user_input is not None:
            mapping: dict[str, str] = {}
            bad: list[str] = []
            unmapped: list[str] = []
            for canonical in REQUIRED_ATTRIBUTES:
                user_key = (user_input.get(canonical) or "").strip()
                if not user_key:
                    if canonical in available:
                        mapping[canonical] = canonical
                    else:
                        unmapped.append(canonical)
                    continue
                if user_key not in available:
                    bad.append(user_key)
                    continue
                mapping[canonical] = user_key
            for canonical in OPTIONAL_ATTRIBUTES:
                user_key = (user_input.get(canonical) or "").strip()
                if not user_key:
                    continue
                if user_key not in available:
                    bad.append(user_key)
                    continue
                mapping[canonical] = user_key
            if bad:
                errors["base"] = "attribute_not_found"
                self._data["_bad_attrs"] = bad
            elif unmapped:
                errors["base"] = "required_attrs_unmapped"
                self._data["_bad_attrs"] = unmapped
            else:
                self._data["attribute_map"] = mapping
                self._data["attribute_mode"] = ATTRIBUTE_MODE_MANUAL
                return await self.async_step_attributes()

        existing = self._data.get("attribute_map") or {}
        reversed_existing = dict(existing)
        fields: dict[Any, Any] = {}
        for canonical in REQUIRED_ATTRIBUTES + OPTIONAL_ATTRIBUTES:
            default = reversed_existing.get(canonical, "") or ""
            fields[vol.Optional(canonical, default=default)] = selector.TextSelector(
                selector.TextSelectorConfig()
            )
        return self.async_show_form(
            step_id="map_attributes",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "available_count": str(len(available)),
                "available_list": (
                    ", ".join(sorted(available)[:40])
                    if available else "none"
                ),
                "bad_list": (
                    ", ".join(self._data.pop("_bad_attrs", [])) or "none"
                ),
            },
        )

    async def async_step_attributes(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show core attribute status. Warning-only, does not block."""
        if user_input is not None:
            return await self.async_step_cycle()

        source_id = (
            self._data.get("source_sensor")
            or self._options.get("source_sensor")
        )
        cmap = self._data.get("custom_attribute_map") or {}
        state = self.hass.states.get(source_id) if source_id else None
        model = self._data.get("model") or MODEL_BASISPROFIEL
        expected = expected_attributes(model)

        present: list[str] = []
        missing: list[str] = []
        if state is None:
            missing = list(expected)
        else:
            attrs = state.attributes
            normalized = {cmap.get(k, k): v for k, v in attrs.items()}
            for key in expected:
                if normalized.get(key) is None:
                    missing.append(key)
                else:
                    present.append(key)

        return self.async_show_form(
            step_id="attributes",
            data_schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
            description_placeholders={
                "present": str(len(present)),
                "total": str(len(expected)),
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

    async def async_step_cycle(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_pendulum(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_quality(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_finalize(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_basic", "reconfigure_full"],
        )

    async def async_step_reconfigure_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        current: dict[str, Any] = dict(entry.data or {})
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
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        self._reconfigure_entry = entry
        self._data = dict(entry.data)
        self._options = dict(entry.options or {})
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DaikinCycleMLOptionsFlow()


class DaikinCycleMLOptionsFlow(_OPTIONS_FLOW_BASE):
    """Menu-driven options editor (batch 18)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "device",
                "pendulum",
                "quality_ml",
                "notifications",
                "advanced",
                "test_notification",
                "test_all_notifications",
            ],
        )

    def _save(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        # Flatten section() input one level: {section: {k: v}} -> {k: v}
        flat: dict[str, Any] = {}
        for k, v in user_input.items():
            if isinstance(v, dict):
                flat.update(v)
            else:
                flat[k] = v
        merged = {**dict(self.config_entry.options or {}), **flat}
        return self.async_create_entry(data=merged)

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        d: dict[str, Any] = dict(self.config_entry.data or {})
        schema = vol.Schema({
            vol.Required("sensors"): section(vol.Schema({
                vol.Optional(
                    "power_sensor_entity",
                    description={"suggested_value": c.get("power_sensor_entity")},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    "cop_sensor_entity",
                    description={"suggested_value": c.get("cop_sensor_entity")},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    "indoor_temp_sensor",
                    description={"suggested_value": c.get("indoor_temp_sensor")},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            })),
            vol.Required("detection"): section(vol.Schema({
                vol.Required(
                    "compressor_rps_threshold",
                    default=c.get("compressor_rps_threshold",
                        DEFAULT_COMPRESSOR_RPS_THRESHOLD),
                ): _num(0, 100, 1, "rps"),
                vol.Required(
                    "fallback_power_threshold_w",
                    default=c.get("fallback_power_threshold_w",
                        DEFAULT_FALLBACK_POWER_THRESHOLD_W),
                ): _num(0, 10000, 10, "W"),
            })),
            vol.Required("comfort"): section(vol.Schema({
                vol.Required(
                    "comfort_min_c",
                    default=c.get("comfort_min_c", DEFAULT_COMFORT_MIN_C),
                ): _num(15.0, 22.0, 0.5, "°C"),
                vol.Required(
                    "comfort_max_c",
                    default=c.get("comfort_max_c", DEFAULT_COMFORT_MAX_C),
                ): _num(22.0, 28.0, 0.5, "°C"),
            })),
        })
        return self.async_show_form(
            step_id="device",
            data_schema=schema,
            description_placeholders={
                "source_sensor": str(d.get("source_sensor", "?")),
                "model": str(d.get("model", "?")),
            },
        )

    async def async_step_pendulum(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        schema = vol.Schema({
            vol.Required("run_off"): section(vol.Schema({
                vol.Required("short_run_threshold_min",
                    default=c.get("short_run_threshold_min", DEFAULT_SHORT_RUN_MIN)
                ): _num(1, 240, 1, "min"),
                vol.Required("short_off_threshold_min",
                    default=c.get("short_off_threshold_min", DEFAULT_SHORT_OFF_MIN)
                ): _num(1, 120, 1, "min"),
            })),
            vol.Required("pendulum"): section(vol.Schema({
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
            })),
            vol.Required("setpoint"): section(vol.Schema({
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
                ): _num(0.1, 2.0, 0.1, "°C"),
            })),
        })
        return self.async_show_form(step_id="pendulum", data_schema=schema)

    async def async_step_quality_ml(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        schema = vol.Schema({
            vol.Required("quality"): section(vol.Schema({
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
            })),
            vol.Required("adaptive"): section(vol.Schema({
                vol.Required("adaptive_thresholds_enabled",
                    default=c.get("adaptive_thresholds_enabled",
                        DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED),
                ): bool,
                vol.Required("adaptive_min_samples",
                    default=c.get("adaptive_min_samples", DEFAULT_ADAPTIVE_MIN_SAMPLES)
                ): _num(5, 500, 1),
            })),
        })
        return self.async_show_form(step_id="quality_ml", data_schema=schema)

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Notifications submenu."""
        return self.async_show_menu(
            step_id="notifications",
            menu_options=[
                "notifications_delivery",
                "notifications_quiet_hours",
                "notifications_content",
                "notifications_dedup",
                "notifications_test_menu",
            ],
        )

    async def async_step_notifications_delivery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if "notify_service" in user_input:
                user_input["notify_service"] = _flatten_notify_choice(
                    user_input["notify_service"]
                )
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        _cur_ns = c.get("notify_service") or DEFAULT_NOTIFY_SERVICE
        _def_ns = _default_notify_choice(self.hass, _cur_ns)
        if _def_ns is not None:  # pragma: no cover
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
        })
        return self.async_show_form(step_id="notifications_delivery", data_schema=schema)

    async def async_step_notifications_quiet_hours(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        schema = vol.Schema({
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
        })
        return self.async_show_form(step_id="notifications_quiet_hours", data_schema=schema)

    async def async_step_notifications_content(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        schema = vol.Schema({
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
        return self.async_show_form(step_id="notifications_content", data_schema=schema)

    async def async_step_notifications_dedup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Per-alert dedup windows (PR D, ALERTS_V2.md 4.7)."""
        if user_input is not None:
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        schema: dict[Any, Any] = {}
        for _alert_type, _default in ALERT_DEDUP_DEFAULTS.items():
            _key = f"alert_agg_{_alert_type}_min"
            schema[vol.Required(
                _key,
                default=c.get(_key, _default),
            )] = _num(1, 10080, 1, "min")
        return self.async_show_form(
            step_id="notifications_dedup",
            data_schema=vol.Schema(schema),
        )

    async def async_step_notifications_test_menu(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Submenu for test notifications."""
        return self.async_show_menu(
            step_id="notifications_test_menu",
            menu_options=["test_notification", "test_all_notifications"],
        )

    def _get_coordinator_handle(self) -> Any:
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

    async def async_step_test_notification(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick an alert kind and dispatch one sample."""
        if user_input is not None:
            kind = str(user_input.get("alert_kind") or "status_summary")
            ignore = bool(user_input.get("ignore_group_filters", False))
            status = "unknown"
            preview = ""
            try:
                coord = self._get_coordinator_handle()
                if coord is None:
                    status = "no_coordinator"
                    preview = "Integration not loaded. Reload the config entry first."
                else:
                    msg = await coord.async_emit_test_alert(kind, ignore_filters=ignore)
                    status = "sent"
                    preview = (msg or "")[:600]
            except Exception as exc:
                status = "failed"
                preview = str(exc)[:600]
            self._test_result = {"status": status, "kind": kind, "preview": preview}
            return await self.async_step_test_notification_result()
        schema = vol.Schema({
            vol.Required("alert_kind", default="status_summary"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        "status_summary",
                        "all_alerts",
                        "pendulum_hourly",
                        "pendulum_daily",
                        "short_run",
                        "short_off",
                        "ml_anomaly",
                        "setpoint_osc",
                        "cop_low",
                        "stooklijn_advies",
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="alert_kind",
                ),
            ),
            vol.Optional("ignore_group_filters", default=False): bool,
        })
        return self.async_show_form(
            step_id="test_notification",
            data_schema=schema,
        )

    async def async_step_test_notification_result(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show test result; Submit returns to menu."""
        if user_input is not None:
            return await self.async_step_init()
        res = getattr(self, "_test_result", None) or {}
        return self.async_show_form(
            step_id="test_notification_result",
            data_schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
            description_placeholders={
                "status": str(res.get("status", "unknown")),
                "kind": str(res.get("kind", "?")),
                "preview": str(res.get("preview", "")),
            },
        )

    async def async_step_test_all_notifications(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """One click -- send one of every alert type (filters bypassed)."""
        if user_input is not None:
            status = "unknown"
            count = 0
            preview = ""
            try:
                coord = self._get_coordinator_handle()
                if coord is None:
                    status = "no_coordinator"
                    preview = "Integration not loaded. Reload the config entry first."
                else:
                    msg = await coord.async_emit_test_alert(
                        "all_alerts", ignore_filters=True
                    )
                    status = "sent"
                    count = (msg or "").count("=== ")
                    preview = (msg or "")[:600]
            except Exception as exc:
                status = "failed"
                preview = str(exc)[:600]
            self._test_all_result = {
                "status": status, "count": count, "preview": preview,
            }
            return await self.async_step_test_all_notifications_result()
        return self.async_show_form(
            step_id="test_all_notifications",
            data_schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
        )

    async def async_step_test_all_notifications_result(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show test-all result; Submit returns to options menu."""
        if user_input is not None:
            return await self.async_step_init()
        res = getattr(self, "_test_all_result", None) or {}
        return self.async_show_form(
            step_id="test_all_notifications_result",
            data_schema=vol.Schema({}, extra=vol.ALLOW_EXTRA),
            description_placeholders={
                "status": str(res.get("status", "unknown")),
                "count": str(res.get("count", 0)),
                "preview": str(res.get("preview", "")),
            },
        )


    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        c: dict[str, Any] = dict(self.config_entry.options or {})
        schema = vol.Schema({
            vol.Required("retention"): section(vol.Schema({
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
                vol.Required("daily_summary_live_enabled",
                    default=c.get("daily_summary_live_enabled",
                                DEFAULT_DAILY_SUMMARY_LIVE_ENABLED)
                ): bool,
            })),
            vol.Required("season"): section(vol.Schema({
                vol.Required("season_start_month",
                    default=c.get("season_start_month", DEFAULT_SEASON_START_MONTH)
                ): vol.All(
                    vol.Coerce(int),
                    vol.In({1: "January", 2: "February", 3: "March",
                            4: "April", 5: "May", 6: "June",
                            7: "July", 8: "August", 9: "September",
                            10: "October", 11: "November", 12: "December"}),
                ),
            })),
        })
        return self.async_show_form(step_id="advanced", data_schema=schema)
