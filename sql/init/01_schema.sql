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


CREATE TABLE IF NOT EXISTS silver.ref_mission_location (
    mission_id                  INTEGER,
    created_at                  TIMESTAMP,
    start_date                  TIMESTAMP,
    end_date                    TIMESTAMP,
    device_id                   TEXT,
    street                      TEXT,
    street_number               TEXT,
    zipcode                     TEXT,
    city                        TEXT,
    location_description        TEXT,
    lat                         NUMERIC(9,6),
    lon                         NUMERIC(9,6),
    is_pair                     BOOLEAN,
    paired_mission_id           INTEGER,
    driving_direction           TEXT,
    opposite_direction          TEXT,
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


-- ── GOLD  ─────────────────────────────────────────────────────────────────────

-- Watermark table to track upserting & deduplication when adding rows. similar role to json tracker in bronze layer
CREATE TABLE IF NOT EXISTS gold.watermark (
    table_name      TEXT UNIQUE,
    last_processed  TIMESTAMP NOT NULL DEFAULT '1970-01-01'
);

-- Hourly aggregated traffic dataset. One row per (mission_id, datum, stunde).
CREATE TABLE IF NOT EXISTS gold.export (
    mission_id                  INTEGER,
    device_id                   TEXT,
    start_date                  TIMESTAMP,
    end_date                    TIMESTAMP,
    date                        DATE,
    hour                        SMALLINT,
    street                      TEXT,
    street_number               TEXT,
    zipcode                     TEXT,
    city                        TEXT,
    location_description        TEXT,
    lat                         NUMERIC(9,6),
    lon                         NUMERIC(9,6),
    motorised                   INTEGER, -- total motorised vehicles (all classes)
    car                         INTEGER,
    bicycle                     INTEGER,
    delivery_van                INTEGER,
    motorbike                   INTEGER,
    lorry                       INTEGER,
    other_motorised_vehicle     INTEGER,
    v_all_motorised             NUMERIC,
    v_car                       NUMERIC,
    v_delivery_van              NUMERIC,
    v_motorbike                 NUMERIC,
    v_lorry                     NUMERIC,
    v_other                     NUMERIC,
    v85                         NUMERIC,    -- 85th-percentile speed (excl. fahrrad)
    modal_share_car             NUMERIC,
    modal_share_bicycle         NUMERIC,
    modal_share_delivery_van    NUMERIC,
    modal_share_motorbike       NUMERIC,
    modal_share_lorry           NUMERIC,
    is_pair                     BOOLEAN,
    paired_mission_id           INTEGER,
    driving_direction           TEXT,
    opposite_direction          TEXT,
    gold_processed_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (mission_id, date, hour) --- adds condition that these three together must not have duplicates
);

CREATE TABLE IF NOT EXISTS gold.dashboard ( -- one row per day
    mission_id                  INTEGER,
    start_date                  TIMESTAMP,
    end_date                    TIMESTAMP,
    date                        DATE,
    streetnr                    TEXT,
    city                        TEXT,
    location_description        TEXT,
    lat                         NUMERIC(9,6),
    lon                         NUMERIC(9,6),
    car                         INTEGER,
    bicycle                     INTEGER,
    delivery_van                INTEGER,
    motorbike                   INTEGER,
    lorry                       INTEGER,
    other                       INTEGER,
    v_car                       NUMERIC,
    v_delivery_van              NUMERIC,
    v_motorbike                 NUMERIC,
    v_lorry                     NUMERIC,
    v_other                     NUMERIC,
    v85                         NUMERIC,    -- 85th-percentile speed (excl. fahrrad)
    modal_share_car             NUMERIC,
    modal_share_bicycle         NUMERIC,
    modal_share_delivery_van    NUMERIC,
    modal_share_motorbike       NUMERIC,
    modal_share_lorry           NUMERIC,
    modal_share_other           NUMERIC,
    is_pair                     BOOLEAN,
    paired_mission_id           INTEGER,
    dashboard_processed_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (mission_id, date) --- adds condition that these three together must not have duplicates
);
