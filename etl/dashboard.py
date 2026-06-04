import logging
import os
import requests
import json
import uuid
import time
import zipfile
import io
import re


logger = logging.getLogger(__name__)
DB_CONNECTION_NAME = "berlin_traffic"

# --------------------Authenticate to Superset-----------------------

def _config() -> dict:
    return {
        "SUPERSET_URL":              os.environ["SUPERSET_URL"],
        "SUPERSET_ADMIN_USER":       os.environ["SUPERSET_ADMIN_USER"],
        "SUPERSET_ADMIN_PASSWORD":   os.environ["SUPERSET_ADMIN_PASSWORD"],
        "POSTGRES_TRAFFIC_USER":     os.environ["POSTGRES_TRAFFIC_USER"],
        "POSTGRES_TRAFFIC_PASSWORD": os.environ["POSTGRES_TRAFFIC_PASSWORD"],
        "POSTGRES_TRAFFIC_HOST":     os.environ["POSTGRES_TRAFFIC_HOST"],
        "POSTGRES_TRAFFIC_PORT":     os.environ["POSTGRES_TRAFFIC_PORT"],
        "POSTGRES_TRAFFIC_DB":       os.environ["POSTGRES_TRAFFIC_DB"],
        "SUPERSET_DASHBOARD_ZIP_PATH": os.environ["SUPERSET_DASHBOARD_ZIP_PATH"],
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


def import_dashboard() -> None:
    cfg = _config()
    session = _authenticate(cfg)
    zip_path = cfg["SUPERSET_DASHBOARD_ZIP_PATH"]

    session.headers.pop("Content-Type", None)

    passwords = json.dumps({"databases/berlin_traffic.yaml": cfg["POSTGRES_TRAFFIC_PASSWORD"]})

    buf = io.BytesIO()
    with zipfile.ZipFile(zip_path, "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith("metadata.yaml"):
                content = data.decode()
                content = re.sub(r"^type:.*$", "type: assets", content, flags=re.MULTILINE)
                data = content.encode()
            zout.writestr(item, data)

    buf.seek(0)

    resp = session.post(
        f"{cfg['SUPERSET_URL']}/api/v1/assets/import/",
        files={"bundle": ("dashboard.zip", buf, "application/zip")},
        data={"overwrite": "true", "passwords": passwords},
    )

    if resp.ok:
        logger.info("Dashboard imported successfully from", zip_path)
    else:
        logger.error("Dashboard import failed:", resp.status_code, resp.text)
        resp.raise_for_status()

#-----------------------------------------------------------------------------
#-----------------------------------------------------------------------------
#--The below creates the dashboard programmatically in Superset.--------------
#----------------------------------------------------------------------------
#use the code if you want to chaneg the dashboard layout programmatically----


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

    chart_name = "v85 Durchschnitt (motorisert)"

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
        "show_legend": True,
        "time_range": "No filter",
        "granularity_sqla": "date",
        "x_axis_title_margin": 30,
        "x_axis_sort": "hour",
        "x_axis_sort_asc": True,
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
        "viz_type":         "table",
        "query_mode":       "aggregate",
        "groupby":          ["streetnr"],
        "metrics":          [
            {"expressionType": "SQL", "sqlExpression": "MAX(\"Gegenüberliegender Standort\")", "label": "Gegenüberliegender Standort", "hasCustomLabel": True},
        ],
        "adhoc_filters":    [],
        "time_range":       "No filter",
        "granularity_sqla": "date",
        "order_desc":       False,
        "page_length":      0,
        "column_config": {
            "streetnr": {"label": "Standort"},
        },
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


# ----------------------Create dashboard -----------------------
#--- note adding charts to Superset has to be done manually - nown bug

def _dashboard(session: requests.Session, cfg: dict, chart_ids: dict) -> int:

    dashboard_title = "Verkehrsdaten Tempelhof-Schöneberg"

    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/")
    resp.raise_for_status()
    for d in resp.json().get("result", []):
        if d["dashboard_title"] == dashboard_title:
            logger.info("Dashboard '%s' already exists (id=%s)", dashboard_title, d["id"])
            return d["id"]

    row0_id = f"ROW-{uuid.uuid4().hex[:8].upper()}"
    row1_id = f"ROW-{uuid.uuid4().hex[:8].upper()}"
    row2_id = f"ROW-{uuid.uuid4().hex[:8].upper()}"
    row3_id = f"ROW-{uuid.uuid4().hex[:8].upper()}"
    c_map   = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_v85   = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_modal = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_summ  = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_gang  = f"CHART-{uuid.uuid4().hex[:8].upper()}"
    c_pairs = f"CHART-{uuid.uuid4().hex[:8].upper()}"

    position_json = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {
            "type": "GRID", "id": "GRID_ID",
            "children": [row0_id, row1_id, row2_id, row3_id],
            "parents": ["ROOT_ID"],
        },
        "HEADER_ID": {
            "id": "HEADER_ID", "type": "HEADER",
            "meta": {"text": dashboard_title},
        },
        # Row 0: map + v85
        row0_id: {
            "type": "ROW", "id": row0_id,
            "children": [c_map, c_v85],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        c_map: {
            "type": "CHART", "id": c_map, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row0_id],
            "meta": {"chartId": chart_ids["map"], "uuid": UUID_CHART_MAP, "width": 9, "height": 50, "sliceName": "Standorte"},
        },
        c_v85: {
            "type": "CHART", "id": c_v85, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row0_id],
            "meta": {"chartId": chart_ids["v85"], "uuid": UUID_CHART_V85, "width": 3, "height": 50, "sliceName": "v85 Durchschnitt (motorisert)"},
        },
        # Row 1: modalsplit + übersicht
        row1_id: {
            "type": "ROW", "id": row1_id,
            "children": [c_modal, c_summ],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        c_modal: {
            "type": "CHART", "id": c_modal, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row1_id],
            "meta": {"chartId": chart_ids["modalsplit"], "uuid": UUID_CHART_MODALSPLIT, "width": 6, "height": 71, "sliceName": "Modalsplit"},
        },
        c_summ: {
            "type": "CHART", "id": c_summ, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row1_id],
            "meta": {"chartId": chart_ids["summary_table"], "uuid": UUID_CHART_SUMMARY, "width": 6, "height": 71, "sliceName": "Übersicht"},
        },
        # Row 2: ganglinien
        row2_id: {
            "type": "ROW", "id": row2_id,
            "children": [c_gang],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        c_gang: {
            "type": "CHART", "id": c_gang, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row2_id],
            "meta": {"chartId": chart_ids["ganglinien"], "uuid": UUID_CHART_GANGLINIEN, "width": 12, "height": 74, "sliceName": "Ganglinien"},
        },
        # Row 3: sensorpaare
        row3_id: {
            "type": "ROW", "id": row3_id,
            "children": [c_pairs],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        c_pairs: {
            "type": "CHART", "id": c_pairs, "children": [],
            "parents": ["ROOT_ID", "GRID_ID", row3_id],
            "meta": {"chartId": chart_ids["pairs"], "uuid": UUID_CHART_PAIRS, "width": 4, "height": 61, "sliceName": "Sensorpaare"},
        },
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
    resp.raise_for_status()
    dashboard_id = resp.json()["id"]
    logger.info("Dashboard '%s' created (id=%s)", dashboard_title, dashboard_id)
    return dashboard_id


# Add filters (Zeitraum, Standort, Wochentag)

def _add_native_filters(session: requests.Session, cfg: dict, dashboard_id: int,
                        dataset_ids: dict, chart_ids: dict) -> None:

    # get all chart integer ids in scope
    charts_in_scope = list(chart_ids.values())

    # get dataset integer ids
    ds_dashboard  = dataset_ids["dashboard"]
    ds_ganglinien = dataset_ids["ganglinien"]
    ds_modalsplit = dataset_ids["modalsplit"]
    ds_summary    = dataset_ids["summary"]
    ds_pairs      = dataset_ids["pairs"]

    native_filter_configuration = [
        {
            "id": "NATIVE_FILTER-standort",
            "type": "NATIVE_FILTER",
            "name": "Standort",
            "filterType": "filter_select",
            "targets": [
                {"column": {"name": "streetnr"}, "datasetUuid": UUID_DATASET_DASHBOARD},
                {"column": {"name": "streetnr"}, "datasetUuid": UUID_DATASET_GANGLINIEN},
                {"column": {"name": "streetnr"}, "datasetUuid": UUID_DATASET_MODALSPLIT},
                {"column": {"name": "streetnr"}, "datasetUuid": UUID_DATASET_SUMMARY},
                {"column": {"name": "streetnr"}, "datasetUuid": UUID_DATASET_PAIRS},
            ],
            "controlValues": {
                "enableEmptyFilter": False,
                "defaultToFirstItem": False,
                "multiSelect": True,
                "searchAllOptions": False,
                "inverseSelection": False,
                "creatable": False,
            },
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": charts_in_scope,
            "tabsInScope": [],
            "description": "Wähle einen oder mehrere Standorte:",
        },
        {
            "id": "NATIVE_FILTER-zeitraum",
            "type": "NATIVE_FILTER",
            "name": "Zeitraum",
            "filterType": "filter_time",
            "targets": [{}],
            "controlValues": {"enableEmptyFilter": False},
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": charts_in_scope,
            "tabsInScope": [],
            "description": "",
        },
        {
            "id": "NATIVE_FILTER-wochentag",
            "type": "NATIVE_FILTER",
            "name": "Wochentag",
            "filterType": "filter_select",
            "targets": [{"column": {"name": "day_of_week"}, "datasetUuid": UUID_DATASET_DASHBOARD}],
            "controlValues": {
                "enableEmptyFilter": False,
                "defaultToFirstItem": False,
                "multiSelect": True,
                "searchAllOptions": False,
                "inverseSelection": False,
                "creatable": False,
            },
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "chartsInScope": charts_in_scope,
            "tabsInScope": [],
            "description": "",
        },
    ]

    # fetch existing json_metadata
    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/{dashboard_id}")
    resp.raise_for_status()
    existing = resp.json()["result"]
    metadata = json.loads(existing["json_metadata"])

    metadata["native_filter_configuration"] = native_filter_configuration

    resp = session.put(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/{dashboard_id}", json={
        "json_metadata": json.dumps(metadata),
    })
    resp.raise_for_status()
    logger.info("Native filters added to dashboard %s", dashboard_id)

# Fix formatting

def _set_column_properties(session: requests.Session, cfg: dict,
                           dataset_id: int, column_name: str, properties: dict) -> None:
    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dataset/{dataset_id}")
    resp.raise_for_status()
    columns = resp.json()["result"]["columns"]

    # strip read-only fields that PUT rejects
    allowed_keys = {
        "id", "column_name", "type", "verbose_name", "description",
        "expression", "filterable", "groupby", "is_dttm",
        "python_date_format", "extra"
    }
    cleaned = []
    for col in columns:
        clean_col = {k: v for k, v in col.items() if k in allowed_keys}
        if col["column_name"] == column_name:
            clean_col.update(properties)
        cleaned.append(clean_col)

    resp = session.put(f"{cfg['SUPERSET_URL']}/api/v1/dataset/{dataset_id}", json={
        "columns": cleaned
    })
    print(resp.json())
    resp.raise_for_status()
    logger.info("Column '%s' properties updated on dataset %s", column_name, dataset_id)


def _wipe(session: requests.Session, cfg: dict) -> None:
    """Deletes all assets created by setup(). Does not delete the DB connection."""

    # delete dashboard
    resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/")
    resp.raise_for_status()
    for d in resp.json().get("result", []):
        if d["uuid"] == UUID_DASHBOARD:
            session.delete(f"{cfg['SUPERSET_URL']}/api/v1/dashboard/{d['id']}")
            logger.info("Deleted dashboard id=%s", d["id"])

    # delete charts
    for chart_uuid in [UUID_CHART_V85, UUID_CHART_MAP, UUID_CHART_GANGLINIEN,
                       UUID_CHART_MODALSPLIT, UUID_CHART_SUMMARY, UUID_CHART_PAIRS]:
        resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/chart/")
        resp.raise_for_status()
        for c in resp.json().get("result", []):
            if c["uuid"] == chart_uuid:
                session.delete(f"{cfg['SUPERSET_URL']}/api/v1/chart/{c['id']}")
                logger.info("Deleted chart uuid=%s id=%s", chart_uuid, c["id"])

    # delete datasets
    for dataset_uuid in [UUID_DATASET_DASHBOARD, UUID_DATASET_GANGLINIEN,
                         UUID_DATASET_MODALSPLIT, UUID_DATASET_SUMMARY, UUID_DATASET_PAIRS]:
        resp = session.get(f"{cfg['SUPERSET_URL']}/api/v1/dataset/")
        resp.raise_for_status()
        for ds in resp.json().get("result", []):
            if ds["uuid"] == dataset_uuid:
                session.delete(f"{cfg['SUPERSET_URL']}/api/v1/dataset/{ds['id']}")
                logger.info("Deleted dataset uuid=%s id=%s", dataset_uuid, ds["id"])

def setup(wipe_first: bool = False) -> None:
    """
    One-time setup: creates DB connection, datasets, charts, dashboard and native filters in Superset.
    Safe to call multiple times — skips assets that already exist.
    """
    cfg = _config()
    session = _authenticate(cfg)
    if wipe_first:
        _wipe(session, cfg)

    db_id = _db_connection(session, cfg)
    logger.info("DB connection id: %s", db_id)

    dataset_id_dashboard  = _get_or_create_dataset(session, cfg, db_id, "gold", "dashboard",      UUID_DATASET_DASHBOARD)
    dataset_id_ganglinien = _get_or_create_dataset(session, cfg, db_id, "gold", "ganglinien",      UUID_DATASET_GANGLINIEN)
    dataset_id_modalsplit = _get_or_create_dataset(session, cfg, db_id, "gold", "v_modalsplit",    UUID_DATASET_MODALSPLIT)
    dataset_id_summary    = _get_or_create_dataset(session, cfg, db_id, "gold", "v_summary_table", UUID_DATASET_SUMMARY)
    dataset_id_pairs      = _get_or_create_dataset(session, cfg, db_id, "gold", "v_pairs",         UUID_DATASET_PAIRS)

    _set_column_properties(session, cfg, dataset_id_pairs, "streetnr", {"verbose_name": "Standort"})
    session.put(f"{cfg['SUPERSET_URL']}/api/v1/dataset/{dataset_id_pairs}/refresh")
    session.put(f"{cfg['SUPERSET_URL']}/api/v1/dataset/{dataset_id_modalsplit}/refresh")
    session.put(f"{cfg['SUPERSET_URL']}/api/v1/dataset/{dataset_id_dashboard}/refresh")

    chart_id_v85           = _chart_v85(session, cfg, dataset_id_dashboard)
    chart_id_map           = _chart_map(session, cfg, dataset_id_dashboard)
    chart_id_ganglinien    = _chart_ganglinien(session, cfg, dataset_id_ganglinien)
    chart_id_modalsplit    = _chart_modalsplit(session, cfg, dataset_id_modalsplit)
    chart_id_summary_table = _chart_summary_table(session, cfg, dataset_id_summary)
    chart_id_pairs         = _chart_pairs_table(session, cfg, dataset_id_pairs)

    dashboard_id = _dashboard(session, cfg, {
        "map":           chart_id_map,
        "v85":           chart_id_v85,
        "modalsplit":    chart_id_modalsplit,
        "ganglinien":    chart_id_ganglinien,
        "summary_table": chart_id_summary_table,
        "pairs":         chart_id_pairs,
    })

    _add_native_filters(session, cfg, dashboard_id, {
        "dashboard":  dataset_id_dashboard,
        "ganglinien": dataset_id_ganglinien,
        "modalsplit":  dataset_id_modalsplit,
        "summary":    dataset_id_summary,
        "pairs":      dataset_id_pairs,
    }, {
        "v85":           chart_id_v85,
        "map":           chart_id_map,
        "ganglinien":    chart_id_ganglinien,
        "modalsplit":    chart_id_modalsplit,
        "summary_table": chart_id_summary_table,
        "pairs":         chart_id_pairs,
    })

    logger.info("Superset setup complete. Dashboard id: %s", dashboard_id)



if __name__ == "__main__":
    cfg = _config()
    session = _authenticate(cfg)
    _wipe(session, cfg)
    import_dashboard()
