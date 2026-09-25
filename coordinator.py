"""DataUpdateCoordinator for Daikin Cycle ML."""
from __future__ import annotations

import logging
import time
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

from .const import (
    COP_SENSOR_ENTITY,
    DOMAIN,
    MODEL_BASISPROFIEL,
    SOURCE_SENSOR_ENTITY,
    UPDATE_INTERVAL_SECONDS,
)
from .engine.action_engine import generate_advice
from .engine.anomaly_engine import evaluate as evaluate_anomaly
from .engine.attribute_reader import missing_required, read
from .engine.cycle_detector import CycleDetector
from .engine.model_profiles import defaults_for
from .engine.notification_engine import build_status_message, evaluate_alerts
from .ml.adaptive_thresholds import AdaptiveThresholds
from .ml.multi_baseline import MultiBaseline
from .ml.clustering import classify_clusters, nearest_centroid
from .ml.features import VECTOR_LEN, extract_feature_vector
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


class DaikinCycleMLCoordinator(DataUpdateCoordinator[DataSnapshot]):
    """Reads the source sensor every UPDATE_INTERVAL_SECONDS."""

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
        self.detector = CycleDetector(self.options)
        self.store = CycleStore()
        self._errors_total = 0
        self._last_alert_sent: dict[str, float] = {}
        self._maintenance_unsub: Any = None
        self._baseline_save_unsub: Any = None
        self._kmeans_unsub: Any = None
        self._status_update_unsub: Any = None
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

    async def _async_maintenance_callback(self, _now) -> None:
        try:
            await self.async_run_maintenance()
        except Exception:  # noqa: BLE001
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
        except Exception:  # noqa: BLE001
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
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception('Maintenance failed: %s', err)
            return {'ok': False, 'reason': 'exception', 'error': str(err)}
        try:
            await self.db.async_set_model_state('last_maintenance_ts', now)
        except Exception:  # noqa: BLE001
            _LOGGER.exception('model_state write failed')
        out = {'ok': True, 'ts': now}
        if isinstance(result, dict):
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
                ):
                    await self.db.async_ensure_cluster_column()
                await self._load_kmeans_state()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("cluster state setup failed", exc_info=True)
        if self._baseline_save_unsub is None:
            self._baseline_save_unsub = async_track_time_interval(
                self.hass,
                self._async_baseline_save_callback,
                timedelta(hours=6),
            )

    async def _async_baseline_save_callback(self, _now) -> None:
        try:
            await self.async_save_baseline_state()
        except Exception:
            _LOGGER.exception("Scheduled baseline save failed")

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

    async def _async_kmeans_callback(self, _now) -> None:
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
        from .ml.features import extract_many
        from .ml.clustering import kmeans, labels_to_dict
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

    async def _async_update_data(self) -> DataSnapshot:
        now = time.time()
        snap = DataSnapshot(last_sample_ts=now)
        self.store.daily_reset_if_needed(now)
        try:
            state = self.hass.states.get(self.source_entity)
            if state is None:
                return snap
            attrs = read(state)
            snap.attrs = attrs
            snap.missing_attrs = missing_required(attrs)
            snap.last_success_ts = now
            record = self.detector.update(
                attrs, now=now, power_w=self._read_power()
            )
            if record is not None:
                self.store.add_cycle(record)
                snap.last_record = record
                await self._process_new_cycle(record, snap)
            snap.state = self.detector.state
            snap.mode = self.detector.snapshot().get("mode", "unknown")
            snap.cycle_start_ts = float(
                self.detector.snapshot().get("start_ts") or 0.0
            )
            await self._maybe_collect_cop_sample(now)
            await self._refresh_cop_today(now)
            await self._maybe_refresh_stooklijn(now)
            snap.cop_today = self._cop_today_cache
            snap.stooklijn_advies = self._stooklijn_cache
            snap.errors_total = self._errors_total
            await self._async_dispatch_alerts(snap)
            await async_check_repairs(
                self.hass, self.entry.entry_id, snap
            )
        except Exception as err:  # noqa: BLE001
            snap.errors = 1
            self._errors_total += 1
            snap.errors_total = self._errors_total
            _LOGGER.exception("Coordinator update failed: %s", err)
        return snap

    # ---------- Batch 7c ML pipeline ----------

    async def _process_new_cycle(
        self, record: dict[str, Any], snap: DataSnapshot
    ) -> None:
        """Update baseline, detect anomaly, generate advice, persist."""
        try:
            vector = extract_feature_vector(record)
            mode = record.get("mode") or snap.mode or "unknown"
            try:
                self.adaptive.observe_cycle(
                    mode,
                    record.get("duration_s"),
                    record.get("off_s"),
                )
            except Exception:  # noqa: BLE001
                _LOGGER.debug("adaptive observe_cycle failed", exc_info=True)
            per_mode = self.baseline.get(mode)
            per_mode.update(vector)
            result = evaluate_anomaly(vector, per_mode, self.options)
            snap.anomaly = result
            snap.advice = generate_advice(
                result, record, mode=snap.mode, options=self.options
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("ML pipeline failed")

        if self.db is None:
            return
        try:
            cid = await self.db.async_insert_cycle(record)
            if cid is not None:
                vec = extract_feature_vector(record)
                await self.db.async_insert_features(cid, vec)
                try:
                    cid_val = self._assign_cluster(vec)
                    if cid_val is not None:
                        snap.cluster_id = cid_val
                        await self.db.async_update_cycle_cluster(
                            cid, cid_val
                        )
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("cluster assign failed", exc_info=True)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("DB persist failed")

    async def _refresh_cop_today(self, now: float) -> None:
        if self.db is None:
            return
        try:
            rows = await self.db.async_fetch_cop_samples(days=1)
        except Exception:  # noqa: BLE001
            return
        if not isinstance(rows, list) or not rows:
            self._cop_today_cache = {}
            return
        try:
            lt = time.localtime(now)
            today_start = time.mktime(
                (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
            )
            todays = [
                r for r in rows
                if isinstance(r.get('ts'), (int, float))
                and float(r['ts']) >= today_start
                and isinstance(r.get('cop'), (int, float))
                and float(r['cop']) > 0.0
            ]
            if not todays:
                self._cop_today_cache = {}
                return
            cops = [float(r['cop']) for r in todays]
            avg = sum(cops) / len(cops)
            try:
                week = await self.db.async_fetch_cop_samples(days=7)
            except Exception:  # noqa: BLE001
                week = rows
            week_cops = [
                float(r['cop']) for r in week
                if isinstance(r.get('cop'), (int, float))
                and float(r['cop']) > 0.0
            ]
            base = sum(week_cops) / len(week_cops) if week_cops else avg
            loss = 0.0
            if base > 0:
                loss = round(max(0.0, (base - avg) / base * 100.0), 1)
            self._cop_today_cache = {
                'cop': round(avg, 2),
                'samples_today': len(cops),
                'cop_min': round(min(cops), 2),
                'cop_max': round(max(cops), 2),
                'baseline_cop_verlies_pct': loss,
            }
        except Exception:  # noqa: BLE001
            self._cop_today_cache = {}

    async def _maybe_refresh_stooklijn(self, now: float) -> None:
        if self.db is None:
            return
        cache_ts = getattr(self, '_stooklijn_cache_ts', 0.0)
        cache = getattr(self, '_stooklijn_cache', {})
        if (now - cache_ts) < 3600.0 and cache:
            return
        try:
            rows = await self.db.async_fetch_cop_samples(days=30)
        except Exception:  # noqa: BLE001
            return
        if not isinstance(rows, list):
            return
        try:
            from .engine.cop_analyzer import (
                CopSample, analyze_stooklijn, bucket_summary,
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
                ))
            comfort_min = float(
                self.options.get('comfort_min_c', 20.0)
            )
            advies = analyze_stooklijn(samples, comfort_min=comfort_min)
            buckets = bucket_summary(samples)
            self._stooklijn_cache = {
                'state': advies.state,
                'optimale_lwt': advies.optimale_lwt,
                'huidige_lwt': advies.huidige_lwt,
                'besparing_cop_pct': advies.besparing_cop_pct,
                'comfort_impact': advies.comfort_impact,
                'betrouwbaarheid': advies.betrouwbaarheid,
                'bucket': advies.bucket,
                'samples': advies.samples,
                'buckets': buckets,
            }
            self._stooklijn_cache_ts = now
        except Exception:  # noqa: BLE001
            return

    async def _maybe_collect_cop_sample(self, now: float) -> None:
        if self.db is None:
            return
        interval = 600.0
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
        row = {
            'ts': now,
            'cop': sample.cop,
            'lwt': sample.lwt,
            'outdoor': sample.outdoor,
            'flow_lmin': sample.flow_lmin,
            'power_stable': True,
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
        except Exception:  # noqa: BLE001
            return default
        return int(learned.get(key, default))

    async def async_save_adaptive_state(self) -> bool:  # pragma: no cover
        if self.db is None:
            return False
        try:
            from .const import MODEL_STATE_ADAPTIVE
            await self.db.async_set_model_state(
                MODEL_STATE_ADAPTIVE, self.adaptive.to_dict()
            )
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.exception("adaptive save failed")
            return False

    async def async_load_adaptive_state(self) -> bool:  # pragma: no cover
        if self.db is None:
            return False
        try:
            from .const import MODEL_STATE_ADAPTIVE
            data = await self.db.async_get_model_state(MODEL_STATE_ADAPTIVE)
            if data:
                self.adaptive = AdaptiveThresholds.from_dict(data)
                return True
        except Exception:  # noqa: BLE001
            _LOGGER.exception("adaptive load failed")
        return False

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
        return {
            "short_run": bool(is_short_run),
            "short_off": bool(is_short_off),
            "pendulum_hourly": bool(is_pend_h),
            "pendulum_daily": bool(is_pend_d),
        }

    def _assign_cluster(self, vector: list[float]) -> int | None:  # pragma: no cover
        if not self._kmeans_centroids:
            return None
        try:
            return nearest_centroid(vector, self._kmeans_centroids)
        except Exception:  # noqa: BLE001
            return None

    def cluster_label(self, cluster_id: int | None) -> str | None:  # pragma: no cover
        if cluster_id is None:
            return None
        return self._cluster_labels.get(cluster_id)

    async def _load_kmeans_state(self) -> bool:  # pragma: no cover
        if self.db is None:
            return False
        try:
            data = await self.db.async_get_model_state("kmeans_state")
            if not data:
                return False
            centroids = data.get("centroids") or []
            if not centroids:
                return False
            self._kmeans_centroids = [
                [float(x) for x in c] for c in centroids
            ]
            self._cluster_labels = classify_clusters(
                self._kmeans_centroids
            )
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.debug("load kmeans_state failed", exc_info=True)
            return False

    async def async_setup_status_updates(self) -> None:  # pragma: no cover
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
        if hours < 1:
            hours = 1
        from datetime import timedelta
        self._status_update_unsub = async_track_time_interval(
            self.hass,
            self._async_status_update_callback,
            timedelta(hours=hours),
        )
        _LOGGER.info("status updates scheduled every %sh", hours)

    async def _async_status_update_callback(self, _now) -> None:  # pragma: no cover
        try:
            await self.async_emit_status_update()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Scheduled status update failed")

    async def async_emit_status_update(self) -> str:  # pragma: no cover
        """Build and dispatch one status summary. Returns message."""
        from .const import NOTIF_ID_STATUS

        snap_dict = self._build_status_snapshot()
        opts = self.options or {}
        emoji = bool(opts.get("notify_emoji_enabled", True))
        msg = build_status_message(snap_dict, emoji_enabled=emoji)

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
        except Exception:  # noqa: BLE001
            _LOGGER.exception("status persistent_notification failed")

        svc = opts.get("notify_service")
        if svc and "." in str(svc):
            try:
                dom, name = str(svc).split(".", 1)
                await self.hass.services.async_call(
                    dom, name, {"message": msg}, blocking=False
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("status notify service failed")

        return msg

    def _build_status_snapshot(self) -> dict:  # pragma: no cover
        import time as _t
        snap = self.data
        store = self.store
        counters = {}
        if store is not None and hasattr(store, "counters_snapshot"):
            try:
                counters = store.counters_snapshot()
            except Exception:  # noqa: BLE001
                counters = {}
        last = None
        if store is not None and hasattr(store, "last_cycle"):
            try:
                last = store.last_cycle()
            except Exception:  # noqa: BLE001
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
            top_advice = getattr(first, "text", None) or str(first)
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

    def _build_alert_context(self, snap) -> dict:  # pragma: no cover
        opts = self.options or {}
        ctx = {
            "pendulum": {
                "target_cph": opts.get("pendulum_cycles_per_hour", 4),
                "target_cpd": opts.get("pendulum_cycles_per_day", 40),
                "cph": "?",
                "cycles_today": "?",
            },
            "short_run": {
                "threshold_min": opts.get("short_run_threshold_min", 20),
                "duration_min": "?",
            },
            "short_off": {
                "threshold_min": opts.get("short_off_threshold_min", 5),
                "off_min": "?",
            },
        }
        last = getattr(snap, "last_record", None) if snap is not None else None
        if isinstance(last, dict):
            dur = last.get("duration_s")
            if dur is not None:
                try:
                    ctx["short_run"]["duration_min"] = int(float(dur) / 60)
                except (TypeError, ValueError):
                    pass
        return ctx

    async def _async_dispatch_alerts(self, snap: DataSnapshot) -> None:
        """Evaluate + emit alerts. Never raises."""
        try:
            states = self._alert_binary_states(snap)
            now = time.time()
            alerts = evaluate_alerts(
                states, self.options, now, self._last_alert_sent,
                context=self._build_alert_context(snap),
            )
            for alert in alerts:
                await self._emit_alert(alert)
                self._last_alert_sent[alert.alert_type] = now
        except Exception:  # noqa: BLE001
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
            except Exception:  # noqa: BLE001
                _LOGGER.exception("persistent_notification failed")
        svc = self.options.get("notify_service")
        if not (isinstance(svc, str) and "." in svc):
            return
        domain, service = svc.split(".", 1)
        try:
            await self.hass.services.async_call(
                domain, service, {"message": alert.message}, blocking=False,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("notify service %s failed", svc)
