-- Berlin Traffic Pipeline Schema
-- Medallion architecture: bronze → silver → gold

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ── BRONZE ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bronze.traffic (
    ---Monica to specify
    geladen_am          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.deployment (
    ----tbc
);

CREATE TABLE IF NOT EXISTS bronze.location (
    location_id         INTEGER,
    created             TIMESTAMP,
    description         TEXT,
    location_title      TEXT,
    street              TEXT,
    street_number       TEXT,
    zipcode             TEXT,
    city                TEXT,
    driving_direction   TEXT,
    opposite_direction  TEXT,
    pos_user_lat        NUMERIC(9,6),
    pos_user_lng        NUMERIC(9,6),
    run_date            DATE DEFAULT CURRENT_DATE
);


-- ── SILVER ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS silver.active_missions (
    ---- Monica
);

CREATE TABLE IF NOT EXISTS silver.traffic (
    ---- Monica
);

-- ── GOLD ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gold.traffic (
  ----Monica

);


--ADD MORE HERE


-- ── PIPELINE LOG ─────────────────────────────────────────────────────────

-- CREATE TABLE IF NOT EXISTS public.pipeline_log (
--     run_at              TIMESTAMP DEFAULT NOW(),
--     dag_id              TEXT,
--     status              TEXT,              -- success / failure
--     rows_ingested       INTEGER,
--     neue_deployments    BOOLEAN,
--     notes               TEXT
-- );
