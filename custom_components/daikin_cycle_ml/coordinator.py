"""DataUpdateCoordinator for Daikin Cycle ML."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

# v1.4.1 BUG-2 / BUG-3: score wiring + threshold.
from .const import (
    MAX_COP,
    MIN_SAMPLES_FOR_AVG,
    COP_CURVE_RECENT_HOURS,
    COP_CURVE_RECENT_MAX_POINTS,
    COP_ROLLUP_WINDOW_HOURS,
    COP_SENSOR_ENTITY,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_FLOW_SENSOR,
    ATTR_INDOOR_AMBIENT_R1T,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_TARGET_COND_TEMP,
    buh_step_kw_for_model as _buh_step_kw_for_model,
    DEFAULT_COMFORT_MIN_C,
    DOMAIN,
    GOOD_CYCLE_MIN_SCORE,
    MODEL_BASISPROFIEL,
    SOURCE_SENSOR_ENTITY,
    UPDATE_INTERVAL_SECONDS,
    BUH_7D_RATIO_THRESHOLD_DEFAULT,
    DEFROST_7D_COUNT_THRESHOLD_DEFAULT,

    DEGRADATION_BASELINE_DAYS,
    DEGRADATION_REFRESH_THROTTLE_S,
    DEGRADATION_WINDOW_DAYS,
    ENERGY_DT_CAP_S,
    ENERGY_DT_WARN_S,
    ENERGY_PERSIST_INTERVAL_S,
    TRANSIENT_MAX_DURATION_S,
    TRANSIENT_NEAR_MAX_DURATION_S,
    TRANSIENT_NEAR_MAX_DT_K,
    TRANSIENT_NEAR_MIN_RPS,
    COP_LOW_MIN_SAMPLES,
    COP_LOW_THRESHOLD,
    STOOKLIJN_MIN_CONFIDENCE,
    STOOKLIJN_MIN_SAVINGS_PCT,
    TEST_ALERT_DELTA,
    ALERT_STORE_VERSION,
    ALERT_STORE_KEY,
    ALERT_STORE_SAVE_DELAY,
    COP_VS_DATASHEET_LOW_PCT,
    DEFAULT_DHW_PENDULUM_CPH,
    HIGH_CYCLE_RATE_MULTIPLIER,
    MODE_DHW,
    DEFAULT_ALERT_RETENTION_DAYS,
    DEFAULT_MODEL_STATE_RETENTION_DAYS,
    DEFAULT_CYCLE_RETENTION_DAYS,
    KMEANS_STALE_AFTER_DAYS,
    ENERGY_ANOMALY_FLOOR_KWH,
    ENERGY_ANOMALY_MIN_DAYS,
    ENERGY_ANOMALY_SIGMA_THRESHOLD,
    ATTR_BOILER_DHW_DEMAND,
)
from .engine.cop_degradation import (
    analyze_degradation,
    analyze_trend,
    build_dirty_hours,
)
from .engine.action_engine import generate_advice
from .engine.attribute_compat import build_compat_view
from .engine.anomaly_engine import evaluate as evaluate_anomaly
from .engine.attribute_reader import missing_required, read
from .engine.thermal import compute_thermal_power_live as _compute_thermal_power_live
from .engine.thermal import dt_from_attrs as _dt_from_attrs
from .engine.thermal import flow_from_attrs as _flow_from_attrs
from .engine.thermal import (
    boiler_active_from_attrs as _boiler_active_from_attrs,
    boiler_heat_active_from_attrs as _boiler_heat_active_from_attrs,
    boiler_efficiency_cop_from_attrs as _boiler_efficiency_cop_from_attrs,
    hybrid_mode_from_attrs as _hybrid_mode_from_attrs,
    rps_from_attrs as _rps_from_attrs,
    safe_bool,
    secondary_rps_from_attrs as _secondary_rps_from_attrs,
)
from .engine.cycle_detector import CycleDetector
from .engine.model_datasheets import (
    get_datasheet as _get_datasheet,
)
from .engine.model_datasheets import (
    load_bundled as _load_bundled_datasheets,
)
from .engine.model_datasheets import (
    UserDatasheetError,
)
from .engine.model_datasheets import (
    load_defaults as _load_datasheet_defaults,
)
from .engine.model_datasheets import (
    load_user as _load_user_datasheets,
)
from .engine.model_datasheets import (
    merge as _merge_datasheets,
)
from .engine.model_profiles import defaults_for
from .engine.notification_engine import (
    build_status_message,
    evaluate_alerts,
    passes_filters,
)
from .engine.quality_scorer import score_cycle
from .ml.adaptive_thresholds import AdaptiveThresholds
from .ml.clustering import classify_clusters, nearest_centroid
from .ml.features import VECTOR_LEN, extract_feature_vector
from .ml.multi_baseline import MultiBaseline
from .engine.timer_health import clamp_cycle_duration as _clamp_duration
from .engine.status_report import KMEANS_ADVICE_BY_REASON  # I2

from .repairs import async_check_repairs
from .storage.store import CycleStore

from .const import OPTION_DAILY_SUMMARY_LIVE_ENABLED

_LOGGER = logging.getLogger(__name__)

_KMEANS_STALE_THRESHOLD_S = 25 * 3600
_KMEANS_BACKFILL_DELAY_S = 300


@dataclass
class DataSnapshot:
    """Latest coordinator payload."""

    attrs: dict[str, Any] = field(default_factory=dict)
    state: str = "idle"
    mode: str = "unknown"
    last_record: dict[str, Any] | None = None
    missing_attrs: list[str] = field(default_factory=list)
    last_sample_ts: float = 0.0
    last_success_ts: float = 0.0
    cycle_start_ts: float = 0.0
    errors: int = 0
    errors_total: int = 0
    anomaly: Any = None
    advice: list[Any] = field(default_factory=list)
    cluster_id: int | None = None
    stooklijn_advies: dict[str, Any] = field(default_factory=dict)
    cop_today: dict[str, Any] = field(default_factory=dict)
    cop_combined_today: dict[str, Any] = field(default_factory=dict)
    cop_hourly_day: dict[str, Any] = field(default_factory=dict)
    cop_hourly_week: dict[str, Any] = field(default_factory=dict)
    cop_hourly_month: dict[str, Any] = field(default_factory=dict)
    cop_curve_recent: dict[str, Any] = field(default_factory=dict)
    spf_state: dict[str, Any] = field(default_factory=dict)
    power_w: float | None = None
    cop: float | None = None
    cop_source: str = "none"
    electrical_power_w: float | None = None
    electrical_power_source: str = "none"
    setpoint_oscillating: bool = False
    datasheet: dict[str, Any] | None = None
    datasheet_model: str | None = None
    cop_normalized_a7w35: float | None = None
    cop_vs_datasheet_pct: float | None = None
    cop_degradation_status: str = "none"
    cop_degradation_week_pct: float | None = None
    cop_trend_30d: float | None = None
    cop_degradation_detail: dict[str, Any] = field(default_factory=dict)
    cop_trend_detail: dict[str, Any] = field(default_factory=dict)
    # Hybrid (EVLQ) support — issue #218
    boiler_active: bool = False
    boiler_heat_active: bool = False
    boiler_dhw_active: bool = False
    hybrid_mode: str = ""
    is_hybrid: bool = False
    boiler_efficiency_cop: float | None = None
    inv_freq_secondary: float | None = None


# --- FEAT-2: live thermal power helpers ---

def _safe_float_opt(value: Any) -> float | None:
    """Parse any value to float, or None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_power_w(value: float | None, unit: str | None) -> float | None:
    """Normalize power reading to Watt (kW -> W, W/unknown stays W)."""
    if value is None:
        return None
    if unit == "kW":
        return value * 1000.0
    return value




COP_MIN_TICKS: int = 4


def _cop_confidence(count: int) -> str:
    """Statistical confidence from real sample count (v1.12.5 #133).

    Thresholds based on 95% CI of the mean at 300s sample cadence:
      n < 3:   variance undefined, unusable           -> "none"
      n 3-5:   very noisy, CI ~ +/-90-115%            -> "low"
      n 6-11:  usable for trend, CI ~ +/-60-80%       -> "medium"
      n >= 12: robust, CI < +/-57%                    -> "high"

    Rationale: 12 samples at 300s cadence = 1h steady-state. Independent
    samples are the unit of confidence; duration does not change the math.
    """
    if count < 3:
        return "none"
    if count < 6:
        return "low"
    if count < 12:
        return "medium"
    return "high"



def _apply_cop_sanity_gate(
    cop_avg: float | None, count: int | None, *, cycle_id: int | None = None
) -> tuple[float | None, str]:
    """v1.13.0 #129/#124: reject COP statistical/physical artifacts.

    v19 caveat: features.vector_json[11]=0.0 from downstream NULL->0.0
    is NOT a measurement; v19 must recompute from cop_samples.
    """
    n = count or 0
    if n < MIN_SAMPLES_FOR_AVG:
        return None, "none"
    if cop_avg is not None and cop_avg > MAX_COP:
        _LOGGER.info(
            "cop_avg %.2f > MAX_COP %.2f, nulling (cycle %s, n=%d)",
            cop_avg, MAX_COP, cycle_id, n,
        )
        return None, "none"
    return cop_avg, _cop_confidence(n)

def _weighted_mean_stdev(
    w_sum: float, weight_sum: float, sq_w_sum: float
) -> tuple[float | None, float | None]:
    """Return (power-weighted mean, stdev) from accumulator sums."""
    if weight_sum <= 0.0:
        return None, None
    mean = w_sum / weight_sum
    var = (sq_w_sum / weight_sum) - (mean * mean)
    if var < 0.0:
        var = 0.0
    return mean, var ** 0.5

def _classify_transient(record: dict[str, Any]) -> bool:
    """v1.12.0 (#105): startup-transient classifier.

    Rule (mirrors the SQL backfill in async_initialize):
      transient if duration_s < TRANSIENT_MAX_DURATION_S (120s)
      OR (duration_s < TRANSIENT_NEAR_MAX_DURATION_S (300s)
          AND dT_max < TRANSIENT_NEAR_MAX_DT_K (3.0K)
          AND rps_max >= TRANSIENT_NEAR_MIN_RPS (40.0))
    """
    dur = record.get("duration_s")
    if isinstance(dur, (int, float)) and dur < TRANSIENT_MAX_DURATION_S:
        return True
    if isinstance(dur, (int, float)) and dur < TRANSIENT_NEAR_MAX_DURATION_S:
        dt = record.get("dT_max")
        rps = record.get("rps_max")
        if (
            isinstance(dt, (int, float))
            and dt < TRANSIENT_NEAR_MAX_DT_K
            and isinstance(rps, (int, float))
            and rps >= TRANSIENT_NEAR_MIN_RPS
        ):
            return True
    return False


def score_and_count(
    record: dict[str, Any],
    options: dict[str, Any] | None,
    store: Any,
    now: float,
) -> None:
    """v1.4.1: compute quality_score + increment good/bad counters.

    Isolated try/except so a scoring failure never aborts the cycle
    pipeline (R191).
    """
    try:
        off_s = store.off_time_since_last(now)
    except Exception:
        off_s = None

    # v1.12.0 (#105 wiring): record short run / short off events.
    # Pre-v1.12.0 these store methods had zero callers, so
    # short_runs_today / short_offs_today sensor attributes always
    # showed 0 even when the corresponding binary sensors flagged
    # short events. Each call is isolated so a counter failure
    # cannot block cycle scoring (R378 pattern).
    _opts = options or {}
    _sr_min = int(_opts.get("short_run_threshold_min", 20))
    _so_min = int(_opts.get("short_off_threshold_min", 5))
    _dur = record.get("duration_s")
    if isinstance(_dur, (int, float)) and _dur < _sr_min * 60:
        try:
            store.record_short_run()
        except Exception:
            _LOGGER.warning(
                "record_short_run failed", exc_info=True
            )
    if isinstance(off_s, (int, float)) and off_s < _so_min * 60:
        try:
            store.record_short_off()
        except Exception:
            _LOGGER.warning(
                "record_short_off failed", exc_info=True
            )

    # v1.12.0 (#105): compute short-cycle ratio for scorer.
    # Counters updated above, so short_runs_today includes this cycle.
    # cycles_today is incremented by add_cycle AFTER score_and_count
    # runs, so add +1 to include the current cycle in the denominator.
    # +1 makes denominator >= 1 by construction; no zero guard needed.
    # Percent (0-100), matching DEFAULT_SHORT_CYCLE_RATIO (50).
    _short_today = store.get("short_runs_today", 0)
    _cycles_denom = store.get("cycles_today", 0) + 1
    _ratio_pct = round(100.0 * _short_today / _cycles_denom, 2)

    try:
        record["quality_score"] = score_cycle(
            record, options, off_time_s=off_s,
            short_cycle_ratio=_ratio_pct,
        )
    except Exception:
        _LOGGER.warning("score_cycle failed", exc_info=True)
        record["quality_score"] = None
    qs = record.get("quality_score")
    if isinstance(qs, int):
        try:
            key = (
                "good_cycles_today"
                if qs >= GOOD_CYCLE_MIN_SCORE
                else "bad_cycles_today"
            )
            store.increment(key)
        except Exception:
            _LOGGER.warning(
                "cycle counter increment failed", exc_info=True
            )


def _compute_daily_summary_recent(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """v1.7.1: transform daily_summary rows into recent-window payload.

    Returns a dict with "state" (int, total cycles) + attrs payload.
    Empty rows yields a fully zeroed payload (days=[], totals zeroed).
    Input rows come from db.async_daily_summary (SELECT * + derived fields).
    """
    totals: dict[str, dict[str, Any]] = {
        "heating": {"days": 0, "cycles": 0, "dur_min": 0.0, "buh": 0, "defrost": 0},
        "dhw": {"days": 0, "cycles": 0, "dur_min": 0.0, "buh": 0, "defrost": 0},
        "cooling": {"days": 0, "cycles": 0, "dur_min": 0.0, "buh": 0, "defrost": 0},
    }
    if not rows:
        return {
            "state": 0,
            "days_available": 0,
            "days_count": 0,
            "latest_day": None,
            "oldest_day": None,
            "days": [],
            "totals_by_mode": totals,
        }
    ordered = sorted(
        rows,
        key=lambda r: (str(r.get("day")), str(r.get("mode") or "unknown")),
        reverse=True,
    )
    days: list[dict[str, Any]] = []
    for r in ordered:
        cycles = int(r.get("cycles") or 0)
        total_s = int(r.get("total_duration_s") or 0)
        dur_max_s = int(r.get("duration_max") or 0)
        q_sum = int(r.get("quality_sum") or 0)
        days.append({
            "day": str(r.get("day")),
            "mode": str(r.get("mode") or "unknown"),
            "cycles": cycles,
            "dur_min": round(total_s / 60.0, 1),
            "dur_min_avg": round(total_s / cycles / 60.0, 1) if cycles else 0.0,
            "dur_max": round(dur_max_s / 60.0, 1),
            "quality_avg": round(q_sum / cycles, 1) if cycles else 0.0,
            "buh": int(r.get("buh_count") or 0),
            "defrost": int(r.get("defrost_count") or 0),
        })
    for d in days:
        bucket = totals.get(d["mode"])
        if bucket is None:
            continue
        bucket["days"] += 1
        bucket["cycles"] += d["cycles"]
        bucket["dur_min"] = round(bucket["dur_min"] + d["dur_min"], 1)
        bucket["buh"] += d["buh"]
        bucket["defrost"] += d["defrost"]
    day_set = {d["day"] for d in days}
    return {
        "state": sum(d["cycles"] for d in days),
        "days_available": len(day_set),
        "days_count": len(day_set),
        "latest_day": max(day_set),
        "oldest_day": min(day_set),
        "days": days,
        "totals_by_mode": totals,
    }


class DaikinCycleMLCoordinator(DataUpdateCoordinator[DataSnapshot]):
    """Reads the source sensor every UPDATE_INTERVAL_SECONDS."""

    # Batch 14c-2 class-level defaults (R52)
    indoor_temp_entity: str | None = None
    _cycle_lwt_sum: float = 0.0
    _cycle_lwt_count: int = 0
    _cycle_indoor_sum: float = 0.0
    _cycle_indoor_count: int = 0
    _cycle_cop_w_sum: float = 0.0
    _cycle_cop_weight_sum: float = 0.0
    _cycle_cop_sq_w_sum: float = 0.0
    _cycle_cop_count: int = 0

    # ---------- v1.6.0-C5/C6: class-level defaults for __new__ tests ----------
    _runtime_day_key: str = ""
    _buh_step1_s: float = 0.0
    _buh_step2_s: float = 0.0
    _prev_defrost: bool = False
    _defrost_start_ts: float | None = None
    _defrost_count_today: int = 0
    _defrost_duration_s: float = 0.0
    _last_defrost_ts: float = 0.0
    _last_runtime_tick_ts: float = 0.0
    _energy_day_key: str = ""
    _last_energy_tick_ts: float = 0.0
    _cop_hourly_cache: dict[str, dict[str, Any]] = {}
    _cop_hourly_cache_ts: float = 0.0
    _cop_degradation_cache: dict[str, Any] = {}
    _cop_degradation_cache_ts: float = 0.0
    # v1.6.0-C6a: persist-throttle timestamps (R52 class defaults)
    _last_runtime_persist_ts: float = 0.0
    _last_energy_persist_ts: float = 0.0

    # R52: class-level defaults so __new__-style tests find these attrs
    _kmeans_centroids: list[Any] = []
    _cluster_labels: dict[int, str] = {}
    _setpoint_history: deque[Any] | None = None
    _last_setpoint: float | None = None

    _notify_fail_streak: int = 0
    _notify_fail_target: str = ""
    _db_integrity_ok: bool = True
    _migration_error: str | None = None

    # v1.14.0: class-level default so partial test fixtures
    # (object.__new__ without __init__) do not AttributeError
    # in the _async_update_data except handler.
    _errors_total: int = 0

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.source_entity: str = entry.data.get(
            "source_sensor", SOURCE_SENSOR_ENTITY
        )
        model = entry.data.get("model", MODEL_BASISPROFIEL)
        self.options: dict[str, Any] = {
            **defaults_for(model),
            **dict(entry.options or {}),
        }
        self.power_sensor: str | None = self.options.get("power_sensor_entity")
        self.indoor_temp_entity: str | None = self.options.get(
            "indoor_temp_sensor"
        ) or None
        self._cycle_lwt_sum: float = 0.0
        self._cycle_lwt_count: int = 0
        self._cycle_indoor_sum: float = 0.0
        self._cycle_indoor_count: int = 0
        self._cycle_cop_w_sum: float = 0.0
        self._cycle_cop_weight_sum: float = 0.0
        self._cycle_cop_sq_w_sum: float = 0.0
        self._cycle_cop_count: int = 0
        self.detector = CycleDetector(self.options)
        self.store = CycleStore()
        self._errors_total = 0
        self._notify_fail_streak: int = 0
        self._notify_fail_target: str = ""
        self._db_integrity_ok: bool = True
        self._migration_error: str | None = None
        self._last_alert_sent: dict[str, float] = {}
        # PR E: 7d rollup cache (refreshed before each dispatch)
        self._defrost_7d_sum: int = 0
        self._defrost_7d_duration_s: float = 0.0
        self._buh_7d_count: int = 0
        self._buh_7d_ratio: float = 0.0
        # I1: db_retention_warning cache (refreshed in _refresh_7d_rollups)
        self._db_retention_stale: dict[str, Any] = {}
        # I2: kmeans_retrain_stale cache (refreshed in _refresh_7d_rollups)
        self._kmeans_stale: dict[str, Any] = {}
        # I6: energy_daily_anomaly cache (refreshed in _refresh_7d_rollups)
        self._energy_daily_anomaly: dict[str, Any] = {}
        # J: avg_duration_7d_min cache (refreshed in _refresh_7d_rollups)
        self._avg_duration_7d_min: int | None = None
        self._alert_store: Any = None
        self._alert_save_unsub: Any = None
        self._setpoint_history: deque[tuple[float, float]] = deque()
        self._last_setpoint: float | None = None
        self._maintenance_unsub: Any = None
        self._baseline_save_unsub: Any = None
        self._kmeans_unsub: Any = None
        self._kmeans_backfill_unsub: Any = None
        self._status_update_unsub: Any = None
        self._stooklijn_unsub: Any = None
        self.baseline = MultiBaseline(VECTOR_LEN)
        self.adaptive = AdaptiveThresholds(
            min_samples=int(
                self.options.get("adaptive_min_samples", 20)
            )
        )
        self._kmeans_centroids: list[list[float]] = []
        self._cluster_labels: dict[int, str] = {}
        self.cop_sensor_entity: str = self.options.get(
            "cop_sensor_entity", COP_SENSOR_ENTITY
        )
        self._last_cop_sample_ts: float = 0.0
        self._cop_sample_seed_done: bool = False
        self._stooklijn_cache: dict[str, Any] = {}
        self._stooklijn_cache_ts: float = 0.0
        self._cop_today_cache: dict[str, Any] = {}
        self._cop_today_heating_cache: dict[str, Any] = {}
        self._cop_hourly_cache: dict[str, dict[str, Any]] = {}
        self._spf_state_cache: dict[str, Any] = {}
        self._datasheet_cache: dict[str, Any] = {}
        self._datasheet_merged: dict[str, Any] = {}
        self._datasheet_defaults: dict[str, Any] = {}
        self._datasheet_user: dict[str, Any] = {}
        self._datasheet_user_loaded: bool = False
        self._cop_hourly_cache_ts: float = 0.0
        self._cop_degradation_cache: dict[str, Any] = {}
        self._cop_degradation_cache_ts: float = 0.0
        # v1.6.0-C6a: persist-throttle
        self._last_runtime_persist_ts: float = 0.0
        self._last_energy_persist_ts: float = 0.0
        # ---------- v1.6.0-C5: runtime/BUH/defrost accumulators ----------
        self._runtime_day_key: str = ""
        self._buh_step1_s: float = 0.0
        self._buh_step2_s: float = 0.0
        self._prev_defrost: bool = False
        self._defrost_start_ts: float | None = None
        self._defrost_count_today: int = 0
        self._defrost_duration_s: float = 0.0
        self._last_defrost_ts: float = 0.0
        self._last_runtime_tick_ts: float = 0.0
        # ---------- v1.6.0-C6a: energy accumulators ----------
        self._energy_day_key: str = ""
        self._energy_acc: dict[str, dict[str, float]] = {
            "heating": {"th": 0.0, "el": 0.0},
            "dhw":     {"th": 0.0, "el": 0.0},
            "cooling": {"th": 0.0, "el": 0.0},
        }
        # v1.11.3: per-day high-water-mark for total_increasing sensors.
        # Never decreases within a day. Reset only at day rollover.
        self._energy_hwm: dict[str, dict[str, float]] = {
            "heating": {"th": 0.0, "el": 0.0},
            "dhw":     {"th": 0.0, "el": 0.0},
            "cooling": {"th": 0.0, "el": 0.0},
        }
        self._last_energy_tick_ts: float = 0.0
        # ---------- v1.6.0-C6b: cost caches ----------
        self._cost_month_cache: dict[str, Any] = {}
        self._cost_month_cache_ts: float = 0.0

        self.db: Any = None
        self._daily_summary_recent: dict[str, Any] | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    async def async_setup_alert_persistence(self) -> None:
        """Hydrate _last_alert_sent from HA Store."""
        from homeassistant.helpers.storage import Store
        self._alert_store = Store(
            self.hass, ALERT_STORE_VERSION, ALERT_STORE_KEY,
        )
        raw = await self._alert_store.async_load() or {}
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        last = data.get("last_sent", {}) if isinstance(data, dict) else {}
        self._last_alert_sent = {
            str(k): float(v)
            for k, v in last.items()
            if isinstance(v, (int, float))
        }

    async def _async_persist_last_alert_sent(self) -> None:
        """Flush _last_alert_sent to HA Store."""
        if self._alert_store is None:
            return
        await self._alert_store.async_save(
            {"data": {"last_sent": dict(self._last_alert_sent)}}
        )

    def _schedule_alert_save(self) -> None:
        """Debounced save: coalesce writes over ALERT_STORE_SAVE_DELAY."""
        if self._alert_store is None:
            return
        if self._alert_save_unsub is not None:
            self._alert_save_unsub()
        async def _on_fire(_now: Any) -> None:
            await self._async_persist_last_alert_sent()
        self._alert_save_unsub = async_call_later(
            self.hass,
            ALERT_STORE_SAVE_DELAY,
            _on_fire,
        )

    async def async_setup_maintenance(self) -> None:
        """Schedule the daily maintenance pass at 03:00 local."""
        if self._maintenance_unsub is not None:
            return
        self._maintenance_unsub = async_track_time_change(
            self.hass,
            self._async_maintenance_callback,
            hour=3,
            minute=0,
            second=0,
        )
        _LOGGER.info('Maintenance hook scheduled at 03:00 local')

    async def _async_maintenance_callback(self, _now: Any) -> None:
        try:
            await self.async_run_maintenance()
        except Exception:
            _LOGGER.exception('Scheduled maintenance failed')

    async def async_run_maintenance(
        self,
        *,
        cycle_retention_days: int | None = None,
        alert_retention_days: int | None = None,
        model_state_retention_days: int | None = None,
        vacuum: bool | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Run retention maintenance with a 20h guard."""
        if self.db is None:
            return {'ok': False, 'reason': 'no_db'}
        opts = self.options or {}
        if not force and not bool(opts.get('retention_enabled', True)):
            return {'ok': False, 'reason': 'retention_disabled'}
        now = time.time()
        last = None
        try:
            last = await self.db.async_get_model_state('last_maintenance_ts')
        except Exception:
            _LOGGER.exception('model_state read failed')
        if (
            not force
            and isinstance(last, (int, float))
            and (now - float(last)) < 20 * 3600
        ):
            return {
                'ok': False,
                'reason': 'too_soon',
                'last_ts': float(last),
                'elapsed_s': now - float(last),
            }
        cdays = (
            int(cycle_retention_days)
            if cycle_retention_days is not None
            else int(opts.get('cycle_retention_days', DEFAULT_CYCLE_RETENTION_DAYS))
        )
        adays = (
            int(alert_retention_days)
            if alert_retention_days is not None
            else int(opts.get('alert_retention_days', DEFAULT_ALERT_RETENTION_DAYS))
        )
        mdays = (
            int(model_state_retention_days)
            if model_state_retention_days is not None
            else int(opts.get(
                'model_state_retention_days',
                DEFAULT_MODEL_STATE_RETENTION_DAYS,
            ))
        )
        dovac = (
            bool(vacuum)
            if vacuum is not None
            else bool(opts.get('vacuum_enabled', True))
        )
        try:
            result = await self.db.async_run_maintenance(
                cycle_retention_days=cdays,
                alert_retention_days=adays,
                model_state_retention_days=mdays,
                vacuum=dovac,
            )
        except Exception as err:
            _LOGGER.exception('Maintenance failed: %s', err)
            return {'ok': False, 'reason': 'exception', 'error': str(err)}
        try:
            await self.db.async_set_model_state('last_maintenance_ts', now)
        except Exception:
            _LOGGER.exception('model_state write failed')
        if self.db is not None:  # pragma: no branch
            try:
                self._db_integrity_ok = await self.db.async_integrity_check()
            except Exception:
                self._db_integrity_ok = False
                _LOGGER.warning("integrity_check post-maintenance failed", exc_info=True)
        out = {'ok': True, 'ts': now}
        if isinstance(result, dict):  # pragma: no branch
            out.update(result)
        return out

    # ---------- Batch 11c MultiBaseline wiring ----------

    async def async_setup_baseline_persistence(self) -> None:
        """Restore baseline from model_state, schedule 6h save."""
        if self.db is not None:
            try:
                data = await self.db.async_get_model_state("baseline_state")
                if data:
                    self.baseline = MultiBaseline.from_dict(data)
                    if getattr(self.baseline, "_migrated_from_dim", None) is not None:
                        _LOGGER.info(
                            "MultiBaseline migrated from dim=%s to %d; persisting now",
                            self.baseline._migrated_from_dim,
                            self.baseline.dim,
                        )
                        await self.async_save_baseline_state()
                    _LOGGER.info(
                        "Baseline restored: modes=%s samples=%s",
                        self.baseline.modes(),
                        self.baseline.total_samples(),
                    )
            except Exception:
                _LOGGER.exception("Baseline restore failed")
            await self.async_load_adaptive_state()
            await self._restore_detector_state()
            await self._restore_runtime_acc()
            await self._restore_energy_acc()
            await self._maybe_backfill_daily_summary()
            try:
                if self.db is not None and hasattr(
                    self.db, "async_ensure_cluster_column"
                ):  # pragma: no branch
                    await self.db.async_ensure_cluster_column()
                await self._load_kmeans_state()
            except Exception:
                _LOGGER.warning("cluster state setup failed", exc_info=True)
        if self._baseline_save_unsub is None:
            self._baseline_save_unsub = async_track_time_interval(
                self.hass,
                self._async_baseline_save_callback,
                timedelta(hours=6),
            )

    async def _async_baseline_save_callback(self, _now: Any) -> None:
        try:
            await self.async_save_baseline_state()
        except Exception:
            _LOGGER.exception("Scheduled baseline save failed")
        try:
            await self.async_save_adaptive_state()
        except Exception:
            _LOGGER.exception("Scheduled adaptive save failed")
        try:
            await self._maybe_rollup_cop_hourly()
        except Exception:
            _LOGGER.exception("Scheduled cop_hourly rollup failed")

    async def _maybe_rollup_cop_hourly(
        self, window_hours: int = COP_ROLLUP_WINDOW_HOURS
    ) -> int:
        """Roll up cop_samples into cop_hourly. No-op without db."""
        if self.db is None:
            return 0
        result: int = await self.db.async_rollup_cop_hourly(
            window_hours=window_hours
        )
        return result

    async def _maybe_refresh_cop_hourly(self, now: float) -> None:
        """Refresh day/week/month cop_hourly caches (throttled 300s)."""
        if self.db is None:
            return
        if (now - self._cop_hourly_cache_ts) < 300.0:
            return
        try:
            for label, days in (
                ("day", 1), ("week", 7), ("month", 30),
            ):
                since = now - float(days) * 86400.0
                stats = await self.db.async_cop_hourly_stats(
                    since_ts=since
                )
                by_mode = await self.db.async_cop_hourly_by_mode(
                    since_ts=since
                )
                self._cop_hourly_cache[label] = {
                    **stats,
                    "by_mode": by_mode,
                }
            self._cop_hourly_cache_ts = now
        except Exception:
            _LOGGER.exception("cop_hourly cache refresh failed")
            return
        try:
            await self._refresh_cop_curve_recent(now)
        except Exception:
            _LOGGER.exception("cop curve_recent refresh failed")

    async def _maybe_refresh_cop_degradation(self, now: float) -> None:
        """Refresh weather-normalized degradation + 30d trend (C4).

        Throttled to DEGRADATION_REFRESH_THROTTLE_S. Uses heating-only
        hourly rows and cycles-filtered dirty hours. On any failure
        leaves the previous cache intact.
        """
        if self.db is None:
            return
        if (now - self._cop_degradation_cache_ts) < DEGRADATION_REFRESH_THROTTLE_S:
            return
        win_s = float(DEGRADATION_WINDOW_DAYS) * 86400.0
        base_s = float(DEGRADATION_BASELINE_DAYS) * 86400.0
        recent_since = now - win_s
        prev_since = now - 2.0 * win_s
        baseline_since = now - (base_s + win_s)
        try:
            recent_rows = await self.db.async_query_cop_hourly(
                since_ts=recent_since, until_ts=now, mode="heating"
            )
            prev_rows = await self.db.async_query_cop_hourly(
                since_ts=prev_since, until_ts=recent_since,
                mode="heating",
            )
            baseline_rows = await self.db.async_query_cop_hourly(
                since_ts=baseline_since, until_ts=recent_since,
                mode="heating",
            )
            cycles_all = await self.db.async_fetch_cycles(
                days=DEGRADATION_BASELINE_DAYS + DEGRADATION_WINDOW_DAYS
            )
            cycles_win = [
                c for c in cycles_all
                if c.get("start_ts") is not None
                and float(c["start_ts"]) >= baseline_since
            ]
            dirty = build_dirty_hours(cycles_win)
            deg = analyze_degradation(
                recent_rows, prev_rows, dirty,
                window_days=DEGRADATION_WINDOW_DAYS, now=now,
            )
            trend = analyze_trend(
                baseline_rows, recent_rows, dirty,
                window_days=DEGRADATION_BASELINE_DAYS,
                baseline_days=DEGRADATION_BASELINE_DAYS,
                recent_days=DEGRADATION_WINDOW_DAYS,
                now=now,
            )
            self._cop_degradation_cache = {
                "degradation": deg, "trend": trend,
            }
            self._cop_degradation_cache_ts = now
        except Exception:
            _LOGGER.exception(
                "cop_degradation cache refresh failed"
            )

    async def _refresh_cop_curve_recent(self, now: float) -> None:
        """Populate _cop_hourly_cache["curve_recent"] with 48h points."""
        if self.db is None:
            return
        since = now - float(COP_CURVE_RECENT_HOURS) * 3600.0
        rows = await self.db.async_query_cop_hourly(since_ts=since)
        # cap to most recent N points
        if len(rows) > COP_CURVE_RECENT_MAX_POINTS:
            rows = rows[-COP_CURVE_RECENT_MAX_POINTS:]
        points: list[dict[str, Any]] = []
        modes_present: set[str] = set()
        for r in rows:
            mode = r.get("mode") or "unknown"
            modes_present.add(mode)
            points.append({
                "ts": int(r["ts_hour"]) * 3600,
                "mode": mode,
                "cop_mean": r.get("cop_mean"),
                "cop_p50": r.get("cop_p50"),
                "cop_p90": r.get("cop_p90"),
                "lwt_mean": r.get("lwt_mean"),
                "outdoor_mean": r.get("outdoor_mean"),
                "n_samples": r.get("n_samples"),
            })
        self._cop_hourly_cache["curve_recent"] = {
            "points": points,
            "n_points": len(points),
            "window_hours": COP_CURVE_RECENT_HOURS,
            "modes_present": sorted(modes_present),
            "updated_ts": now,
        }

    async def async_save_baseline_state(self) -> bool:
        if self.db is None:
            return False
        try:
            await self.db.async_set_model_state(
                "baseline_state", self.baseline.to_dict()
            )
            return True
        except Exception:
            _LOGGER.exception("Baseline save failed")
            return False

    async def async_setup_kmeans(self) -> None:
        """Schedule weekly k-means on Sunday 04:00."""
        if self._kmeans_unsub is not None:
            return
        self._kmeans_unsub = async_track_time_change(
            self.hass,
            self._async_kmeans_callback,
            hour=4,
            minute=0,
            second=0,
        )

    async def _async_kmeans_callback(self, _now: Any) -> None:
        # R46: async_track_time_change has no day_of_week; filter to Sunday here.
        try:
            fire_ts = time.time()
            await self._merge_kmeans_state(
                {"last_scheduled_fire_ts": fire_ts}
            )
            if _now.weekday() != 6:
                return
            result = await self.async_run_kmeans()
            ok = bool(result.get("ok"))
            await self._merge_kmeans_state(
                {
                    "last_scheduled_attempt_ts": fire_ts,
                    "last_scheduled_outcome": (
                        "success" if ok else str(result.get("reason", "unknown"))
                    ),
                    "last_scheduled_cycles_n": result.get("n"),
                }
            )
        except Exception:
            _LOGGER.exception("Scheduled kmeans failed")

    async def _persist_kmeans_attempt(
        self,
        ok: bool,
        reason: str | None = None,
        n: int | None = None,
        k: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """I2: persist a kmeans attempt. Never raises.

        Merges into existing kmeans_state so legacy {centroids, labels, ts}
        payloads are preserved. On success also updates last_ok_ts and
        zeroes failure counters; on failure increments consecutive_failures
        and records last_failure_reason.
        """
        _db = getattr(self, "db", None)
        if _db is None:
            return
        try:
            existing = await _db.async_get_model_state("kmeans_state", default={})
        except Exception:
            _LOGGER.exception("kmeans persist: read failed")
            return
        state: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
        now = time.time()
        state["last_attempt_ts"] = now
        if ok:
            if extra:
                state.update(extra)
            state["last_ok_ts"] = now
            state["consecutive_failures"] = 0
            state["last_failure_reason"] = None
        else:
            prev = state.get("consecutive_failures", 0)
            try:
                prev_i = int(prev)
            except (TypeError, ValueError):
                prev_i = 0
            state["consecutive_failures"] = prev_i + 1
            state["last_failure_reason"] = reason
        try:
            await _db.async_set_model_state("kmeans_state", state)
        except Exception:
            _LOGGER.exception("kmeans persist: write failed")

    async def async_run_kmeans(self, days: int = 7) -> dict[str, Any]:
        """Cluster last N days of cycles into 3 groups."""
        if self.db is None:
            return {"ok": False, "reason": "no_db"}
        from .ml.clustering import kmeans, labels_to_dict
        from .ml.features import extract_many
        try:
            cycles = await self.db.async_fetch_cycles(days=days)
        except Exception:
            _LOGGER.exception("kmeans fetch failed")
            await self._persist_kmeans_attempt(ok=False, reason="fetch_failed")
            return {"ok": False, "reason": "fetch_failed"}
        vectors = extract_many(cycles)
        if len(vectors) < 3:
            await self._persist_kmeans_attempt(
                ok=False, reason="too_few", n=len(vectors),
            )
            return {"ok": False, "reason": "too_few", "n": len(vectors)}
        try:
            result = kmeans(vectors, k=3)
        except Exception:
            _LOGGER.exception("kmeans run failed")
            await self._persist_kmeans_attempt(ok=False, reason="kmeans_failed")
            return {"ok": False, "reason": "kmeans_failed"}
        payload = labels_to_dict(result)
        payload["ts"] = time.time()
        await self._persist_kmeans_attempt(
            ok=True, n=len(vectors), k=result.k, extra=payload,
        )
        return {"ok": True, "n": len(vectors), "k": result.k}

    async def _merge_kmeans_state(self, fields: dict[str, Any]) -> None:
        """Read-modify-write kmeans_state. Never raises. Fix D (#125)."""
        _db = getattr(self, "db", None)
        if _db is None:
            return
        try:
            existing = await _db.async_get_model_state("kmeans_state", default={})
            state = dict(existing) if isinstance(existing, dict) else {}
            state.update(fields)
            await _db.async_set_model_state("kmeans_state", state)
        except Exception:
            _LOGGER.debug("kmeans scheduled persist failed", exc_info=True)

    async def _post_migration_retrain_check(self, _db: Any) -> bool:
        """Trigger 1 (#125): post-v1.12.4 one-shot kmeans + baseline.

        True  = handled this session (caller must NOT run Trigger 2).
        False = no migration marker OR both markers present; caller
                may proceed to Trigger 2.
        """
        ms = await _db.async_get_model_state(
            "data_migration_v1_12_4", default=None
        )
        if ms is None:
            return False
        if not (isinstance(ms, dict) and ms.get("completed") is True):
            _LOGGER.debug(
                "post-migration retrain: migration incomplete, deferring"
            )
            return True
        km = await _db.async_get_model_state(
            "post_v1124_retrain_v1125", default=None
        )
        bl = await _db.async_get_model_state(
            "post_v1124_baseline_v1125", default=None
        )
        if km is not None and bl is not None:
            return False
        if km is None:
            _LOGGER.info("post-migration retrain: kmeans")
            r = await self.async_run_kmeans()
            if r.get("ok"):
                await _db.async_set_model_state(
                    "post_v1124_retrain_v1125", {"ts": time.time()}
                )
        if bl is None:
            _LOGGER.info("post-migration retrain: baseline")
            from .services import _do_recompute_baseline
            br = await _do_recompute_baseline(self, 30)
            if br.get("computed"):
                await _db.async_set_model_state(
                    "post_v1124_baseline_v1125", {"ts": time.time()}
                )
        return True

    async def async_setup_kmeans_backfill(self, entry: Any) -> None:
        """Schedule delayed one-shot stale check (Fix B, #125)."""
        if self._kmeans_backfill_unsub is not None:
            return
        from homeassistant.helpers.event import async_call_later
        self._kmeans_backfill_unsub = async_call_later(
            self.hass,
            _KMEANS_BACKFILL_DELAY_S,
            self._run_kmeans_backfill_check,
        )
        entry.async_on_unload(self._kmeans_backfill_unsub)

    async def _run_kmeans_backfill_check(self, _now: Any) -> None:
        """One-shot: retrain if kmeans_state is stale (>25h)."""
        self._kmeans_backfill_unsub = None
        _db = getattr(self, "db", None)
        if _db is None:
            return
        # Trigger 1 — post-migration one-shot
        try:
            handled = await self._post_migration_retrain_check(_db)
        except Exception:
            _LOGGER.exception("post-migration retrain check failed")
            handled = False
        if handled:
            return
        # Trigger 2 — staleness safety net (Fix B)
        try:
            state = await _db.async_get_model_state("kmeans_state", default={})
        except Exception:
            _LOGGER.exception("kmeans backfill: read failed")
            return
        if not isinstance(state, dict):
            return
        last_ok = state.get("last_ok_ts")
        try:
            last_ok_f = float(last_ok) if last_ok is not None else None
        except (TypeError, ValueError):
            last_ok_f = None
        if last_ok_f is not None:
            age_s = time.time() - last_ok_f
            if age_s <= _KMEANS_STALE_THRESHOLD_S:
                return
            _LOGGER.info(
                "kmeans backfill: stale (age=%.1fh), retraining",
                age_s / 3600.0,
            )
        else:
            _LOGGER.info("kmeans backfill: no last_ok_ts, retraining")
        try:
            await self.async_run_kmeans()
        except Exception:
            _LOGGER.exception("kmeans backfill: run failed")

    def _read_power(self) -> float | None:
        ps = getattr(self, "power_sensor", None)
        if not ps:
            return None
        state = self.hass.states.get(ps)
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _read_power_w(self) -> float | None:
        """FEAT-2: read power sensor and normalize to Watt."""
        ps = getattr(self, "power_sensor", None)
        if not ps:
            return None
        state = self.hass.states.get(ps)
        if state is None:
            return None
        try:
            raw = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = state.attributes.get("unit_of_measurement")
        return _normalize_power_w(raw, unit)

    def _read_cop(self) -> float | None:
        """FEAT-2: read COP sensor value (dimensionless)."""
        if not self.cop_sensor_entity:
            return None
        state = self.hass.states.get(self.cop_sensor_entity)
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _detect_v2_stats(self, attrs: dict[str, Any] | None) -> bool:
        """v1.14.0: ESPAltherma 2.0 'Stats:' section detection."""
        if not attrs:
            return False
        from .const import V2_STATS_KEY
        return V2_STATS_KEY in attrs

    def _v2_stats_active(
        self, now: float, attrs: dict[str, Any] | None
    ) -> bool:
        """v1.14.0: v2 detection with 300s hysteresis (R507)."""
        from .const import V2_STATS_HYSTERESIS_S
        if self._detect_v2_stats(attrs):
            self._last_v2_stats_ts = now
            return True
        last = getattr(self, "_last_v2_stats_ts", 0.0)
        return (now - last) < V2_STATS_HYSTERESIS_S

    def _compute_electrical_power(
        self, now: float, attrs: dict[str, Any] | None
    ) -> tuple[float | None, str]:
        """v1.14.0: raomin-aligned cascade (Discussion #599)."""
        pw = self._power_from_meter()
        if pw is not None:
            return pw, "power_meter"
        pw = self._power_from_v2_stats(now, attrs)
        if pw is not None:
            return pw, "espaltherma_v2_stats"
        pw = self._power_from_inverter(attrs)
        if pw is not None:
            return pw, "inverter_estimated_v1"
        return None, "none"

    def _power_from_meter(self) -> float | None:
        ps = getattr(self, "power_sensor", None)
        if not ps:
            return None
        st = self.hass.states.get(ps)
        if st is None or st.state in (None, "unknown", "unavailable", ""):
            return None
        try:
            pw = float(st.state)
        except (TypeError, ValueError):
            return None
        return pw if pw > 0 else None

    def _power_from_v2_stats(
        self, now: float, attrs: dict[str, Any] | None
    ) -> float | None:
        from .const import V2_STATS_KEY
        if not attrs or not self._v2_stats_active(now, attrs):
            return None
        try:
            v = attrs.get(V2_STATS_KEY)
            if v is None:
                return None
            pw = float(v) * 1000.0
        except (TypeError, ValueError):
            return None
        return pw if pw > 0 else None

    def _power_from_inverter(
        self, attrs: dict[str, Any] | None
    ) -> float | None:
        """v1.14.0: v1 fallback — INV current + BUH + offset (R507)."""
        from .const import (
            INV_PRIMARY_CURRENT_KEY,
            VOLTAGE_NOMINAL_V,
            SUPPLY_PHASES_DEFAULT,
            BUH_STEP1_KW_DEFAULT,
            BUH_STEP2_KW_DEFAULT,
            BUH_STEP1_KEY,
            BUH_STEP2_KEY,
            ELECTRICAL_OFFSET_W_V1,
        )
        if not attrs:
            return None
        try:
            inv_a = float(attrs.get(INV_PRIMARY_CURRENT_KEY) or 0)
        except (TypeError, ValueError):
            inv_a = 0.0
        if inv_a <= 0:
            return None
        opts = getattr(self, "options", None) or {}
        phases = int(opts.get("supply_phases", SUPPLY_PHASES_DEFAULT))
        base_w = inv_a * VOLTAGE_NOMINAL_V * phases
        buh_w = 0.0
        if self._is_on(attrs.get(BUH_STEP1_KEY)):
            buh_w += float(opts.get("buh_step1_kw", BUH_STEP1_KW_DEFAULT)) * 1000.0
        if self._is_on(attrs.get(BUH_STEP2_KEY)):
            buh_w += float(opts.get("buh_step2_kw", BUH_STEP2_KW_DEFAULT)) * 1000.0
        return base_w + buh_w + ELECTRICAL_OFFSET_W_V1

    @staticmethod
    def _is_on(v: Any) -> bool:
        if v is None:
            return False
        return str(v).strip().upper() == "ON"

    def _read_cop_effective(
        self, now: float, attrs: dict[str, Any] | None
    ) -> tuple[float | None, str]:
        """v1.14.0: COP source cascade (sensor > computed)."""
        sensor_cop = self._read_cop()
        if sensor_cop is not None and sensor_cop > 0:
            return sensor_cop, "cop_sensor"
        if not attrs:
            return None, "none"
        power_w, power_src = self._compute_electrical_power(now, attrs)
        if power_w is None or power_w <= 0:
            return None, "no_power"
        from .engine.attribute_compat import build_compat_view
        from .engine.thermal import dt_from_attrs, compute_thermal_power_live
        compat = build_compat_view(attrs)
        dt_k = dt_from_attrs(compat)
        if dt_k is None or dt_k <= 0:
            return None, "no_dt"
        try:
            flow_lmin = float(compat.get("Flow sensor (l/min)") or 0)
        except (TypeError, ValueError):
            flow_lmin = 0.0
        try:
            rps = float(compat.get("INV frequency (rps)") or 0)
        except (TypeError, ValueError):
            rps = 0.0
        mode = "heating"
        data_obj = getattr(self, "data", None)
        dm = getattr(data_obj, "mode", None) if data_obj else None
        if dm:
            mode = str(dm)
        thermal_kw, _tsrc = compute_thermal_power_live(
            power_w=None, cop=None,
            flow_lmin=flow_lmin if flow_lmin > 0 else None,
            dt_k=dt_k,
            rps=rps if rps > 0 else None,
            mode=mode,
        )
        if thermal_kw is None or thermal_kw <= 0:
            return None, "no_thermal"
        from .const import MAX_COP
        cop = thermal_kw * 1000.0 / power_w
        if cop <= 0 or cop > MAX_COP:
            return None, "cop_out_of_range"
        return round(cop, 4), f"computed_{power_src}"

    async def _async_update_data(self) -> DataSnapshot:
        now = time.time()
        snap = DataSnapshot(last_sample_ts=now)
        self.store.daily_reset_if_needed(now)
        # v1.6.0-C6a: persist OLD-day accumulators BEFORE reset
        _day_now = time.strftime("%Y-%m-%d", time.localtime(float(now)))
        if self._runtime_day_key and self._runtime_day_key != _day_now:
            await self._persist_runtime_acc()
        if self._energy_day_key and self._energy_day_key != _day_now:
            await self._persist_energy_acc()
        # v1.9.1 I9: retry restore if startup restore was skipped/failed
        if not self._energy_day_key and self.db is not None:
            await self._restore_energy_acc()
        if not self._runtime_day_key and self.db is not None:
            await self._restore_runtime_acc()
        self._maybe_reset_daily_accumulators(now)
        try:
            state = self.hass.states.get(self.source_entity)
            if state is None:
                return snap
            custom_map = (
                self.options.get("custom_attribute_map")
                or self.entry.data.get("custom_attribute_map")
                or self.entry.data.get("attribute_map")
            )
            attrs = read(state, custom_map=custom_map)
            snap.attrs = attrs
            snap.missing_attrs = missing_required(attrs)
            snap.last_success_ts = now
            if snap.missing_attrs:
                # v1.12.1 (#109): freeze detector when source
                # publishes partial attrs. Post-restart ESPAltherma
                # may not be ready; advancing detector with empty
                # rps force-closes the running cycle -> phantom
                # ~60s off-gap -> short_off alert. last_success_ts
                # is intentionally NOT frozen so source_stale still
                # tracks real sensor liveness.
                _frozen = self.detector.snapshot()
                snap.state = self.detector.state
                snap.mode = _frozen.get("mode", "unknown")
                snap.cycle_start_ts = float(_frozen.get("start_ts") or 0.0)
                return snap
            self._track_setpoint(attrs)
            snap.power_w = self._read_power_w()
            snap.cop, _cop_src = self._read_cop_effective(now, attrs)
            snap.cop_source = _cop_src
            snap.electrical_power_w, snap.electrical_power_source = self._compute_electrical_power(now, attrs)
            # Hybrid (EVLQ) fields — issue #218
            _compat_hybrid = build_compat_view(attrs)
            snap.is_hybrid = self._is_hybrid_install()
            snap.boiler_active = _boiler_active_from_attrs(_compat_hybrid)
            snap.boiler_dhw_active = safe_bool(_compat_hybrid.get(ATTR_BOILER_DHW_DEMAND))
            snap.boiler_heat_active = _boiler_heat_active_from_attrs(_compat_hybrid)
            snap.hybrid_mode = _hybrid_mode_from_attrs(_compat_hybrid)
            snap.boiler_efficiency_cop = _boiler_efficiency_cop_from_attrs(_compat_hybrid)
            snap.inv_freq_secondary = _secondary_rps_from_attrs(_compat_hybrid)
            snap.setpoint_oscillating = self._compute_setpoint_oscillating()
            prev_detector_state = self.detector.state
            # R317: use unit-normalised power (kW->W) so the fallback
            # threshold compares in watts regardless of source sensor unit.
            record = self.detector.update(
                attrs, now=now, power_w=self._read_power_w(),
                boiler_active=snap.boiler_active,
                boiler_heat_active=snap.boiler_heat_active,
                boiler_dhw_active=snap.boiler_dhw_active,
            )
            if self.detector.state != prev_detector_state:
                await self._persist_detector_state()
            self._accumulate_cycle_samples(attrs)
            if record is not None:
                # v1.12.0 (#105): classify transient before scoring/insert
                record["is_transient"] = int(_classify_transient(record))
                score_and_count(record, self.options, self.store, now)
                self.store.add_cycle(record)
                snap.last_record = record
                await self._process_new_cycle(record, snap)
            snap.state = self.detector.state
            snap.mode = self.detector.snapshot().get("mode", "unknown")
            snap.cycle_start_ts = float(
                self.detector.snapshot().get("start_ts") or 0.0
            )
            self._tick_buh_and_defrost(attrs, now)
            self._tick_energy(
                attrs, now,
                mode=snap.mode,
                power_w=snap.power_w,
                cop=snap.cop,
            )
            await self._maybe_persist_accumulators(now)
            await self._maybe_collect_cop_sample(now)
            await self._refresh_cop_today(now)
            await self._maybe_refresh_stooklijn(now)
            await self._maybe_refresh_cop_hourly(now)
            await self._maybe_refresh_cop_degradation(now)
            await self._maybe_refresh_spf(now)
            snap.cop_today = self._cop_today_heating_cache
            snap.cop_combined_today = self._cop_today_cache
            snap.spf_state = self._spf_state_cache
            snap.cop_hourly_day = self._cop_hourly_cache.get("day", {})
            snap.cop_hourly_week = self._cop_hourly_cache.get("week", {})
            snap.cop_hourly_month = self._cop_hourly_cache.get("month", {})
            snap.cop_curve_recent = self._cop_hourly_cache.get(
                "curve_recent", {}
            )
            _deg = self._cop_degradation_cache.get("degradation", {})
            _tr = self._cop_degradation_cache.get("trend", {})
            snap.cop_degradation_status = _deg.get("severity", "none")
            snap.cop_degradation_week_pct = _deg.get("week_pct")
            snap.cop_trend_30d = _tr.get("trend_30d")
            snap.cop_degradation_detail = _deg
            snap.cop_trend_detail = _tr
            snap.stooklijn_advies = self._stooklijn_cache
            snap.errors_total = self._errors_total
            await self._refresh_datasheet_state(
                now,
                _safe_float_opt(self._stooklijn_cache.get("huidige_lwt")),
                self._resolve_outdoor_temp(snap),
                snap.cop,
            )
            snap.datasheet = self._datasheet_cache.get("datasheet")
            snap.datasheet_model = self._datasheet_cache.get("model")
            snap.cop_normalized_a7w35 = self._datasheet_cache.get(
                "cop_normalized_a7w35"
            )
            snap.cop_vs_datasheet_pct = self._datasheet_cache.get(
                "cop_vs_datasheet_pct"
            )
            await self._async_dispatch_alerts(snap)
            await async_check_repairs(
                self.hass, self.entry.entry_id, snap, self
            )
        except Exception as err:
            snap.errors = 1
            self._errors_total += 1
            snap.errors_total = self._errors_total
            _LOGGER.exception("Coordinator update failed: %s", err)
        return snap

    @property
    def daily_summary_recent(self) -> dict[str, Any] | None:
        """v1.7.1: cached recent daily-summary payload (public)."""
        return self._daily_summary_recent

    async def _refresh_daily_summary_recent(self) -> None:
        """v1.7.1: refresh cached recent daily-summary payload (all days)."""
        if self.db is None:
            return
        try:
            rows = await self.db.async_daily_summary(days=36500)
        except Exception:
            _LOGGER.exception("daily_summary recent refresh failed")
            return
        self._daily_summary_recent = _compute_daily_summary_recent(rows)

    @property
    def runtime_snapshot(self) -> dict[str, float]:
        """Read-only snapshot of runtime/BUH/defrost accumulators (R216)."""
        return {
            "buh_step1_s": self._buh_step1_s,
            "buh_step2_s": self._buh_step2_s,
            "defrost_count": float(self._defrost_count_today),
            "defrost_duration_s": self._defrost_duration_s,
            "last_defrost_ts": self._last_defrost_ts,
        }

    @property
    def energy_snapshot(self) -> dict[str, dict[str, float]]:
        """Read-only snapshot of energy accumulators (R216).

        v1.11.3: returns the high-water-mark, not the live accumulator.
        Guarantees the total_increasing contract the recorder enforces:
        a value reported once must never be reported lower within the
        same day. The live accumulator can transiently dip (e.g. a
        throttled DB persist being restored over a newer in-memory value),
        but the HWM never does. Day rollover resets both together, which
        the recorder correctly interprets as a new accumulation period.
        """
        self._ensure_energy_acc()  # guarantees _energy_hwm exists too
        return {mode: dict(vals) for mode, vals in self._energy_hwm.items()}

    def _ensure_energy_acc(self) -> dict[str, dict[str, float]]:
        """Return the instance-owned energy accumulator dict.

        Lazy-init: needed because __new__-based tests skip __init__.
        Without this, _tick_energy would mutate a class-shared dict.

        v1.11.3: also lazy-inits _energy_hwm (high-water-mark) so
        __new__-based tests and restored-from-DB paths always have it.
        """
        acc = self.__dict__.get("_energy_acc")
        if acc is None:
            acc = {
                "heating": {"th": 0.0, "el": 0.0},
                "dhw":     {"th": 0.0, "el": 0.0},
                "cooling": {"th": 0.0, "el": 0.0},
            }
            self._energy_acc = acc
        hwm = self.__dict__.get("_energy_hwm")
        if hwm is None:
            self._energy_hwm = {
                "heating": {"th": 0.0, "el": 0.0},
                "dhw":     {"th": 0.0, "el": 0.0},
                "cooling": {"th": 0.0, "el": 0.0},
            }
        return acc

    def _maybe_reset_daily_accumulators(self, now: float) -> None:
        """Reset runtime + energy accumulators on local-day boundary.

        Persist-before-reset is done by _async_update_data.
        Throttled persist after each tick via _maybe_persist_accumulators.
        """
        day = time.strftime("%Y-%m-%d", time.localtime(float(now)))
        # I8: decoupled gates — runtime and energy resets are independent so
        # that a failed restore in one subsystem cannot wipe the other.
        if self._runtime_day_key != day:
            self._runtime_day_key = day
            self._buh_step1_s = 0.0
            self._buh_step2_s = 0.0
            self._prev_defrost = False
            self._defrost_start_ts = None
            self._defrost_count_today = 0
            self._defrost_duration_s = 0.0
        if self._energy_day_key != day:
            self._energy_day_key = day
            self._energy_acc = {
                "heating": {"th": 0.0, "el": 0.0},
                "dhw":     {"th": 0.0, "el": 0.0},
                "cooling": {"th": 0.0, "el": 0.0},
            }
            self._energy_hwm = {
                "heating": {"th": 0.0, "el": 0.0},
                "dhw":     {"th": 0.0, "el": 0.0},
                "cooling": {"th": 0.0, "el": 0.0},
            }

    async def _persist_runtime_acc(self) -> None:
        """Persist runtime accumulators to model_state. Never raises.

        v1.9.1 I9: self-healing guard. Same rationale as _persist_energy_acc.
        """
        if self.db is None or not self._runtime_day_key:
            return
        try:
            existing = await self.db.async_get_model_state(
                f"runtime_acc.{self._runtime_day_key}"
            )
            if (
                isinstance(existing, dict)
                and existing.get("day") == self._runtime_day_key
            ):
                db_total = (
                    float(existing.get("buh_step1_s") or 0.0)
                    + float(existing.get("buh_step2_s") or 0.0)
                    + float(existing.get("defrost_duration_s") or 0.0)
                )
                mem_total = (
                    self._buh_step1_s
                    + self._buh_step2_s
                    + self._defrost_duration_s
                )
                if db_total > mem_total and db_total > 0.0:
                    _LOGGER.warning(
                        "runtime_acc: refusing overwrite (db=%.1fs > mem=%.1fs); restoring from DB",
                        db_total, mem_total,
                    )
                    self._buh_step1_s = float(existing.get("buh_step1_s", 0.0))
                    self._buh_step2_s = float(existing.get("buh_step2_s", 0.0))
                    self._defrost_count_today = int(existing.get("defrost_count", 0))
                    self._defrost_duration_s = float(
                        existing.get("defrost_duration_s", 0.0)
                    )
                    self._last_defrost_ts = float(
                        existing.get("last_defrost_ts", 0.0)
                    )
                    return
            await self.db.async_set_model_state(
                f"runtime_acc.{self._runtime_day_key}",
                {
                    "day": self._runtime_day_key,
                    "buh_step1_s": self._buh_step1_s,
                    "buh_step2_s": self._buh_step2_s,
                    "defrost_count": self._defrost_count_today,
                    "defrost_duration_s": self._defrost_duration_s,
                    "last_defrost_ts": self._last_defrost_ts,
                },
            )
        except Exception:
            _LOGGER.exception("runtime_acc persist failed")

    async def _persist_energy_acc(self) -> None:
        """Persist energy accumulators to model_state. Never raises.

        v1.9.1 I9: self-healing guard. If the DB already contains a higher
        total than memory (typically after a failed restore zeroed memory
        but the DB still holds real data), restore from DB instead of
        overwriting. Prevents the boot-wipe loop where every restart
        silently destroys the day's accumulated energy.
        """
        self._ensure_energy_acc()  # guarantees _energy_hwm on __new__-tests
        if self.db is None or not self._energy_day_key:
            return
        try:
            existing = await self.db.async_get_model_state(
                f"energy_acc.{self._energy_day_key}"
            )
            if (
                isinstance(existing, dict)
                and existing.get("day") == self._energy_day_key
            ):
                db_total = sum(
                    float(existing.get(f"{m}_{k}_kwh") or 0.0)
                    for m in ("heating", "dhw", "cooling")
                    for k in ("th", "el")
                )
                mem_total = sum(
                    self._energy_acc[m][k]
                    for m in ("heating", "dhw", "cooling")
                    for k in ("th", "el")
                )
                if db_total > mem_total and db_total > 0.0:
                    _LOGGER.warning(
                        "energy_acc: refusing overwrite (db=%.4f > mem=%.4f); restoring from DB",
                        db_total, mem_total,
                    )
                    self._energy_acc = {
                        m: {
                            "th": float(existing.get(f"{m}_th_kwh") or 0.0),
                            "el": float(existing.get(f"{m}_el_kwh") or 0.0),
                        }
                        for m in ("heating", "dhw", "cooling")
                    }
                    for m in ("heating", "dhw", "cooling"):
                        for k in ("th", "el"):
                            loaded_hwm = float(
                                existing.get(f"{m}_{k}_hwm_kwh") or 0.0
                            )
                            self._energy_hwm[m][k] = max(
                                self._energy_hwm[m][k],
                                loaded_hwm,
                                self._energy_acc[m][k],
                            )
                    return
            payload: dict[str, Any] = {"day": self._energy_day_key}
            for mode in ("heating", "dhw", "cooling"):
                payload[f"{mode}_th_kwh"] = self._energy_acc[mode]["th"]
                payload[f"{mode}_el_kwh"] = self._energy_acc[mode]["el"]
                payload[f"{mode}_th_hwm_kwh"] = self._energy_hwm[mode]["th"]
                payload[f"{mode}_el_hwm_kwh"] = self._energy_hwm[mode]["el"]
            await self.db.async_set_model_state(
                f"energy_acc.{self._energy_day_key}", payload
            )
        except Exception:
            _LOGGER.exception("energy_acc persist failed")

    async def _restore_runtime_acc(self) -> bool:
        """R310: rehydrate runtime accumulators. Never raises."""
        if self.db is None:
            return False
        try:
            today = time.strftime("%Y-%m-%d", time.localtime(time.time()))
            payload = await self.db.async_get_model_state(
                f"runtime_acc.{today}"
            )
            if not isinstance(payload, dict):
                _LOGGER.warning(
                    "runtime_acc restore: payload not dict (type=%s)",
                    type(payload).__name__,
                )
                return False
            if payload.get("day") != today:
                _LOGGER.warning(
                    "runtime_acc restore: day mismatch (db=%s today=%s)",
                    payload.get("day"), today,
                )
                return False
            self._buh_step1_s = float(payload.get("buh_step1_s", 0.0))
            self._buh_step2_s = float(payload.get("buh_step2_s", 0.0))
            self._defrost_count_today = int(payload.get("defrost_count", 0))
            self._defrost_duration_s = float(
                payload.get("defrost_duration_s", 0.0)
            )
            self._last_defrost_ts = float(
                payload.get("last_defrost_ts", 0.0)
            )
            self._runtime_day_key = today
            _LOGGER.info(
                "runtime_acc restored: day=%s buh_s1=%.1f buh_s2=%.1f defrost_n=%d",
                today, self._buh_step1_s, self._buh_step2_s,
                self._defrost_count_today,
            )
            return True
        except Exception:
            _LOGGER.exception("runtime_acc restore failed")
            return False

    async def _maybe_backfill_daily_summary(self) -> None:
        """v1.7.0: one-shot backfill of daily_summary on startup."""
        if self.db is None:
            return
        try:
            await self.db.async_backfill_daily_summary()
        except Exception:
            _LOGGER.exception("daily_summary backfill failed")
            return
        await self._refresh_daily_summary_recent()

    async def _restore_energy_acc(self) -> bool:
        """R310: rehydrate energy accumulators. Never raises."""
        if self.db is None:
            return False
        try:
            # v1.11.3: guarantees _energy_hwm exists even on __new__-based
            # tests (which skip __init__). Same lazy-init pattern as
            # _ensure_energy_acc for _energy_acc itself.
            self._ensure_energy_acc()
            today = time.strftime("%Y-%m-%d", time.localtime(time.time()))
            payload = await self.db.async_get_model_state(
                f"energy_acc.{today}"
            )
            if not isinstance(payload, dict):
                _LOGGER.warning(
                    "energy_acc restore: payload not dict (type=%s)",
                    type(payload).__name__,
                )
                return False
            if payload.get("day") != today:
                _LOGGER.warning(
                    "energy_acc restore: day mismatch (db=%s today=%s)",
                    payload.get("day"), today,
                )
                return False
            loaded = {
                "heating": {
                    "th": float(payload.get("heating_th_kwh", 0.0)),
                    "el": float(payload.get("heating_el_kwh", 0.0)),
                },
                "dhw": {
                    "th": float(payload.get("dhw_th_kwh", 0.0)),
                    "el": float(payload.get("dhw_el_kwh", 0.0)),
                },
                "cooling": {
                    "th": float(payload.get("cooling_th_kwh", 0.0)),
                    "el": float(payload.get("cooling_el_kwh", 0.0)),
                },
            }
            same_day = (self._energy_day_key == today)
            for m in ("heating", "dhw", "cooling"):
                for k in ("th", "el"):
                    if same_day:
                        # v1.11.3: merge, never lower. DB is up to 300s stale.
                        self._energy_acc[m][k] = max(
                            self._energy_acc[m][k], loaded[m][k]
                        )
                    else:
                        self._energy_acc[m][k] = loaded[m][k]
                    loaded_hwm = float(
                        payload.get(f"{m}_{k}_hwm_kwh") or 0.0
                    )
                    if same_day:
                        self._energy_hwm[m][k] = max(
                            self._energy_hwm[m][k], loaded_hwm
                        )
                    else:
                        self._energy_hwm[m][k] = loaded_hwm
                    if self._energy_acc[m][k] > self._energy_hwm[m][k]:
                        self._energy_hwm[m][k] = self._energy_acc[m][k]
            self._energy_day_key = today
            _LOGGER.info(
                "energy_acc restored: day=%s heating_el=%.3f heating_th=%.3f dhw_el=%.3f dhw_th=%.3f",
                today,
                self._energy_acc["heating"]["el"],
                self._energy_acc["heating"]["th"],
                self._energy_acc["dhw"]["el"],
                self._energy_acc["dhw"]["th"],
            )
            return True
        except Exception:
            _LOGGER.exception("energy_acc restore failed")
            return False

    async def _maybe_persist_accumulators(self, now: float) -> None:
        """Persist runtime + energy accumulators throttled at 30s.

        Called from _async_update_data after each tick. Without this,
        accumulators are lost on HA restart (C5a known gap).

        v1.12.0: interval reduced 300s -> 30s to align with the tick.
        Bounds hard-crash loss to at most one tick instead of up to
        five minutes. Write amplification is negligible in WAL mode.
        """
        interval = ENERGY_PERSIST_INTERVAL_S
        if (now - self._last_runtime_persist_ts) >= interval:
            await self._persist_runtime_acc()
            self._last_runtime_persist_ts = now
        if (now - self._last_energy_persist_ts) >= interval:
            await self._persist_energy_acc()
            self._last_energy_persist_ts = now

    def _tick_buh_and_defrost(self, attrs: dict[str, Any], now: float) -> None:
        """Accumulate BUH-runtime + defrost-events for one tick. Never raises."""
        try:
            last = self._last_runtime_tick_ts or now
            raw_dt = now - last
            dt_s = max(0.0, min(raw_dt, ENERGY_DT_CAP_S))
            self._last_runtime_tick_ts = now
            if raw_dt > ENERGY_DT_WARN_S:
                _LOGGER.warning(
                    "buh tick gap %.1fs exceeds %.0fs threshold; capped at %.0fs",
                    raw_dt, ENERGY_DT_WARN_S, ENERGY_DT_CAP_S,
                )
            if dt_s <= 0.0:
                return
            s1 = attrs.get(ATTR_BUH_STEP1)
            s2 = attrs.get(ATTR_BUH_STEP2)
            if s1 is True:
                self._buh_step1_s += dt_s
            if s2 is True:
                self._buh_step2_s += dt_s
            defrost_on = attrs.get(ATTR_DEFROST_OPERATION) is True
            if defrost_on and not self._prev_defrost:
                self._defrost_count_today += 1
                self._defrost_start_ts = now
                self._last_defrost_ts = now
            elif not defrost_on and self._prev_defrost:
                if self._defrost_start_ts is not None:
                    dur = max(0.0, now - self._defrost_start_ts)
                    self._defrost_duration_s += dur
                self._defrost_start_ts = None
            elif defrost_on and self._defrost_start_ts is not None:
                # Running tally while defrost continues (live view).
                dur = max(0.0, now - self._defrost_start_ts)
                # Not accumulated twice: value is recomputed not summed.
                self._defrost_duration_s = max(
                    self._defrost_duration_s, dur
                )
            self._prev_defrost = defrost_on
        except Exception:
            _LOGGER.exception("BUH/defrost tick failed")

    def _tick_energy(
        self,
        attrs: dict[str, Any],
        now: float,
        mode: str,
        power_w: float | None,
        cop: float | None,
    ) -> None:
        """Accumulate thermal + electrical kWh for one tick. Never raises.

        R286: skip standby/idle/cooldown. Only count ticks where the compressor
        is running or the BUH is active, to prevent standby power (e.g. 21 W
        controller draw) from being booked as heating consumption.

        R287: no fallback to "heating" for unknown modes. Unknown means the
        detector has not classified the cycle yet; those ticks are skipped.
        """
        try:
            last = self._last_energy_tick_ts or now
            raw_dt = now - last
            dt_s = max(0.0, min(raw_dt, ENERGY_DT_CAP_S))
            self._last_energy_tick_ts = now
            if raw_dt > ENERGY_DT_WARN_S:
                _LOGGER.warning(
                    "energy tick gap %.1fs exceeds %.0fs threshold; capped at %.0fs",
                    raw_dt, ENERGY_DT_WARN_S, ENERGY_DT_CAP_S,
                )
            if dt_s <= 0.0:
                return
            if mode not in ("heating", "dhw", "cooling"):
                return
            try:
                compressor_on = self.detector.state == "running"
            except Exception:
                compressor_on = False
            buh_on = (
                attrs.get(ATTR_BUH_STEP1) is True
                or attrs.get(ATTR_BUH_STEP2) is True
            )
            if not (compressor_on or buh_on):
                return
            m = mode
            kw_th, _src = _compute_thermal_power_live(
                power_w=power_w,
                cop=cop,
                flow_lmin=_flow_from_attrs(attrs),
                dt_k=_dt_from_attrs(attrs),
                rps=_rps_from_attrs(attrs),
                mode=m,
            )
            if kw_th is None:
                # R286b: BUH-only fallback — BUH is resistive, treat as
                # 100 percent efficient electrical-to-thermal for the
                # electrical accumulator only. Skip thermal to avoid mixing
                # with compressor COP-derived values.
                if buh_on and power_w is not None and power_w > 0.0:
                    acc = self._ensure_energy_acc()
                    acc[m]["el"] += (power_w / 1000.0) * dt_s / 3600.0
                return
            kw_el: float | None = None
            if power_w is not None and power_w > 0.0:
                kw_el = power_w / 1000.0
            elif cop is not None and cop > 0.0:
                kw_el = kw_th / cop
            acc = self._ensure_energy_acc()
            acc[m]["th"] += kw_th * dt_s / 3600.0
            if acc[m]["th"] > self._energy_hwm[m]["th"]:
                self._energy_hwm[m]["th"] = acc[m]["th"]
            if kw_el is not None:
                acc[m]["el"] += kw_el * dt_s / 3600.0
                if acc[m]["el"] > self._energy_hwm[m]["el"]:
                    self._energy_hwm[m]["el"] = acc[m]["el"]
        except Exception:
            _LOGGER.exception("energy tick failed")

    def _accumulate_cycle_samples(self, attrs: dict[str, Any]) -> None:
        """Add LWT + indoor temp to running sums while cycle is active."""
        try:
            is_active = self.detector.state != "idle"
        except Exception:
            return
        if not is_active:
            return
        lwt = None
        for k in ("lwt", "leaving_water_temp", "leaving_temp", "R2T"):
            v = attrs.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                lwt = float(v)
                break
        if lwt is not None:
            self._cycle_lwt_sum += lwt
            self._cycle_lwt_count += 1
        if self.indoor_temp_entity:
            st = self.hass.states.get(self.indoor_temp_entity)
            if st is not None:
                try:
                    v = float(st.state)
                    self._cycle_indoor_sum += v
                    self._cycle_indoor_count += 1
                except (TypeError, ValueError):
                    _LOGGER.debug("indoor cast failed", exc_info=True)


        cop = self._read_cop()
        if cop is None or cop <= 0.0:
            return
        power_w = self._read_power_w()
        if power_w is not None and power_w > 0.0:
            weight = power_w
        else:
            weight = 1.0
        self._cycle_cop_w_sum += cop * weight
        self._cycle_cop_weight_sum += weight
        self._cycle_cop_sq_w_sum += (cop * cop) * weight
        self._cycle_cop_count += 1
    async def _collect_cycle_averages(
        self, record: dict[str, Any]
    ) -> tuple[float | None, float | None, float | None]:
        """Return (cop_avg, lwt_avg, indoor_temp_avg) for a closed cycle.

        v1.12.5 #133: cop_sample_count = real COUNT(*) from cop_samples,
        mode-filtered. cop_avg remains power-weighted from live ticks
        (thermodynamically correct: sum Q / sum P over cycle). Falls
        back to DB AVG only when no live ticks are available.
        """
        lwt_avg: float | None = None
        if self._cycle_lwt_count > 0:
            lwt_avg = self._cycle_lwt_sum / float(self._cycle_lwt_count)
        indoor_avg: float | None = None
        if self._cycle_indoor_count > 0:
            indoor_avg = self._cycle_indoor_sum / float(self._cycle_indoor_count)
        self._cycle_lwt_sum = 0.0
        self._cycle_lwt_count = 0
        self._cycle_indoor_sum = 0.0
        self._cycle_indoor_count = 0

        pw_avg, pw_stdev = _weighted_mean_stdev(
            self._cycle_cop_w_sum,
            self._cycle_cop_weight_sum,
            self._cycle_cop_sq_w_sum,
        )
        tick_count = self._cycle_cop_count
        self._cycle_cop_w_sum = 0.0
        self._cycle_cop_weight_sum = 0.0
        self._cycle_cop_sq_w_sum = 0.0
        self._cycle_cop_count = 0

        # v1.12.5 #133: real DB count (mode-filtered) replaces tick counter
        db_avg: float | None = None
        db_count: int | None = None
        start_ts = record.get("start_ts")
        end_ts = record.get("end_ts")
        mode = record.get("mode")
        if (
            self.db is not None
            and isinstance(start_ts, (int, float))
            and isinstance(end_ts, (int, float))
            and isinstance(mode, str)
        ):
            try:
                db_avg, db_count = await self.db._sample_aggregates(
                    float(start_ts), float(end_ts), mode=mode
                )
            except Exception:
                _LOGGER.debug(
                    "sample_aggregates failed for cycle close", exc_info=True
                )

        if pw_avg is not None:
            cop_avg: float | None = pw_avg
            cop_stdev: float | None = pw_stdev
        elif db_avg is not None:
            cop_avg = db_avg
            cop_stdev = None
        else:
            cop_avg = None
            cop_stdev = None

        if db_count is not None:
            cop_sample_count: int | None = db_count if db_count > 0 else None
        elif tick_count > 0:
            cop_sample_count = tick_count
        else:
            cop_sample_count = None

        cop_avg, _cop_conf = _apply_cop_sanity_gate(
            cop_avg, cop_sample_count, cycle_id=record.get("id")
        )
        record["cop_avg"] = cop_avg
        record["cop_sample_count"] = cop_sample_count
        record["cop_sample_stdev"] = cop_stdev
        record["cop_confidence"] = _cop_conf
        return cop_avg, lwt_avg, indoor_avg

    # ---------- Batch 7c ML pipeline ----------
    async def _process_new_cycle(
        self, record: dict[str, Any], snap: DataSnapshot
    ) -> None:
        """Update baseline, detect anomaly, generate advice, persist."""
        # v1.6.0-C6a: clamp duration to guard ML/DB against clock jumps.
        _raw_dur = record.get("duration_s")
        if _raw_dur is not None:
            _max_min = int(self.options.get("max_cycle_duration_min", 240))
            record["duration_s"] = _clamp_duration(_raw_dur, _max_min)
        cop_avg, lwt_avg, indoor_avg = await self._collect_cycle_averages(
            record
        )

        # v1.12.0 (#103): DB-first persist. Cycle row must be durable
        # BEFORE the ML pipeline runs. Pre-v1.12.0 the cycle insert
        # happened AFTER ML, so any ML exception or slow await widened
        # the crash-loss window for this cycle.
        cid: int | None = None
        if self.db is not None:  # pragma: no branch
            try:
                cid = await self.db.async_insert_cycle(record)
            except Exception:
                _LOGGER.exception("DB persist cycle failed")
                cid = None

        # v1.12.9 (#131 PR-2): forward bridge-merge. If the just-inserted
        # cycle can be absorbed into a preceding same-mode non-transient
        # cycle (directly adjacent OR bridged over a transient, gap<120s),
        # fold it into the keeper and roll back the in-memory store entries.
        # Mirrors v18 R446b semantics on the live 30s hot path so the #131
        # pattern (189/190/191) cannot recur post-migration.
        if cid is not None and not record.get("is_transient"):
            try:
                absorbed = await self.db.async_merge_cycle_forward(cid)
                if absorbed > 0:
                    rolled = self.store.rollback_last_cycles(absorbed)
                    _LOGGER.debug(
                        "cycle %s forward-merged (%d deleted, %d rolled back)",
                        cid, absorbed, rolled,
                    )
                    return
            except Exception:
                _LOGGER.warning(
                    "forward merge failed for cycle %s",
                    cid, exc_info=True,
                )

        # v1.12.0 (#103): features block. Always includes thermal_kw_avg
        # so the stored feature vector matches the ML pipeline's view.
        # Pre-v1.12.0 this call was missing thermal_kw_avg, producing a
        # different feature row than ML saw — latent drift.
        if cid is not None:  # pragma: no branch
            try:
                vec = extract_feature_vector(
                    record,
                    cop_avg=cop_avg,
                    lwt_avg=lwt_avg,
                    indoor_temp_avg=indoor_avg,
                    thermal_kw_avg=record.get("thermal_kw_avg") or 0.0,
                )
                await self.db.async_insert_features(cid, vec)
                try:
                    cid_val = self._assign_cluster(vec)
                    if cid_val is not None:
                        snap.cluster_id = cid_val
                        await self.db.async_update_cycle_cluster(
                            cid, cid_val
                        )
                except Exception:
                    _LOGGER.warning(
                        "cluster assign failed", exc_info=True
                    )
            except Exception:
                _LOGGER.exception("DB features persist failed")

        # ML pipeline (best-effort, never blocks cycle durability).
        try:
            vector = extract_feature_vector(
                record,
                cop_avg=cop_avg,
                lwt_avg=lwt_avg,
                indoor_temp_avg=indoor_avg,
                thermal_kw_avg=record.get("thermal_kw_avg") or 0.0,
            )
            mode = record.get("mode") or snap.mode or "unknown"
            try:
                self.adaptive.observe_cycle(
                    mode,
                    record.get("duration_s"),
                    record.get("off_s"),
                )
            except Exception:
                _LOGGER.warning(
                    "adaptive observe_cycle failed", exc_info=True
                )
            per_mode = self.baseline.get(mode)
            if not record.get("is_transient"):
                # v1.12.0 (#105): skip baseline update on transients
                per_mode.update(vector)
            result = evaluate_anomaly(vector, per_mode, self.options)
            snap.anomaly = result
            if self.options.get("action_advice_enabled", True):
                snap.advice = generate_advice(
                    result, record, mode=snap.mode, options=self.options
                )
        except Exception:
            _LOGGER.exception("ML pipeline failed")

        # Daily rollup only when DB available (matches pre-v1.12.0
        # `if self.db is None: return` behaviour before rollup).
        if self.db is not None:  # pragma: no branch
            await self._maybe_rollup_day(record)

    async def _maybe_rollup_day(
        self, record: dict[str, Any]
    ) -> None:
        """v1.7.0: live daily-summary rollup on cycle close (idempotent)."""
        if not (self.options or {}).get(
            OPTION_DAILY_SUMMARY_LIVE_ENABLED, True
        ):
            return
        if self.db is None:
            return
        end_ts = record.get("end_ts")
        if not isinstance(end_ts, (int, float)):
            return
        try:
            day = time.strftime(
                "%Y-%m-%d", time.localtime(float(end_ts))
            )
            await self.db.async_rollup_day(day)
        except Exception:
            _LOGGER.exception("live daily rollup failed")
            return
        await self._refresh_daily_summary_recent()

    def _is_hybrid_install(self) -> bool:
        """True if the configured model belongs to the EVLQ hybrid family."""
        entry = getattr(self, 'entry', None)
        if entry is None:
            return False
        model = (getattr(entry, 'data', None) or {}).get("model", "")
        if not model:
            return False
        try:
            from .const import family_for_model
            return family_for_model(model) == "evlq"
        except Exception:
            return False

    def _boiler_kwargs_for_alerts(self) -> dict[str, Any]:
        """Return boiler_active / hp_running / boiler_dhw_active for evaluate_alerts.

        B4 fix (v1.15.0): previously the production dispatch path never
        passed these kwargs, so boiler-only alert suppression was silently
        a no-op (defaults False/True made 'boiler_active AND NOT hp_running'
        always False).

        DEFENSIVE: bool isinstance guards. bool(MagicMock()) is True, and
        bool(1) / bool("true") are True -- any truthy non-bool would silently
        suppress real HP-cycle alerts. Safety principle: NEVER silence alerts
        on an ambiguous signal. Only accept real booleans from the snapshot.
        Anything else (Mock, int, str, None) -> treated as inactive.
        """
        snap = getattr(self, 'data', None)
        if snap is None:
            return {
                "boiler_active": False,
                "hp_running": True,
                "boiler_dhw_active": False,
            }
        _ba = getattr(snap, 'boiler_active', False)
        _bd = getattr(snap, 'boiler_dhw_active', False)
        _st = getattr(snap, 'state', '')
        return {
            "boiler_active": _ba if isinstance(_ba, bool) else False,
            "hp_running": isinstance(_st, str) and _st == 'running',
            "boiler_dhw_active": _bd if isinstance(_bd, bool) else False,
        }

    async def _refresh_cop_today(self, now: float) -> None:
        if self.db is None:
            return
        try:
            rows = await self.db.async_fetch_cop_samples(days=1)
        except Exception:
            return
        if not isinstance(rows, list) or not rows:
            self._cop_today_cache = {}
            self._cop_today_heating_cache = {}
            return
        try:
            lt = time.localtime(now)
            today_start = time.mktime(
                (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
            )
            try:
                week = await self.db.async_fetch_cop_samples(days=7)
            except Exception:
                week = rows

            def _build(mode: str | None) -> dict[str, Any]:
                todays = [
                    r for r in rows
                    if isinstance(r.get('ts'), (int, float))
                    and float(r['ts']) >= today_start
                    and isinstance(r.get('cop'), (int, float))
                    and float(r['cop']) > 0.0
                    and not r.get('boiler_active')  # Issue #218: pure HP only
                    and (mode is None or r.get('mode') == mode)
                ]
                # Issue #218 (Block B): boiler contribution pct
                all_todays = [
                    r for r in rows
                    if isinstance(r.get('ts'), (int, float))
                    and float(r['ts']) >= today_start
                    and isinstance(r.get('cop'), (int, float))
                    and float(r['cop']) > 0.0
                    and (mode is None or r.get('mode') == mode)
                ]
                if not all_todays:
                    return {}  # no samples at all for this mode
                _boiler_n = sum(
                    1 for r in all_todays if r.get('boiler_active')
                )
                _boiler_pct = round(_boiler_n / len(all_todays) * 100.0, 1)
                if not todays:
                    # all samples were co-fire, no pure HP → boiler_pct only
                    return {'boiler_pct': _boiler_pct}
                cops = [float(r['cop']) for r in todays]
                avg = sum(cops) / len(cops)
                week_cops = [
                    float(r['cop']) for r in week
                    if isinstance(r.get('cop'), (int, float))
                    and float(r['cop']) > 0.0
                    and not r.get('boiler_active')  # pure HP only
                    and (mode is None or r.get('mode') == mode)
                ]
                base = sum(week_cops) / len(week_cops) if week_cops else avg
                loss = 0.0
                if base > 0:  # pragma: no branch
                    loss = round(max(0.0, (base - avg) / base * 100.0), 1)
                result = {
                    'cop': round(avg, 2),
                    'samples_today': len(cops),
                    'cop_min': round(min(cops), 2),
                    'cop_max': round(max(cops), 2),
                    'baseline_cop_verlies_pct': loss,
                }
                if self._is_hybrid_install():
                    result['boiler_pct'] = _boiler_pct
                return result

            self._cop_today_cache = _build(None)
            self._cop_today_heating_cache = _build('heating')
        except Exception:
            self._cop_today_cache = {}
            self._cop_today_heating_cache = {}

    async def _maybe_refresh_spf(self, now: float) -> None:
        """Refresh SPF state at most once per hour (or on cold start)."""
        if self.db is None:
            return
        last = self._spf_state_cache.get("updated_ts", 0) if self._spf_state_cache else 0
        if self._spf_state_cache and (now - float(last)) < 3600.0:
            return
        await self._refresh_spf_state(now)

    async def _refresh_spf_state(self, now: float) -> None:
        """Compute SPF / SCOP over season, YTD and rolling 365d windows.

        NOTE: SPF is defined per EN14825 as heat output / electric input.
        Without per-sample power data we approximate it by the arithmetic
        mean of per-sample COP values (same approach as cop_today).
        """
        if self.db is None:
            return
        try:
            opts = self.options or {}
            start_month = int(opts.get("season_start_month", 10))
            if not (1 <= start_month <= 12):
                start_month = 10
        except Exception:
            start_month = 10

        lt = time.localtime(now)
        season_year = lt.tm_year if lt.tm_mon >= start_month else lt.tm_year - 1
        season_start = time.mktime(
            (season_year, start_month, 1, 0, 0, 0, 0, 0, -1)
        )
        ytd_start = time.mktime((lt.tm_year, 1, 1, 0, 0, 0, 0, 0, -1))
        rolling_start = now - 365.0 * 86400.0

        async def _mean_since(start_ts: float) -> tuple[float | None, int]:
            try:
                rows = await self.db.async_fetch_cop_samples_between(start_ts, now)
            except Exception:
                return (None, 0)
            cops = [
                float(r["cop"]) for r in rows
                if isinstance(r.get("cop"), (int, float)) and float(r["cop"]) > 0.0
            ]
            if not cops:
                return (None, 0)
            return (round(sum(cops) / len(cops), 2), len(cops))

        spf_s, n_s = await _mean_since(season_start)
        spf_y, n_y = await _mean_since(ytd_start)
        spf_r, n_r = await _mean_since(rolling_start)

        self._spf_state_cache = {
            "season_start_month": start_month,
            "spf_season": spf_s, "spf_season_n": n_s,
            "spf_ytd": spf_y, "spf_ytd_n": n_y,
            "scop_365d": spf_r, "scop_365d_n": n_r,
            "updated_ts": now,
        }
        try:
            await self.db.async_set_model_state("spf_state", self._spf_state_cache)
        except Exception:
            _LOGGER.exception("spf_state write failed")

    async def async_reload_user_datasheets(self) -> None:
        """Reload user datasheet Store and rebuild merged view.

        Raises UserDatasheetError if the Store is corrupt or has an
        unsupported version. Caller (setup_entry or _refresh) decides
        whether to surface a Repair or fall back to bundled-only.
        """
        self._datasheet_user = await _load_user_datasheets(
            self.hass, self.entry.entry_id
        )
        _bundled = await asyncio.get_running_loop().run_in_executor(
            None, _load_bundled_datasheets
        )
        self._datasheet_merged = _merge_datasheets(
            _bundled, self._datasheet_user
        )
        self._datasheet_cache = {}
        self._datasheet_user_loaded = True

    @property
    def datasheet_sources(self) -> dict[str, str]:
        """Per-model origin: 'bundled' | 'user'. Public API (R216)."""
        out: dict[str, str] = {}
        for k, v in self._datasheet_merged.items():
            if isinstance(v, dict):
                out[k] = str(v.get("source", "bundled"))
        return out

    def _resolve_outdoor_temp(self, snap: Any) -> float | None:
        """Resolve outdoor temp with attr fallback for datasheet normalization.

        Primary: ``snap.last_record['outdoor_temp']``. Fallback:
        ``snap.attrs['R1T-Outdoor air temp.']`` (ESPAltherma raw key).
        Returns None if neither source has a usable value.
        """
        t_out = _safe_float_opt((snap.last_record or {}).get("outdoor_temp"))
        if t_out is None:
            raw_attrs = getattr(snap, "attrs", None) or {}
            t_out = _safe_float_opt(raw_attrs.get("R1T-Outdoor air temp."))
        return t_out

    async def _refresh_datasheet_state(
        self,
        now: float,
        lwt_now: float | None,
        t_out: float | None,
        cop_meas: float | None,
    ) -> None:
        """Compute datasheet-normalized COP (C3a) for the current tick."""
        if not self._datasheet_user_loaded:
            try:
                await self.async_reload_user_datasheets()
            except UserDatasheetError:
                _LOGGER.warning(
                    "user datasheet store unreadable; falling back to bundled"
                )
                self._datasheet_user = {}
                _bundled = await asyncio.get_running_loop().run_in_executor(
                    None, _load_bundled_datasheets
                )
                self._datasheet_merged = _merge_datasheets(_bundled, {})
                self._datasheet_user_loaded = True
        if not self._datasheet_defaults:
            self._datasheet_defaults = (
                await asyncio.get_running_loop().run_in_executor(
                    None, _load_datasheet_defaults
                )
            )
        try:
            model = self.entry.data.get("model", MODEL_BASISPROFIEL)
        except Exception:
            model = MODEL_BASISPROFIEL
        ds_raw = _get_datasheet(self._datasheet_merged, model)
        ds: dict[str, Any] | None = None
        if ds_raw is not None:
            defaults = self._datasheet_defaults
            lwt_max = ds_raw.get("lwt_max")
            buh_offset = defaults.get("buh_above_offset_c", -5)
            buh_above = (
                lwt_max + buh_offset
                if isinstance(lwt_max, (int, float))
                else None
            )
            ds = {
                **ds_raw,
                "model": model,
                "outdoor_min_c": defaults.get("outdoor_min_c"),
                "outdoor_max_c": defaults.get("outdoor_max_c"),
                "defrost_below_c": defaults.get("defrost_below_c"),
                "off_above_c": defaults.get("off_above_c"),
                "buh_above_c": buh_above,
            }
        out: dict[str, Any] = {
            "datasheet": ds,
            "cop_normalized_a7w35": None,
            "cop_vs_datasheet_pct": None,
            "model": model,
            "updated_ts": now,
        }
        if ds is None or cop_meas is None or lwt_now is None or t_out is None:
            self._datasheet_cache = out
            return
        ref = next(
            (pt for pt in ds["points"] if pt.get("label") == "A7/W35"),
            None,
        )
        if ref is None or float(ref.get("cop", 0)) <= 0:
            self._datasheet_cache = out
            return
        t_cond_ref = 35.0 + 5.0 + 273.15
        t_evap_ref = 7.0 - 8.0 + 273.15
        dT_ref = t_cond_ref - t_evap_ref
        t_cond_live = lwt_now + 5.0 + 273.15
        t_evap_live = t_out - 8.0 + 273.15
        dT_live = t_cond_live - t_evap_live
        if dT_live <= 0:
            self._datasheet_cache = out
            return
        cop_norm = cop_meas * (
            (t_cond_ref / dT_ref) / (t_cond_live / dT_live)
        )
        pct = ((cop_norm - float(ref["cop"])) / float(ref["cop"])) * 100.0
        out["cop_normalized_a7w35"] = round(cop_norm, 3)
        out["cop_vs_datasheet_pct"] = round(pct, 2)
        self._datasheet_cache = out

    async def _maybe_refresh_stooklijn(
        self, now: float, *, force: bool = False
    ) -> None:
        if self.db is None:
            return
        # 52b3: DHW-check FIRST -- must run before cache-check,
        # otherwise the 1-hour cache short-circuits the DHW skip.
        if not force:
            _data = getattr(self, 'data', None)
            _mode = getattr(_data, 'mode', None) if _data is not None else None
            if _mode == 'dhw':
                cache = getattr(self, '_stooklijn_cache', {})
                if cache.get('reason') != 'dhw_active':
                    self._stooklijn_cache = {
                        'state': 'no_data',
                        'reason': 'dhw_active',
                        'huidige_lwt': None,
                        'optimale_lwt': None,
                        'besparing_cop_pct': 0.0,
                        'comfort_impact': 0.0,
                        'betrouwbaarheid': 0.0,
                        'bucket': '',
                        'samples': 0,
                        'buckets': {},
                        'setpoint_lwt': None,
                        'doel_setpoint': None,
                        'step_c': 0,
                        'delta_c': 0.0,
                        'tracking_error': None,
                        'err_indoor': None,
                        'urgency': 0.0,
                        'comfort_cap': None,
                    }
                    self._stooklijn_cache_ts = now
                return
        cache_ts = getattr(self, '_stooklijn_cache_ts', 0.0)
        cache = getattr(self, '_stooklijn_cache', {})
        if not force and (now - cache_ts) < 3600.0 and cache:
            return
        try:
            rows = await self.db.async_fetch_cop_samples(days=30)
        except Exception:
            return
        if not isinstance(rows, list):
            return
        try:
            from .engine.cop_analyzer import (
                CopSample,
                analyze_stooklijn,
                bucket_summary,
            )
            samples: list[CopSample] = []
            for r in rows:
                if not isinstance(r.get('cop'), (int, float)):
                    continue
                if float(r['cop']) <= 0.0:
                    continue
                # Issue #218: heating curve only uses pure-HP samples
                if r.get('boiler_active'):
                    continue
                samples.append(CopSample(
                    cop=float(r['cop']),
                    lwt=r.get('lwt'),
                    outdoor=r.get('outdoor'),
                    flow_lmin=r.get('flow_lmin'),
                    defrost=False,
                    data_quality='Good',
                    power_stable=bool(r.get('power_stable')),
                    mode=str(r.get('mode') or 'unknown'),
                    ts=float(r.get('ts') or 0.0),
                ))
            from .const import ATTR_LW_SETPOINT, DEFAULT_COMFORT_MAX_C
            comfort_min = float(
                self.options.get('comfort_min_c', DEFAULT_COMFORT_MIN_C)
            )
            comfort_max = float(
                self.options.get('comfort_max_c', DEFAULT_COMFORT_MAX_C)
            )
            setpoint_lwt = None
            _snap = getattr(self, 'data', None)
            _attrs = getattr(_snap, 'attrs', None) if _snap is not None else None
            if isinstance(_attrs, dict):
                _sp = _attrs.get(ATTR_LW_SETPOINT)
                if isinstance(_sp, (int, float)):
                    setpoint_lwt = float(_sp)
            indoor_avg = None
            _ient = getattr(self, 'indoor_temp_entity', None)
            if _ient and self.hass is not None:
                try:
                    _st = self.hass.states.get(_ient)
                    if _st is not None and _st.state not in ('unknown', 'unavailable', ''):
                        indoor_avg = float(_st.state)
                except (TypeError, ValueError, AttributeError):
                    indoor_avg = None
            advies = analyze_stooklijn(
                samples,
                comfort_min=comfort_min,
                indoor_avg=indoor_avg,
                setpoint_lwt=setpoint_lwt,
                comfort_max=comfort_max,
            )
            buckets = bucket_summary(samples)
            self._stooklijn_cache = {
                'state': advies.state,
                'reason': advies.reason,
                'optimale_lwt': advies.optimale_lwt,
                'huidige_lwt': advies.huidige_lwt,
                'besparing_cop_pct': advies.besparing_cop_pct,
                'comfort_impact': advies.comfort_impact,
                'betrouwbaarheid': advies.betrouwbaarheid,
                'bucket': advies.bucket,
                'samples': advies.samples,
                'buckets': buckets,
                'setpoint_lwt': advies.setpoint_lwt,
                'doel_setpoint': advies.doel_setpoint,
                'step_c': advies.step_c,
                'delta_c': advies.delta_c,
                'tracking_error': advies.tracking_error,
                'err_indoor': advies.err_indoor,
                'urgency': advies.urgency,
                'comfort_cap': advies.comfort_cap,
                'offset_delta_c': advies.offset_delta_c,
                'slope_delta': advies.slope_delta,
            }
            self._stooklijn_cache_ts = now
        except Exception:
            return

    async def async_setup_stooklijn(self) -> None:
        if self._stooklijn_unsub is not None:
            return
        self._stooklijn_unsub = async_track_time_change(
            self.hass,
            self._async_stooklijn_callback,
            hour=4, minute=0, second=0,
        )
        _LOGGER.info('Stooklijn hook scheduled at 04:00 local')

    async def _async_stooklijn_callback(self, _now: Any) -> None:
        try:
            await self.async_run_stooklijn_analysis()
        except Exception:
            _LOGGER.exception('Scheduled stooklijn analysis failed')

    async def async_run_stooklijn_analysis(self) -> dict[str, Any]:
        if self.db is None:
            return {'ok': False, 'reason': 'no_db'}
        now = time.time()
        try:
            await self._maybe_refresh_stooklijn(now, force=True)
            await self._refresh_cop_today(now)
        except Exception:
            _LOGGER.exception('stooklijn refresh failed')
            return {'ok': False, 'reason': 'refresh_failed'}
        await self._maybe_notify_cop_low(now, self._cop_today_cache)
        await self._maybe_notify_stooklijn(now, self._stooklijn_cache)
        cache = self._stooklijn_cache or {}
        return {
            'ok': True,
            'state': cache.get('state', 'unknown'),
            'samples': cache.get('samples', 0),
        }

    async def _maybe_notify_cop_low(
        self, now: float, cop_today: dict[str, Any]
    ) -> None:
        if not isinstance(cop_today, dict) or not cop_today:
            return
        cop = cop_today.get('cop')
        if not isinstance(cop, (int, float)):
            return
        if float(cop) >= COP_LOW_THRESHOLD:
            return
        samples = cop_today.get('samples_today') or 0
        if samples < COP_LOW_MIN_SAMPLES:
            return
        if not passes_filters('cop_low', 'warning', self.options, now):
            return
        last = self._last_alert_sent.get('cop_low', 0.0)
        _cop_window_min = float(
            self.options.get('alert_agg_cop_low_min', 30)
        )
        if (now - last) < _cop_window_min * 60.0:
            return
        from types import SimpleNamespace

        from .engine.notification_engine import build_cop_low_message
        msg = build_cop_low_message(
            float(cop), int(samples),
            language=self.options.get('notification_language', 'en'),
            emoji_enabled=bool(self.options.get('notify_emoji_enabled', True)),
        )
        alert = SimpleNamespace(
            persistent=True,
            message=msg,
            notif_id='daikin_cop_low',
            alert_type='cop_low',
            context={
                "cop": float(cop),
                "samples": int(samples),
                "mode": self._resolve_cop_sample_mode(),
            },
        )
        try:
            await self._emit_alert(alert)
            self._last_alert_sent['cop_low'] = now
            self._schedule_alert_save()
        except Exception:
            _LOGGER.exception('cop_low notify failed')

    async def _maybe_notify_stooklijn(
        self, now: float, cache: dict[str, Any]
    ) -> None:
        if not isinstance(cache, dict) or not cache:
            return
        state = cache.get('state')
        if state not in ('lower_lwt', 'raise_lwt'):
            return
        try:
            betrouw = float(cache.get('betrouwbaarheid') or 0.0)
            besparing = float(cache.get('besparing_cop_pct') or 0.0)
            float(cache.get('comfort_impact') or 0.0)
        except (TypeError, ValueError):
            return
        if (betrouw < STOOKLIJN_MIN_CONFIDENCE
                or besparing < STOOKLIJN_MIN_SAVINGS_PCT):
            return
        if not passes_filters('stooklijn_advies', 'warning', self.options, now):
            return
        last = self._last_alert_sent.get('stooklijn_advies', 0.0)
        _stook_window_min = float(
            self.options.get('alert_agg_stooklijn_advies_min', 10080)
        )
        if (now - last) < _stook_window_min * 60.0:
            return
        from types import SimpleNamespace

        from .engine.notification_engine import build_stooklijn_message
        msg = build_stooklijn_message(
            cache,
            language=self.options.get('notification_language', 'en'),
            emoji_enabled=bool(self.options.get('notify_emoji_enabled', True)),
        )
        alert = SimpleNamespace(
            persistent=True,
            message=msg,
            notif_id='daikin_stooklijn',
            alert_type='stooklijn_advies',
        )
        try:
            await self._emit_alert(alert)
            self._last_alert_sent['stooklijn_advies'] = now
            self._schedule_alert_save()
        except Exception:
            _LOGGER.exception('stooklijn notify failed')

    def _resolve_cop_sample_mode(self) -> str:
        """Return mode string for cop_samples row.

        Bug I (batch 52b7): snap.mode is 'unknown' during active DHW cycles.
        Fall back to classify_mode(snap.attrs), which reads I/U operation mode.

        Issue #128: prefer detector.state when it is cycle-committed. The
        detector's state machine is cycle-aware and correctly tracks
        compound-mode DHW, while snap.mode remains 'unknown' through
        transition windows.
        """
        det = getattr(self, "detector", None)
        if det is not None:
            det_state = getattr(det, "state", None)
            if isinstance(det_state, str) and det_state in ("heating", "dhw"):
                return det_state
        data = getattr(self, 'data', None)
        if data is not None:
            raw = getattr(data, 'mode', None)
            if raw is not None:
                norm = str(raw).strip().lower()
                if norm and norm != 'unknown':
                    return norm
        attrs = getattr(data, 'attrs', None) if data is not None else None
        if attrs:
            # 52b7b: direct I/U lookup -- classify_mode gates on
            # compressor state and returns 'unknown' during DHW-off.
            for key in ('I/U operation mode', 'iu_operation_mode',
                        'ATTR_IU_OPERATION_MODE'):
                iu = attrs.get(key)
                if isinstance(iu, str):
                    n = iu.strip().lower()
                    if n in ('dhw', 'heating', 'cooling'):
                        return n
            try:
                from .engine.cycle_detector import classify_mode
                cm = classify_mode(attrs)
            except Exception:
                cm = 'unknown'
            if cm and cm != 'unknown':
                return cm
        return 'unknown'

    async def _maybe_collect_cop_sample(self, now: float) -> None:
        if self.db is None:
            return
        if not getattr(self, "_cop_sample_seed_done", False):
            self._cop_sample_seed_done = True
            try:
                last_ts = await self.db.async_get_max_cop_sample_ts()
                if last_ts is not None:
                    self._last_cop_sample_ts = float(last_ts)
                    _LOGGER.debug(
                        "cop_sample timer seeded from DB: last_ts=%.0f",
                        self._last_cop_sample_ts,
                    )
            except Exception as err:
                _LOGGER.debug(
                    "cop_sample seed failed (non-fatal): %s", err
                )
        interval = 300.0
        if (now - self._last_cop_sample_ts) < interval:
            return
        # v1.13.2 #196: source-driven COP sampling.
        # Old path read attrs from cop_sensor (a numeric template sensor
        # with no synthetic keys). Result: data_quality always 'unknown',
        # power_stable always False, so ALL samples rejected -- 0 rows on
        # fresh installs despite valid cycles. See issue #196.
        #
        # New path: read source ESPAltherma attrs via build_compat_view,
        # overlay COP value from cop_sensor (its only job), fall back to
        # self.data.cop. Legacy fallback preserved for callers without
        # source attrs (tests, edge cases).
        raw = None
        cop_attrs: dict[str, Any] = {}
        data_obj = getattr(self, 'data', None)
        if self.cop_sensor_entity:
            st = self.hass.states.get(self.cop_sensor_entity)
            if st is not None:
                sv = st.state
                if sv not in (None, 'unknown', 'unavailable', '', '0.0', '0'):
                    raw = sv
                    cop_attrs = dict(st.attributes or {})
        if raw is None:
            dc = getattr(data_obj, 'cop', None) if data_obj is not None else None
            if dc is not None:
                try:
                    _fv = float(dc)
                    if _fv > 0.0:
                        raw = str(_fv)
                except (TypeError, ValueError):
                    pass
        if raw is None:
            return

        # Issue #218 (Block 3C.1): skip samples during boiler-only operation.
        # When the gas boiler is producing heat and the HP compressor is idle,
        # any COP reading on the source is stale (last HP cycle) — not a
        # valid HP-COP sample. Co-fire (HP on + boiler on) is allowed; the
        # boiler_contribution_samples field tracks co-fire separately.
        # R555 (M2 2b-2): isinstance guards — bool(MagicMock()) is True.
        # Only real booleans pass through. Truthy non-bool -> treated inactive.
        _ba = getattr(data_obj, 'boiler_active', False)
        _ba = _ba if isinstance(_ba, bool) else False
        _st = getattr(data_obj, 'state', '')
        _hp_on = isinstance(_st, str) and _st == 'running'
        if _ba and not _hp_on:
            return
        # M2 2b-2: derive granular mode from heat/dhw flags (isinstance-guarded).
        _bh = getattr(data_obj, 'boiler_heat_active', False)
        _bh = _bh if isinstance(_bh, bool) else False
        _bd = getattr(data_obj, 'boiler_dhw_active', False)
        _bd = _bd if isinstance(_bd, bool) else False
        if _bh and _bd:
            _boiler_mode = 'both'
        elif _bh:
            _boiler_mode = 'heat'
        elif _bd:
            _boiler_mode = 'dhw'
        else:
            _boiler_mode = ''

        source_attrs = getattr(data_obj, 'attrs', None) if data_obj is not None else None
        if not isinstance(source_attrs, dict):
            source_attrs = {}
        _r1t_before: float | None = None
        if source_attrs:
            compat = build_compat_view(source_attrs)
            mapped: dict[str, Any] = {'state': raw}
            _r1t_before = compat.get(
                'Leaving water temp. before BUH (R1T)'
            )
            _lwt = (
                compat.get('Leaving water temp. after BUH (R2T)')
                or compat.get('Leaving water temp. before BUH (R1T)')
            )
            if _lwt is not None:
                mapped['leaving_temp'] = _lwt
            _inlet = compat.get('Inlet water temp.(R4T)')
            if _inlet is not None:
                mapped['inlet_temp'] = _inlet
            _outdoor = compat.get('Outdoor air temp.(R1T)')
            if _outdoor is not None:
                mapped['outdoor_temperature'] = _outdoor
            _flow = compat.get('Flow sensor (l/min)')
            if _flow is not None:
                mapped['flow_rate'] = _flow
            _defrost = compat.get('Defrost Operation')
            if _defrost is not None:
                mapped['defrost_operation'] = _defrost
            if (
                mapped.get('leaving_temp') is not None
                and mapped.get('outdoor_temperature') is not None
            ):
                mapped['data_quality'] = 'Good'
            else:
                mapped['data_quality'] = 'Partial'
            # v1.13.2 hotfix: power_stable always True in source path.
            # Refine with self.data.power_w signal in v1.13.3 (#188 scope).
            mapped['power_stable'] = True
        else:
            # Legacy fallback: pre-v1.13.2 behavior for callers without
            # source attrs. Preserves test contracts.
            mapped = dict(cop_attrs)
            mapped['state'] = raw

        from .engine.cop_analyzer import parse_global_cop_attrs
        sample = parse_global_cop_attrs(mapped)
        if sample is None or sample.cop <= 0.0:
            return
        if sample.defrost:
            return
        if sample.data_quality != 'Good':
            return
        if not sample.power_stable:
            return
        _mode = self._resolve_cop_sample_mode()
        row = {
            'ts': now,
            'cop': sample.cop,
            'lwt': sample.lwt,
            'outdoor': sample.outdoor,
            'r1t': _r1t_before,
            'r4t': getattr(sample, 'inlet', None),
            'flow_lmin': sample.flow_lmin,
            'power_stable': True,
            'mode': str(_mode),
            'source': 'interval',
            'boiler_active': 1 if _ba else 0,
            'boiler_mode': _boiler_mode,
        }
        ok = await self.db.async_insert_cop_sample(row)
        if ok:
            self._last_cop_sample_ts = now

    # ---------- Batch 6b-3b alert dispatch ----------

    def _effective_threshold(self, key: str, default: int) -> int:
        """Return learned threshold when adaptive mode is enabled."""
        opts = self.options or {}
        if not opts.get("adaptive_thresholds_enabled", False):
            return default
        mode = getattr(self.data, "mode", None) or "unknown"
        try:
            learned = self.adaptive.suggest(mode)
        except Exception:
            return default
        return int(learned.get(key, default))

    async def async_save_adaptive_state(self) -> bool:
        if self.db is None:
            return False
        try:
            from .const import MODEL_STATE_ADAPTIVE
            await self.db.async_set_model_state(
                MODEL_STATE_ADAPTIVE, self.adaptive.to_dict()
            )
            return True
        except Exception:
            _LOGGER.exception("adaptive save failed")
            return False

    async def async_load_adaptive_state(self) -> bool:
        if self.db is None:
            return False
        try:
            from .const import MODEL_STATE_ADAPTIVE
            data = await self.db.async_get_model_state(MODEL_STATE_ADAPTIVE)
            if data:
                self.adaptive = AdaptiveThresholds.from_dict(data)
                return True
        except Exception:
            _LOGGER.exception("adaptive load failed")
        return False

    async def _async_flush_accumulators(self) -> None:
        """v1.12.0 (#104): best-effort flush of all accumulators.

        Called from async_unload_entry (before db.async_close) and
        _async_handle_shutdown (HA EVENT_HOMEASSISTANT_STOP).

        Each flush is isolated so one failure never blocks downstream
        (R378 pattern). Idempotent — safe to call twice if both the
        stop event and entry unload fire during shutdown.
        """
        for _name in (
            "_persist_runtime_acc",
            "_persist_energy_acc",
            "_persist_detector_state",
        ):
            try:
                await getattr(self, _name)()
            except Exception:
                _LOGGER.exception("flush %s failed", _name)

    async def _async_handle_shutdown(self, _event: Any = None) -> None:
        """v1.12.0 (#104): HA shutdown handler — flush all accumulators.

        Registered via entry.async_on_unload(hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, ...)) in async_setup_entry. Fires on
        graceful HA stop (OS reboot, docker stop, `ha core restart`).
        Does NOT close the DB — HA tears down the entry via unload.
        """
        _LOGGER.info("Daikin Cycle ML shutdown flush")
        _kbu = getattr(self, "_kmeans_backfill_unsub", None)
        if _kbu is not None:
            try:
                _kbu()
            except Exception:
                _LOGGER.debug(
                    "kmeans backfill cancel failed", exc_info=True
                )
            self._kmeans_backfill_unsub = None
        await self._async_flush_accumulators()

    async def _persist_detector_state(self) -> None:
        """Persist detector state to model_state. Never raises."""
        if self.db is None:
            return
        try:
            from .const import DETECTOR_STATE_KEY
            payload = self.detector.to_dict()
            await self.db.async_set_model_state(DETECTOR_STATE_KEY, payload)
        except Exception:
            _LOGGER.exception("detector state persist failed")

    async def _restore_detector_state(self) -> bool:
        """Restore detector state from model_state. Never raises."""
        if self.db is None:
            return False
        try:
            from .const import DETECTOR_STATE_KEY
            payload = await self.db.async_get_model_state(DETECTOR_STATE_KEY)
            if not payload:
                return False
            self.detector.restore_from_dict(payload, time.time())
            if self.detector.state == "running":
                snap = self.detector.snapshot()
                _LOGGER.info(
                    "Detector state restored: start_ts=%s mode=%s",
                    snap.get("start_ts"), snap.get("mode"),
                )
                return True
        except Exception:
            _LOGGER.exception("detector state restore failed")
        return False

    def _track_setpoint(self, attrs: dict[str, Any]) -> int:
        """Track LW-setpoint changes within a rolling window.

        Returns the number of changes currently inside the window.
        """
        if self._setpoint_history is None:
            self._setpoint_history = deque()
        from .const import (
            ATTR_LW_SETPOINT,
            DEFAULT_SETPOINT_OSC_MIN_DELTA,
            DEFAULT_SETPOINT_OSC_WINDOW_MIN,
        )
        raw = attrs.get(ATTR_LW_SETPOINT)
        val = None
        if raw is not None:
            try:
                val = float(raw)
            except (TypeError, ValueError):
                val = None

        try:
            window_min = int(self.options.get(
                "setpoint_osc_window_min",
                DEFAULT_SETPOINT_OSC_WINDOW_MIN,
            ))
        except (TypeError, ValueError):
            window_min = DEFAULT_SETPOINT_OSC_WINDOW_MIN
        if window_min <= 0:
            window_min = DEFAULT_SETPOINT_OSC_WINDOW_MIN

        try:
            min_delta = float(self.options.get(
                "setpoint_osc_min_delta",
                DEFAULT_SETPOINT_OSC_MIN_DELTA,
            ))
        except (TypeError, ValueError):
            min_delta = DEFAULT_SETPOINT_OSC_MIN_DELTA
        if min_delta <= 0:
            min_delta = DEFAULT_SETPOINT_OSC_MIN_DELTA

        now = time.time()
        if (val is not None and self._last_setpoint is not None
                and abs(val - self._last_setpoint) >= min_delta):
            self._setpoint_history.append((now, val))
        if val is not None:
            self._last_setpoint = val

        cutoff = now - (window_min * 60)
        hist = self._setpoint_history
        while hist and hist[0][0] < cutoff:
            hist.popleft()

        return len(hist)

    def _compute_setpoint_oscillating(self) -> bool:
        """Return True if setpoint changes in window exceed threshold."""
        from .const import DEFAULT_SETPOINT_OSC_THRESHOLD
        try:
            th = int(self.options.get(
                "setpoint_oscillation_threshold",
                DEFAULT_SETPOINT_OSC_THRESHOLD,
            ))
        except (TypeError, ValueError):
            th = DEFAULT_SETPOINT_OSC_THRESHOLD
        if th <= 0:
            th = DEFAULT_SETPOINT_OSC_THRESHOLD
        hist = self._setpoint_history
        if hist is None:
            return False
        if len(hist) < th:
            return False
        # Q4: require at least one direction reversal (sign flip of
        # consecutive deltas). Guards against slow monotonic drift.
        vals: list[float] = []
        for item in hist:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    vals.append(float(item[1]))
                except (TypeError, ValueError):
                    continue
        if len(vals) < th:
            return False
        for i in range(len(vals) - 2):
            d1 = vals[i + 1] - vals[i]
            d2 = vals[i + 2] - vals[i + 1]
            if (d1 > 0) != (d2 > 0):
                return True
        return False

    async def _refresh_7d_rollups(self) -> None:
        """PR E: refresh 7d aggregate cache (defrost count, BUH ratio).

        Never raises. On failure, cached values remain unchanged so a
        transient DB error does not silently disable the alerts.
        """
        _db = getattr(self, "db", None)
        if _db is None:
            return
        try:
            rows = await _db.async_daily_summary(days=7)
            self._defrost_7d_sum = sum(
                int(r.get("defrost_count", 0) or 0) for r in rows
            )
            try:
                _dds = await _db.async_defrost_duration_since(
                    time.time() - (7 * 86400)
                )
                self._defrost_7d_duration_s = float(_dds or 0.0)
            except Exception:
                _LOGGER.debug("defrost 7d duration failed", exc_info=True)
            _buh = sum(int(r.get("buh_count", 0) or 0) for r in rows)
            _cyc = sum(int(r.get("cycles", 0) or 0) for r in rows)
            self._buh_7d_count = _buh
            self._buh_7d_ratio = round(_buh / _cyc, 3) if _cyc > 0 else 0.0
            # I1: db_retention_warning cache (never raises here;
            # sub-helper swallows its own exceptions and returns
            # an empty dict on failure, leaving the previous cache in place)
            self._db_retention_stale = await self._compute_db_retention_stale()
            # I2: kmeans_retrain_stale cache (same pattern, helper swallows exceptions)
            self._kmeans_stale = await self._compute_kmeans_stale()
            # I6: finalize yesterday's baseline (before compute uses it)
            await self._persist_energy_baseline()
            # I6: energy_daily_anomaly cache (same pattern)
            self._energy_daily_anomaly = await self._compute_energy_daily_anomaly()
            self._avg_duration_7d_min = await self._compute_avg_duration_7d_min()
        except Exception:
            _LOGGER.exception("7d rollup refresh failed")

    async def _compute_db_retention_stale(self) -> dict[str, Any]:
        """I1: count rows past retention for db_retention_warning.

        Returns {} on failure or no DB, so a transient error leaves
        the previous cached state in place (alert stays suppressed
        rather than false-firing).
        """
        _db = getattr(self, "db", None)
        if _db is None:
            return {}
        try:
            opts = dict(self.options or {})
            alert_days = int(opts.get(
                "alert_retention_days", DEFAULT_ALERT_RETENTION_DAYS,
            ))
            cycle_days = int(opts.get(
                "cycle_retention_days", DEFAULT_CYCLE_RETENTION_DAYS,
            ))
            now = time.time()
            stale_alerts = await _db.async_count_alerts_before(
                now - alert_days * 86400.0
            )
            stale_cycles = await _db.async_count_cycles_before(
                now - cycle_days * 86400.0
            )
            return {
                "fired": (stale_alerts > 100) or (stale_cycles > 100),
                "stale_alerts": int(stale_alerts),
                "stale_cycles": int(stale_cycles),
                "alert_retention_days": alert_days,
                "cycle_retention_days": cycle_days,
            }
        except Exception:
            _LOGGER.exception("db_retention count failed")
            return {}

    async def _compute_kmeans_stale(self) -> dict[str, Any]:
        """I2: compute kmeans retrain staleness for kmeans_retrain_stale.

        Returns {} on failure or no DB, so a transient error leaves
        the previous cached state in place (alert stays suppressed
        rather than false-firing). Does not fire if last_ok_ts is
        absent (fresh install or legacy payload without I2 fields).
        """
        _db = getattr(self, "db", None)
        if _db is None:
            return {}
        try:
            data = await _db.async_get_model_state(
                "kmeans_state", default={}
            ) or {}
            if not isinstance(data, dict):
                return {}
            last_ok_ts = data.get("last_ok_ts")
            _failures_raw = data.get("consecutive_failures", 0)
            try:
                _failures_i = int(_failures_raw) if _failures_raw is not None else 0
            except (TypeError, ValueError):
                _failures_i = 0
            if last_ok_ts is None:
                return {
                    "fired": False,
                    "hours_since_ok": None,
                    "last_ok_ts": None,
                    "last_attempt_ts": data.get("last_attempt_ts"),
                    "consecutive_failures": _failures_i,
                    "last_failure_reason": data.get("last_failure_reason"),
                    "stale_after_days": KMEANS_STALE_AFTER_DAYS,
                }
            now = time.time()
            hours_since_ok = (now - float(last_ok_ts)) / 3600.0
            fired = hours_since_ok > KMEANS_STALE_AFTER_DAYS * 24
            return {
                "fired": fired,
                "hours_since_ok": round(hours_since_ok, 1),
                "last_ok_ts": float(last_ok_ts),
                "last_attempt_ts": data.get("last_attempt_ts"),
                "consecutive_failures": _failures_i,
                "last_failure_reason": data.get("last_failure_reason"),
                "stale_after_days": KMEANS_STALE_AFTER_DAYS,
            }
        except Exception:
            _LOGGER.exception("kmeans stale count failed")
            return {}

    async def _compute_energy_daily_anomaly(self) -> dict[str, Any]:
        """I6: compute today's electrical energy anomaly vs per-mode baseline.

        Always populates candidate fields (mode, today_el_kwh, baseline_el_mean,
        baseline_el_sigma, z_score, samples) from the most-relevant mode even
        when the alert does not fire, so Test-all and diagnostics show real
        current state instead of zeros.

        Display candidate = highest today_el_kwh.
        Fire candidate    = highest z-score among modes passing all gates
                            (n >= MIN_DAYS, sigma > 0, today_el >= FLOOR,
                            z > SIGMA_THRESHOLD).
        If a fire candidate exists, it drives the result and fired=True.
        Else the display candidate drives the result with fired=False.
        If no candidate at all (all energies corrupt), returns zero-dict.

        Returns {} on DB failure/no-DB so transient errors leave the
        previous cache in place (matches I1/I2 suppression pattern).
        """
        _db = getattr(self, "db", None)
        if _db is None:
            return {}
        try:
            baseline_state = await _db.async_get_model_state(
                "thermal_daily_baseline", default={}
            ) or {}
            if not isinstance(baseline_state, dict):
                return {}

            today = time.strftime("%Y-%m-%d", time.localtime())
            energy_today = await _db.async_get_model_state(
                f"energy_acc.{today}", default={}
            ) or {}
            if not isinstance(energy_today, dict):
                return {}

            best_display: dict[str, Any] | None = None
            best_display_el = -1.0
            best_fire: dict[str, Any] | None = None
            best_fire_z = 0.0

            for mode in ("heating", "dhw", "cooling"):
                try:
                    today_el = float(
                        energy_today.get(f"{mode}_el_kwh", 0.0) or 0.0
                    )
                except (TypeError, ValueError):
                    continue

                n = 0
                mean = 0.0
                sigma = 0.0
                b = baseline_state.get(mode)
                if isinstance(b, dict):
                    try:
                        n = int(b.get("n", 0) or 0)
                        mean = float(b.get("mean", 0.0) or 0.0)
                        m2 = float(b.get("m2", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        n, mean, m2 = 0, 0.0, 0.0
                    sigma = (m2 / n) ** 0.5 if n > 0 else 0.0

                z = (today_el - mean) / sigma if sigma > 0 else 0.0
                candidate = {
                    "mode": mode,
                    "today_el_kwh": round(today_el, 2),
                    "baseline_el_mean": round(mean, 2) if n >= 1 else None,
                    "baseline_el_sigma": round(sigma, 2) if n >= 2 else None,
                    "z_score": round(z, 2) if n >= 2 and sigma > 0 else None,
                    "samples": n,
                }

                if today_el > best_display_el:
                    best_display = candidate
                    best_display_el = today_el

                if n < ENERGY_ANOMALY_MIN_DAYS:
                    continue
                if sigma <= 0.0:
                    continue
                if today_el < ENERGY_ANOMALY_FLOOR_KWH:
                    continue
                if z <= ENERGY_ANOMALY_SIGMA_THRESHOLD:
                    continue
                if best_fire is None or z > best_fire_z:
                    best_fire = candidate
                    best_fire_z = z

            if best_fire is not None:
                result = dict(best_fire)
                result["fired"] = True
            elif best_display is not None:
                result = dict(best_display)
                result["fired"] = False
            else:
                result = {
                    "fired": False,
                    "mode": None,
                    "today_el_kwh": 0.0,
                    "baseline_el_mean": None,
                    "baseline_el_sigma": None,
                    "z_score": None,
                    "samples": 0,
                }
            result["threshold_sigma"] = ENERGY_ANOMALY_SIGMA_THRESHOLD
            return result
        except Exception:
            _LOGGER.exception("energy anomaly count failed")
            return {}

    async def _persist_energy_baseline(self) -> None:
        """I6: finalize yesterday's electrical kWh into per-mode Welford baseline.

        Runs from _refresh_7d_rollups (1h tick). For each mode, if
        last_day in thermal_daily_baseline != yesterday, read
        energy_acc.<yesterday> from model_state and Welford-update the
        {mean, m2, n, last_day} state, then persist.

        Gap-skip: if energy_acc.<yesterday> is missing (restart, outage),
        it is treated as empty (all modes zero); last_day advances without
        a Welford update so the gap is skipped, not retried. If a single
        mode's value is 0 or corrupt, only that mode's last_day advances
        with no update. Matches design decision "skip gaps silently".

        Never raises; DB failures leave baseline untouched.
        """
        _db = getattr(self, "db", None)
        if _db is None:
            return
        try:
            state = await _db.async_get_model_state(
                "thermal_daily_baseline", default={}
            ) or {}
            if not isinstance(state, dict):
                state = {}

            # Ensure every mode key exists
            for mode in ("heating", "dhw", "cooling"):
                if not isinstance(state.get(mode), dict):
                    state[mode] = {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""}

            # Yesterday's local-day key (matches _energy_day_key convention)
            yesterday = time.strftime(
                "%Y-%m-%d", time.localtime(time.time() - 86400.0)
            )

            energy_y = await _db.async_get_model_state(
                f"energy_acc.{yesterday}", default={}
            ) or {}
            if not isinstance(energy_y, dict):
                return

            changed = False
            for mode in ("heating", "dhw", "cooling"):
                b = state[mode]
                if b.get("last_day") == yesterday:
                    continue  # already finalized
                try:
                    x = float(energy_y.get(f"{mode}_el_kwh", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                if x <= 0.0:
                    # Nothing to contribute; still advance last_day to avoid
                    # repeatedly scanning the same empty day.
                    b["last_day"] = yesterday
                    changed = True
                    continue
                # Welford update
                try:
                    n = int(b.get("n", 0) or 0)
                    mean = float(b.get("mean", 0.0) or 0.0)
                    m2 = float(b.get("m2", 0.0) or 0.0)
                except (TypeError, ValueError):
                    n, mean, m2 = 0, 0.0, 0.0
                n_new = n + 1
                delta = x - mean
                mean_new = mean + delta / n_new
                delta2 = x - mean_new
                m2_new = m2 + delta * delta2
                b["mean"] = mean_new
                b["m2"] = m2_new
                b["n"] = n_new
                b["last_day"] = yesterday
                changed = True

            if changed:
                await _db.async_set_model_state("thermal_daily_baseline", state)
        except Exception:
            _LOGGER.exception("energy baseline finalize failed")
            return



    def _alert_binary_states(self, snap: DataSnapshot) -> dict[str, bool]:
        """Snapshot the 4 alert-relevant binary states."""
        now = time.time()
        short_run_th = self._effective_threshold(
            "short_run_threshold_min",
            int(self.options.get("short_run_threshold_min", 20)),
        ) * 60
        short_off_th = self._effective_threshold(
            "short_off_threshold_min",
            int(self.options.get("short_off_threshold_min", 5)),
        ) * 60
        pend_hour = int(self.options.get("pendulum_cycles_per_hour", 4))
        pend_day = self._effective_threshold(
            "pendulum_cycles_per_day",
            int(self.options.get("pendulum_cycles_per_day", 40)),
        )

        last = self.store.last_cycle()
        dur = (last or {}).get("duration_s")
        is_short_run = isinstance(dur, (int, float)) and dur < short_run_th
        off = self.store.off_time_since_last(now)
        is_short_off = off is not None and off < short_off_th
        is_pend_h = self.store.cycles_in_window(now, 3600) >= pend_hour
        is_pend_d = (
            len(self.store.non_transient_today(now)) >= pend_day
        )
        is_ml_anom = bool(
            getattr(snap, "anomaly", None)
            and getattr(snap.anomaly, "is_anomaly", False)
        )
        # PR E: P1 alert triggers (v1.9.0)
        from .binary_sensor import SOURCE_STALE_FACTOR
        from .const import (
            BUH_7D_RATIO_THRESHOLD_DEFAULT,
            COP_DEGRADATION_WEEK_PCT_THRESHOLD,
            DEFROST_7D_COUNT_THRESHOLD_DEFAULT,
            UPDATE_INTERVAL_SECONDS,
        )
        _cop_week_pct = getattr(snap, "cop_degradation_week_pct", None)
        is_cop_degradation = (
            isinstance(_cop_week_pct, (int, float))
            and _cop_week_pct < COP_DEGRADATION_WEEK_PCT_THRESHOLD
        )
        _defrost_thr = int(self.options.get(
            "defrost_7d_count_threshold", DEFROST_7D_COUNT_THRESHOLD_DEFAULT,
        ))
        _defrost_7d = int(getattr(self, "_defrost_7d_sum", 0) or 0)
        is_defrost_excessive = _defrost_7d > _defrost_thr
        _buh_thr = float(self.options.get(
            "buh_7d_ratio_threshold", BUH_7D_RATIO_THRESHOLD_DEFAULT,
        ))
        _buh_7d_ratio = float(getattr(self, "_buh_7d_ratio", 0.0) or 0.0)
        is_buh_excessive = _buh_7d_ratio > _buh_thr
        _last_ok = float(getattr(snap, "last_success_ts", 0.0) or 0.0)
        _stale_thr = SOURCE_STALE_FACTOR * UPDATE_INTERVAL_SECONDS
        is_source_stale = _last_ok > 0 and (now - _last_ok) > _stale_thr
        is_missing_attributes = len(getattr(snap, "missing_attrs", []) or []) > 0
        # PR F: P2 alert triggers (v1.9.0)
        _dhw_cph = 0
        with contextlib.suppress(Exception):
            _dhw_cph = int(self.store.cycles_in_window_mode(now, 3600, MODE_DHW))
        _dhw_thr = int(self.options.get(
            "dhw_pendulum_cycles_per_hour", DEFAULT_DHW_PENDULUM_CPH,
        ))
        is_dhw_pendulum = _dhw_cph >= _dhw_thr
        _hcr_cph = 0
        with contextlib.suppress(Exception):
            _hcr_cph = int(self.store.non_transient_in_window(now, 3600))
        _hcr_base = int(self.options.get("pendulum_cycles_per_hour", 4))
        is_high_cycle_rate = _hcr_cph > _hcr_base * HIGH_CYCLE_RATE_MULTIPLIER
        _cop_ds_pct = getattr(snap, "cop_vs_datasheet_pct", None)
        is_cop_vs_datasheet_low = (
            isinstance(_cop_ds_pct, (int, float))
            and _cop_ds_pct < COP_VS_DATASHEET_LOW_PCT
        )
        return {
            "short_run": bool(is_short_run),
            "short_off": bool(is_short_off),
            "pendulum_hourly": bool(is_pend_h),
            "pendulum_daily": bool(is_pend_d),
            "ml_anomaly": is_ml_anom,
            "setpoint_osc": self._compute_setpoint_oscillating(),
            "cop_degradation": bool(is_cop_degradation),
            "defrost_excessive": bool(is_defrost_excessive),
            "buh_excessive": bool(is_buh_excessive),
            "source_stale": bool(is_source_stale),
            "missing_attributes": bool(is_missing_attributes),
            "dhw_pendulum": bool(is_dhw_pendulum),
            "high_cycle_rate": bool(is_high_cycle_rate),
            "cop_vs_datasheet_low": bool(is_cop_vs_datasheet_low),
            "db_retention_warning": bool(
                getattr(self, "_db_retention_stale", {}).get("fired", False)
            ),
            "kmeans_retrain_stale": bool(
                getattr(self, "_kmeans_stale", {}).get("fired", False)
            ),
            "energy_daily_anomaly": bool(
                getattr(self, "_energy_daily_anomaly", {}).get("fired", False)
            ),
        }

    def _assign_cluster(self, vector: list[float]) -> int | None:
        if not self._kmeans_centroids:
            return None
        try:
            return nearest_centroid(vector, self._kmeans_centroids)
        except Exception:
            return None

    def cluster_label(self, cluster_id: int | None) -> str | None:
        if cluster_id is None:
            return None
        return self._cluster_labels.get(cluster_id)

    async def _load_kmeans_state(self) -> bool:
        if self.db is None:
            return False
        try:
            data = await self.db.async_get_model_state("kmeans_state")
            if not data:
                return False
            centroids = data.get("centroids") or []
            if not centroids:
                return False
            _raw_centroids = data.get('centroids') or []
            if _raw_centroids and len(_raw_centroids[0]) == 8:
                _LOGGER.warning(
                    'kmeans_state is legacy 8-dim, resetting (retrain on Sunday)'
                )
                self._kmeans_centroids = []
                return False
            self._kmeans_centroids = [
                [float(x) for x in c] for c in centroids
            ]
            self._cluster_labels = classify_clusters(
                self._kmeans_centroids
            )
            return True
        except Exception:
            _LOGGER.debug("load kmeans_state failed", exc_info=True)
            return False

    async def async_setup_status_updates(self) -> None:
        """Schedule periodic status summaries (opt-in)."""
        if self._status_update_unsub is not None:
            return
        opts = self.options or {}
        if not opts.get("status_update_enabled", False):
            _LOGGER.debug("status updates disabled by options")
            return
        try:
            hours = int(opts.get("status_update_interval_hours", 24))
        except (TypeError, ValueError):
            hours = 24
        hours = max(hours, 1)
        self._status_update_unsub = async_track_time_interval(
            self.hass,
            self._async_status_update_callback,
            timedelta(hours=hours),
        )
        _LOGGER.info("status updates scheduled every %sh", hours)

    async def _async_status_update_callback(self, _now: Any) -> None:
        try:
            await self.async_emit_status_update()
        except Exception:
            _LOGGER.exception("Scheduled status update failed")

    async def _build_rich_status_snapshot(self) -> dict[str, Any]:
        """Extended snapshot for the rich status report."""
        base = self._build_status_snapshot()
        snap = self.data
        opts = self.options or {}
        base['target_cph'] = int(opts.get('pendulum_cycles_per_hour', 4) or 4)
        base['target_cpd'] = int(opts.get('target_cycles_per_day', 8) or 8)
        try:
            import time as _t
            now = _t.time()
            if self.store is not None and hasattr(self.store, 'cycles_in_window'):
                base['cycles_per_hour'] = int(self.store.cycles_in_window(now, 3600))
        except Exception:
            base['cycles_per_hour'] = None
        try:
            if self.store is not None and hasattr(self.store, 'counters_snapshot'):
                c = self.store.counters_snapshot() or {}
                base['short_runs_today'] = c.get('short_runs')
                base['good_cycles_today'] = c.get('good_cycles')
        except Exception:
            _LOGGER.debug("snapshot counters failed", exc_info=True)
        try:
            attrs = getattr(snap, 'attributes', None) or {}
            base['lwt'] = attrs.get('leaving_water_temp')
            base['indoor'] = attrs.get('indoor_temp')
            base['outdoor'] = attrs.get('outdoor_temp')
            base['flow_lmin'] = attrs.get('flow_lmin')
        except Exception:
            _LOGGER.debug("snapshot attrs failed", exc_info=True)
        try:
            last = getattr(snap, 'last_cycle', None)
            if isinstance(last, dict):
                base['thermal_kw'] = last.get('thermal_kw_avg')
        except Exception:
            _LOGGER.debug("snapshot last_cycle failed", exc_info=True)
        try:
            base['cop_today'] = getattr(self, '_cop_today_value', None)
            base['cop_today_samples'] = getattr(self, '_cop_today_samples', None)
        except Exception:  # pragma: no cover
            _LOGGER.debug("snapshot cop_today failed", exc_info=True)
        try:
            if self.db is not None:
                base.update(await self._db_cycle_stats())
        except Exception:
            _LOGGER.debug("snapshot db_stats failed", exc_info=True)
        return base

    async def _db_cycle_stats(self) -> dict[str, Any]:
        """Return DB aggregates for status report (defensive)."""
        import time as _t
        out: dict[str, Any] = {'db_total': None, 'db_7d': None, 'db_30d': None, 'db_avg_duration_min': None}
        if self.db is None:
            return out
        now = _t.time()
        try:
            getter = getattr(self.db, 'async_count_cycles_since', None)
            if callable(getter):
                out['db_total'] = await getter(0)  # pylint: disable=not-callable
                out['db_7d'] = await getter(now - 7 * 86400)  # pylint: disable=not-callable
                out['db_30d'] = await getter(now - 30 * 86400)  # pylint: disable=not-callable
            avg_getter = getattr(self.db, 'async_avg_duration_since', None)
            if callable(avg_getter):
                avg_s = await avg_getter(now - 7 * 86400)  # pylint: disable=not-callable
                if avg_s is not None:
                    out['db_avg_duration_min'] = float(avg_s) / 60.0
        except Exception:
            _LOGGER.warning("db_cycle_stats failed", exc_info=True)
        return out

    async def async_emit_status_update(self) -> str:
        """Build and dispatch one status summary. Returns message."""
        from .const import NOTIF_ID_STATUS

        snap_dict = await self._build_rich_status_snapshot()
        opts = self.options or {}
        emoji = bool(opts.get("notify_emoji_enabled", True))
        lang = opts.get("notification_language", "en")
        msg = build_status_message(
            snap_dict, emoji_enabled=emoji, language=lang
        )

        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Daikin Cycle ML",
                    "message": msg,
                    "notification_id": NOTIF_ID_STATUS,
                },
                blocking=False,
            )
        except Exception:
            _LOGGER.exception("status persistent_notification failed")

        svc = opts.get("notify_service")
        if svc and "." in str(svc):
            try:
                dom, name = str(svc).split(".", 1)
                await self.hass.services.async_call(
                    dom, name, {"message": msg}, blocking=False
                )
            except Exception:
                _LOGGER.exception("status notify service failed")

        return msg

    def _build_status_snapshot(self) -> dict[str, Any]:
        import time as _t
        snap = self.data
        store = self.store
        counters = {}
        if store is not None and hasattr(store, "counters_snapshot"):
            try:
                counters = store.counters_snapshot()
            except Exception:
                counters = {}
        last = None
        if store is not None and hasattr(store, "last_cycle"):
            try:
                last = store.last_cycle()
            except Exception:
                last = None
        opts = self.options or {}
        cyc_today = counters.get("cycles_today") or counters.get("total_today")
        tgt = opts.get("target_cycles_per_day", 8)
        q = last.get("quality_score") if isinstance(last, dict) else None
        ago = None
        if isinstance(last, dict) and last.get("end_ts"):
            try:
                ago = int((_t.time() - float(last["end_ts"])) / 60)
            except (TypeError, ValueError):
                ago = None
        sev = None
        anomaly = getattr(snap, "anomaly", None)
        if anomaly is not None:
            sev = getattr(anomaly, "severity", None)
        advice_list = getattr(snap, "advice", None) or []
        top_advice = None
        if advice_list:
            first = advice_list[0]
            top_advice = (
                getattr(first, "title", None)
                or getattr(first, "text", None)
                or str(first)
            )
        return {
            "mode": getattr(snap, "mode", "unknown"),
            "state": getattr(snap, "state", "idle"),
            "cycles_today": cyc_today,
            "target_cpd": tgt,
            "last_cycle_ago_min": ago,
            "quality_last": q,
            "anomaly_severity": sev,
            "baseline_samples": self.baseline.total_samples(),
            "baseline_modes": self.baseline.modes(),
            "top_advice": top_advice,
        }

    def _snap_attr(self, snap: Any, *keys: str) -> Any:
        attrs = {}
        if snap is not None:
            for _attr_name in ("attrs", "attributes", "raw_attrs"):
                _a = getattr(snap, _attr_name, None)
                if isinstance(_a, dict) and _a:
                    attrs = _a
                    break
        attrs = build_compat_view(attrs)
        for k in keys:
            v = attrs.get(k)
            if v is not None:
                return v
        return None

    def _setpoint_current(self, snap: Any) -> Any:
        v = self._snap_attr(snap,
            "lwt_setpoint", "target_lwt", "lw_setpoint",
            ATTR_LW_SETPOINT, "setpoint")
        if v is not None:
            return v
        hist = getattr(self, "_setpoint_history", None) or []
        if hist:
            last = hist[-1]
            if isinstance(last, (list, tuple)) and len(last) >= 2:
                return last[1]
            return last
        return None

    def _setpoint_target(self, snap: Any) -> Any:
        return self._snap_attr(snap,
            "target_lwt", "lwt_target", "calculated_lwt",
            ATTR_TARGET_COND_TEMP, "target_cond_temp")

    def _setpoint_delta(self, snap: Any) -> Any:
        hist = getattr(self, "_setpoint_history", None) or []
        vals = []
        for item in hist:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    vals.append(float(item[1]))
                except (TypeError, ValueError):
                    continue
            else:
                try:
                    vals.append(float(item))
                except (TypeError, ValueError):
                    continue
        if len(vals) < 2:
            return None
        return max(vals) - min(vals)

    def _last_duration_min(self) -> int | None:
        try:
            last = self.store.last_cycle()
            if isinstance(last, dict):
                d = last.get("duration_s")
                if d is not None:
                    return int(float(d) / 60)
        except Exception:
            _LOGGER.debug("last_duration_min failed", exc_info=True)
        return None

    async def _compute_avg_duration_7d_min(self) -> int | None:
        """Average cycle duration (minutes) over last 7d, or None."""
        db = getattr(self, "db", None)
        if db is None:
            return None
        getter = getattr(db, "async_avg_duration_since", None)
        if getter is None:
            return None
        try:
            avg_s = await getter(time.time() - (7 * 86400))
        except Exception:
            _LOGGER.debug("avg_duration_7d_min query failed", exc_info=True)
            return None
        if avg_s is None:
            return None
        return int(round(float(avg_s) / 60.0))

    def _build_alert_context(self, snap: Any) -> dict[str, Any]:
        opts = self.options or {}
        now = time.time()
        cph = 0
        cyc_today = 0
        with contextlib.suppress(Exception):
            cph = int(self.store.cycles_in_window(now, 3600))
        with contextlib.suppress(Exception):
            cyc_today = len(self.store.cycles_today(now))
        _dhw_cph_ctx = 0
        with contextlib.suppress(Exception):
            _dhw_cph_ctx = int(self.store.cycles_in_window_mode(now, 3600, MODE_DHW))
        # SB-2 (R331): global advice bleed disabled in v1.8.1.
        # Per-alert advice comes from ALERT_ADVICE in status_report.
        # Previous block (snap.advice[0].title -> advice_text)
        # removed: every alert carried the same first-advice string
        # (e.g. 'Low dT' bled onto ML-anomaly alerts).
        # See git history / R331 for pre-fix version.
        advice_text = ""
        # (end SB-2 block)
        mode_str = "unknown"
        if snap is not None:
            _m = str(getattr(snap, "mode", "") or "").strip()
            if _m and _m.lower() != "unknown":
                mode_str = _m
        if mode_str == "unknown":
            try:
                _last = self.store.last_cycle()
                if isinstance(_last, dict):
                    _lm = str(_last.get("mode", "") or "").strip()
                    if _lm and _lm.lower() != "unknown":
                        mode_str = _lm
            except Exception:
                pass
        if mode_str == "unknown":
            _mode_raw = self._snap_attr(
                snap, "operation_mode", "I/U operation mode"
            )
            if _mode_raw:
                _mode_s = str(_mode_raw).strip().lower()
                if _mode_s in ("heating", "cooling", "dhw"):
                    mode_str = _mode_s
                elif "heat" in _mode_s:
                    mode_str = "heating"
                elif "cool" in _mode_s:
                    mode_str = "cooling"
                elif "dhw" in _mode_s or "water" in _mode_s:
                    mode_str = "dhw"
        lwt_set = self._setpoint_current(snap)
        lwt_tgt = self._setpoint_target(snap)
        delta = self._setpoint_delta(snap)
        out_t = self._snap_attr(
            snap, "outdoor_temp", "outdoor", ATTR_OUTDOOR_AIR_R1T
        )
        lwt_act = self._snap_attr(
            snap, "leaving_water_temp", "lwt", ATTR_LEAVING_WATER_AFTER_BUH
        )
        in_t = self._snap_attr(
            snap, "indoor_temp", "indoor", ATTR_INDOOR_AMBIENT_R1T
        )
        flow = self._snap_attr(
            snap, "flow_lmin", "flow", ATTR_FLOW_SENSOR
        )
        avg_dur = self._last_duration_min()

        def _f(v: Any, digits: int = 1) -> str | None:
            if v is None:
                return None
            try:
                return ("%." + str(digits) + "f") % float(v)
            except (TypeError, ValueError):
                return None

        _ce = getattr(self, "config_entry", None)
        _ks = getattr(self, "_kmeans_stale", {}) or {}
        _ea = getattr(self, "_energy_daily_anomaly", {}) or {}
        _ad = getattr(self, "_avg_duration_7d_min", None)
        _d7d = int(round(float(getattr(self, "_defrost_7d_duration_s", 0.0) or 0.0) / 60.0))
        ctx = {
            "pendulum": {
                "target_cph": opts.get("pendulum_cycles_per_hour", 4),
                "target_cpd": opts.get("pendulum_cycles_per_day", 40),
                "cph": cph, "cycles_today": cyc_today,
                "mode": mode_str, "lwt_setpoint": _f(lwt_set),
                "last_duration_min": avg_dur,
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "pendulum_hourly": {
                "target_cph": opts.get("pendulum_cycles_per_hour", 4),
                "target_cpd": opts.get("pendulum_cycles_per_day", 40),
                "cph": cph, "cycles_today": cyc_today,
                "mode": mode_str, "lwt_setpoint": _f(lwt_set),
                "last_duration_min": avg_dur,
                "avg_duration_7d_min": _ad,
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "pendulum_daily": {
                "target_cph": opts.get("pendulum_cycles_per_hour", 4),
                "target_cpd": opts.get("pendulum_cycles_per_day", 40),
                "cph": cph, "cycles_today": cyc_today,
                "mode": mode_str, "lwt_setpoint": _f(lwt_set),
                "last_duration_min": avg_dur,
                "avg_duration_7d_min": _ad,
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "short_run": {
                "threshold_min": opts.get("short_run_threshold_min", 20),
                "duration_min": None, "mode": mode_str,
                "lwt_setpoint": _f(lwt_set), "lwt_actual": _f(lwt_act),
                "indoor": _f(in_t), "flow": _f(flow),
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "short_off": {
                "threshold_min": opts.get("short_off_threshold_min", 5),
                "off_min": None, "mode": mode_str,
                "lwt_setpoint": _f(lwt_set),
                "indoor": _f(in_t), "flow": _f(flow),
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "ml_anomaly": {
                "mode": mode_str, "z_max": None, "top_dim": None,
                "last_duration_min": avg_dur,
                "avg_duration_7d_min": _ad,
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "setpoint_osc": {
                "osc_count": len(self._setpoint_history or []),
                "window_min": int(self.options.get("setpoint_osc_window_min", 30) or 30),
                "threshold": int(self.options.get("setpoint_oscillation_threshold", 6) or 6),
                "lwt_setpoint": _f(lwt_set),
                "lwt_target": _f(lwt_tgt if lwt_tgt is not None else lwt_set),
                "delta_max": _f(delta), "mode": mode_str,
                "advice": advice_text,
            },
            # PR E: P1 alert contexts (v1.9.0)
            "cop_degradation": {
                "week_pct": _f(getattr(snap, "cop_degradation_week_pct", None)),
                "threshold_pct": "-15",
                "trend_30d": _f(getattr(snap, "cop_trend_30d", None)),
                "mode": mode_str,
                "outdoor": _f(out_t),
                "advice": advice_text,
            },
            "defrost_excessive": {
                "count_7d": int(getattr(self, "_defrost_7d_sum", 0) or 0),
                "threshold": int(opts.get(
                    "defrost_7d_count_threshold",
                    DEFROST_7D_COUNT_THRESHOLD_DEFAULT,
                )),
                "duration_7d_min": _d7d,
                "mode": mode_str,
                "outdoor": _f(out_t),
                "advice": advice_text,
            },
            "buh_excessive": {
                "buh_ratio_7d": float(getattr(self, "_buh_7d_ratio", 0.0) or 0.0),
                "threshold_ratio": float(opts.get(
                    "buh_7d_ratio_threshold",
                    BUH_7D_RATIO_THRESHOLD_DEFAULT,
                )),
                "buh_count_7d": int(getattr(self, "_buh_7d_count", 0) or 0),
                "mode": mode_str,
                "outdoor": _f(out_t),
                "advice": advice_text,
            },
            "source_stale": {
                "age_s": _f(round(now - float(getattr(snap, "last_success_ts", 0.0) or 0.0), 1)) if getattr(snap, "last_success_ts", 0) else 0.0,
                "threshold_s": 60.0,
                "source_sensor": (_ce.data.get("source_sensor", "?") if _ce else "?"),
                "mode": mode_str,
                "advice": advice_text,
            },
            "missing_attributes": {
                "missing_count": len(getattr(snap, "missing_attrs", []) or []),
                "missing_list": (", ".join((getattr(snap, "missing_attrs", []) or [])[:3]) + ("…" if len(getattr(snap, "missing_attrs", []) or []) > 3 else "")),
                "source_sensor": (_ce.data.get("source_sensor", "?") if _ce else "?"),
                "mode": mode_str,
                "advice": advice_text,
            },
            # PR F: P2 alert contexts (v1.9.0)
            "dhw_pendulum": {
                "dhw_cph": int(_dhw_cph_ctx),
                "target_cph": int(opts.get(
                    "dhw_pendulum_cycles_per_hour", DEFAULT_DHW_PENDULUM_CPH,
                )),
                "mode": mode_str,
                "outdoor": _f(out_t),
                "advice": advice_text,
            },
            "high_cycle_rate": {
                "cph": int(cph),
                "target_cph": int(opts.get("pendulum_cycles_per_hour", 4)),
                "multiplier": float(HIGH_CYCLE_RATE_MULTIPLIER),
                "mode": mode_str,
                "outdoor": _f(out_t),
                "advice": advice_text,
            },
            "cop_vs_datasheet_low": {
                "pct_diff": _f(getattr(snap, "cop_vs_datasheet_pct", None)),
                "cop_expected": str(
                    getattr(self, "_datasheet_cache", {}).get("cop_expected")
                    or "datasheet"
                ),
                "mode": mode_str,
                "outdoor": _f(out_t),
                "advice": advice_text,
            },
            "db_retention_warning": {
                "stale_alerts": int(
                    getattr(self, "_db_retention_stale", {}).get(
                        "stale_alerts", 0
                    )
                ),
                "stale_cycles": int(
                    getattr(self, "_db_retention_stale", {}).get(
                        "stale_cycles", 0
                    )
                ),
                "alert_retention_days": int(
                    getattr(self, "_db_retention_stale", {}).get(
                        "alert_retention_days", DEFAULT_ALERT_RETENTION_DAYS
                    )
                ),
                "cycle_retention_days": int(
                    getattr(self, "_db_retention_stale", {}).get(
                        "cycle_retention_days", DEFAULT_CYCLE_RETENTION_DAYS
                    )
                ),
                "mode": mode_str,
                "advice": advice_text,
            },
            "kmeans_retrain_stale": {
                "hours_since_ok": (
                    int(round(_ks.get("hours_since_ok", 0) or 0))
                    if _ks.get("hours_since_ok") is not None
                    else 0
                ),
                "last_ok_ts": _format_last_ok_ts(_ks.get("last_ok_ts")),
                "consecutive_failures": int(
                    _ks.get("consecutive_failures", 0) or 0
                ),
                "last_failure_reason": (
                    _ks.get("last_failure_reason") or "\u2014"
                ),
                "mode": mode_str,
                "advice": _kmeans_advice(
                    _ks.get("last_failure_reason"),
                    str(opts.get("language", "en") or "en"),
                ),
            },
            "energy_daily_anomaly": {
                "mode": (_ea.get("mode") or mode_str or "\u2014"),
                "today_el_kwh": float(_ea.get("today_el_kwh", 0.0) or 0.0),
                "baseline_el_mean": _ea.get("baseline_el_mean"),
                "baseline_el_sigma": _ea.get("baseline_el_sigma"),
                "z_score": _ea.get("z_score"),
                "samples": int(_ea.get("samples", 0) or 0),
                "advice": "",
            },
        }
        # Resolve last cycle record: prefer per-tick snap.last_record
        # (set on cycle-completion ticks), fall back to persisted store
        # for non-completion ticks. Fixes duration_min showing em-dash
        # despite sensor.last_cycle rendering real data.
        last = getattr(snap, "last_record", None) if snap is not None else None
        if not isinstance(last, dict) or not isinstance(
            last.get("duration_s"), (int, float)
        ):
            try:
                _store_last = self.store.last_cycle()
                if isinstance(_store_last, dict):
                    last = _store_last
            except Exception:
                pass
        if isinstance(last, dict):
            dur = last.get("duration_s")
            if dur is not None:
                with contextlib.suppress(TypeError, ValueError):
                    ctx["short_run"]["duration_min"] = int(float(dur) / 60)
        try:
            off = self.store.off_time_since_last(now)
            if off is not None:
                ctx["short_off"]["off_min"] = max(1, round(off / 60))
        except Exception:
            _LOGGER.debug("alert ctx short_off failed", exc_info=True)
        anomaly = getattr(snap, "anomaly", None) if snap else None
        if anomaly is not None:
            z = getattr(anomaly, "max_abs_z", None)
            td = getattr(anomaly, "top_dim", None)
            if z is not None:
                with contextlib.suppress(TypeError, ValueError):
                    ctx["ml_anomaly"]["z_max"] = round(float(z), 2)
            if td is not None:
                try:
                    from .ml.features import FEATURE_NAMES
                    _idx = int(td)
                    if 0 <= _idx < len(FEATURE_NAMES):
                        ctx["ml_anomaly"]["top_dim"] = FEATURE_NAMES[_idx]
                    else:
                        ctx["ml_anomaly"]["top_dim"] = "dim " + str(td)
                except Exception:
                    _LOGGER.debug("alert ctx top_dim failed", exc_info=True)
        return ctx

    async def async_emit_test_alert(
        self, alert_kind: str, *, ignore_filters: bool = False
    ) -> str:
        """Dispatch one sample alert for the OptionsFlow test button."""
        import time as _t

        from .engine.notification_engine import (
            BINARY_ALERT_MAP,
            AlertSpec,
            build_cop_low_message,
            build_stooklijn_message,
            evaluate_alerts,
        )

        if alert_kind == "status_summary":
            return await self.async_emit_status_update()

        if alert_kind == "all_alerts":
            return await self._emit_all_test_alerts(ignore_filters=ignore_filters)

        opts = dict(self.options or {})
        if ignore_filters:
            opts["quiet_hours_enabled"] = False
            opts["alert_aggregation_minutes"] = 0
            for k in list(opts.keys()):
                if k.startswith("alert_group_"):
                    opts[k] = True

        now = _t.time()
        persistent = bool(opts.get("persistent_enabled", True))

        if alert_kind == "cop_low":
            msg = build_cop_low_message(
                COP_LOW_THRESHOLD - TEST_ALERT_DELTA, 8,
                language=opts.get("notification_language", "en"),
                emoji_enabled=bool(opts.get("notify_emoji_enabled", True)),
            )
            spec = AlertSpec(
                alert_type="cop_low",
                severity="warning",
                message=msg,
                notif_id="daikin_cycle_ml_cop_low",
                dedupe_key="cop_low",
                persistent=persistent,
            )
            await self._emit_alert(spec)
            return msg

        if alert_kind == "stooklijn_advies":
            fake = {
                "state": "ok",
                "besparing_cop_pct": 12.0,
                "comfort_impact": -0.3,
                "betrouwbaarheid": 0.75,
                "samples": 42,
            }
            msg = build_stooklijn_message(
                fake,
                language=opts.get("notification_language", "en"),
                emoji_enabled=bool(opts.get("notify_emoji_enabled", True)),
            )
            spec = AlertSpec(
                alert_type="stooklijn_advies",
                severity="warning",
                message=msg,
                notif_id="daikin_cycle_ml_stooklijn_advies",
                dedupe_key="stooklijn_advies",
                persistent=persistent,
            )
            await self._emit_alert(spec)
            return msg

        target_bkeys = [
            bkey
            for bkey, spec_tuple in BINARY_ALERT_MAP.items()
            if spec_tuple[0] == alert_kind or bkey == alert_kind
        ]
        if not target_bkeys:
            raise ValueError("unknown alert_kind: " + str(alert_kind))

        states = dict.fromkeys(target_bkeys, True)
        ctx = self._build_alert_context(self.data)
        alerts = evaluate_alerts(
            states,
            opts,
            now,
            {},
            context=ctx,
            language=opts.get("notification_language", "en"),
            **self._boiler_kwargs_for_alerts(),
        )
        if not alerts:
            return (
                "[filtered] No alert produced. Use the ignore-filters "
                "toggle or check alert_group_* / quiet_hours / "
                "aggregation options."
            )
        parts = []
        for a in alerts:
            await self._emit_alert(a)
            parts.append(a.message)
        return "\n---\n".join(parts)

    async def _emit_all_test_alerts(self, *, ignore_filters: bool = False) -> str:
        """Emit one of each alert type for verification."""
        from .engine.notification_engine import (
            BINARY_ALERT_MAP,
            AlertSpec,
        )
        from .engine.status_report import (
            build_cop_low_report,
            build_rich_alert,
            build_stooklijn_report,
)

        opts = dict(self.options or {})
        if ignore_filters:
            opts["quiet_hours_enabled"] = False
            opts["alert_aggregation_minutes"] = 0
            for k in list(opts.keys()):
                if k.startswith("alert_group_"):
                    opts[k] = True
        persistent = bool(opts.get("persistent_enabled", True))
        emoji = bool(opts.get("notify_emoji_enabled", True))
        lang = opts.get("notification_language", "en")
        ctx_all = self._build_alert_context(self.data)

        parts: list[str] = []
        seen: set[str] = set()
        for bkey, spec_tuple in BINARY_ALERT_MAP.items():
            if bkey in seen:
                continue
            seen.add(bkey)
            alert_type, severity, _ = spec_tuple
            ctx = ctx_all.get(bkey) or ctx_all.get(alert_type) or {}
            msg = build_rich_alert(
                bkey, severity, ctx,
                language=lang, emoji_enabled=emoji,
            )
            spec = AlertSpec(
                alert_type=alert_type,
                severity=severity,
                message=msg,
                notif_id="daikin_cycle_ml_test_" + bkey,
                dedupe_key="test_" + bkey,
                persistent=persistent,
            )
            await self._emit_alert(spec)
            parts.append("=== " + bkey + " ===\n" + msg)

        cop_msg = build_cop_low_report(
            COP_LOW_THRESHOLD - TEST_ALERT_DELTA, 8,
            language=lang, emoji_enabled=emoji,
        )
        await self._emit_alert(AlertSpec(
            alert_type="cop_low", severity="warning",
            message=cop_msg,
            notif_id="daikin_cycle_ml_test_cop_low",
            dedupe_key="test_cop_low", persistent=persistent,
        ))
        parts.append("=== cop_low ===\n" + cop_msg)

        fake_stook = {
            "state": "lower_lwt",
            "step_c": 2,
            "besparing_cop_pct": 12.0,
            "comfort_impact": -0.3,
            "betrouwbaarheid": 0.75,
            "samples": 42,
        }
        stook_msg = build_stooklijn_report(fake_stook, language=lang, emoji_enabled=emoji)
        await self._emit_alert(AlertSpec(
            alert_type="stooklijn_advies", severity="warning",
            message=stook_msg,
            notif_id="daikin_cycle_ml_test_stooklijn",
            dedupe_key="test_stooklijn", persistent=persistent,
        ))
        parts.append("=== stooklijn_advies ===\n" + stook_msg)

        return "\n\n".join(parts)

    async def _async_dispatch_alerts(self, snap: DataSnapshot) -> None:


        """Evaluate + emit alerts. Never raises."""
        try:
            await self._refresh_7d_rollups()
            states = self._alert_binary_states(snap)
            now = time.time()
            alerts = evaluate_alerts(
                states, self.options, now, self._last_alert_sent,
                context=self._build_alert_context(snap),
                language=self.options.get("notification_language", "en"),
                **self._boiler_kwargs_for_alerts(),
            )
            for alert in alerts:
                await self._emit_alert(alert)
                self._last_alert_sent[alert.alert_type] = now
                self._schedule_alert_save()
        except Exception:
            _LOGGER.exception("Alert dispatch failed")

    async def _emit_alert(self, alert: Any) -> None:
        """Deliver a single alert via persistent + notify service."""
        if alert.persistent:
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "Daikin Cycle ML",
                        "message": alert.message,
                        "notification_id": alert.notif_id,
                    },
                    blocking=False,
                )
            except Exception:
                _LOGGER.exception("persistent_notification failed")
        svc = self.options.get("notify_service")
        if not (isinstance(svc, str) and "." in svc):
            return
        domain, service = svc.split(".", 1)
        payload: dict[str, Any] = {"message": alert.message}
        try:
            await self.hass.services.async_call(
                domain, service, payload, blocking=False,
            )
            self._notify_fail_streak = 0
        except Exception:
            self._notify_fail_streak += 1
            self._notify_fail_target = str(svc)
            _LOGGER.exception("notify service %s failed", svc)

# ---------------------------------------------------------------------
# I2 (v1.9.0): kmeans_retrain_stale render helpers
# ---------------------------------------------------------------------
def _format_last_ok_ts(ts: Any) -> str:
    """Format a last_ok_ts epoch as YYYY-MM-DD HH:MM; em-dash if absent."""
    if not isinstance(ts, (int, float)):
        return "\u2014"
    try:
        import datetime as _dt
        return _dt.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return "\u2014"


def _kmeans_advice(reason: Any, language: str) -> str:
    """Return reason-derived advice string (falls back to None-key entry)."""
    table = KMEANS_ADVICE_BY_REASON.get(language, KMEANS_ADVICE_BY_REASON["en"])
    if reason in table:
        return table[reason]
    return table.get(None, "")

