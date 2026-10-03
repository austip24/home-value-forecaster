-- Initial schema: the contract between the forecaster (writer) and web/ (reader).
-- Keep web/src/lib/types.ts in sync with any change here.

CREATE TABLE IF NOT EXISTS regions (
    region_id    INTEGER PRIMARY KEY,      -- Zillow RegionID
    region_name  TEXT    NOT NULL,
    state        TEXT,
    size_rank    INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    release     TEXT        NOT NULL,      -- YYYY-MM
    git_sha     TEXT        NOT NULL,
    config      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observations (
    region_id  INTEGER NOT NULL REFERENCES regions(region_id),
    date       DATE    NOT NULL,
    metric     TEXT    NOT NULL,
    value      DOUBLE PRECISION,
    release    TEXT    NOT NULL,
    PRIMARY KEY (region_id, date, metric, release)
);

CREATE TABLE IF NOT EXISTS forecasts (
    region_id    INTEGER NOT NULL REFERENCES regions(region_id),
    origin_date  DATE    NOT NULL,
    target_date  DATE    NOT NULL,
    horizon      INTEGER NOT NULL,
    model        TEXT    NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    lower        DOUBLE PRECISION,
    upper        DOUBLE PRECISION,
    release      TEXT    NOT NULL,
    PRIMARY KEY (region_id, origin_date, horizon, model, release)
);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    run_id   TEXT NOT NULL REFERENCES runs(run_id),
    model    TEXT NOT NULL,
    horizon  INTEGER NOT NULL,
    metric   TEXT NOT NULL,                -- mase | mape | directional_accuracy
    value    DOUBLE PRECISION NOT NULL,
    segment  TEXT NOT NULL DEFAULT 'all',  -- all | size tier | region name
    PRIMARY KEY (run_id, model, horizon, metric, segment)
);
