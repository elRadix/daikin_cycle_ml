"""DataUpdateCoordinator for Daikin Cycle ML."""
from __future__ import annotations

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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

# v1.4.1 BUG-2 / BUG-3: score wiring + threshold.
from .const import (
    COP_CURVE_RECENT_HOURS,
    COP_CURVE_RECENT_MAX_POINTS,
    COP_ROLLUP_WINDOW_HOURS,
    COP_SENSOR_ENTITY,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    buh_step_kw_for_model as _buh_step_kw_for_model,
    DEFAULT_COMFORT_MIN_C,
    DOMAIN,
    GOOD_CYCLE_MIN_SCORE,
    MODEL_BASISPROFIEL,
    SOURCE_SENSOR_ENTITY,
    UPDATE_INTERVAL_SECONDS,

    DEGRADATION_BASELINE_DAYS,
    DEGRADATION_REFRESH_THROTTLE_S,
    DEGRADATION_WINDOW_DAYS,
)
from .engine.cop_degradation import (
    analyze_degradation,
    analyze_trend,
    build_dirty_hours,
)
from .engine.action_engine import generate_advice
from .engine.anomaly_engine import evaluate as evaluate_anomaly
from .engine.attribute_reader import missing_required, read
from .engine.thermal import compute_thermal_power_live as _compute_thermal_power_live
from .engine.thermal import dt_from_attrs as _dt_from_attrs
from .engine.thermal import flow_from_attrs as _flow_from_attrs
from .engine.thermal import rps_from_attrs as _rps_from_attrs
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
from .engine.notification_engine import build_status_message, evaluate_alerts
from .engine.quality_scorer import score_cycle
from .ml.adaptive_thresholds import AdaptiveThresholds
from .ml.clustering import classify_clusters, nearest_centroid
from .ml.features import VECTOR_LEN, extract_feature_vector
from .ml.multi_baseline import MultiBaseline
from .engine.timer_health import clamp_cycle_duration as _clamp_duration
from .repairs import async_check_repairs
from .storage.store import CycleStore

_LOGGER = logging.getLogger(__name__)


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


def _cop_confidence(count: int, duration_s: float | None) -> str:
    """Classify confidence from in-cycle tick density (Q6)."""
    if count < COP_MIN_TICKS:
        return "none"
    if duration_s is None or duration_s <= 0:
        return "low"
    expected = float(duration_s) / float(UPDATE_INTERVAL_SECONDS)
    return "high" if count >= expected * 0.5 else "low"


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
    try:
        record["quality_score"] = score_cycle(
            record, options, off_time_s=off_s
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
        self._setpoint_history: deque[tuple[float, float]] = deque()
        self._last_setpoint: float | None = None
        self._maintenance_unsub: Any = None
        self._baseline_save_unsub: Any = None
        self._kmeans_unsub: Any = None
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
        self._last_energy_tick_ts: float = 0.0
        # ---------- v1.6.0-C6b: cost caches ----------
        self._cost_month_cache: dict[str, Any] = {}
        self._cost_month_cache_ts: float = 0.0

        self.db: Any = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
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
            else int(opts.get('cycle_retention_days', 90))
        )
        adays = (
            int(alert_retention_days)
            if alert_retention_days is not None
            else int(opts.get('alert_retention_days', 30))
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
            if _now.weekday() != 6:
                return
            await self.async_run_kmeans()
        except Exception:
            _LOGGER.exception("Scheduled kmeans failed")

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
            return {"ok": False, "reason": "fetch_failed"}
        vectors = extract_many(cycles)
        if len(vectors) < 3:
            return {"ok": False, "reason": "too_few", "n": len(vectors)}
        try:
            result = kmeans(vectors, k=3)
        except Exception:
            _LOGGER.exception("kmeans run failed")
            return {"ok": False, "reason": "kmeans_failed"}
        payload = labels_to_dict(result)
        payload["ts"] = time.time()
        try:
            await self.db.async_set_model_state("kmeans_state", payload)
        except Exception:
            _LOGGER.exception("kmeans save failed")
        return {"ok": True, "n": len(vectors), "k": result.k}
    def _read_power(self) -> float | None:
        if not self.power_sensor:
            return None
        state = self.hass.states.get(self.power_sensor)
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _read_power_w(self) -> float | None:
        """FEAT-2: read power sensor and normalize to Watt."""
        if not self.power_sensor:
            return None
        state = self.hass.states.get(self.power_sensor)
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

    async def _async_update_data(self) -> DataSnapshot:
        now = time.time()
        snap = DataSnapshot(last_sample_ts=now)
        self.store.daily_reset_if_needed(now)
        # v1.6.0-C6a: persist OLD-day accumulators BEFORE reset
        _day_now = time.strftime("%Y-%m-%d", time.localtime(float(now)))
        if self._runtime_day_key and self._runtime_day_key != _day_now:
            await self._persist_runtime_acc()
            await self._persist_energy_acc()
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
            self._track_setpoint(attrs)
            snap.power_w = self._read_power_w()
            snap.cop = self._read_cop()
            snap.setpoint_oscillating = self._compute_setpoint_oscillating()
            record = self.detector.update(
                attrs, now=now, power_w=self._read_power()
            )
            self._accumulate_cycle_samples(attrs)
            if record is not None:
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
                _safe_float_opt((snap.last_record or {}).get("outdoor_temp")),
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
        """Read-only snapshot of energy accumulators (R216)."""
        acc = self._ensure_energy_acc()
        return {mode: dict(vals) for mode, vals in acc.items()}

    def _ensure_energy_acc(self) -> dict[str, dict[str, float]]:
        """Return the instance-owned energy accumulator dict.

        Lazy-init: needed because __new__-based tests skip __init__.
        Without this, _tick_energy would mutate a class-shared dict.
        """
        acc = self.__dict__.get("_energy_acc")
        if acc is None:
            acc = {
                "heating": {"th": 0.0, "el": 0.0},
                "dhw":     {"th": 0.0, "el": 0.0},
                "cooling": {"th": 0.0, "el": 0.0},
            }
            self._energy_acc = acc
        return acc

    def _maybe_reset_daily_accumulators(self, now: float) -> None:
        """Reset runtime + energy accumulators on local-day boundary.

        Persist-before-reset is done by _async_update_data.
        Throttled persist after each tick via _maybe_persist_accumulators.
        """
        day = time.strftime("%Y-%m-%d", time.localtime(float(now)))
        if self._runtime_day_key == day:
            return
        self._runtime_day_key = day
        self._buh_step1_s = 0.0
        self._buh_step2_s = 0.0
        self._prev_defrost = False
        self._defrost_start_ts = None
        self._defrost_count_today = 0
        self._defrost_duration_s = 0.0
        self._energy_day_key = day
        self._energy_acc = {
            "heating": {"th": 0.0, "el": 0.0},
            "dhw":     {"th": 0.0, "el": 0.0},
            "cooling": {"th": 0.0, "el": 0.0},
        }

    async def _persist_runtime_acc(self) -> None:
        """Persist runtime accumulators to model_state. Never raises."""
        if self.db is None or not self._runtime_day_key:
            return
        try:
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
        """Persist energy accumulators to model_state. Never raises."""
        if self.db is None or not self._energy_day_key:
            return
        try:
            payload: dict[str, Any] = {"day": self._energy_day_key}
            for mode in ("heating", "dhw", "cooling"):
                payload[f"{mode}_th_kwh"] = self._energy_acc[mode]["th"]
                payload[f"{mode}_el_kwh"] = self._energy_acc[mode]["el"]
            await self.db.async_set_model_state(
                f"energy_acc.{self._energy_day_key}", payload
            )
        except Exception:
            _LOGGER.exception("energy_acc persist failed")

    async def _maybe_persist_accumulators(self, now: float) -> None:
        """Persist runtime + energy accumulators throttled at 300s.

        Called from _async_update_data after each tick. Without this,
        accumulators are lost on HA restart (C5a known gap).
        """
        interval = 300.0
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
            dt_s = max(0.0, min(now - last, 120.0))
            self._last_runtime_tick_ts = now
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
            dt_s = max(0.0, min(now - last, 120.0))
            self._last_energy_tick_ts = now
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
            if kw_el is not None:
                acc[m]["el"] += kw_el * dt_s / 3600.0
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
        """Return (cop_avg, lwt_avg, indoor_temp_avg) for a closed cycle."""
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
        cop_avg, cop_stdev = _weighted_mean_stdev(
            self._cycle_cop_w_sum,
            self._cycle_cop_weight_sum,
            self._cycle_cop_sq_w_sum,
        )
        cop_count = self._cycle_cop_count
        self._cycle_cop_w_sum = 0.0
        self._cycle_cop_weight_sum = 0.0
        self._cycle_cop_sq_w_sum = 0.0
        self._cycle_cop_count = 0
        if cop_count < COP_MIN_TICKS and self.db is not None:
            start_ts = record.get("start_ts")
            end_ts = record.get("end_ts")
            if isinstance(start_ts, (int, float)) and isinstance(
                end_ts, (int, float)
            ):
                try:
                    if hasattr(self.db, "async_avg_cop_between"):
                        fallback = await self.db.async_avg_cop_between(
                            float(start_ts), float(end_ts)
                        )
                        if fallback is not None:
                            cop_avg = fallback
                except Exception:
                    _LOGGER.debug(
                        "cop_avg lookup failed", exc_info=True
                    )
        record["cop_avg"] = cop_avg
        record["cop_sample_count"] = cop_count if cop_count > 0 else None
        record["cop_sample_stdev"] = cop_stdev
        record["cop_confidence"] = _cop_confidence(
            cop_count, record.get("duration_s")
        )
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
        cop_avg, lwt_avg, indoor_avg = await self._collect_cycle_averages(record)
        try:
            vector = extract_feature_vector(record, cop_avg=cop_avg,
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
                _LOGGER.warning("adaptive observe_cycle failed", exc_info=True)
            per_mode = self.baseline.get(mode)
            per_mode.update(vector)
            result = evaluate_anomaly(vector, per_mode, self.options)
            snap.anomaly = result
            if self.options.get("action_advice_enabled", True):
                snap.advice = generate_advice(
                    result, record, mode=snap.mode, options=self.options
                )
        except Exception:
            _LOGGER.exception("ML pipeline failed")

        if self.db is None:
            return
        try:
            cid = await self.db.async_insert_cycle(record)
            if cid is not None:  # pragma: no branch
                vec = extract_feature_vector(
                    record,
                    cop_avg=cop_avg,
                    lwt_avg=lwt_avg,
                    indoor_temp_avg=indoor_avg,
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
                    _LOGGER.warning("cluster assign failed", exc_info=True)
        except Exception:
            _LOGGER.exception("DB persist failed")

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
                    and (mode is None or r.get('mode') == mode)
                ]
                if not todays:
                    return {}
                cops = [float(r['cop']) for r in todays]
                avg = sum(cops) / len(cops)
                week_cops = [
                    float(r['cop']) for r in week
                    if isinstance(r.get('cop'), (int, float))
                    and float(r['cop']) > 0.0
                    and (mode is None or r.get('mode') == mode)
                ]
                base = sum(week_cops) / len(week_cops) if week_cops else avg
                loss = 0.0
                if base > 0:  # pragma: no branch
                    loss = round(max(0.0, (base - avg) / base * 100.0), 1)
                return {
                    'cop': round(avg, 2),
                    'samples_today': len(cops),
                    'cop_min': round(min(cops), 2),
                    'cop_max': round(max(cops), 2),
                    'baseline_cop_verlies_pct': loss,
                }

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
        self._datasheet_merged = _merge_datasheets(
            _load_bundled_datasheets(), self._datasheet_user
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
                self._datasheet_merged = _merge_datasheets(
                    _load_bundled_datasheets(), {}
                )
                self._datasheet_user_loaded = True
        if not self._datasheet_defaults:
            self._datasheet_defaults = _load_datasheet_defaults()
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
                        'comfort_cap': 3.0,
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
        if float(cop) >= 2.5:
            return
        samples = cop_today.get('samples_today') or 0
        if samples < 3:
            return
        last = self._last_alert_sent.get('cop_low', 0.0)
        if (now - last) < 20 * 3600.0:
            return
        from types import SimpleNamespace

        from .engine.notification_engine import build_cop_low_message
        msg = build_cop_low_message(float(cop), int(samples))
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
        if betrouw < 0.7 or besparing < 5.0:
            return
        last = self._last_alert_sent.get('stooklijn_advies', 0.0)
        if (now - last) < 20 * 3600.0:
            return
        from types import SimpleNamespace

        from .engine.notification_engine import build_stooklijn_message
        msg = build_stooklijn_message(cache)
        alert = SimpleNamespace(
            persistent=True,
            message=msg,
            notif_id='daikin_stooklijn',
            alert_type='stooklijn_advies',
        )
        try:
            await self._emit_alert(alert)
            self._last_alert_sent['stooklijn_advies'] = now
        except Exception:
            _LOGGER.exception('stooklijn notify failed')

    def _resolve_cop_sample_mode(self) -> str:
        """Return mode string for cop_samples row.

        Bug I (batch 52b7): snap.mode is 'unknown' during active DHW cycles.
        Fall back to classify_mode(snap.attrs), which reads I/U operation mode.
        """
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
        interval = 300.0
        if (now - self._last_cop_sample_ts) < interval:
            return
        state = self.hass.states.get(self.cop_sensor_entity)
        if state is None:
            return
        raw = state.state
        if raw in (None, 'unknown', 'unavailable', '', '0.0', '0'):
            return
        attrs = dict(state.attributes or {})
        attrs['state'] = raw
        from .engine.cop_analyzer import parse_global_cop_attrs
        sample = parse_global_cop_attrs(attrs)
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
            'flow_lmin': sample.flow_lmin,
            'power_stable': True,
            'mode': str(_mode),
            'source': 'interval',
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
        return len(hist) >= th

    def _alert_binary_states(self, snap: DataSnapshot) -> dict[str, bool]:
        """Snapshot the 4 alert-relevant binary states."""
        now = time.time()
        short_run_th = self._effective_threshold(
            "short_run_threshold_min",
            int(self.options.get("short_run_threshold_min", 20)),
        ) * 60
        short_off_th = self._effective_threshold(
            "good_off_threshold_min",
            int(self.options.get("short_off_threshold_min", 5)),
        ) * 60
        pend_hour = int(self.options.get("pendulum_cycles_per_hour", 4))
        pend_day = self._effective_threshold(
            "target_cycles_per_day",
            int(self.options.get("pendulum_cycles_per_day", 40)),
        )

        last = self.store.last_cycle()
        dur = (last or {}).get("duration_s")
        is_short_run = isinstance(dur, (int, float)) and dur < short_run_th
        off = self.store.off_time_since_last(now)
        is_short_off = off is not None and off < short_off_th
        is_pend_h = self.store.cycles_in_window(now, 3600) >= pend_hour
        is_pend_d = len(self.store.cycles_today(now)) >= pend_day
        is_ml_anom = bool(
            getattr(snap, "anomaly", None)
            and getattr(snap.anomaly, "is_anomaly", False)
        )
        return {
            "short_run": bool(is_short_run),
            "short_off": bool(is_short_off),
            "pendulum_hourly": bool(is_pend_h),
            "pendulum_daily": bool(is_pend_d),
            "ml_anomaly": is_ml_anom,
            "setpoint_osc": self._compute_setpoint_oscillating(),
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
            a = getattr(snap, "attributes", None)
            if isinstance(a, dict):
                attrs = a
            elif hasattr(snap, "raw_attrs"):
                a2 = getattr(snap, "raw_attrs", None)
                if isinstance(a2, dict):
                    attrs = a2
        for k in keys:
            v = attrs.get(k)
            if v is not None:
                return v
        return None

    def _setpoint_current(self, snap: Any) -> Any:
        v = self._snap_attr(snap,
            "lwt_setpoint", "target_lwt", "lw_setpoint",
            "ATTR_LWT_SETPOINT", "setpoint")
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
            "ATTR_TARGET_LWT", "target_cond_temp")

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

    def _avg_duration_min(self) -> int | None:
        try:
            last = self.store.last_cycle()
            if isinstance(last, dict):
                d = last.get("duration_s")
                if d is not None:
                    return int(float(d) / 60)
        except Exception:
            _LOGGER.debug("avg_duration_min failed", exc_info=True)
        return None

    def _build_alert_context(self, snap: Any) -> dict[str, Any]:
        opts = self.options or {}
        now = time.time()
        cph = 0
        cyc_today = 0
        with contextlib.suppress(Exception):
            cph = int(self.store.cycles_in_window(now, 3600))
        with contextlib.suppress(Exception):
            cyc_today = len(self.store.cycles_today(now))
        advice_text = ""
        advice_list = (getattr(snap, "advice", None) or []) if snap else []
        if advice_list:
            _first = advice_list[0]
            _t = (getattr(_first, 'title', None)
                  or getattr(_first, 'text', None) or '')
            if _t:
                advice_text = "\n\u2022 " + str(_t)
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
        lwt_set = self._setpoint_current(snap)
        lwt_tgt = self._setpoint_target(snap)
        delta = self._setpoint_delta(snap)
        out_t = self._snap_attr(snap, "outdoor_temp", "outdoor", "ATTR_OUTDOOR")
        lwt_act = self._snap_attr(snap, "leaving_water_temp", "lwt", "ATTR_LWT")
        in_t = self._snap_attr(snap, "indoor_temp", "indoor", "ATTR_INDOOR")
        flow = self._snap_attr(snap, "flow_lmin", "flow", "ATTR_FLOW")
        avg_dur = self._avg_duration_min()

        def _f(v: Any, digits: int = 1) -> str:
            if v is None:
                return "\u2014"
            try:
                return ("%." + str(digits) + "f") % float(v)
            except (TypeError, ValueError):
                return "\u2014"

        ctx = {
            "pendulum": {
                "target_cph": opts.get("pendulum_cycles_per_hour", 4),
                "target_cpd": opts.get("pendulum_cycles_per_day", 40),
                "cph": cph, "cycles_today": cyc_today,
                "mode": mode_str, "lwt_setpoint": _f(lwt_set),
                "avg_duration_min": avg_dur if avg_dur is not None else "\u2014",
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "pendulum_hourly": {
                "target_cph": opts.get("pendulum_cycles_per_hour", 4),
                "target_cpd": opts.get("pendulum_cycles_per_day", 40),
                "cph": cph, "cycles_today": cyc_today,
                "mode": mode_str, "lwt_setpoint": _f(lwt_set),
                "avg_duration_min": avg_dur if avg_dur is not None else "\u2014",
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "pendulum_daily": {
                "target_cph": opts.get("pendulum_cycles_per_hour", 4),
                "target_cpd": opts.get("pendulum_cycles_per_day", 40),
                "cph": cph, "cycles_today": cyc_today,
                "mode": mode_str, "lwt_setpoint": _f(lwt_set),
                "avg_duration_min": avg_dur if avg_dur is not None else "\u2014",
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "short_run": {
                "threshold_min": opts.get("short_run_threshold_min", 20),
                "duration_min": "\u2014", "mode": mode_str,
                "lwt_setpoint": _f(lwt_set), "lwt_actual": _f(lwt_act),
                "indoor": _f(in_t), "flow": _f(flow),
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "short_off": {
                "threshold_min": opts.get("short_off_threshold_min", 5),
                "off_min": "\u2014", "mode": mode_str,
                "lwt_setpoint": _f(lwt_set),
                "indoor": _f(in_t), "flow": _f(flow),
                "outdoor": _f(out_t), "advice": advice_text,
            },
            "ml_anomaly": {
                "mode": mode_str, "z_max": "\u2014", "top_dim": "\u2014",
                "avg_duration_min": avg_dur if avg_dur is not None else "\u2014",
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
        }
        last = getattr(snap, "last_record", None) if snap is not None else None
        if isinstance(last, dict):
            dur = last.get("duration_s")
            if dur is not None:
                with contextlib.suppress(TypeError, ValueError):
                    ctx["short_run"]["duration_min"] = int(float(dur) / 60)
        try:
            off = self.store.off_time_since_last(now)
            if off is not None:
                ctx["short_off"]["off_min"] = int(off / 60)
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
            if getattr(anomaly, "severity", None):
                ctx["ml_anomaly"]["mode"] = str(
                    getattr(snap, "mode", "unknown")
                )
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
            msg = build_cop_low_message(2.1, 8)
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
            msg = build_stooklijn_message(fake)
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

        cop_msg = build_cop_low_report(2.10, 8, language=lang, emoji_enabled=emoji)
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
            states = self._alert_binary_states(snap)
            now = time.time()
            alerts = evaluate_alerts(
                states, self.options, now, self._last_alert_sent,
                context=self._build_alert_context(snap),
                language=self.options.get("notification_language", "en"),
            )
            for alert in alerts:
                await self._emit_alert(alert)
                self._last_alert_sent[alert.alert_type] = now
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
        ctx = getattr(alert, "context", None)
        if isinstance(ctx, dict):
            payload.update(ctx)
        try:
            await self.hass.services.async_call(
                domain, service, payload, blocking=False,
            )
            self._notify_fail_streak = 0
        except Exception:
            self._notify_fail_streak += 1
            self._notify_fail_target = str(svc)
            _LOGGER.exception("notify service %s failed", svc)
