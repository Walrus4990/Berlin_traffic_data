## instrcitions

i wanr to build a superset dashboard with fours charts: map of all sensors, v85 displayed as lareg number, summary table adn ganglinien chart
below is teh table that I can buidl from as well as eth charts i want to build and teh filzters i need.

i hve already tried thsi via yaml and teh UII it is driving me craz - so please look at superset carefully look at instructions of how to buidl a superset dashboadr from scratch using commands adn yaml.

help me buidl it from scratch, lets' buidl one really easy chart first to learn and buidl up eth dashboard from there


## Datasets


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

## Filters

Filters:Filters:

Zeitraum — filter_time, date range picker, default "Last 30 days", applies to all charts
Standort — filter_select on streetnr from gold.dashboard, multiselect, searches all options

Display per location:

streetnr — primary label in the Standort filter dropdown (street || ' ' || street_number)
location_description — shown as additional context alongside streetnr
city — shown for borough context

Pair button:

Appears only when is_pair = true
Opens same dashboard in new tab filtered to paired_mission_id
Independent date range slider in the new tab

The pair button is the one thing not achievable purely in YAML — it needs either a custom URL or a Jinja template in Superset.

## tables and where they point to

SELECT AVG(v85) AS v85
FROM gold.dashboard
WHERE date >= [filter_start] AND date <= [filter_end]


Modalsplit — pie
-- Converts wide table (one col per vehicle type) to long format
-- Required by Superset pie chart which expects one row per category
SELECT date, mission_id, 'Fahrrad'      AS vehicle_type, bicycle      AS count FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'Auto',                    car                   FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'LKW',                           lorry                 FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'Motorrad',                      motorbike             FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'Lieferwagen',                   delivery_van          FROM gold.dashboard

Ganglinie — bar
SELECT hour, AVG(bicycle) AS bicycle, AVG(car) AS car,
AVG(lorry) AS lorry, AVG(motorbike) AS motorbike, AVG(delivery_van) AS delivery_van
FROM gold.export
WHERE date >= [filter_start] AND date <= [filter_end]
GROUP BY hour
ORDER BY hour ASC


Übersicht — table
-- Converts wide table to long format for table chart
-- Includes daily average and speed per vehicle type where available
SELECT date, mission_id, 'PKW (Auto)'  AS vehicle_type, car          AS daily_total, v_car          AS avg_speed FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'Fahrrad',                      bicycle,                    NULL                       FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'LKW',                          lorry,                      v_lorry                    FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'Motorrad',                     motorbike,                  v_motorbike                FROM gold.dashboard
UNION ALL
SELECT date, mission_id, 'Lieferwagen',                  delivery_van,               v_delivery_van             FROM gold.dashboard
WHERE date >= [filter_start] AND date <= [filter_end]
GROUP BY fahrzeug

## Fonts and colours
Colours — vehicle types:

Fahrrad → #00aa84
PKW (Auto) → #f5b4cb
Lieferwagen → #9185be
Motorrad → #f39300
LKW → #004f9f
Sonstige → #e6e6e6

Font CSS:
css@font-face {
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



code:

#!/usr/bin/env python3
"""
build_dashboard.py
==================
Builds the complete traffic dashboard in Superset from scratch via REST API.
Reads credentials from .env in the same directory (or path via --env flag).

Run order:
  1. python build_dashboard.py --env /path/to/.env --inspect-db
     → confirms Superset can reach postgres-traffic, prints DB id if already registered

  2. python build_dashboard.py --env /path/to/.env --build
     → creates database connection, datasets, charts, dashboard, native filters

  3. python build_dashboard.py --env /path/to/.env --build --wipe-first
     → deletes any previously created assets with same names first (idempotent re-run)

Requirements:
  pip install requests python-dotenv
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests
from dotenv import dotenv_values

# ─────────────────────────────────────────────────────────────────────────────
# NAMES  — change these if you want different display names in Superset
# ─────────────────────────────────────────────────────────────────────────────
DB_DISPLAY_NAME       = "postgres-traffic"
DS_DASHBOARD          = "gold.dashboard"       # dataset for v85, modalsplit, übersicht
DS_EXPORT             = "gold.export"          # dataset for ganglinie
DASHBOARD_TITLE       = "Verkehrsdaten Dashboard"

CHART_V85             = "v85 Durchschnitt"
CHART_MODALSPLIT      = "Modalsplit"
CHART_UEBERSICHT      = "Übersicht"
CHART_GANGLINIE       = "Ganglinie"

# ─────────────────────────────────────────────────────────────────────────────
# COLOURS
# ─────────────────────────────────────────────────────────────────────────────
COLOURS = {
    "Fahrrad":      "#00aa84",
    "PKW (Auto)":   "#f5b4cb",
    "Lieferwagen":  "#9185be",
    "Motorrad":     "#f39300",
    "LKW":          "#004f9f",
    "Sonstige":     "#e6e6e6",
}

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD CSS  (BerlinType font)
# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# SQL DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

# Virtual dataset SQL — Superset stores these as "virtual" (SQL-based) datasets.
# Temporal filters are applied by Superset's native filter mechanism on top.

SQL_V85 = """
SELECT
    mission_id,
    date,
    v85
FROM gold.dashboard
"""

SQL_MODALSPLIT = """
SELECT
    date,
    mission_id,
    streetnr,
    'Fahrrad'    AS vehicle_type,
    bicycle      AS count
FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'PKW (Auto)',  car          FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'LKW',         lorry        FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Motorrad',    motorbike    FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Lieferwagen', delivery_van FROM gold.dashboard
"""

SQL_UEBERSICHT = """
SELECT
    date,
    mission_id,
    streetnr,
    'PKW (Auto)'  AS vehicle_type,
    car           AS daily_total,
    v_car         AS avg_speed
FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Fahrrad',    bicycle,     NULL         FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'LKW',        lorry,       v_lorry      FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Motorrad',   motorbike,   v_motorbike  FROM gold.dashboard
UNION ALL
SELECT date, mission_id, streetnr, 'Lieferwagen',delivery_van,v_delivery_van FROM gold.dashboard
"""

# Ganglinie uses gold.export (hourly data) — weighted averages by vehicle count
SQL_GANGLINIE = """
SELECT
    hour,
    -- weighted average: sum(speed * count) / sum(count) per hour
    CASE WHEN SUM(bicycle)      > 0 THEN SUM(v_car          * car)          / NULLIF(SUM(car),          0) END AS v_car,
    CASE WHEN SUM(car)          > 0 THEN SUM(v_car          * car)          / NULLIF(SUM(car),          0) END AS avg_speed_car,
    SUM(bicycle)                    AS bicycle,
    SUM(car)                        AS car,
    SUM(lorry)                      AS lorry,
    SUM(motorbike)                  AS motorbike,
    SUM(delivery_van)               AS delivery_van,
    -- hourly totals for bar chart
    SUM(motorised)                  AS motorised
FROM gold.export
GROUP BY hour
ORDER BY hour ASC
"""

# Simpler ganglinie — bar chart with raw hourly sums (date filter applied by Superset)
SQL_GANGLINIE = """
SELECT
    date,
    hour,
    mission_id,
    bicycle,
    car,
    lorry,
    motorbike,
    delivery_van
FROM gold.export
"""


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class SupersetClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self._login(username, password)

    def _login(self, username: str, password: str):
        resp = self.session.post(
            f"{self.base}/api/v1/security/login",
            json={"username": username, "password": password,
                  "provider": "db", "refresh": True},
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]

        csrf = self.session.get(
            f"{self.base}/api/v1/security/csrf_token/",
            headers={"Authorization": f"Bearer {token}"},
        )
        csrf.raise_for_status()
        csrf_token = csrf.json()["result"]

        self.session.headers.update({
            "Authorization":  f"Bearer {token}",
            "X-CSRFToken":    csrf_token,
            "Content-Type":   "application/json",
            "Referer":        self.base,
        })
        print(f"✓ Authenticated to {self.base}")

    # ── low-level ────────────────────────────────────────────────────────────

    def get(self, path: str, params: dict = None):
        r = self.session.get(f"{self.base}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, payload: dict):
        r = self.session.post(f"{self.base}{path}", json=payload)
        return r

    def put(self, path: str, payload: dict):
        r = self.session.put(f"{self.base}{path}", json=payload)
        return r

    def delete(self, path: str):
        r = self.session.delete(f"{self.base}{path}")
        return r

    def get_all(self, path: str, page_size: int = 100) -> list:
        results, page = [], 0
        while True:
            data = self.get(path, params={"q": json.dumps(
                {"page": page, "page_size": page_size})})
            batch = data.get("result", [])
            results.extend(batch)
            if len(results) >= data.get("count", 0):
                break
            page += 1
        return results

    # ── finders ──────────────────────────────────────────────────────────────

    def find_database(self, name: str) -> dict | None:
        for db in self.get_all("/api/v1/database/"):
            if db["database_name"] == name:
                return db
        return None

    def find_dataset(self, name: str) -> dict | None:
        for ds in self.get_all("/api/v1/dataset/"):
            if ds["table_name"] == name:
                return ds
        return None

    def find_chart(self, name: str) -> dict | None:
        for c in self.get_all("/api/v1/chart/"):
            if c["slice_name"] == name:
                return c
        return None

    def find_dashboard(self, title: str) -> dict | None:
        for d in self.get_all("/api/v1/dashboard/"):
            if d["dashboard_title"] == title:
                return d
        return None

    # ── creators ─────────────────────────────────────────────────────────────

    def create_database(self, name: str, sqlalchemy_uri: str) -> int:
        existing = self.find_database(name)
        if existing:
            print(f"  DB '{name}' already exists (id={existing['id']}), skipping.")
            return existing["id"]
        r = self.post("/api/v1/database/", {
            "database_name": name,
            "sqlalchemy_uri": sqlalchemy_uri,
            "expose_in_sqllab": True,
            "allow_run_async": False,
        })
        if not r.ok:
            print(f"  ✗ DB create failed: {r.status_code} {r.text[:300]}")
            sys.exit(1)
        db_id = r.json()["id"]
        print(f"  ✓ Database '{name}' created (id={db_id})")
        return db_id

    def create_virtual_dataset(self, name: str, sql: str, db_id: int,
                                schema: str = "gold") -> int:
        existing = self.find_dataset(name)
        if existing:
            print(f"  Dataset '{name}' already exists (id={existing['id']}), skipping.")
            return existing["id"]
        r = self.post("/api/v1/dataset/", {
            "table_name":  name,
            "sql":         sql.strip(),
            "database":    db_id,
            "schema":      schema,
            "is_managed_externally": False,
        })
        if not r.ok:
            print(f"  ✗ Dataset '{name}' create failed: {r.status_code} {r.text[:400]}")
            sys.exit(1)
        ds_id = r.json()["id"]
        print(f"  ✓ Dataset '{name}' created (id={ds_id})")
        # Refresh columns so Superset knows about them
        time.sleep(0.5)
        self.put(f"/api/v1/dataset/{ds_id}/refresh", {})
        return ds_id

    def create_chart(self, payload: dict) -> int:
        name = payload["slice_name"]
        existing = self.find_chart(name)
        if existing:
            print(f"  Chart '{name}' already exists (id={existing['id']}), skipping.")
            return existing["id"]
        r = self.post("/api/v1/chart/", payload)
        if not r.ok:
            print(f"  ✗ Chart '{name}' failed: {r.status_code} {r.text[:400]}")
            sys.exit(1)
        cid = r.json()["id"]
        print(f"  ✓ Chart '{name}' created (id={cid})")
        return cid

    def update_chart(self, chart_id: int, payload: dict):
        r = self.put(f"/api/v1/chart/{chart_id}", payload)
        if not r.ok:
            print(f"  ✗ Chart update failed: {r.status_code} {r.text[:300]}")

    def create_dashboard(self, title: str, chart_ids: list[int],
                          css: str = "") -> int:
        existing = self.find_dashboard(title)
        if existing:
            print(f"  Dashboard '{title}' already exists (id={existing['id']}), skipping.")
            return existing["id"]

        position_json = _make_position_json(chart_ids)

        r = self.post("/api/v1/dashboard/", {
            "dashboard_title": title,
            "published":       False,
            "css":             css,
            "position_json":   json.dumps(position_json),
            "json_metadata":   json.dumps({"refresh_frequency": 0,
                                            "color_scheme": ""}),
            "owners":          [],
            "roles":           [],
        })
        if not r.ok:
            print(f"  ✗ Dashboard create failed: {r.status_code} {r.text[:400]}")
            sys.exit(1)
        did = r.json()["id"]
        print(f"  ✓ Dashboard '{title}' created (id={did})")
        return did

    def add_native_filters(self, dashboard_id: int,
                            dataset_id_dashboard: int):
        """Add date range + streetnr native filters."""
        filters = _make_native_filters(dataset_id_dashboard)
        meta = {"native_filter_configuration": filters,
                "refresh_frequency": 0,
                "color_scheme": ""}
        r = self.put(f"/api/v1/dashboard/{dashboard_id}", {
            "json_metadata": json.dumps(meta),
        })
        if r.ok:
            print("  ✓ Native filters added")
        else:
            print(f"  ✗ Filter update failed: {r.status_code} {r.text[:300]}")

    # ── wipe ─────────────────────────────────────────────────────────────────

    def wipe(self, dashboard_title: str, chart_names: list[str],
             dataset_names: list[str], db_name: str):
        print("  Wiping previous assets …")
        d = self.find_dashboard(dashboard_title)
        if d:
            self.delete(f"/api/v1/dashboard/{d['id']}")
            print(f"    deleted dashboard {d['id']}")
        for name in chart_names:
            c = self.find_chart(name)
            if c:
                self.delete(f"/api/v1/chart/{c['id']}")
                print(f"    deleted chart '{name}'")
        for name in dataset_names:
            ds = self.find_dataset(name)
            if ds:
                self.delete(f"/api/v1/dataset/{ds['id']}")
                print(f"    deleted dataset '{name}'")
        # Leave the DB connection — it may be shared


# ─────────────────────────────────────────────────────────────────────────────
# LAYOUT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _uid():
    return str(uuid.uuid4())[:8].upper()


def _make_position_json(chart_ids: list[int]) -> dict:
    """
    Grid layout:
      Row 0: [v85 big number  | Modalsplit pie]     — 2 cols
      Row 1: [Übersicht table (full width)]          — 1 col
      Row 2: [Ganglinie bar   (full width)]          — 1 col
    Superset grid is 12 columns wide.
    """
    assert len(chart_ids) == 4, "Expected exactly 4 chart ids"
    v85_id, modal_id, ueber_id, gang_id = chart_ids

    root_id   = "ROOT_ID"
    grid_id   = "GRID_ID"
    row0_id   = f"ROW-{_uid()}"
    row1_id   = f"ROW-{_uid()}"
    row2_id   = f"ROW-{_uid()}"
    c0_id     = f"CHART-{_uid()}"
    c1_id     = f"CHART-{_uid()}"
    c2_id     = f"CHART-{_uid()}"
    c3_id     = f"CHART-{_uid()}"

    pos = {
        root_id: {
            "type":     "ROOT",
            "id":       root_id,
            "children": [grid_id],
        },
        grid_id: {
            "type":     "GRID",
            "id":       grid_id,
            "children": [row0_id, row1_id, row2_id],
            "parents":  [root_id],
        },
        # ── Row 0: v85 + Modalsplit ──────────────────────────────────────────
        row0_id: {
            "type":     "ROW",
            "id":       row0_id,
            "children": [c0_id, c1_id],
            "parents":  [root_id, grid_id],
            "meta":     {"background": "BACKGROUND_TRANSPARENT"},
        },
        c0_id: {
            "type":    "CHART",
            "id":      c0_id,
            "children": [],
            "parents": [root_id, grid_id, row0_id],
            "meta": {
                "chartId": v85_id,
                "width":   4,
                "height":  25,
                "sliceName": CHART_V85,
            },
        },
        c1_id: {
            "type":    "CHART",
            "id":      c1_id,
            "children": [],
            "parents": [root_id, grid_id, row0_id],
            "meta": {
                "chartId": modal_id,
                "width":   8,
                "height":  25,
                "sliceName": CHART_MODALSPLIT,
            },
        },
        # ── Row 1: Übersicht ─────────────────────────────────────────────────
        row1_id: {
            "type":     "ROW",
            "id":       row1_id,
            "children": [c2_id],
            "parents":  [root_id, grid_id],
            "meta":     {"background": "BACKGROUND_TRANSPARENT"},
        },
        c2_id: {
            "type":    "CHART",
            "id":      c2_id,
            "children": [],
            "parents": [root_id, grid_id, row1_id],
            "meta": {
                "chartId": ueber_id,
                "width":   12,
                "height":  30,
                "sliceName": CHART_UEBERSICHT,
            },
        },
        # ── Row 2: Ganglinie ─────────────────────────────────────────────────
        row2_id: {
            "type":     "ROW",
            "id":       row2_id,
            "children": [c3_id],
            "parents":  [root_id, grid_id],
            "meta":     {"background": "BACKGROUND_TRANSPARENT"},
        },
        c3_id: {
            "type":    "CHART",
            "id":      c3_id,
            "children": [],
            "parents": [root_id, grid_id, row2_id],
            "meta": {
                "chartId": gang_id,
                "width":   12,
                "height":  35,
                "sliceName": CHART_GANGLINIE,
            },
        },
        "HEADER_ID": {
            "id":   "HEADER_ID",
            "type": "HEADER",
            "meta": {"text": DASHBOARD_TITLE},
        },
    }
    return pos


# ─────────────────────────────────────────────────────────────────────────────
# NATIVE FILTER HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_native_filters(ds_id: int) -> list:
    date_filter_id     = f"NATIVE_FILTER-{_uid()}"
    standort_filter_id = f"NATIVE_FILTER-{_uid()}"

    return [
        {
            "id":          date_filter_id,
            "name":        "Zeitraum",
            "filterType":  "filter_time",
            "targets":     [{}],
            "defaultDataMask": {
                "extraFormData": {
                    "time_range": "Last 30 days",
                },
                "filterState": {
                    "value": "Last 30 days",
                },
            },
            "controlValues": {
                "enableEmptyFilter": False,
            },
            "cascadeParentIds": [],
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": [],
            },
            "isInstant": True,
        },
        {
            "id":          standort_filter_id,
            "name":        "Standort",
            "filterType":  "filter_select",
            "targets":     [{
                "datasetId": ds_id,
                "column":    {"name": "streetnr"},
            }],
            "defaultDataMask": {
                "extraFormData": {},
                "filterState":   {"value": None},
            },
            "controlValues": {
                "enableEmptyFilter": False,
                "multiSelect":       True,
                "defaultToFirstItem": False,
                "searchAllOptions":   True,
                "inverseSelection":   False,
            },
            "cascadeParentIds": [],
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": [],
            },
            "isInstant": True,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CHART PAYLOAD BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def chart_v85(ds_id: int) -> dict:
    """Big Number — average v85 across selected date range & location."""
    params = {
        "viz_type":       "big_number_total",
        "metric":         {
            "expressionType": "SQL",
            "sqlExpression":  "AVG(v85)",
            "label":          "Ø v85 (km/h)",
            "hasCustomLabel": True,
        },
        "subheader":      "Ø v85 (km/h)",
        "y_axis_format":  ".1f",
        "time_range":     "No filter",
        "adhoc_filters":  [],
        "header_font_size": 0.4,
        "subheader_font_size": 0.15,
    }
    return {
        "slice_name":     CHART_V85,
        "viz_type":       "big_number_total",
        "datasource_id":  ds_id,
        "datasource_type": "table",
        "params":         json.dumps(params),
        "query_context":  "",
        "description":    "85th-percentile speed averaged over selected period",
    }


def chart_modalsplit(ds_id: int) -> dict:
    """Pie chart — modal split by vehicle type."""
    colour_map = [
        {"label": k, "value": k, "olapQueryContext": "", "colorScheme": v}
        for k, v in COLOURS.items()
    ]
    params = {
        "viz_type":       "pie",
        "metric":         {
            "expressionType": "SQL",
            "sqlExpression":  "SUM(count)",
            "label":          "Anzahl",
            "hasCustomLabel": True,
        },
        "groupby":        ["vehicle_type"],
        "adhoc_filters":  [],
        "time_range":     "No filter",
        "donut":          False,
        "show_labels":    True,
        "show_legend":    True,
        "label_type":     "key_percent",
        "color_scheme":   "supersetColors",
        # Per-category colour overrides stored in label_colors
        "label_colors":   {k: v for k, v in COLOURS.items()},
        "show_total":     True,
    }
    return {
        "slice_name":      CHART_MODALSPLIT,
        "viz_type":        "pie",
        "datasource_id":   ds_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "query_context":   "",
        "description":     "Modal split pie chart",
    }


def chart_uebersicht(ds_id: int) -> dict:
    """Table — daily totals and avg speed per vehicle type."""
    params = {
        "viz_type":       "table",
        "query_mode":     "aggregate",
        "groupby":        ["vehicle_type"],
        "metrics":        [
            {
                "expressionType": "SQL",
                "sqlExpression":  "SUM(daily_total)",
                "label":          "Gesamt",
                "hasCustomLabel": True,
            },
            {
                "expressionType": "SQL",
                "sqlExpression":  "AVG(avg_speed)",
                "label":          "Ø Geschw. (km/h)",
                "hasCustomLabel": True,
            },
        ],
        "adhoc_filters":  [],
        "time_range":     "No filter",
        "order_desc":     True,
        "show_totals":    True,
        "table_timestamp_format": "smart_date",
        "page_length":    10,
        "include_search": False,
    }
    return {
        "slice_name":      CHART_UEBERSICHT,
        "viz_type":        "table",
        "datasource_id":   ds_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "query_context":   "",
        "description":     "Summary table — totals and avg speed per vehicle type",
    }


def chart_ganglinie(ds_id: int) -> dict:
    """Mixed/bar chart — hourly traffic volume per vehicle type."""
    params = {
        "viz_type":       "echarts_timeseries_bar",
        "x_axis":         "hour",
        "metrics":        [
            {"expressionType": "SQL", "sqlExpression": "SUM(bicycle)",
             "label": "Fahrrad", "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "SUM(car)",
             "label": "PKW (Auto)", "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "SUM(lorry)",
             "label": "LKW", "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "SUM(motorbike)",
             "label": "Motorrad", "hasCustomLabel": True},
            {"expressionType": "SQL", "sqlExpression": "SUM(delivery_van)",
             "label": "Lieferwagen", "hasCustomLabel": True},
        ],
        "groupby":        [],
        "adhoc_filters":  [],
        "time_range":     "No filter",
        "x_axis_title":   "Stunde",
        "y_axis_title":   "Fahrzeuge",
        "color_scheme":   "supersetColors",
        "label_colors":   {k: v for k, v in COLOURS.items()},
        "stack":          True,
        "show_legend":    True,
        "legendOrientation": "top",
        "x_axis_time_format": "~g",
        "truncate_metric": True,
    }
    return {
        "slice_name":      CHART_GANGLINIE,
        "viz_type":        "echarts_timeseries_bar",
        "datasource_id":   ds_id,
        "datasource_type": "table",
        "params":          json.dumps(params),
        "query_context":   "",
        "description":     "Hourly traffic volume (Ganglinie) — stacked bar",
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def load_env(env_path: str) -> dict:
    p = Path(env_path)
    if not p.exists():
        print(f"✗ .env not found at {p.resolve()}")
        sys.exit(1)
    cfg = dotenv_values(p)
    return cfg


def build_sqlalchemy_uri(cfg: dict) -> str:
    user   = cfg["POSTGRES_TRAFFIC_USER"]
    passwd = cfg["POSTGRES_TRAFFIC_PASSWORD"]
    db     = cfg["POSTGRES_TRAFFIC_DB"]
    # Inside Docker network, Superset reaches postgres-traffic by service name
    return f"postgresql+psycopg2://{user}:{passwd}@postgres-traffic:5432/{db}"


def main():
    parser = argparse.ArgumentParser(
        description="Build Verkehrsdaten dashboard in Superset via REST API")
    parser.add_argument("--env",          default=".env",
                        help="Path to .env file (default: .env)")
    parser.add_argument("--superset-url", default=None,
                        help="Override Superset URL (default: read from .env or localhost:8089)")
    parser.add_argument("--inspect-db",   action="store_true",
                        help="List databases registered in Superset and exit")
    parser.add_argument("--build",        action="store_true",
                        help="Create all assets")
    parser.add_argument("--wipe-first",   action="store_true",
                        help="Delete existing assets with same names before building")
    args = parser.parse_args()

    if not args.inspect_db and not args.build:
        parser.print_help()
        sys.exit(0)

    cfg = load_env(args.env)

    # Superset URL: CLI override > .env SUPERSET_URL > default
    superset_url = (
        args.superset_url
        or cfg.get("SUPERSET_URL")
        or "http://localhost:8089"
    )
    admin_user   = cfg.get("SUPERSET_ADMIN_USER", "admin")
    admin_pass   = cfg.get("SUPERSET_ADMIN_PASSWORD", "admin")

    client = SupersetClient(superset_url, admin_user, admin_pass)

    # ── inspect only ─────────────────────────────────────────────────────────
    if args.inspect_db:
        print("\n── Registered databases ──────────────────────────────")
        for db in client.get_all("/api/v1/database/"):
            print(f"  id={db['id']}  name={db['database_name']}")
        print("\n── Datasets ──────────────────────────────────────────")
        for ds in client.get_all("/api/v1/dataset/"):
            print(f"  id={ds['id']}  name={ds['table_name']}")
        print("\n── Charts ────────────────────────────────────────────")
        for c in client.get_all("/api/v1/chart/"):
            print(f"  id={c['id']}  name={c['slice_name']}")
        print("\n── Dashboards ────────────────────────────────────────")
        for d in client.get_all("/api/v1/dashboard/"):
            print(f"  id={d['id']}  title={d['dashboard_title']}")
        return

    # ── build ─────────────────────────────────────────────────────────────────
    if args.wipe_first:
        client.wipe(
            dashboard_title=DASHBOARD_TITLE,
            chart_names=[CHART_V85, CHART_MODALSPLIT,
                         CHART_UEBERSICHT, CHART_GANGLINIE],
            dataset_names=[DS_DASHBOARD, DS_EXPORT, "gold.dashboard_modal",
                           "gold.dashboard_uebersicht", "gold.export_ganglinie"],
            db_name=DB_DISPLAY_NAME,
        )
        print()

    sqlalchemy_uri = build_sqlalchemy_uri(cfg)
    print(f"\n[1/5] Database connection")
    db_id = client.create_database(DB_DISPLAY_NAME, sqlalchemy_uri)

    print(f"\n[2/5] Datasets")
    # Four virtual datasets — one per chart's SQL
    ds_v85_id    = client.create_virtual_dataset(
        "gold.dashboard_v85",        SQL_V85,        db_id)
    ds_modal_id  = client.create_virtual_dataset(
        "gold.dashboard_modal",      SQL_MODALSPLIT, db_id)
    ds_ueber_id  = client.create_virtual_dataset(
        "gold.dashboard_uebersicht", SQL_UEBERSICHT, db_id)
    ds_gang_id   = client.create_virtual_dataset(
        "gold.export_ganglinie",     SQL_GANGLINIE,  db_id)

    print(f"\n[3/5] Charts")
    cid_v85    = client.create_chart(chart_v85(ds_v85_id))
    cid_modal  = client.create_chart(chart_modalsplit(ds_modal_id))
    cid_ueber  = client.create_chart(chart_uebersicht(ds_ueber_id))
    cid_gang   = client.create_chart(chart_ganglinie(ds_gang_id))

    print(f"\n[4/5] Dashboard")
    dash_id = client.create_dashboard(
        DASHBOARD_TITLE,
        chart_ids=[cid_v85, cid_modal, cid_ueber, cid_gang],
        css=DASHBOARD_CSS,
    )

    print(f"\n[5/5] Native filters")
    # Use gold.dashboard_v85 dataset as filter target (has date + streetnr cols)
    client.add_native_filters(dash_id, ds_v85_id)

    print(f"""
{'═'*55}
  ✓  Done!
  Open: {superset_url}/superset/dashboard/{dash_id}/

  Next steps:
  1. Open the dashboard — charts may show 'no data' until
     you set the Zeitraum filter (expected behaviour).
  2. If a chart shows a SQL error, open it in Explore,
     check the query, and re-run this script with --wipe-first.
  3. The Standort filter uses 'streetnr' from gold.dashboard —
     make sure that column is populated in your data.
{'═'*55}
""")


if __name__ == "__main__":
    main()
