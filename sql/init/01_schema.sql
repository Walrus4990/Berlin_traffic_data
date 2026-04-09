-- Berlin Traffic Pipeline Schema
-- Medallion architecture: bronze → silver → gold

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ── BRONZE ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bronze.traffic (
    geraet_id           INTEGER,
    datum               TIMESTAMP,
    geschwindigkeit     NUMERIC,           -- Geschwindigkeit (km/h)
    eintrittsgeschw     NUMERIC,           -- Eintrittsgeschwindigkeit
    austrittsgeschw     NUMERIC,           -- Austrittsgeschwindigkeit
    laenge_dm           NUMERIC,           -- Länge (dm)
    klasse              TEXT,              -- Fahrzeugklassen-Bezeichnung
    schall_db           NUMERIC,
    abstand_cm          NUMERIC,
    quelldatei          TEXT,              -- source filename for traceability
    geladen_am          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.deployment (
    geraet_id           INTEGER,
    startdatum          TIMESTAMP,
    enddatum            TIMESTAMP,
    beschreibung        TEXT,
    geraetetyp          TEXT,
    standorttitel       TEXT,
    stadt               TEXT,
    erstellt            TIMESTAMP,
    geladen_am          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.location (
    standorttitel       TEXT,
    beschreibung        TEXT,
    strasse             TEXT,
    hausnummer          TEXT,
    postleitzahl        TEXT,
    stadt               TEXT,
    land                TEXT,
    fahrtrichtung       TEXT,
    gegenrichtung       TEXT,
    lat                 NUMERIC,           -- Benutzer Position Lat
    lon                 NUMERIC,           -- Benutzer Position Long
    erstellt            TIMESTAMP,
    geladen_am          TIMESTAMP DEFAULT NOW()
);

-- ── SILVER ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS silver.active_deployment (
    geraet_id           INTEGER PRIMARY KEY,
    standorttitel       TEXT,
    strasse             TEXT,
    hausnummer          TEXT,
    fahrtrichtung       TEXT,
    lat                 NUMERIC,
    lon                 NUMERIC,
    startdatum          TIMESTAMP,
    aktualisiert_am     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS silver.traffic (
    id                  SERIAL PRIMARY KEY,
    geraet_id           INTEGER,
    datum               DATE,
    stunde              SMALLINT,          -- 0-23
    klasse              TEXT,              -- vehicle class after mapping
    geschwindigkeit     NUMERIC,
    -- location columns copied directly at ingest
    standorttitel       TEXT,
    strasse             TEXT,
    fahrtrichtung       TEXT,
    lat                 NUMERIC,
    lon                 NUMERIC,
    quelldatei          TEXT,
    verarbeitet_am      TIMESTAMP DEFAULT NOW()
);

-- ── GOLD ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gold.by_location (
    id                  SERIAL PRIMARY KEY,
    standorttitel       TEXT,
    strasse             TEXT,
    lat                 NUMERIC,
    lon                 NUMERIC,
    datum               DATE,
    kfz                 INTEGER,
    pkw                 INTEGER,
    lkw                 INTEGER,
    lfw                 INTEGER,
    krad                INTEGER,
    fahrrad             INTEGER,
    v_kfz               NUMERIC,
    v_pkw               NUMERIC,
    v_lkw               NUMERIC,
    v85                 NUMERIC,
    aktualisiert_am     TIMESTAMP DEFAULT NOW()
);


--ADD MORE HERE


-- ── PIPELINE LOG ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.pipeline_log (
    run_at              TIMESTAMP DEFAULT NOW(),
    dag_id              TEXT,
    status              TEXT,              -- success / failure
    rows_ingested       INTEGER,
    neue_deployments    BOOLEAN,
    notes               TEXT
);
