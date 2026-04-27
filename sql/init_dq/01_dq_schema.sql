-- Data Quality checks schema
-- Medallion architecture: bronze → silver → gold

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS bronze.mission_completeness (
    id              SERIAL PRIMARY KEY,
    run_at          TIMESTAMP NOT NULL,
    mission_id      TEXT NOT NULL,
    expected_chunks INT NOT NULL,
    actual_chunks   INT NOT NULL,
    missing_count   INT NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze.missing_chunks (
    id                SERIAL PRIMARY KEY,
    run_at            TIMESTAMP NOT NULL,
    mission_id        TEXT NOT NULL,
    expected_filename TEXT NOT NULL
);
