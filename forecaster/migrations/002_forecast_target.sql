-- Forecasts now cover more than ZHVI: national FRED series (mortgage rate,
-- unemployment, CPI) and metro unemployment rates. A metro can have both a home
-- value and an unemployment forecast, so `target` joins the primary key.
-- Keep web/src/lib/types.ts in sync.

ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS target TEXT NOT NULL DEFAULT 'zhvi';

ALTER TABLE forecasts DROP CONSTRAINT IF EXISTS forecasts_pkey;
ALTER TABLE forecasts
    ADD PRIMARY KEY (region_id, origin_date, horizon, model, target, release);
