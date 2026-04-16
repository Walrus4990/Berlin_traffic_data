-- Berlin Traffic Pipeline Schema
-- Medallion architecture: bronze → silver → gold

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ── BRONZE ───────────────────────────────────────────────────────────────────

-- One row per device deployment period fetched from the DDweb portal.
-- Updated incrementally: only new (device_id, start_date) pairs are inserted.
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

-- Raw sensor passage rows loaded from DDweb Excel exports.
-- Append-only; idempotent on source_file.
CREATE TABLE IF NOT EXISTS bronze.traffic (
    device_id           TEXT,
    date_raw            TEXT,                  -- unparsed datetime string from source
    speed_entry         NUMERIC,               -- km/h
    speed_exit          NUMERIC,               -- km/h
    length_dm           NUMERIC,               -- vehicle length in decimetres
    vehicle_class       INTEGER,
    vehicle_class_label TEXT,
    source_file         TEXT,                  -- original Excel filename, used for dedup
    ingested_at         TIMESTAMP DEFAULT NOW()
);


-- ── SILVER ───────────────────────────────────────────────────────────────────

-- One row per deployment: bronze.mission enriched with GPS coords from
-- bronze.location. Fully replaced on every run. deploy_end is Timestamp.max
-- for still-active sensors (sentinel end dates 2049/2100).
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
    -- joined from bronze.location
    driving_direction           TEXT,
    opposite_direction          TEXT,
    lat                         NUMERIC(9,6),
    lon                         NUMERIC(9,6),
    -- derived
    deploy_end                  TIMESTAMP,     -- Timestamp.max when sensor still active
    updated_at                  TIMESTAMP DEFAULT NOW()
);

-- Cleaned, geo-enriched, flag-annotated passage rows. Append-only on source_file.
CREATE TABLE IF NOT EXISTS silver.traffic (
    -- raw fields carried over from bronze.traffic
    device_id                           TEXT,
    date_raw                            TEXT,
    speed_entry                         NUMERIC,
    speed_exit                          NUMERIC,
    length_dm                           NUMERIC,
    vehicle_class                       INTEGER,
    vehicle_class_label                 TEXT,
    source_file                         TEXT,
    ingested_at                         TIMESTAMP,
    -- parsed timestamp fields
    datum_parsed                        TIMESTAMP,
    datum                               DATE,
    stunde                              SMALLINT,
    wochentag                           TEXT,
    -- quality flags (row level)
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
    -- geo-enrichment from silver.active_mission (time-windowed join)
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
    -- pipeline metadata
    processed_at                        TIMESTAMP DEFAULT NOW(),
    pipeline_path                       TEXT    -- 'full' or 'reduced'
);


-- ── GOLD ─────────────────────────────────────────────────────────────────────

-- Hourly aggregated traffic dataset. One row per (device_id, location_title,
-- datum, stunde, wochentag). Equivalent to hourly_dataset in the analysis
-- notebook. Fully replaced on every run.
--
-- NOTE: the Python ETL currently writes this as gold.hourly. Update the
-- to_sql() call in gold_data_layer.py to use "traffic" instead of "hourly"
-- and simplify run_gold() to remove the by_location / by_vehicle / by_time tables.
CREATE TABLE IF NOT EXISTS gold.traffic (
    -- group keys
    device_id               TEXT,
    location_title          TEXT,
    datum                   DATE,
    stunde                  SMALLINT,           -- hour of day 0–23
    wochentag               TEXT,               -- e.g. 'Monday'
    -- vehicle class passage counts (all rows, including flagged)
    count_total             INTEGER,
    count_pkw               INTEGER,            -- Pkw — car
    count_pkw_a             INTEGER,            -- PkwA — car with trailer
    count_lkw               INTEGER,            -- Lkw — lorry
    count_lkw_a             INTEGER,            -- LkwA — lorry with trailer
    count_sattel            INTEGER,            -- Sattel-Kfz — articulated / HGV
    count_bus               INTEGER,
    count_krad              INTEGER,            -- Krad — motorcycle
    count_lfw               INTEGER,            -- Lfw — delivery van
    count_fahrrad           INTEGER,            -- Fahrrad — bicycle
    count_nk_kfz            INTEGER,            -- nk Kfz — unclassified motor vehicle
    count_kfz64             INTEGER,            -- Kfz class 64 — all motor vehicles aggregate
    count_motorised         INTEGER,            -- sum of motorised classes excl. 64 & unclassified
    -- speed metrics (computed on clean, unflagged rows only)
    mean_speed_entry        NUMERIC,            -- km/h, motorised only
    mean_speed_exit         NUMERIC,            -- km/h, motorised only
    mean_speed_bicycle      NUMERIC,            -- km/h, bicycles only
    v85_entry               NUMERIC,            -- 85th-percentile entry speed (excl. krad & fahrrad)
    n_v85_eligible          INTEGER,            -- sample size used for V85
    thin_v85_sample         BOOLEAN,            -- true when n_v85_eligible < 5
    -- location coordinates (first non-null value in the group)
    lat                     NUMERIC(9,6),
    lon                     NUMERIC(9,6),
    -- hour-level quality flags (true = at least one row in this hour triggered the flag)
    flag_any                BOOLEAN,
    flag_unclassifiable     BOOLEAN,
    flag_speed_issues       BOOLEAN,
    flag_duplicate          BOOLEAN,
    n_flagged_rows          INTEGER,
    -- pipeline metadata
    aggregated_at           TIMESTAMP DEFAULT NOW()
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
