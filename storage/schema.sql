-- Daikin Cycle ML schema v0.1.0
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts REAL NOT NULL,
    end_ts REAL,
    duration_s INTEGER,
    mode TEXT,
    dT_max REAL,
    dT_avg REAL,
    rps_max INTEGER,
    rps_avg REAL,
    outdoor_temp REAL,
    buh_used INTEGER DEFAULT 0,
    defrost_used INTEGER DEFAULT 0,
    quality_score INTEGER,
    label TEXT,
    cluster_id INTEGER,
    UNIQUE(start_ts)
);

CREATE TABLE IF NOT EXISTS features (
    cycle_id INTEGER PRIMARY KEY REFERENCES cycles(id),
    vector_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    aggregated_count INTEGER DEFAULT 1,
    UNIQUE(ts, alert_type)
);

CREATE INDEX IF NOT EXISTS idx_cycles_start_ts ON cycles(start_ts);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
CREATE INDEX IF NOT EXISTS idx_cycles_end_ts ON cycles(end_ts);

CREATE TABLE IF NOT EXISTS daily_summary (
    day TEXT NOT NULL,
    mode TEXT NOT NULL,
    cycles INTEGER NOT NULL DEFAULT 0,
    total_duration_s INTEGER NOT NULL DEFAULT 0,
    duration_min INTEGER,
    duration_max INTEGER,
    quality_sum INTEGER NOT NULL DEFAULT 0,
    dt_max_sum REAL NOT NULL DEFAULT 0,
    rps_sum REAL NOT NULL DEFAULT 0,
    buh_count INTEGER NOT NULL DEFAULT 0,
    defrost_count INTEGER NOT NULL DEFAULT 0,
    updated_ts REAL NOT NULL,
    PRIMARY KEY (day, mode)
);

CREATE INDEX IF NOT EXISTS idx_daily_summary_day ON daily_summary(day);
