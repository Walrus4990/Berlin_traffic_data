## Session Handover: Superset Dashboard — Berlin Traffic Data
### Context
A fully automated traffic dashboard is being built in Superset 6.0.0 (Docker) backed by Postgres. All assets are created via REST API in dashboard.py. Data is loaded by an Airflow pipeline via gold.py. The user will share both files at the start of the session.
Current state

DB connection, 5 datasets, 6 charts, 1 dashboard created via REST API
Dashboard structure exists but charts are not linked (known Superset bug B1)
Plan: complete all programmatic work, then manually drag-and-drop charts, export ZIP, use ZIP for prod deploy
No native filters built yet

### Datasets

gold.dashboard — physical, UUID 00000000-0000-0000-0001-000000000001
gold.ganglinien — physical, UUID 00000000-0000-0000-0001-000000000002
gold.v_modalsplit — Postgres view, UUID 00000000-0000-0000-0001-000000000003
gold.v_summary_table — Postgres view, UUID 00000000-0000-0000-0001-000000000004
gold.v_pairs — Postgres view, UUID 00000000-0000-0000-0001-000000000005

### Charts

Standorte — deck_scatter map, UUID 00000000-0000-0000-0000-000000000002
v85 Durchschnitt — big_number_total, UUID 00000000-0000-0000-0000-000000000001
Modalsplit — pie, UUID 00000000-0000-0000-0000-000000000004
Übersicht — table, UUID 00000000-0000-0000-0000-000000000005
Ganglinien — echarts_timeseries_bar, UUID 00000000-0000-0000-0000-000000000003
Sensorpaare — table, UUID 00000000-0000-0000-0000-000000000006
Dashboard UUID: 00000000-0000-0000-0000-000000000010

### Tasks for next session — execute in this order
Task 1: Fix Ganglinien x-axis

Constraint: x-axis must show hours 0–23, one bar per hour, no negative side, axis must not cross y-axis
Current symptom: axis maxes at 25, first bar appears on negative side
Approach: inspect stored params via API, search Superset GitHub for echarts_timeseries_bar x-axis bounds params, fix in _chart_ganglinien
Acceptance: chart shows 24 bars, one per hour, x-axis starts at 0 ends at 23

Task 2: Fix Sensorpaare duplicates

Constraint: table must show only distinct pairs, must respond to Standort and Zeitraum filters
Current symptom: view uses DISTINCT but date column causes row explosion
Approach: search Superset docs/GitHub for filtering on a column not displayed in table chart, fix gold.v_pairs view and _chart_pairs_table params
Acceptance: table shows one row per unique pair, updates when Standort filter changes

Task 3: Fix Modalsplit rounding

Constraint: percentages must display as integers (e.g. "45%" not "45.23%")
Current symptom: number_format: ".0%" stored correctly in DB but Superset renders 2 decimal places
Approach: search Superset GitHub for pie chart number_format ignored bug, find correct param name for Superset 6.0.0
Acceptance: all pie slices show 0 decimal places

Task 4: Build native filters
Execute in this order, test each before moving to next:

4a. Zeitraum — filter_range on date column, absolute calendar picker, applies to all charts
4b. Standort — filter_select on streetnr, multiselect, applies to all charts, targets: gold.dashboard, gold.ganglinien, gold.v_modalsplit, gold.v_summary_table, gold.v_pairs
4c. Wochentag — filter_select on day_of_week_name, multiselect checkboxes, sorted by day_of_week_num, applies to all charts
For each filter: use _add_native_filters function via PUT /api/v1/dashboard/{id} updating json_metadata.native_filter_configuration
Known schema available in handover ADR (from manual filter creation in this session)

Task 5: Dashboard wipe function

Write _wipe(session, cfg) that deletes all charts, datasets, dashboard by UUID
Constraint: never deletes DB connection
Acceptance: running _wipe then full rebuild produces identical result

Task 6: Manual completion and ZIP export

Once tasks 1–5 complete: manually drag-and-drop all 6 charts into correct positions
Export dashboard as ZIP from UI
Commit ZIP to git
Test POST /api/v1/assets/import/ with ZIP on clean Superset instance

### Known bugs — do not attempt to fix, document only

B1: POST /api/v1/dashboard/ never writes dashboard_slices — workaround is manual drag-and-drop then ZIP export
B2: PUT /api/v1/dashboard/ rejects slices field in Superset 6.0.0
B3: Recreating a dataset breaks chart links — never recreate datasets
B4: YAML import does not write dashboard_slices
B5: Chart params stored correctly but UI ignores some rendering params
B6: filter_time only shows relative ranges — use filter_range instead

### Files:

## Bugs and design decisions (final):Bugs and design decisions (final):
Confirmed Superset bugs:
B1 — POST /api/v1/dashboard/ never writes dashboard_slices
Charts appear in position_json but show "no chart definition" message. Only a UI save writes to the dashboard_slices join table. No REST API workaround found. Decision: build everything programmatically, do one manual drag-and-drop, then export ZIP for prod deploy.
B2 — PUT /api/v1/dashboard/ rejects slices field in Superset 6.0.0
{'message': {'slices': ['Unknown field.']}} — accepted on PUT in older versions, rejected in 6.0.0.
B3 — Virtual dataset → physical dataset change breaks chart links
Charts store datasource_id as integer PK. Recreating a dataset generates a new ID, silently breaking all charts pointing to it. Decision: physical datasets only, never recreate.
B4 — YAML import does not write dashboard_slices
Same root cause as B1. Import succeeds, structure appears, charts show "no definition." Hand-editing YAML also causes schema mismatch failures.
B5 — Chart params stored correctly but UI ignores some
number_format, column_config, subheader all confirmed correct in DB via API but inconsistently applied in rendering. Workaround: push formatting into Postgres views where possible.
B6 — Native filter filter_time only shows relative ranges
Cannot be bounded by dataset start_date/end_date. Decision: use filter_range on date column for absolute calendar picker.

Design decisions:
D1 — Pure REST API, no YAML
YAML import/export is unreliable across versions and hand-editing breaks imports. All assets created programmatically via REST API.
D2 — Fixed UUIDs for all assets
Charts, datasets, and dashboard all have fixed UUIDs as constants in dashboard.py. Prevents ID drift on rebuild.
D3 — Physical datasets only
No virtual datasets in Superset. Wide-to-long pivots done in Postgres views (gold.v_modalsplit, gold.v_summary_table, gold.v_pairs).
D4 — dashboard.py is a one-time setup tool
Called once from the initial DAG. Weekly DAG never touches Superset — data freshness is purely a Postgres concern.
D5 — Dashboard deploy via ZIP import in prod
Once dashboard is manually completed (drag-and-drop), export ZIP, commit to git, deploy via POST /api/v1/assets/import/ which correctly writes dashboard_slices.

## useful urls

Superset bugs:

https://github.com/apache/superset/issues/32966 — dashboard chart linking bug (dashboard_slices)
https://github.com/apache/superset/discussions/18338 — timeseries bar x-axis categorical vs linear

Superset filter state:

https://preset.io/blog/managing-filter-state-for-embedded-dashboards/ — native filter schema reference
https://github.com/apache/superset/discussions/34873 — native filter preselect and hidden
https://www.blef.fr/superset-filters-in-url — URL filter params format

ECharts (underlying library):

https://apache.github.io/echarts-handbook/en/how-to/chart-types/bar/basic-bar/ — bar chart params including boundaryGap
https://github.com/apache/echarts/issues/15733 — boundaryGap for category axis

Superset viz plugins:

https://preset.io/blog/enhancing-superset-visualization-plugins-part-1/ — generic chart axis feature flag
https://preset.io/blog/echarts-time-series-visualizations-in-superset/ — ECharts timeseries viz types explained

Worth bookmarking for next session: https://github.com/apache/superset/issues and searching by viz type when you hit rendering bugs — the issue tracker is more useful than the official docs for Superset 6.x specifics.

## Code

### View and table snippets:
def _modalsplit_view(engine) -> None:
    """Creates long-format view of gold.dashboard for modalsplit pie chart."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW gold.v_modalsplit AS
            SELECT date, mission_id, streetnr, day_of_week_num, day_of_week_name, 'Auto' AS "Fahrzeugtyp", car AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week_num, day_of_week_name, 'Fahrrad' AS "Fahrzeugtyp", bicycle AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week_num, day_of_week_name, 'LKW' AS "Fahrzeugtyp", lorry AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week_num, day_of_week_name, 'Motorrad' AS "Fahrzeugtyp", motorbike AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week_num, day_of_week_name, 'Lieferwagen' AS "Fahrzeugtyp", delivery_van AS value FROM gold.dashboard
            UNION ALL
            SELECT date, mission_id, streetnr, day_of_week_num, day_of_week_name, 'Sonstige' AS "Fahrzeugtyp", other AS value FROM gold.dashboard
                    """))
        conn.commit()
        logger.info("View gold.v_modalsplit created.")

def _summary_table_view(engine) -> None:
    """Creates long-format view of gold.dashboard for summary table chart."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW gold.v_summary_table AS
            SELECT * FROM (
            SELECT 1 AS sort_order, 'Auto' AS "Fahrzeugtyp", date, mission_id, streetnr, day_of_week_num, day_of_week_name, car AS daily_total, v_car AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 2, 'Fahrrad', date, mission_id, streetnr, day_of_week_num, day_of_week_name, bicycle AS daily_total, NULL AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 3, 'Lieferwagen', date, mission_id, streetnr, day_of_week_num, day_of_week_name, delivery_van AS daily_total, v_delivery_van AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 4, 'LKW', date, mission_id, streetnr, day_of_week_num, day_of_week_name, lorry AS daily_total, v_lorry AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 5, 'Motorrad', date, mission_id, streetnr, day_of_week_num, day_of_week_name, motorbike AS daily_total, v_motorbike AS avg_speed FROM gold.dashboard
            UNION ALL
            SELECT 6, 'Sonstige', date, mission_id, streetnr, day_of_week_num, day_of_week_name, other AS daily_total, NULL AS avg_speed FROM gold.dashboard
            ) sub
            ORDER BY sort_order
        """))
        conn.commit()
        logger.info("View gold.v_summary_table created.")

def _create_pairs_view(engine) -> None:
    """Creates view of paired sensor locations for Sensorpaare chart."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW gold.v_pairs AS
            SELECT DISTINCT
                a.date,
                a.mission_id,
                a.streetnr AS "Standort",
                b.streetnr AS "Gegenüberliegender Standort"
            FROM gold.dashboard a
            JOIN gold.dashboard b ON a.paired_mission_id = b.mission_id
            WHERE a.is_pair = true
        """))
        conn.commit()
        logger.info("View gold.v_pairs created.")

def load_dashboard(run_type) -> tuple[int, datetime]:
    """
    Loads rows from gold.export aggregates by day. One row = one day.
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    dq_engine = get_dq_engine()
    logger.info("=== gold.dashboard update start ===")

    #check watermark is there, if not add it and raise error if missing on weekly run
    with engine.connect() as conn:
        watermark = _get_or_create_watermark(
            conn,
            "gold.dashboard",
            run_type,
            "SELECT MAX(dashboard_processed_at) FROM gold.dashboard",
            dq_engine
        )

    # insert new rows & aggregate them
    with engine.connect() as conn:
        result =conn.execute(
            text(
            """
            INSERT INTO gold.dashboard (
                mission_id, start_date, end_date, date,  day_of_week_num, day_of_week_name, streetnr, city,
                location_description, lat, lon, car, bicycle, delivery_van, motorbike, lorry, other, v_car,
                v_delivery_van, v_motorbike, v_lorry, v85, is_pair, paired_mission_id, dashboard_processed_at
            )
            SELECT
                mission_id,
                start_date,
                end_date,
                date,
                day_of_week_num,
                day_of_week_name,
                street || ' ' || street_number AS streetnr,
                city,
                location_description,
                lat,
                lon,
                SUM(car)                    AS car,
                SUM(bicycle)                AS bicycle,
                SUM(delivery_van)           AS delivery_van,
                SUM(motorbike)              AS motorbike,
                SUM(lorry)                  AS lorry,
                SUM(other_motorised_vehicle) AS other,
                SUM(v_car * car) / NULLIF(SUM(car), 0)                             AS v_car,
                SUM(v_delivery_van * delivery_van) / NULLIF(SUM(delivery_van), 0)  AS v_delivery_van,
                SUM(v_motorbike * motorbike) / NULLIF(SUM(motorbike), 0)           AS v_motorbike,
                SUM(v_lorry * lorry)  / NULLIF(SUM(lorry), 0)                      AS v_lorry,
                v85,
                is_pair,
                paired_mission_id,
                NOW() AS dashboard_processed_at
            FROM gold.export
            WHERE gold_processed_at > :watermark
            GROUP BY
                date,
                day_of_week_num,
                day_of_week_name,
                mission_id,
                start_date,
                end_date,
                street,
                street_number,
                city,
                location_description,
                lat,
                lon,
                v85,
                is_pair,
                paired_mission_id
            ON CONFLICT (mission_id, date) DO UPDATE SET
                start_date                  = EXCLUDED.start_date,
                end_date                    = EXCLUDED.end_date,
                streetnr                    = EXCLUDED.streetnr,
                city                        = EXCLUDED.city,
                location_description        = EXCLUDED.location_description,
                lat                         = EXCLUDED.lat,
                lon                         = EXCLUDED.lon,
                car                         = EXCLUDED.car,
                bicycle                     = EXCLUDED.bicycle,
                delivery_van                = EXCLUDED.delivery_van,
                motorbike                   = EXCLUDED.motorbike,
                lorry                       = EXCLUDED.lorry,
                other                       = EXCLUDED.other,
                v_car                       = EXCLUDED.v_car,
                v_delivery_van              = EXCLUDED.v_delivery_van,
                v_motorbike                 = EXCLUDED.v_motorbike,
                v_lorry                     = EXCLUDED.v_lorry,
                v85                         = EXCLUDED.v85,
                is_pair                     = EXCLUDED.is_pair,
                paired_mission_id           = EXCLUDED.paired_mission_id,
                dashboard_processed_at      = NOW()
            """),
            {"watermark": watermark})
        conn.commit()
        logger.info("Dashboard table build complete - %d new rows appended to gold.dashboard.", result.rowcount)

    with engine.connect() as conn:
        conn.execute(
            text(
            """
            UPDATE gold.watermark SET last_processed = NOW() WHERE table_name = 'gold.dashboard'
            """)
        )
        conn.commit()
        today=datetime.now()
        logger.info("gold.watermarktable dashboard watermark updated with date %s ", today)

        _modalsplit_view(engine)
        _summary_table_view(engine)
        _create_pairs_view(engine)

    return result.rowcount, today


def load_ganglinien(run_type) -> tuple[int, datetime]:
    """
    Loads rows from gold.export aggregated by hour. One row per (mission_id, date, hour).
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    dq_engine = get_dq_engine()
    logger.info("=== gold.ganglinien update start ===")

    with engine.connect() as conn:
        watermark = _get_or_create_watermark(
            conn,
            "gold.ganglinien",
            run_type,
            "SELECT MAX(ganglinien_processed_at) FROM gold.ganglinien",
            dq_engine
        )

    with engine.connect() as conn:
        result = conn.execute(
            text("""
            INSERT INTO gold.ganglinien (
                mission_id, date, hour, day_of_week_num, day_of_week_name,
                streetnr, car, bicycle, delivery_van, motorbike, lorry,
                ganglinien_processed_at
            )
            SELECT
                mission_id,
                date,
                hour,
                day_of_week_num,
                day_of_week_name,
                street || ' ' || street_number AS streetnr,
                car,
                bicycle,
                delivery_van,
                motorbike,
                lorry,
                NOW() AS ganglinien_processed_at
            FROM gold.export
            WHERE gold_processed_at > :watermark
            ON CONFLICT (mission_id, date, hour) DO UPDATE SET
                day_of_week_num         = EXCLUDED.day_of_week_num,
                day_of_week_name        = EXCLUDED.day_of_week_name,
                streetnr                = EXCLUDED.streetnr,
                car                     = EXCLUDED.car,
                bicycle                 = EXCLUDED.bicycle,
                delivery_van            = EXCLUDED.delivery_van,
                motorbike               = EXCLUDED.motorbike,
                lorry                   = EXCLUDED.lorry,
                ganglinien_processed_at = NOW()
            """),
            {"watermark": watermark}
        )

### Current state of dashboard.py --- this si what we will be working on

```python
import logging
import os
import requests
from pathlib import Path
import json
import uuid
import time
from dotenv import dotenv_values

logger = logging.getLogger(__name__)
DB_CONNECTION_NAME = "berlin_traffic"

UUID_DATASET_DASHBOARD  = "00000000-0000-0000-0001-000000000001"
UUID_DATASET_GANGLINIEN = "00000000-0000-0000-0001-000000000002"
UUID_DATASET_MODALSPLIT = "00000000-0000-0000-0001-000000000003"
UUID_DATASET_SUMMARY    = "00000000-0000-0000-0001-000000000004"
UUID_DATASET_PAIRS      = "00000000-0000-0000-0001-000000000005"

UUID_CHART_V85        = "00000000-0000-0000-0000-000000000001"
UUID_CHART_MAP        = "00000000-0000-0000-0000-000000000002"
UUID_CHART_GANGLINIEN = "00000000-0000-0000-0000-000000000003"
UUID_CHART_MODALSPLIT = "00000000-0000-0000-0000-000000000004"
UUID_CHART_SUMMARY    = "00000000-0000-0000-0000-000000000005"
UUID_CHART_PAIRS      = "00000000-0000-0000-0000-000000000006"

UUID_DASHBOARD        = "00000000-0000-0000-0000-000000000010"

DASHBOARD_CSS = """
        @font-face {
        font-family: "BerlinType";
        src: url("https://storage.data-hub.berlin/assets/fonts/BerlinTypeWeb-Regular.woff2") format("woff2"),
            url("https://storage.data-hub.berlin/assets/fonts/BerlinTypeWeb-Regular.woff") format("woff"),
            url("https://storage.data-hub.berlin/assets/fonts/BerlinTypeWeb-Regular.eot");
        font-weight: 400;
        font-style: normal;
        font-display: swap;
        }
        @font-face {
        font-family: "BerlinType";
        src: url("https://storage.data-hub.berlin/assets/fonts/BerlinTypeWeb-Bold.woff2") format("woff2"),
            url("https://storage.data-hub.berlin/assets/fonts/BerlinTypeWeb-Bold.woff") format("woff"),
            url("https://storage.data-hub.berlin/assets/fonts/BerlinTypeWeb-Bold.eot");
        font-weight: 700;
        font-style: normal;
        font-display: swap;
        }
        .dashboard-content * {
        font-family: "BerlinType", system-ui, -apple-system, Roboto, Arial, sans-serif;
        }
        """

# --------------------Authenticate to Superset-----------------------

def _config() -> dict:
    cfg = dotenv_values(Path(__file__).parent.parent / ".env")
    return {
        "SUPERSET_URL":              cfg["SUPERSET_URL"],
        "SUPERSET_ADMIN_USER":       cfg["SUPERSET_ADMIN_USER"],
        "SUPERSET_ADMIN_PASSWORD":   cfg["SUPERSET_ADMIN_PASSWORD"],
        "POSTGRES_TRAFFIC_USER":     cfg["POSTGRES_TRAFFIC_USER"],
        "POSTGRES_TRAFFIC_PASSWORD": cfg["POSTGRES_TRAFFIC_PASSWORD"],
        "POSTGRES_TRAFFIC_HOST":     cfg["POSTGRES_TRAFFIC_HOST"],
        "POSTGRES_TRAFFIC_PORT":     cfg["POSTGRES_TRAFFIC_PORT"],
        "POSTGRES_TRAFFIC_DB":       cfg["POSTGRES_TRAFFIC_DB"],
    }

def _authenticate(cfg: dict) -> requests.Session:
    """ get JWT adn CSRF tokens"""
    session = requests.Session()

    resp = session.post(
        f"{cfg['SUPERSET_URL']}/api/v1/security/login",
        json={
            "username": cfg["SUPERSET_ADMIN_USER"],
            "password": cfg["SUPERSET_ADMIN_PASSWORD"],
            "provider": "db",
            "refresh":  True,
        },
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]

    csrf = session.get(
        f"{cfg['SUPERSET_URL']}/api/v1/security/csrf_token/",
        headers={"Authorization": f"Bearer {token}"},
    )
    csrf.raise_for_status()

    session.headers.update({
        "Authorization": f"Bearer {token}",
        "X-CSRFToken":   csrf.json()["result"],
        "Content-Type":  "application/json",
        "Referer":       cfg["SUPERSET_URL"],
    })
    logger.info("Authenticated to Superset at %s", cfg["SUPERSET_URL"])
    return session


# -------------------Register the Postgres database connection---------------

def _db_connection(session: requests.Session, cfg: dict) -> int:

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/database/")
    resp.raise_for_status()
    for db in resp.json().get("result", []):
        if db["database_name"] == DB_CONNECTION_NAME:
            logger.info("DB connection already exists (id=%s)", db["id"])
            return db["id"]

    # register postgres connection string inside Superset so that Superset can query it
    sqlalchemy_uri = (
        f"postgresql+psycopg2://"
        f"{cfg['POSTGRES_TRAFFIC_USER']}:{cfg['POSTGRES_TRAFFIC_PASSWORD']}"
        f"@{cfg['POSTGRES_TRAFFIC_HOST']}:{cfg['POSTGRES_TRAFFIC_PORT']}"
        f"/{cfg['POSTGRES_TRAFFIC_DB']}"
    )
    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/database/", json={
        "database_name":    DB_CONNECTION_NAME,
        "sqlalchemy_uri":   sqlalchemy_uri,
        "expose_in_sqllab": True,
    })
    resp.raise_for_status()
    db_id = resp.json()["id"]
    logger.info("DB connection created (id=%s)", db_id)
    return db_id

# --------------- Create datasets-------------------------
# (physical tables, not virtual — gold.dashboard and gold.ganglinien)
#note: Superset uses the term dataset for tables in our database

def _get_or_create_dataset(session: requests.Session, cfg: dict, db_id: int, schema: str, table_name: str, dataset_uuid: str) -> int:

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dataset/")
    resp.raise_for_status()
    for ds in resp.json().get("result", []):
        if ds["schema"] == schema and ds["table_name"] == table_name:
            logger.info("Dataset %s.%s already exists (id=%s)", schema, table_name, ds["id"])
            return ds["id"]

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/dataset/", json={
        "database":   db_id,
        "schema":     schema,
        "table_name": table_name,
        "uuid":       dataset_uuid,
    })
    resp.raise_for_status()
    dataset_id = resp.json()["id"]
    logger.info("Dataset %s.%s created (id=%s)", schema, table_name, dataset_id)
    return dataset_id


# ----------------Create charts (v85 big number, modalsplit pie, übersicht table, ganglinie bar)--

# map
def _chart_map(session: requests.Session, cfg: dict, dataset_id: int) -> int:

    chart_name = "Standorte"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/")
    resp.raise_for_status()
    for chart in resp.json().get("result", []):
        if chart["slice_name"] == chart_name:
            logger.info("Chart '%s' already exists (id=%s)", chart_name, chart["id"])
            return chart["id"]

    params = {
        "viz_type":        "deck_scatter",
        "spatial":         {"type": "latlong", "latCol": "lat", "lonCol": "lon"},
        "point_radius_fixed": {"type": "fix", "value": 100},
        "point_radius_unit":  "pixels",
        "multiplier":   1,
        "color_picker":        {"r": 255, "g": 0, "b": 0, "a": 1},
        "stroke_color_picker": {"r": 255, "g": 0, "b": 0, "a": 1},
        "line_width":      1,
        "time_range":      "No filter",
        "adhoc_filters":   [],
        "tooltip_fields":  ["streetnr"],
        "granularity_sqla": "date"
    }

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/chart/", json={
        "slice_name":      chart_name,
        "viz_type":        "deck_scatter",
        "datasource_id":   dataset_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "uuid":            UUID_CHART_MAP,
    })
    resp.raise_for_status()
    chart_id = resp.json()["id"]
    logger.info("Chart '%s' created (id=%s)", chart_name, chart_id)
    return chart_id

#v85 Big Number
def _chart_v85(session: requests.Session, cfg: dict, dataset_id: int) -> int:

    chart_name = "v85 Durchschnitt"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/")
    resp.raise_for_status()
    for chart in resp.json().get("result", []):
        if chart["slice_name"] == chart_name:
            logger.info("Chart '%s' already exists (id=%s)", chart_name, chart["id"])
            return chart["id"]

    params = {
        "viz_type": "big_number_total",
        "metric": {
            "expressionType": "SQL",
            "sqlExpression":  "AVG(v85)",
            "label":          "km/h",
            "hasCustomLabel": True,
        },
        "subheader": "km/h",
        "subheader_font_size": 0.15,
        "y_axis_format": ".1f",
        "time_range": "No filter",
        "adhoc_filters": [],
        "granularity_sqla": "date"
    }

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/chart/", json={
        "slice_name":      chart_name,
        "viz_type":        "big_number_total",
        "datasource_id":   dataset_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "uuid":            UUID_CHART_V85,
    })
    resp.raise_for_status()
    chart_id = resp.json()["id"]
    logger.info("Chart '%s' created (id=%s)", chart_name, chart_id)
    return chart_id

#Modalsplit
def _chart_modalsplit(session: requests.Session, cfg: dict, dataset_id: int) -> int:

    chart_name = "Modalsplit"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/")
    resp.raise_for_status()
    for chart in resp.json().get("result", []):
        if chart["slice_name"] == chart_name:
            logger.info("Chart '%s' already exists (id=%s)", chart_name, chart["id"])
            return chart["id"]

    params = {
        "viz_type": "pie",
        "metric": {
            "expressionType": "SQL",
            "sqlExpression": "SUM(value)",
            "label": "Fahrzeuge",
            "hasCustomLabel": True,
            "optionName": "metric_Fahrzeuge",
        },
        "groupby": ["Fahrzeugtyp"],
        "adhoc_filters": [],
        "time_range": "No filter",
        "donut": False,
        "show_labels": True,
        "show_legend": True,
        "label_type": "key_percent",
        "number_format": "SMART_NUMBER",
        "show_total": False,
        "granularity_sqla": "date"
    }

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/chart/", json={
        "slice_name":      chart_name,
        "viz_type":        "pie",
        "datasource_id":   dataset_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "uuid":            UUID_CHART_MODALSPLIT,
    })
    resp.raise_for_status()
    chart_id = resp.json()["id"]
    logger.info("Chart '%s' created (id=%s)", chart_name, chart_id)
    return chart_id

#Ganglinien
def _chart_ganglinien(session: requests.Session, cfg: dict, dataset_id: int) -> int:

    chart_name = "Ganglinien"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/")
    resp.raise_for_status()
    for chart in resp.json().get("result", []):
        if chart["slice_name"] == chart_name:
            logger.info("Chart '%s' already exists (id=%s)", chart_name, chart["id"])
            return chart["id"]

    params = {
        "viz_type": "echarts_timeseries_bar",
        "x_axis": "hour",
        "metrics": [
            {"expressionType": "SQL", "sqlExpression": "AVG(bicycle)",     "label": "Fahrrad",     "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "AVG(car)",         "label": "Auto",        "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "AVG(lorry)",       "label": "LKW",         "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "AVG(motorbike)",   "label": "Motorrad",    "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "AVG(delivery_van)","label": "Lieferwagen", "hasCustomLabel": True},
        ],
        "groupby": [],
        "adhoc_filters": [],
        "x_axis_title": "Stunde",
        "y_axis_title": "Ø Anzahl",
        "label_colors": {
            "Fahrrad":     "#00aa84",
            "Auto":        "#f5b4cb",
            "Lieferwagen": "#9185be",
            "Motorrad":    "#f39300",
            "LKW":         "#004f9f",
            "Sonstige":    "#e6e6e6",
        },
        "stack": False,
        "show_legend": True,
        "time_range": "No filter",
        "granularity_sqla": "date",
        "x_axis_title_margin": 30,
    }

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/chart/", json={
        "slice_name":      chart_name,
        "viz_type":        "echarts_timeseries_bar",
        "datasource_id":   dataset_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "uuid":            UUID_CHART_GANGLINIEN,
    })
    resp.raise_for_status()
    chart_id = resp.json()["id"]
    logger.info("Chart '%s' created (id=%s)", chart_name, chart_id)
    return chart_id


#Übersicht
def _chart_summary_table(session: requests.Session, cfg: dict, dataset_id: int) -> int:

    chart_name = "Übersicht"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/")
    resp.raise_for_status()
    for chart in resp.json().get("result", []):
        if chart["slice_name"] == chart_name:
            logger.info("Chart '%s' already exists (id=%s)", chart_name, chart["id"])
            return chart["id"]

    params = {
        "viz_type": "table",
        "query_mode": "aggregate",
        "groupby": ["Fahrzeugtyp"],
        "metrics": [
            {"expressionType": "SQL", "sqlExpression": "SUM(daily_total)", "label": "Gesamt", "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "AVG(daily_total)", "label": "Ø pro Tag", "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "AVG(avg_speed)", "label": "Ø Geschw. (km/h)", "hasCustomLabel": True},
        ],
        "adhoc_filters": [],
        "time_range": "No filter",
        "order_desc": True,
        "show_totals": False,
        "page_length": 0,
        "granularity_sqla": "date"
    }

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/chart/", json={
        "slice_name":      chart_name,
        "viz_type":        "table",
        "datasource_id":   dataset_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "uuid":            UUID_CHART_SUMMARY,
    })
    resp.raise_for_status()
    chart_id = resp.json()["id"]
    logger.info("Chart '%s' created (id=%s)", chart_name, chart_id)
    return chart_id

#Sensorpaare
def _chart_pairs_table(session: requests.Session, cfg: dict, dataset_id: int) -> int:

    chart_name = "Sensorpaare"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/")
    resp.raise_for_status()
    for chart in resp.json().get("result", []):
        if chart["slice_name"] == chart_name:
            logger.info("Chart '%s' already exists (id=%s)", chart_name, chart["id"])
            return chart["id"]

    params = {
        "viz_type":        "table",
        "query_mode":      "raw",
        "columns": ["Standort", "Gegenüberliegender Standort"],
        "adhoc_filters":   [],
        "time_range":      "No filter",
        "granularity_sqla": "date",
        "order_desc":      False,
        "page_length":     0,
    }

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/chart/", json={
        "slice_name":      chart_name,
        "viz_type":        "table",
        "datasource_id":   dataset_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "uuid":            UUID_CHART_PAIRS,
    })
    resp.raise_for_status()
    chart_id = resp.json()["id"]
    logger.info("Chart '%s' created (id=%s)", chart_name, chart_id)
    return chart_id


# ----------------------Create dashboard with layout-----------------------

def _dashboard(session: requests.Session, cfg: dict, chart_ids: dict) -> int:

    dashboard_title = "Verkehrsdaten Tempelhof-Schöneberg"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/")
    print(resp.json())
    resp.raise_for_status()
    for d in resp.json().get("result", []):
        if d["dashboard_title"] == dashboard_title:
            logger.info("Dashboard '%s' already exists (id=%s)", dashboard_title, d["id"])
            return d["id"]

    row0_id = f"ROW-{uuid.uuid4().hex[:8].upper()}"
    row1_id = f"ROW-{uuid.uuid4().hex[:8].upper()}"
    c_map   = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_v85   = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_modal = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_gang  = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_summ  = f"CHART-{uuid.uuid4().hex[:8].upper()}"

    position_json = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [row0_id, row1_id], "parents": ["ROOT_ID"]},
        row0_id: {
            "type": "ROW", "id": row0_id, "children": [c_map, c_v85, c_modal],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        c_map: {
            "type": "CHART", "id": c_map, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row0_id],
            "meta": {"chartId": chart_ids["map"], "uuid": UUID_CHART_MAP, "width": 5, "height": 50, "sliceName": "Standorte"},
        },
        c_v85: {
            "type": "CHART", "id": c_v85, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row0_id],
            "meta": {"chartId": chart_ids["v85"], "uuid": UUID_CHART_V85, "width": 2, "height": 50, "sliceName": "v85 Durchschnitt"},
        },
        c_modal: {
            "type": "CHART", "id": c_modal, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row0_id],
            "meta": {"chartId": chart_ids["modalsplit"], "uuid": UUID_CHART_MODALSPLIT, "width": 5, "height": 50, "sliceName": "Modalsplit"},
        },
        row1_id: {
            "type": "ROW", "id": row1_id, "children": [c_gang, c_summ],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        c_gang: {
            "type": "CHART", "id": c_gang, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row1_id],
            "meta": {"chartId": chart_ids["ganglinien"], "uuid": UUID_CHART_GANGLINIEN, "width": 8, "height": 35, "sliceName": "Ganglinien"},
        },
        c_summ: {
            "type": "CHART", "id": c_summ, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row1_id],
            "meta": {"chartId": chart_ids["summary_table"], "uuid": UUID_CHART_SUMMARY, "width": 4, "height": 35, "sliceName": "Übersicht"},
        },
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": dashboard_title}},
    }

    resp = session.post(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/", json={
        "dashboard_title": dashboard_title,
        "published":       False,
        "css":             DASHBOARD_CSS,
        "uuid":            UUID_DASHBOARD,
        "position_json":   json.dumps(position_json),
        "json_metadata":   json.dumps({
            "refresh_frequency": 0,
            "label_colors": {
                "Fahrrad":     "#00aa84",
                "Auto":        "#f5b4cb",
                "Lieferwagen": "#9185be",
                "Motorrad":    "#f39300",
                "LKW":         "#004f9f",
                "Sonstige":    "#e6e6e6",
            },
        }),
    })
    print(resp.json())
    resp.raise_for_status()
    dashboard_id = resp.json()["id"]
    print(resp.json())

    # fetch dashboard to trigger chart reconciliation
    resp_get = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/{dashboard_id}")
    resp_get.raise_for_status()
    existing = resp_get.json()["result"]

    time.sleep(5)

    resp2 = session.put(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/{dashboard_id}", json={
        "position_json": existing["position_json"],
        "json_metadata":  existing["json_metadata"],
        "css":            existing["css"],
    })

    print(resp2.json())
    logger.info("Dashboard '%s' created (id=%s)", dashboard_title, dashboard_id)

    return dashboard_id

# Add filters (Zeitraum, Standort, Wochentag)


if __name__ == "__main__":
    cfg = _config()
    session = _authenticate(cfg)
    db_id = _db_connection(session, cfg)
    dataset_id_dashboard  = _get_or_create_dataset(session, cfg, db_id, "gold", "dashboard",   UUID_DATASET_DASHBOARD)
    dataset_id_ganglinien = _get_or_create_dataset(session, cfg, db_id, "gold", "ganglinien",  UUID_DATASET_GANGLINIEN)
    dataset_id_modalsplit = _get_or_create_dataset(session, cfg, db_id, "gold", "v_modalsplit", UUID_DATASET_MODALSPLIT)
    dataset_id_summary    = _get_or_create_dataset(session, cfg, db_id, "gold", "v_summary_table", UUID_DATASET_SUMMARY)
    dataset_id_pairs = _get_or_create_dataset(session, cfg, db_id, "gold", "v_pairs", UUID_DATASET_PAIRS)
    chart_id_v85 = _chart_v85(session, cfg, dataset_id_dashboard)
    print(f"v85 {chart_id_v85}")
    chart_id_map = _chart_map(session, cfg, dataset_id_dashboard)
    print(f"map: {chart_id_map}")
    chart_id_ganglinien = _chart_ganglinien(session, cfg, dataset_id_ganglinien)
    print(f"gang: {chart_id_ganglinien}")
    chart_id_modalsplit = _chart_modalsplit(session, cfg, dataset_id_modalsplit)
    print(f"modal: {chart_id_modalsplit}")
    chart_id_summary_table = _chart_summary_table(session, cfg, dataset_id_summary)
    print(f"summ: {chart_id_summary_table}")
    chart_id_pairs = _chart_pairs_table(session, cfg, dataset_id_pairs)
    print(f"pairs: {chart_id_pairs}")

    for chart_id, name in [(chart_id_v85, "v85"), (chart_id_map, "map"),
                        (chart_id_ganglinien, "gang"), (chart_id_modalsplit, "modal"),
                        (chart_id_summary_table, "summ"), (chart_id_pairs, "pairs")]:
        params = json.loads(session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/{chart_id}").json()["result"]["params"])
        print(f"\n=== {name} ===")
        print(json.dumps(params, indent=2))

    # resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/2")
    # import json
    # params = json.loads(resp.json()["result"]["params"])
    # print(json.dumps(params, indent=2))

    # dashboard_id = _dashboard(session, cfg, {
    # "map":           chart_id_map,
    # "v85":           chart_id_v85,
    # "modalsplit":    chart_id_modalsplit,
    # "ganglinien":    chart_id_ganglinien,
    # "summary_table": chart_id_summary_table,
    # })
    # print(f"Dashboard id: {dashboard_id}")

```


##  Previous Bugs & Learnings (older session, for background info nly)

### Context
Building a fully automated, code-first Superset dashboard for Berlin traffic data.
Superset version: 6.0.0 (Docker). Postgres backend. Airflow orchestration.

---

### Bug 1: POST /api/v1/dashboard/ does not link charts

**Status:** Confirmed open bug, present since ~2021, still in 5.0.0 and assumed 6.0.0.
**Symptom:** Dashboard creates successfully with correct `position_json` and chart UUIDs. Charts show "There is no chart definition associated with this component."
**Root cause:** `POST /api/v1/dashboard/` never writes to Superset's `dashboard_slices` join table. Chart-to-dashboard relationship is only written on a UI save.
**GitHub refs:** #15457, #32966
**Workaround attempted:** GET dashboard then PUT same `position_json` back — does not trigger `dashboard_slices` write.
**Confirmed workaround:** Manual UI save (not acceptable for automation).
**Proposed fix:** Direct INSERT into Superset metadata DB `dashboard_slices` table after API dashboard creation.

---

### Bug 2: PUT /api/v1/dashboard/{id} rejects `slices` field

**Status:** Confirmed. `slices` is accepted on PUT in some versions, rejected in 6.0.0.
**Symptom:** `{'message': {'slices': ['Unknown field.']}}`
**Workaround:** None found via REST API alone.

---

### Bug 3: Virtual dataset → physical dataset change breaks chart links

**Status:** Confirmed behaviour (not strictly a bug but a hard constraint).
**Symptom:** Changing a virtual dataset to a physical one, or recreating a dataset, generates a new dataset ID. Any chart pointing to the old ID loses its data source silently.
**Root cause:** Charts store `datasource_id` (integer PK), not a stable UUID.
**Decision taken:** Use physical datasets only from the start. Never change a dataset — only update the underlying table.

---

### Bug 4: YAML import does not reconcile chart-to-dashboard links

**Status:** Confirmed open bug (#26338).
**Symptom:** Import succeeds, dashboard structure appears, charts show "no definition" message.
**Root cause:** Import updates `position_json` chartId references but does not write `dashboard_slices`.
**Note:** Also observed that editing YAML manually after export breaks import entirely — schema mismatches cause silent failures.

---

### Bug 5: Native filter chart scope uses integer IDs not UUIDs (partially fixed)

**Status:** Fixed in recent versions. Assumption: fixed in 6.0.0 — not yet verified.
**Symptom:** Native filter `chartsInScope` stores integer chart IDs. On import to a different instance, IDs differ and filters break.
**Implication:** If we ever migrate dashboards between instances, native filters will need manual repair.
