-- Data Quality checks schema
-- Medallion architecture: bronze → silver → gold

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

----------------- bronze ---------------

CREATE TABLE IF NOT EXISTS bronze.segment_download_events (
    run_at        TIMESTAMP NOT NULL,
    mission_id    TEXT NOT NULL,
    segment_start   DATE NOT NULL,
    segment_end     DATE NOT NULL,
    status        TEXT NOT NULL,  -- 'empty' or 'failed'
    reason        TEXT
);

CREATE TABLE IF NOT EXISTS bronze.mission_completeness (
    id              SERIAL PRIMARY KEY,
    run_at          TIMESTAMP NOT NULL,
    mission_id      TEXT NOT NULL,
    expected_segments INT NOT NULL,
    actual_segments   INT NOT NULL,
    missing_count   INT NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.missing_segments (
    id                SERIAL PRIMARY KEY,
    run_at            TIMESTAMP NOT NULL,
    mission_id        TEXT NOT NULL,
    expected_filename TEXT NOT NULL
);

----------------- silver ---------------

CREATE TABLE IF NOT EXISTS silver.traffic_source_file_report (
    run_at                      TIMESTAMP NOT NULL,
    source_file                 TEXT NOT NULL,
    rows_total                  INTEGER,
    rows_written_to_silver      INTEGER,
    flag_duplicate_n            INTEGER,
    flag_duplicate_pct          NUMERIC(6,4),
    flag_speed_entry_100_n      INTEGER,
    flag_speed_entry_100_pct    NUMERIC(6,4),
    flag_speed_exit_100_n       INTEGER,
    flag_speed_exit_100_pct     NUMERIC(6,4),
    flag_speed_100_n            INTEGER,
    flag_speed_100_pct          NUMERIC(6,4),
    flag_bike_speed_40_n        INTEGER,
    flag_bike_speed_40_pct      NUMERIC(6,4)
);

CREATE TABLE IF NOT EXISTS silver.vehicle_length_profile (
    run_at                      TIMESTAMP NOT NULL,
    source_file                 TEXT NOT NULL,
    vehicle_class               INTEGER,
    vehicle_class_label         TEXT,
    n                           INTEGER,
    min_length_dm               NUMERIC,
    max_length_dm               NUMERIC,
    avg_length_dm               NUMERIC,
    pct_below_min               NUMERIC(6,4),
    pct_above_max               NUMERIC(6,4)
);

----------------- gold ---------------

CREATE TABLE IF NOT EXISTS gold.missing_watermark_alerts (
    run_at              TIMESTAMP NOT NULL,
    message             TEXT NOT NULL,
    recovered_timestamp TIMESTAMP
);
