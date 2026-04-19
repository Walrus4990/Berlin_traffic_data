-- Berlin Traffic Pipeline Schema
-- Medallion architecture: bronze → silver → gold

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ── BRONZE ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bronze.mission (
    mission_id          INTEGER,
    created_at          TIMESTAMP,
    start_date          TIMESTAMP,
    end_date            TIMESTAMP,
    description         TEXT,
    location_title      TEXT,                  -- join key to bronze.location
    city                TEXT,
    street              TEXT,
    street_number       TEXT,
    zipcode             TEXT,
    device_id           TEXT,                  -- primary device identifier
    device_type         TEXT,
    ingested_at         TIMESTAMP DEFAULT NOW()
);

-- Location reference table. Fully replaced on every run.
CREATE TABLE IF NOT EXISTS bronze.location (
    location_id         INTEGER,
    created_at          TIMESTAMP,
    description         TEXT,
    location_title      TEXT,                  -- join key to bronze.mission
    street              TEXT,
    street_number       TEXT,
    zipcode             TEXT,
    city                TEXT,
    driving_direction   TEXT,
    opposite_direction  TEXT,
    lat                 NUMERIC(9,6),
    lon                 NUMERIC(9,6),
    ingested_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.traffic (
    device_id           TEXT,
    date_raw            TEXT,                  -- unparsed datetime string from source
    speed_entry         NUMERIC,               -- km/h
    speed_exit          NUMERIC,               -- km/h
    length_dm           NUMERIC,               -- vehicle length in decimetres
    vehicle_class       INTEGER,
    vehicle_class_label TEXT,
    source_file         TEXT,                  -- original Excel filename
    ingested_at         TIMESTAMP DEFAULT NOW()
);


-- ── SILVER ───────────────────────────────────────────────────────────────────
-- One row per deployment: bronze.mission enriched with GPS coords from bronze.location.
CREATE TABLE IF NOT EXISTS silver.active_mission (
    -- from bronze.mission
    mission_id                  INTEGER,
    created_at                  TIMESTAMP,
    start_date                  TIMESTAMP,
    end_date                    TIMESTAMP,
    description                 TEXT,
    location_title              TEXT,
    city                        TEXT,
    street                      TEXT,
    street_number               TEXT,
    zipcode                     TEXT,
    device_id                   TEXT,
    device_type                 TEXT,
    ingested_at                 TIMESTAMP,
    driving_direction           TEXT,
    opposite_direction          TEXT,
    lat                         NUMERIC(9,6),
    lon                         NUMERIC(9,6),
    deploy_end                  TIMESTAMP,
    updated_at                  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS silver.traffic (
    device_id                           TEXT,
    date_raw                            TEXT,
    speed_entry                         NUMERIC,
    speed_exit                          NUMERIC,
    length_dm                           NUMERIC,
    vehicle_class                       INTEGER,
    vehicle_class_label                 TEXT,
    source_file                         TEXT,
    ingested_at                         TIMESTAMP,
    datum_parsed                        TIMESTAMP,
    datum                               DATE,
    stunde                              SMALLINT,
    wochentag                           TEXT,
    flag_unparseable_timestamp          BOOLEAN,
    flag_unknown_device                 BOOLEAN,
    flag_outside_deployment_window      BOOLEAN,
    flag_ambiguous_location             BOOLEAN,
    flag_unclassifiable                 BOOLEAN,
    flag_speed_entry                    BOOLEAN,
    flag_speed_exit                     BOOLEAN,
    flag_speed                          BOOLEAN,
    flag_duplicate                      BOOLEAN,
    flag_speed_delta                    BOOLEAN,
    speed_ratio                         NUMERIC,
    any_flag                            BOOLEAN,
    flag_reasons                        TEXT,   -- semicolon-separated list of triggered flags
    location_title                      TEXT,
    street                              TEXT,
    street_number                       TEXT,
    zipcode                             TEXT,
    driving_direction                   TEXT,
    lat                                 NUMERIC(9,6),
    lon                                 NUMERIC(9,6),
    start_date                          TIMESTAMP,
    deploy_end                          TIMESTAMP,
    flag_no_coords                      BOOLEAN,
    processed_at                        TIMESTAMP DEFAULT NOW(),
    pipeline_path                       TEXT
);


-- ── GOLD ─────────────────────────────────────────────────────────────────────

-- Hourly aggregated traffic dataset. One row per (geraet_id, standort, datum, stunde). Fully replaced on every run.
CREATE TABLE IF NOT EXISTS gold.traffic (
    -- group keys
    datum                   DATE,
    datum_iso               TEXT,               -- ISO date string YYYY-MM-DD (display convenience)
    stunde                  SMALLINT,           -- hour of day 0–23
    geraet_id               TEXT,               -- permanent sensor ID
    standort                TEXT,               -- street name
    latitude                NUMERIC(9,6),
    longitude               NUMERIC(9,6),
    kfz                     INTEGER,            -- total motorised vehicles (all classes)
    pkw                     INTEGER,            -- Pkw — cars
    lkw                     INTEGER,            -- Lkw — lorries
    lfw                     INTEGER,            -- Lfw — delivery vans
    krad                    INTEGER,            -- Krad — motorcycles
    fahrrad                 INTEGER,            -- Fahrrad — bicycles
    v_kfz                   NUMERIC,            -- avg speed all motorised vehicles
    v_pkw                   NUMERIC,            -- avg speed cars
    v_lkw                   NUMERIC,            -- avg speed lorries
    v85                     NUMERIC,            -- 85th-percentile speed (excl. krad & fahrrad)
    modal_share_pkw         NUMERIC,
    modal_share_fahrrad     NUMERIC,
    modal_share_lkw         NUMERIC,
    modal_share_krad        NUMERIC
);


-- ── PIPELINE LOG ─────────────────────────────────────────────────────────────

-- CREATE TABLE IF NOT EXISTS public.pipeline_log (
--     run_at              TIMESTAMP DEFAULT NOW(),
--     dag_id              TEXT,
--     status              TEXT,              -- success / failure
--     rows_ingested       INTEGER,
--     neue_deployments    BOOLEAN,
--     notes               TEXT
-- );

-- Compatibility view for Superset dashboard
CREATE OR REPLACE VIEW public.traffic_berlin AS
SELECT
  datum,
  datum_iso::DATE AS datum_iso,
  stunde,
  geraet_id,
  standort,
  latitude,
  longitude,
  COALESCE(kfz, 0) AS kfz,
  COALESCE(pkw, 0) AS pkw,
  COALESCE(lkw, 0) AS lkw,
  COALESCE(lfw, 0) AS lfw,
  COALESCE(krad, 0) AS krad,
  COALESCE(fahrrad, 0) AS fahrrad,
  v_kfz, v_pkw, v_lkw, v85,
  COALESCE(modal_share_pkw, 0) AS modal_share_pkw,
  COALESCE(modal_share_fahrrad, 0) AS modal_share_fahrrad,
  COALESCE(modal_share_lkw, 0) AS modal_share_lkw,
  COALESCE(modal_share_krad, 0) AS modal_share_krad
FROM gold.traffic
WHERE datum_iso IS NOT NULL AND datum_iso != 'nan';
