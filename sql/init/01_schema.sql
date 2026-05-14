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
    mission_id          INTEGER,
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

CREATE INDEX IF NOT EXISTS idx_bronze_traffic_source_file ON bronze.traffic (source_file); --to make dedup quicker

-- ── SILVER ───────────────────────────────────────────────────────────────────

--
CREATE TABLE IF NOT EXISTS silver.ref_mission_location ( --needs revision/update
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
    mission_id                          INTEGER,
    device_id                           TEXT,
    date_raw                            TEXT,
    date_parsed                         TIMESTAMP,
    speed_entry                         NUMERIC,
    speed_exit                          NUMERIC,
    speed                               NUMERIC,
    length_dm                           NUMERIC,
    vehicle_class                       INTEGER,
    vehicle_class_label                 TEXT,
    source_file                         TEXT,
    ingested_at                         TIMESTAMP,
    silver_processed_at                 TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_silver_traffic_source_file ON silver.traffic (source_file); --to make dedup quicker

CREATE TABLE IF NOT EXISTS silver.staging_traffic (
    mission_id                          INTEGER,
    device_id                           TEXT,
    date_raw                            TEXT,
    date_parsed                         TIMESTAMP,
    speed_entry                         NUMERIC,
    speed_exit                          NUMERIC,
    flag_speed_entry_100                BOOLEAN,
    flag_speed_exit_100                 BOOLEAN,
    flag_speed_100                      BOOLEAN,
    flag_bike_speed_40                  BOOLEAN,
    speed                               NUMERIC,
    length_dm                           NUMERIC,
    flag_length_below_min               BOOLEAN,
    flag_length_above_max               BOOLEAN,
    vehicle_class                       INTEGER,
    vehicle_class_label                 TEXT,
    source_file                         TEXT,
    ingested_at                         TIMESTAMP,
    flag_duplicate                      BOOLEAN,
    silver_processed_at                 TIMESTAMP DEFAULT NOW()
);



-- ── GOLD - needs revision, update ─────────────────────────────────────────────────────────────────────

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
