"""Constants for the Daikin Cycle ML integration."""
from __future__ import annotations

DOMAIN = "daikin_cycle_ml"
NAME = "Daikin Cycle ML"
VERSION = "1.16.0"

# --- Coordinator ---
UPDATE_INTERVAL_SECONDS = 30

# R288: dt_s cap and warning threshold for energy accumulator.
ENERGY_DT_CAP_S = 300.0
# R315 safety net: force-close runaway cycles (stuck pump signal, etc).
# 48h covers legitimate long modulating runs (weather-compensated
# Daikin units routinely exceed 18h in steady winter operation);
# still caps true runaway cycles that never report pump-off.
MAX_CYCLE_DURATION_S = 48 * 3600.0

# --- Sanity gates for cycle aggregates (#129, #124) ---
# COP: MIN+MAX in _collect_cycle_averages; Thermal: MAX only.
MIN_SAMPLES_FOR_AVG = 3
MAX_COP = 11.0
MAX_THERMAL_KW = 14.0
"""Absolute maximum cycle duration before forced close (R315)."""
ENERGY_DT_WARN_S = 60.0
ENERGY_PERSIST_INTERVAL_S = 30.0

# v1.12.0 (#105): transient cycle classification thresholds
# A cycle is transient if: duration < TRANSIENT_MAX_DURATION_S
# OR (duration < TRANSIENT_NEAR_MAX_DURATION_S
#     AND dT_max < TRANSIENT_NEAR_MAX_DT_K
#     AND rps_max >= TRANSIENT_NEAR_MIN_RPS)
TRANSIENT_MAX_DURATION_S = 120
TRANSIENT_NEAR_MAX_DURATION_S = 300
TRANSIENT_NEAR_MAX_DT_K = 3.0
TRANSIENT_NEAR_MIN_RPS = 40.0

# --- Source sensor ---
SOURCE_SENSOR_ENTITY = "sensor.althermasensors"

# --- Defaults: cycle detection ---
DEFAULT_COMPRESSOR_RPS_THRESHOLD = 3
DEFAULT_FALLBACK_POWER_THRESHOLD_W = 200
DEFAULT_MAX_CYCLE_DURATION_MIN = int(MAX_CYCLE_DURATION_S // 60)

# --- Defaults: pendulum thresholds ---
DEFAULT_SHORT_RUN_MIN = 20
DEFAULT_SHORT_OFF_MIN = 5
DEFAULT_SHORT_CYCLE_RATIO = 50
DEFAULT_PENDULUM_CPH = 4
DEFAULT_PENDULUM_CPD = 40
DEFAULT_DHW_PENDULUM_CPH = 3
DEFAULT_DEFROST_INTERVAL_MIN = 30
DEFAULT_SETPOINT_OSC_THRESHOLD = 6

# --- Defaults: quality thresholds ---
DEFAULT_GOOD_RUN_MIN = 45
DEFAULT_GOOD_DT_K = 5.0
DEFAULT_GOOD_OFF_MIN = 20
DEFAULT_TARGET_CYCLES_PER_DAY = 8
DEFAULT_GOOD_CYCLE_RATIO = 60

# v1.4.1 BUG-3: score threshold for good-cycle counter.
GOOD_CYCLE_MIN_SCORE = 70

# --- Defaults: notifications ---
DEFAULT_PERSISTENT_ENABLED = True
DEFAULT_NOTIFY_SERVICE = ""
DEFAULT_QUIET_HOURS_ENABLED = False
DEFAULT_QUIET_HOURS_START = "22:00"
DEFAULT_QUIET_HOURS_END = "07:00"
DEFAULT_ALERT_AGGREGATION_MIN = 30
DEFAULT_ACTION_ADVICE_ENABLED = True
DEFAULT_RETENTION_ENABLED = True
DEFAULT_CYCLE_RETENTION_DAYS = 90
DEFAULT_ALERT_RETENTION_DAYS = 90
KMEANS_STALE_AFTER_DAYS = 14

# --- I6 (v1.9.0): energy_daily_anomaly ---
ENERGY_ANOMALY_SIGMA_THRESHOLD = 2.0
ENERGY_ANOMALY_FLOOR_KWH = 2.0  # electrical, absolute
ENERGY_ANOMALY_MIN_DAYS = 7
DEFAULT_VACUUM_ENABLED = True

# --- Model identifiers ---
MODEL_BASISPROFIEL = "basisprofiel"
MODEL_EPRA12EAV3 = "epra12eav3"
MODEL_EPRA08EAV3 = "epra08eav3"
MODEL_ERLA11DAV3 = "erla11dav3"
MODEL_CUSTOM = "custom"

MODEL_EPRA04EAV3 = "epra04eav3"
MODEL_EPRA06EAV3 = "epra06eav3"
MODEL_EPRA10EAV3 = "epra10eav3"
MODEL_EPRA11EAV3 = "epra11eav3"
MODEL_EPRA14EAV3 = "epra14eav3"
MODEL_EPRA16EAV3 = "epra16eav3"
MODEL_ERLA04DAV3 = "erla04dav3"
MODEL_ERLA06DAV3 = "erla06dav3"
MODEL_ERLA08DAV3 = "erla08dav3"
MODEL_ERLA12DAV3 = "erla12dav3"
MODEL_ERLA14DAV3 = "erla14dav3"
MODEL_ERLA16DAV3 = "erla16dav3"
MODEL_ERGA04EAV3 = "erga04eav3"
MODEL_ERGA06EAV3 = "erga06eav3"
MODEL_ERGA08EAV3 = "erga08eav3"
MODEL_ERGA08EVH7 = "erga08evh7"
MODEL_EPGA10DAV3 = "epga10dav3"
MODEL_EPGA11DAV3 = "epga11dav3"
MODEL_EPGA14DAV3 = "epga14dav3"
MODEL_EPGA16DAV3 = "epga16dav3"
MODEL_EDLA09D3V3 = "edla09d3v3"
MODEL_EDLA11D3V3 = "edla11d3v3"
MODEL_EDLA14D3V3 = "edla14d3v3"
MODEL_EDLA16D3V3 = "edla16d3v3"
MODEL_EBLA04EV3 = "ebla04ev3"
MODEL_EBLA06EV3 = "ebla06ev3"
MODEL_EBLA08EV3 = "ebla08ev3"
MODEL_EBLA09DA3W1 = "ebla09da3w1"
MODEL_EDLQ05CV3 = "edlq05cv3"
MODEL_EDLQ07CV3 = "edlq07cv3"
MODEL_EDLQ11CV3 = "edlq11cv3"
MODEL_EDLQ14CV3 = "edlq14cv3"
MODEL_EDLQ16CV3 = "edlq16cv3"
MODEL_EPSK06AW1 = "epsk06aw1"
MODEL_EPSK08AW1 = "epsk08aw1"
MODEL_EPSK10AW1 = "epsk10aw1"
MODEL_EPSK12AW1 = "epsk12aw1"
MODEL_EPSK14AW1 = "epsk14aw1"
MODEL_EPRA18EAV3 = "epra18eav3"

# LT monobloc EBLQ CV3 (R-410A)
MODEL_EBLQ05CV3 = "eblq05cv3"
MODEL_EBLQ07CV3 = "eblq07cv3"
MODEL_EBLQ11CV3 = "eblq11cv3"
MODEL_EBLQ14CV3 = "eblq14cv3"
MODEL_EBLQ16CV3 = "eblq16cv3"

# HT split EKHBRD + ERRQ (R-410A, up to 80 C LWT)
MODEL_EKHBRD011 = "ekhbrd011"
MODEL_EKHBRD014 = "ekhbrd014"
MODEL_EKHBRD016 = "ekhbrd016"

# HT outdoor ERRQ-ERSQ (R-410A, up to 80 C LWT)
MODEL_ERRQ011 = "errq011"
MODEL_ERRQ014 = "errq014"
MODEL_ERRQ016 = "errq016"
MODEL_EVLQ05CV3 = "evlq05cv3"
MODEL_EVLQ08CV3 = "evlq08cv3"


MODEL_CHOICES = [
    MODEL_BASISPROFIEL,
    MODEL_EPRA04EAV3,
    MODEL_EPRA06EAV3,
    MODEL_EPRA08EAV3,
    MODEL_EPRA10EAV3,
    MODEL_EPRA11EAV3,
    MODEL_EPRA12EAV3,
    MODEL_EPRA14EAV3,
    MODEL_EPRA16EAV3,
    MODEL_ERLA04DAV3,
    MODEL_ERLA06DAV3,
    MODEL_ERLA08DAV3,
    MODEL_ERLA11DAV3,
    MODEL_ERLA12DAV3,
    MODEL_ERLA14DAV3,
    MODEL_ERLA16DAV3,
    MODEL_ERGA04EAV3,
    MODEL_ERGA06EAV3,
    MODEL_ERGA08EAV3,
    MODEL_ERGA08EVH7,
    MODEL_EPGA10DAV3,
    MODEL_EPGA11DAV3,
    MODEL_EPGA14DAV3,
    MODEL_EPGA16DAV3,
    MODEL_EDLA09D3V3,
    MODEL_EDLA11D3V3,
    MODEL_EDLA14D3V3,
    MODEL_EDLA16D3V3,
    MODEL_EBLA04EV3,
    MODEL_EBLA06EV3,
    MODEL_EBLA08EV3,
    MODEL_EBLA09DA3W1,
    MODEL_EDLQ05CV3,
    MODEL_EDLQ07CV3,
    MODEL_EDLQ11CV3,
    MODEL_EDLQ14CV3,
    MODEL_EDLQ16CV3,
    MODEL_EPSK06AW1,
    MODEL_EPSK08AW1,
    MODEL_EPSK10AW1,
    MODEL_EPSK12AW1,
    MODEL_EPSK14AW1,
    MODEL_EPRA18EAV3,
    MODEL_EBLQ05CV3,
    MODEL_EBLQ07CV3,
    MODEL_EBLQ11CV3,
    MODEL_EBLQ14CV3,
    MODEL_EBLQ16CV3,
    MODEL_EKHBRD011,
    MODEL_EKHBRD014,
    MODEL_EKHBRD016,
    MODEL_ERRQ011,
    MODEL_ERRQ014,
    MODEL_ERRQ016,
    MODEL_EVLQ05CV3,
    MODEL_EVLQ08CV3,
    MODEL_CUSTOM,
]

MODEL_LABELS = {
    MODEL_BASISPROFIEL: "Basic profile (safe defaults)",
    MODEL_EPRA04EAV3: "Daikin Altherma 3 H MT - EPRA04EAV3",
    MODEL_EPRA06EAV3: "Daikin Altherma 3 H MT - EPRA06EAV3",
    MODEL_EPRA08EAV3: "Daikin Altherma 3 H MT - EPRA08EAV3",
    MODEL_EPRA10EAV3: "Daikin Altherma 3 H MT - EPRA10EAV3",
    MODEL_EPRA11EAV3: "Daikin Altherma 3 H MT - EPRA11EAV3",
    MODEL_EPRA12EAV3: "Daikin Altherma 3 H MT - EPRA12EAV3",
    MODEL_EPRA14EAV3: "Daikin Altherma 3 H MT - EPRA14EAV3",
    MODEL_EPRA16EAV3: "Daikin Altherma 3 H MT - EPRA16EAV3",
    MODEL_ERLA04DAV3: "Daikin Altherma 3 R - ERLA04DAV3",
    MODEL_ERLA06DAV3: "Daikin Altherma 3 R - ERLA06DAV3",
    MODEL_ERLA08DAV3: "Daikin Altherma 3 R - ERLA08DAV3",
    MODEL_ERLA11DAV3: "Daikin Altherma 3 R - ERLA11DAV3",
    MODEL_ERLA12DAV3: "Daikin Altherma 3 R - ERLA12DAV3",
    MODEL_ERLA14DAV3: "Daikin Altherma 3 R - ERLA14DAV3",
    MODEL_ERLA16DAV3: "Daikin Altherma 3 R - ERLA16DAV3",
    MODEL_ERGA04EAV3: "Daikin Altherma 3 R - ERGA04EAV3 (Split)",
    MODEL_ERGA06EAV3: "Daikin Altherma 3 R - ERGA06EAV3 (Split)",
    MODEL_ERGA08EAV3: "Daikin Altherma 3 R - ERGA08EAV3 (Split)",
    MODEL_ERGA08EVH7: "Daikin Altherma 3 R - ERGA08EVH7 (Split)",
    MODEL_EPGA10DAV3: "Daikin Altherma 3 R - EPGA10DAV3 (Split high capacity)",
    MODEL_EPGA11DAV3: "Daikin Altherma 3 R - EPGA11DAV3 (Split high capacity)",
    MODEL_EPGA14DAV3: "Daikin Altherma 3 R - EPGA14DAV3 (Split high capacity)",
    MODEL_EPGA16DAV3: "Daikin Altherma 3 R - EPGA16DAV3 (Split high capacity)",
    MODEL_EDLA09D3V3: "Daikin Altherma 3 H HT - EDLA09D3V3",
    MODEL_EDLA11D3V3: "Daikin Altherma 3 H HT - EDLA11D3V3",
    MODEL_EDLA14D3V3: "Daikin Altherma 3 H HT - EDLA14D3V3",
    MODEL_EDLA16D3V3: "Daikin Altherma 3 H HT - EDLA16D3V3",
    MODEL_EBLA04EV3: "Daikin Altherma 3 H - EBLA04EV3",
    MODEL_EBLA06EV3: "Daikin Altherma 3 H - EBLA06EV3",
    MODEL_EBLA08EV3: "Daikin Altherma 3 H - EBLA08EV3",
    MODEL_EBLA09DA3W1: "Daikin Altherma 3 M - EBLA09DA3W1 (3-phase R32)",
    MODEL_EDLQ05CV3: "Daikin Altherma Monobloc - EDLQ05CV3",
    MODEL_EDLQ07CV3: "Daikin Altherma Monobloc - EDLQ07CV3",
    MODEL_EDLQ11CV3: "Daikin Altherma Monobloc - EDLQ11CV3",
    MODEL_EDLQ14CV3: "Daikin Altherma Monobloc - EDLQ14CV3",
    MODEL_EDLQ16CV3: "Daikin Altherma Monobloc - EDLQ16CV3",
    MODEL_EPSK06AW1: "Daikin Altherma 4 H - EPSK06AW1 (R290)",
    MODEL_EPSK08AW1: "Daikin Altherma 4 H - EPSK08AW1 (R290)",
    MODEL_EVLQ05CV3: "Daikin Altherma R Hybrid - EVLQ05CV3 (5kW)",
    MODEL_EVLQ08CV3: "Daikin Altherma R Hybrid - EVLQ08CV3 (8kW)",
    MODEL_EPSK10AW1: "Daikin Altherma 4 H - EPSK10AW1 (R290)",
    MODEL_EPSK12AW1: "Daikin Altherma 4 H - EPSK12AW1 (R290)",
    MODEL_EPSK14AW1: "Daikin Altherma 4 H - EPSK14AW1 (R290)",
    MODEL_EPRA18EAV3: "Daikin Altherma 3 H MT - EPRA18EAV3",
    MODEL_EBLQ05CV3: "Daikin Altherma Monobloc - EBLQ05CV3",
    MODEL_EBLQ07CV3: "Daikin Altherma Monobloc - EBLQ07CV3",
    MODEL_EBLQ11CV3: "Daikin Altherma Monobloc - EBLQ11CV3",
    MODEL_EBLQ14CV3: "Daikin Altherma Monobloc - EBLQ14CV3",
    MODEL_EBLQ16CV3: "Daikin Altherma Monobloc - EBLQ16CV3",
    MODEL_EKHBRD011: "Daikin Altherma HT - EKHBRD011 + ERRQ011",
    MODEL_EKHBRD014: "Daikin Altherma HT - EKHBRD014 + ERRQ014",
    MODEL_EKHBRD016: "Daikin Altherma HT - EKHBRD016 + ERRQ016",
    MODEL_ERRQ011: "Daikin Altherma HT outdoor - ERRQ011-ERSQ011",
    MODEL_ERRQ014: "Daikin Altherma HT outdoor - ERRQ014-ERSQ014",
    MODEL_ERRQ016: "Daikin Altherma HT outdoor - ERRQ016-ERSQ016",
    MODEL_CUSTOM: "Custom (own heat pump)",
}

# --- Core attribute keys (fixed set, not user-selectable) ---
ATTR_INV_FREQUENCY_RPS = "INV frequency (rps)"
ATTR_INV_FREQUENCY_2_RPS = "INV frequency 2 (rps)"
ATTR_OPERATION_MODE = "Operation Mode"
ATTR_IU_OPERATION_MODE = "I/U operation mode"
ATTR_3WAY_VALVE = "3way valve(On:DHW_Off:Space)"
ATTR_DEFROST_OPERATION = "Defrost Operation"
ATTR_LEAVING_WATER_AFTER_BUH = "Leaving water temp. after BUH (R2T)"
ATTR_INLET_WATER_R4T = "Inlet water temp.(R4T)"
ATTR_DHW_TANK_TEMP = "DHW tank temp. (R5T)"
ATTR_OUTDOOR_AIR_R1T = "Outdoor air temp.(R1T)"
ATTR_FLOW_SENSOR = "Flow sensor (l/min)"
ATTR_INDOOR_AMBIENT_R1T = "Indoor ambient temp. (R1T)"
ATTR_WATER_PUMP_OPERATION = "Water pump operation"
ATTR_BUH_STEP1 = "BUH Step1"
ATTR_BUH_STEP2 = "BUH Step2"
ATTR_LW_SETPOINT = "LW setpoint (main)"
ATTR_TARGET_COND_TEMP = "Target Cond. Temp."
# Hybrid (EVLQ series) — optional, only present on ALTHERMA(HYBRID).h
ATTR_BOILER_OPERATION_DEMAND = "Boiler Operation Demand"
ATTR_BOILER_DHW_DEMAND = "Boiler DHW Demand"
ATTR_HYBRID_OP_MODE = "Hybrid Op. Mode"
ATTR_BE_COP = "BE COP"
R5T_DISCONNECTED_THRESHOLD = -20.0

CORE_ATTRIBUTES = [
    ATTR_INV_FREQUENCY_RPS,
    ATTR_OPERATION_MODE,
    ATTR_IU_OPERATION_MODE,
    ATTR_3WAY_VALVE,
    ATTR_DEFROST_OPERATION,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_INLET_WATER_R4T,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_FLOW_SENSOR,
    ATTR_WATER_PUMP_OPERATION,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_LW_SETPOINT,
]

# Legacy alias — kept for backwards-compatible imports.
OPTIONAL_ATTRIBUTES = [
    ATTR_INV_FREQUENCY_RPS,
    ATTR_BOILER_OPERATION_DEMAND,
    ATTR_BOILER_DHW_DEMAND,
    ATTR_HYBRID_OP_MODE,
]

REQUIRED_ATTRIBUTES = [
    a for a in CORE_ATTRIBUTES if a not in OPTIONAL_ATTRIBUTES
]

# --- Config-flow attribute-mode ---
ATTRIBUTE_MODE_AUTO = "auto"
ATTRIBUTE_MODE_MANUAL = "manual"


# --- Operation-mode values (from ESPAltherma) ---
OP_MODE_FAN_ONLY = "Fan Only"
OP_MODE_HEATING = "Heating"
OP_MODE_COOLING = "Cooling"
OP_MODE_DHW = "DHW"

# Internal normalized mode strings (lowercase, match classify_mode())
MODE_HEATING = "heating"
MODE_COOLING = "cooling"
MODE_DHW = "dhw"
MODE_DEFROST = "defrost"
MODE_UNKNOWN = "unknown"

# --- Tracker states ---
STATE_IDLE = "idle"
STATE_RUNNING = "running"

# --- Notification IDs (fixed -> overwrite, no spam) ---
NOTIF_ID_PENDULUM_HOURLY = f"{DOMAIN}_pendulum_hourly"
NOTIF_ID_PENDULUM_DAILY = f"{DOMAIN}_pendulum_daily"
NOTIF_ID_SHORT_RUN = f"{DOMAIN}_short_run"
NOTIF_ID_SHORT_OFF = f"{DOMAIN}_short_off"
NOTIF_ID_ML_ANOMALY = f"{DOMAIN}_ml_anomaly"
NOTIF_ID_SETPOINT_OSC = f"{DOMAIN}_setpoint_osc"
NOTIF_ID_COP_DEGRADATION = f"{DOMAIN}_cop_degradation"
NOTIF_ID_DEFROST_EXCESSIVE = f"{DOMAIN}_defrost_excessive"
NOTIF_ID_BUH_EXCESSIVE = f"{DOMAIN}_buh_excessive"
NOTIF_ID_SOURCE_STALE = f"{DOMAIN}_source_stale"
NOTIF_ID_MISSING_ATTRIBUTES = f"{DOMAIN}_missing_attributes"
NOTIF_ID_DHW_PENDULUM = f"{DOMAIN}_dhw_pendulum"
NOTIF_ID_HIGH_CYCLE_RATE = f"{DOMAIN}_high_cycle_rate"
NOTIF_ID_COP_VS_DATASHEET_LOW = f"{DOMAIN}_cop_vs_datasheet_low"
NOTIF_ID_DB_RETENTION_WARNING = f"{DOMAIN}_db_retention_warning"
NOTIF_ID_KMEANS_RETRAIN_STALE = f"{DOMAIN}_kmeans_retrain_stale"
NOTIF_ID_ENERGY_DAILY_ANOMALY = f"{DOMAIN}_energy_daily_anomaly"

# --- Brine exclusion (confirmed absent on EPRA12: always 0) ---
BRINE_ALWAYS_ZERO = True

# --- 12c: notifications v2 + status updates ---
# Emoji constants: source uses backslash-U escapes to stay ASCII-only.
EMOJI_CRITICAL = "\U0001F534"
EMOJI_WARNING = "\U0001F7E0"
EMOJI_WATCH = "\U0001F7E1"
EMOJI_INFO = "\U0001F535"
EMOJI_OK = "\U0001F7E2"
EMOJI_STATUS = "\U0001F4CA"
EMOJI_PENDULUM = "\U0001F501"
EMOJI_SHORT_RUN = "\u23F1"
EMOJI_SHORT_OFF = "\U0001F4A4"
EMOJI_ML_ANOMALY = "\U0001F9E0"
EMOJI_SETPOINT = "\U0001F3AF"
EMOJI_DHW_PENDULUM = "\U0001F6BF"
EMOJI_HIGH_CYCLE_RATE = "\U0001F504"
EMOJI_COP_VS_DATASHEET = "\U0001F4CA"

SEVERITY_EMOJI = {
    "critical": EMOJI_CRITICAL,
    "warning": EMOJI_WARNING,
    "warn": EMOJI_WARNING,
    "watch": EMOJI_WATCH,
    "info": EMOJI_INFO,
    "ok": EMOJI_OK,
    "normal": EMOJI_OK,
    "status": EMOJI_STATUS,
}

ALERT_TYPE_EMOJI = {
    "pendulum_hourly": EMOJI_PENDULUM,
    "pendulum_daily": EMOJI_PENDULUM,
    "short_run": EMOJI_SHORT_RUN,
    "short_off": EMOJI_SHORT_OFF,
    "ml_anomaly": EMOJI_ML_ANOMALY,
    "setpoint_osc": EMOJI_SETPOINT,
    "cop_degradation": "\U0001F4C9",
    "defrost_excessive": "\u2744\uFE0F",
    "buh_excessive": "\U0001F525",
    "source_stale": "\U0001F4E1",
    "missing_attributes": "\u2753",
    "cop_low": "\U0001F4C9",
    "stooklijn_advies": "\U0001F4C9",
    "dhw_pendulum": EMOJI_DHW_PENDULUM,
    "high_cycle_rate": EMOJI_HIGH_CYCLE_RATE,
    "cop_vs_datasheet_low": EMOJI_COP_VS_DATASHEET,
    "db_retention_warning": "\U0001F5C4\uFE0F",
    "kmeans_retrain_stale": "\u2699\uFE0F",
    "energy_daily_anomaly": "\u26A1\uFE0F",
}

# Status update (periodic summary) - opt-in, default off
DEFAULT_NOTIFY_EMOJI_ENABLED = True
DEFAULT_STATUS_UPDATE_ENABLED = False
DEFAULT_STATUS_UPDATE_INTERVAL_HOURS = 24
NOTIF_ID_STATUS = f"{DOMAIN}_status"

# --- 12a: adaptive thresholds ---
DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED = False
DEFAULT_ADAPTIVE_MIN_SAMPLES = 20
ADAPTIVE_MIN_SAMPLES_LOWER_BOUND = 5
ADAPTIVE_MIN_SAMPLES_UPPER_BOUND = 500

# --- COP analysis (batch 14b) ---
COP_SENSOR_ENTITY = "sensor.altherma_global_cop"
DEFAULT_COP_SAMPLE_INTERVAL_SECONDS = 600
DEFAULT_COP_RETENTION_DAYS = 365
DEFAULT_MODEL_STATE_RETENTION_DAYS = 400

# v1.4.2
COP_ROLLUP_WINDOW_HOURS = 720
DEFAULT_COP_ANALYSIS_DAYS = 30
DEFAULT_COMFORT_MIN_C = 20.0
DEFAULT_SEASON_START_MONTH = 10

# ---------- v1.6.0-C5: BUH step power by model ----------
# Daikin Altherma service handbook: BUH is 3kW step1 + 3kW or 6kW step2.
# Fallback (3.0, 3.0) underestimates EPRA/ERLA 11-16 with step2=6kW.
BUH_STEP_KW_BY_MODEL: dict[str, tuple[float, float]] = {
    "EPRA04": (3.0, 3.0),
    "EPRA06": (3.0, 3.0),
    "EPRA08": (3.0, 3.0),
    "EPRA11": (3.0, 6.0),
    "EPRA12": (3.0, 6.0),
    "EPRA14": (3.0, 6.0),
    "EPRA16": (3.0, 6.0),
    "ERLA04": (3.0, 3.0),
    "ERLA06": (3.0, 3.0),
    "ERLA08": (3.0, 3.0),
    "ERLA11": (3.0, 6.0),
    "ERLA12": (3.0, 6.0),
    "ERLA14": (3.0, 6.0),
    "ERLA16": (3.0, 6.0),
}
BUH_STEP_KW_DEFAULT: tuple[float, float] = (3.0, 3.0)


def buh_step_kw_for_model(model: str | None) -> tuple[float, float]:
    """Return (step1_kw, step2_kw) for a model key, fallback (3.0, 3.0)."""
    if not model:
        return BUH_STEP_KW_DEFAULT
    return BUH_STEP_KW_BY_MODEL.get(str(model).upper(), BUH_STEP_KW_DEFAULT)

DEFAULT_COMFORT_MAX_C = 24.0
K_EMIT_DEFAULT = 0.20
LWT_STEP_MIN = 1.0
LWT_STEP_MAX = 3.0
LWT_TRACKING_TOLERANCE = 1.5
COMFORT_TOLERANCE = 1.0
DEFAULT_INDOOR_TEMP_SENSOR: str | None = None
DEFAULT_COP_AVG_LOOKBACK_DAYS = 1

# --- FEAT-2: live thermal power cascade ---
# Empirical coefficient for EPRA12 air-water, nominal ~0.20 kW/rps.
# To be re-verified against real power-sensor data in heating season.
RPS_KW_FACTOR = 0.20
WATER_SPECIFIC_HEAT_KJ_KG_K = 4.186
WATER_DENSITY_KG_L = 1.0
ADAPTIVE_SHORT_RUN_PERCENTILE = 20
ADAPTIVE_GOOD_OFF_PERCENTILE = 50
ADAPTIVE_TARGET_CPD_PERCENTILE = 50
ADAPTIVE_MIN_RUN_MIN = 2
ADAPTIVE_MAX_RUN_MIN = 240
ADAPTIVE_MIN_OFF_MIN = 0
ADAPTIVE_MAX_OFF_MIN = 240
ADAPTIVE_MIN_TARGET_CPD = 1
ADAPTIVE_MAX_TARGET_CPD = 100

# model_state key for adaptive thresholds persistence
MODEL_STATE_ADAPTIVE = "adaptive_thresholds"
DETECTOR_STATE_KEY = "cycle_detector_state"

DEFAULT_SETPOINT_OSC_WINDOW_MIN = 30

DEFAULT_SETPOINT_OSC_MIN_DELTA = 0.5

# --- Batch 22: notification language + alert groups + setpoint_osc options ---
LANG_EN = "en"
LANG_NL = "nl"
NOTIFICATION_LANGUAGES = [LANG_EN, LANG_NL]
DEFAULT_NOTIFICATION_LANGUAGE = LANG_EN

ALERT_GROUP_PENDULUM = "pendulum"
ALERT_GROUP_SHORT_CYCLE = "short_cycle"
ALERT_GROUP_ML = "ml"
ALERT_GROUP_SETPOINT = "setpoint"
ALERT_GROUP_COP_STOOKLIJN = "cop_stooklijn"
ALERT_GROUP_COMPONENT_HEALTH = "component_health"
ALERT_GROUP_DATA_QUALITY = "data_quality"

ALERT_GROUPS = [
    ALERT_GROUP_PENDULUM,
    ALERT_GROUP_SHORT_CYCLE,
    ALERT_GROUP_ML,
    ALERT_GROUP_SETPOINT,
    ALERT_GROUP_COP_STOOKLIJN,
    ALERT_GROUP_COMPONENT_HEALTH,
    ALERT_GROUP_DATA_QUALITY,
]

ALERT_GROUP_MAP = {
    "pendulum_hourly": ALERT_GROUP_PENDULUM,
    "pendulum_daily": ALERT_GROUP_PENDULUM,
    "short_run": ALERT_GROUP_SHORT_CYCLE,
    "short_off": ALERT_GROUP_SHORT_CYCLE,
    "ml_anomaly": ALERT_GROUP_ML,
    "setpoint_osc": ALERT_GROUP_SETPOINT,
    "cop_low": ALERT_GROUP_COP_STOOKLIJN,
    "stooklijn_advies": ALERT_GROUP_COP_STOOKLIJN,
    "cop_degradation": ALERT_GROUP_COP_STOOKLIJN,
    "defrost_excessive": ALERT_GROUP_COMPONENT_HEALTH,
    "buh_excessive": ALERT_GROUP_COMPONENT_HEALTH,
    "source_stale": ALERT_GROUP_DATA_QUALITY,
    "missing_attributes": ALERT_GROUP_DATA_QUALITY,
    "dhw_pendulum": ALERT_GROUP_PENDULUM,
    "high_cycle_rate": ALERT_GROUP_SHORT_CYCLE,
    "cop_vs_datasheet_low": ALERT_GROUP_COP_STOOKLIJN,
}

# Alert thresholds (PR C: unify magic numbers)
COP_LOW_THRESHOLD = 2.5
COP_LOW_MIN_SAMPLES = 3
STOOKLIJN_MIN_CONFIDENCE = 0.7
STOOKLIJN_MIN_SAVINGS_PCT = 5.0

# Demo fixture for OptionsFlow test emitters (rendered delta below threshold)
TEST_ALERT_DELTA = 0.1

# --- PR E: P1 alert thresholds (v1.9.0) ---
COP_DEGRADATION_WEEK_PCT_THRESHOLD = -15.0
DEFROST_7D_COUNT_THRESHOLD_DEFAULT = 30
BUH_7D_RATIO_THRESHOLD_DEFAULT = 0.15

# --- PR F: P2 alert thresholds (v1.9.0) ---
COP_VS_DATASHEET_LOW_PCT = -10.0
HIGH_CYCLE_RATE_MULTIPLIER = 1.5

# Stooklijn advice state -> display label (Batch 39c)
STOOKLIJN_STATE_LABEL_EN = {
    "keep": "Keep current LWT",
    "lower_lwt": "Lower LWT by {step} \u00b0C",
    "raise_lwt": "Raise LWT by {step} \u00b0C",
    "no_data": "No data",
    "unknown": "Unknown",
    "behoud": "Keep current LWT",
    "verlaag_lwt": "Lower LWT by {step} \u00b0C",
    "verhoog_lwt": "Raise LWT by {step} \u00b0C",
    "verlaag_lwt_2c": "Lower LWT by 2 \u00b0C",
    "verhoog_lwt_2c": "Raise LWT by 2 \u00b0C",
    "geen_data": "No data",
}

STOOKLIJN_STATE_LABEL_NL = {
    "keep": "Behoud huidige LWT",
    "lower_lwt": "Verlaag LWT met {step} \u00b0C",
    "raise_lwt": "Verhoog LWT met {step} \u00b0C",
    "no_data": "Geen data",
    "unknown": "Onbekend",
    "behoud": "Behoud huidige LWT",
    "verlaag_lwt": "Verlaag LWT met {step} \u00b0C",
    "verhoog_lwt": "Verhoog LWT met {step} \u00b0C",
    "verlaag_lwt_2c": "Verlaag LWT met 2 \u00b0C",
    "verhoog_lwt_2c": "Verhoog LWT met 2 \u00b0C",
    "geen_data": "Geen data",
}

STOOKLIJN_STATE_LABEL = STOOKLIJN_STATE_LABEL_EN
# --- B6: cop_hourly REST API + curve sensor ---
COP_HOURLY_API_URL = "/api/daikin_cycle_ml/cop_hourly"
COP_HOURLY_API_DEFAULT_DAYS = 30
COP_HOURLY_API_MAX_DAYS = 365
COP_CURVE_RECENT_HOURS = 48
COP_CURVE_RECENT_MAX_POINTS = 96

# --- C4: weather-normalized COP degradation (v1.6.0) ---
DEGRADATION_WINDOW_DAYS = 7
DEGRADATION_BASELINE_DAYS = 30
DEGRADATION_MIN_HOURS_PER_BIN = 6
DEGRADATION_THRESHOLD_PCT = -8.0
DEGRADATION_CRITICAL_PCT = -15.0
DEGRADATION_MIN_DAYS = 3
DEGRADATION_EXCLUSION_SKEW_MAX = 0.15
DEGRADATION_MIN_SAMPLES_1BIN = 200
DEGRADATION_MIN_SAMPLES_2BIN = 100
DEGRADATION_MIN_SAMPLES_3BIN = 80
DEGRADATION_LWT_SHIFT_C = 5.0
DEGRADATION_MIN_HOURS_FIT = 10
DEGRADATION_MIN_SPREAD_C = 5.0
DEGRADATION_REFRESH_THROTTLE_S = 300.0
OUTDOOR_BINS: tuple[tuple[float, float, str], ...] = (
    (-25.0, -10.0, "very_cold"),
    (-10.0,   0.0, "cold"),
    (  0.0,   5.0, "cool"),
    (  5.0,  10.0, "mild"),
    ( 10.0,  15.0, "warm"),
    ( 15.0,  25.0, "hot"),
)
OUTDOOR_BINS_ORDER: tuple[str, ...] = tuple(b[2] for b in OUTDOOR_BINS)

# v1.7.0: one-time guard for daily_summary backfill
DAILY_SUMMARY_BACKFILL_KEY = "daily_summary_backfilled_v1_7_0"

# v1.7.0: live daily summary rollup toggle
OPTION_DAILY_SUMMARY_LIVE_ENABLED = "daily_summary_live_enabled"

# v1.7.0: default for the live daily summary rollup toggle
DEFAULT_DAILY_SUMMARY_LIVE_ENABLED = True

# --- PR D: alert dedup persistence (v1.9.0) ---
ALERT_STORE_KEY = "daikin_cycle_ml.alerts"
ALERT_STORE_VERSION = 1
ALERT_STORE_SAVE_DELAY = 5.0
ALERT_DEDUP_OPTION_PREFIX = "alert_agg_"
ALERT_DEDUP_OPTION_SUFFIX = "_min"
ALERT_DEDUP_DEFAULTS: dict[str, int] = {
    "pendulum_hourly": 60,
    "pendulum_daily": 1440,
    "short_run": 30,
    "short_off": 30,
    "ml_anomaly": 60,
    "setpoint_osc": 30,
    "cop_low": 30,
    "stooklijn_advies": 10080,
    "cop_degradation": 1440,
    "defrost_excessive": 1440,
    "buh_excessive": 1440,
    "source_stale": 60,
    "missing_attributes": 60,
    "dhw_pendulum": 60,
    "high_cycle_rate": 60,
    "cop_vs_datasheet_low": 1440,
    "db_retention_warning": 1440,
    "kmeans_retrain_stale": 1440,
    "energy_daily_anomaly": 1440,
}


# v1.10.0 #75 — per-entry DB file migration
DB_FILENAME = "daikin_cycle_ml.db"
DB_FILENAME_TEMPLATE = "daikin_cycle_ml_{entry_id}.db"
DB_LEGACY_MARKER_FILENAME = ".daikin_cycle_ml_v1100_migrated"

# v1.14.0 raomin-aligned electrical input cascade (Discussion #599)
SUPPLY_PHASES_DEFAULT = 1
SUPPLY_PHASES_ALLOWED = (1, 3)
BUH_STEP1_KW_DEFAULT = 3.0
BUH_STEP2_KW_DEFAULT = 3.0
ELECTRICAL_OFFSET_W_V1 = 100.0
VOLTAGE_NOMINAL_V = 230.0
V2_STATS_KEY = "Stats: Electrical input estimated (kW)"
INV_PRIMARY_CURRENT_KEY = "INV primary current (A)"
BUH_STEP1_KEY = "BUH Step1"
BUH_STEP2_KEY = "BUH Step2"
V2_STATS_HYSTERESIS_S = 300.0


# === v1.13.2 model families + aliases ===

MODEL_FAMILIES: dict[str, str] = {
    "epra": "Altherma 3 H MT",
    "erla": "Altherma 3 R",
    "erga": "Altherma 3 R Split",
    "epga": "Altherma 3 H",
    "edla": "Altherma 3 R (Monobloc)",
    "ebla": "Altherma 3 M",
    "eblq": "Altherma 3 M (Monobloc)",
    "edlq": "Altherma 3 (Monobloc)",
    "epsk": "Altherma 3 (Split)",
    "ekhbrd": "Altherma HT (Hydrobox)",
    "errq": "Altherma HT (Split)",
    "evlq": "Altherma R Hybrid",
}

MODEL_ALIASES: dict[str, str] = {
    MODEL_ERGA08EVH7: MODEL_ERGA08EAV3,
    "ehyhbh05av32": MODEL_EVLQ05CV3,
    "ehyhbh08av32": MODEL_EVLQ08CV3,
    "ehyhbx08av3": MODEL_EVLQ08CV3,
    "erg04eav3": MODEL_ERGA04EAV3,
    "erg06eav3": MODEL_ERGA06EAV3,
    "erg08eav3": MODEL_ERGA08EAV3,
}


def resolve_model_key(model_code: str) -> str:
    """Resolve a commercial-name alias to its base technical model code."""
    return MODEL_ALIASES.get(model_code, model_code)


def family_for_model(model_code: str) -> str:
    """Return the family prefix (e.g. 'erga') for a model code or alias."""
    key = resolve_model_key(model_code) if model_code else ''
    if not key or key in (MODEL_BASISPROFIEL, MODEL_CUSTOM):
        return key if key else MODEL_BASISPROFIEL
    i = 0
    while i < len(key) and key[i].isalpha():
        i += 1
    prefix = key[:i].lower()
    return prefix if prefix in MODEL_FAMILIES else MODEL_BASISPROFIEL


def models_in_family(family: str) -> list[str]:
    """Return ordered list of MODEL_CHOICES entries whose family matches."""
    if family in (MODEL_BASISPROFIEL, MODEL_CUSTOM):
        return [family]
    return [m for m in MODEL_CHOICES if family_for_model(m) == family]
