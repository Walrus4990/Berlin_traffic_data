from __future__ import annotations
"""
bronze.py — Bronze layer ingestion
====================================
Reads DataFrames produced by the DDweb ingest scripts and loads them into
PostgreSQL bronze schema tables.

Inputs:
    df_missions  — DataFrame returned by ddweb_ingest_ref.fetch_missions()
    df_locations — DataFrame returned by ddweb_ingest_ref.fetch_locations()
    Traffic xlsx — files in DOWNLOAD_DIR written by ddweb_ingest_traffic.py

Tables written:
    bronze.mission   — deployment history, updated when changed
    bronze.location  — location reference, full reload each run
    bronze.traffic   — weekly append of raw sensor passage rows

Entry point: run_bronze(df_missions, df_locations)
Returns:     dict with "new_mission_detected" (bool) and row counts
"""

import logging
import warnings
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy import text

from utils.db import get_traffic_engine, save
from etl.ddweb_auth import DDWebAuth
from etl.ddweb_ingest_ref import fetch_missions
from etl.ddweb_ingest_ref import fetch_locations

warnings.filterwarnings("ignore", category=UserWarning)

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("/opt/airflow/data/DDWEB_Downloads/") #adjustable - depends on the ingestion output (link to Miiion)

# Column mapping: ingest file field names → bronze schema
#
# The DDweb ingest scripts return the raw portal API field names.
MISSION_RENAME = {
    "Id":            "mission_id",
    "Created":       "created_at",
    "FromDate":      "start_date",
    "ToDate":        "end_date",
    "Description":   "description",
    "LocationTitle": "location_title", # join key
    "City":          "city",
    "Street":        "street",
    "StreetNumber":  "street_number",
    "Zipcode":       "zipcode",
    "DeviceNumber":  "device_id",      # primary identifier
    "DeviceType":    "device_type",
}

LOCATION_RENAME = {
    "Id":                "location_id",
    "Created":           "created_at",
    "Description":       "description",
    "LocationTitle":     "location_title", # join key
    "Street":            "street",
    "StreetNumber":      "street_number",
    "Zipcode":           "zipcode",
    "City":              "city",
    "DrivingDirection":  "driving_direction",
    "OppositeDirection": "opposite_direction",
    "PosUserLat":        "lat",
    "PosUserLng":        "lon",
}

# Traffic Excel columns that are always zero — dropped before loading to bronze.
TRAFFIC_COLS_DROP = [
    "Schall (dB)", "Abstand (cm)", "Fahrspur",
    "Geschwindigkeit (km/h)", "Richtung",
]

TRAFFIC_RENAME = {
    "Geräte-ID":                        "device_id",
    "Datum":                            "date_raw",
    "Eintrittsgeschwindigkeit (km/h)":  "speed_entry",
    "Austrittsgeschwindigkeit (km/h)":  "speed_exit",
    "Länge (dm)":                       "length_dm",
    "Klasse":                           "vehicle_class",
    "Fahrzeugklassen-Bezeichnung":      "vehicle_class_label",
}

import re

def _parse_msdate(val):
    """Convert /Date(1646050942957)/ → datetime. Returns NaT if unparseable."""
    if isinstance(val, str):
        m = re.search(r'/Date\((-?\d+)\)/', val)
        if m:
            return pd.Timestamp(int(m.group(1)), unit="ms")
    return pd.NaT

def _table_exists(engine: Engine, table: str, schema: str = "bronze") -> bool:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_schema=:s AND table_name=:t"
                ")"
            ),
            {"s": schema, "t": table},
        ).scalar()


def _get_existing_mission_keys(engine: Engine) -> set[tuple]:
    """Return (device_id, start_date) pairs already stored in bronze.mission."""
    if not _table_exists(engine, "mission"):
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT device_id::text, start_date FROM bronze.mission")
        ).fetchall()
    return {(str(r[0]), pd.Timestamp(r[1])) for r in rows}


def _load_traffic_file(fpath: Path) -> pd.DataFrame: #read the files in the download dir (bucket)
    """
    What does this function do:
    Read one traffic Excel file saved by ddweb_ingest_traffic.download_mission(),
    drop the always-zero columns, rename to bronze schema.
    """
    df = pd.read_excel(fpath, dtype={"Geräte-ID": str})
    df["source_file"] = fpath.name
    df = df.drop(columns=TRAFFIC_COLS_DROP, errors="ignore")
    df = df.rename(columns=TRAFFIC_RENAME)
    df["device_id"] = df["device_id"].astype(str).str.strip()
    return df


# Bronze layer functions

def fetch_and_ingest_missions(auth: DDWebAuth, engine: Engine) -> tuple[bool, int]:
    """
    Fetch missions from DDWeb and load into bronze.mission.
    Only inserts rows whose (device_id, start_date) key is new.

    Returns:
        (new_mission_detected, rows_added)
    """
    df = fetch_missions(auth).rename(columns=MISSION_RENAME)
    df["device_id"] = df["device_id"].astype(str).str.strip()
    for col in ("created_at", "start_date", "end_date"):
        df[col] = df[col].apply(_parse_msdate)
    df["ingested_at"] = pd.Timestamp.now()

    existing_keys = _get_existing_mission_keys(engine)
    new_keys = {
        (str(row["device_id"]), pd.Timestamp(row["start_date"]))
        for _, row in df.iterrows()
        if pd.notna(row["start_date"])
    }
    truly_new = new_keys - existing_keys

    if not truly_new:
        logger.info("No new missions detected — bronze.mission unchanged.")
        return False, 0

    new_mask = df.apply(
        lambda r: (str(r["device_id"]), pd.Timestamp(r["start_date"])) in truly_new
        if pd.notna(r["start_date"]) else False,
        axis=1,
    )
    rows_to_insert = df[new_mask].copy()
    save(rows_to_insert, "mission", "bronze", engine)

    logger.info(
        "Inserted %d new mission row(s) into bronze.mission.", len(rows_to_insert)
    )
    return True, len(rows_to_insert)

def fetch_and_ingest_locations(auth: DDWebAuth, engine: Engine) -> int:
    """
    Fetch locations from DDWeb and fully replace bronze.location.
    Returns number of rows written.
    """
    df = fetch_locations(auth).rename(columns=LOCATION_RENAME)

    df["created_at"] = df["created_at"].apply(_parse_msdate)

    for col in ("lat", "lon"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["ingested_at"] = pd.Timestamp.now()

    with engine.begin() as conn:
        if _table_exists(engine, "location"):
            conn.execute(text("TRUNCATE TABLE bronze.location"))

    save(df, "location", "bronze", engine)
    logger.info("Replaced bronze.location: %d rows written.", len(df))
    return len(df)

def ingest_traffic(engine: Engine) -> int:
    """
    Load all traffic Excel files from DOWNLOAD_DIR into bronze.traffic.
    Files written by ddweb_ingest_traffic.py match the pattern mission_*.xlsx.

    Skips files whose source_file name already exists in bronze.traffic -> idempotent

    Returns number of rows appended.
    """
    traffic_files = sorted(DOWNLOAD_DIR.glob("DDweb_VI_Rohdaten_*.xlsx"))
    if not traffic_files:
        logger.warning("No traffic files found in %s", DOWNLOAD_DIR)
        return 0

    already_loaded: set[str] = set()
    if _table_exists(engine, "traffic"):
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT source_file FROM bronze.traffic")
            ).fetchall()
            already_loaded = {r[0] for r in rows}

    total_rows = 0
    for fpath in traffic_files:
        if fpath.name in already_loaded:
            logger.info("  Skipping (already loaded): %s", fpath.name)
            continue

        df = _load_traffic_file(fpath)
        df["ingested_at"] = pd.Timestamp.now()
        save(df, "traffic", "bronze", engine)
        total_rows += len(df)
        logger.info("  Loaded %d rows from %s", len(df), fpath.name)

    logger.info("Traffic ingestion complete: %d rows appended.", total_rows)
    return total_rows


def run_bronze() -> dict:
    """
    Full bronze ingestion run — authenticates with DDWeb, fetches missions and
    locations, then loads all three bronze tables.

    Steps:
        1. Authenticate once with DDWeb portal
        2. Fetch missions → compare to bronze.mission → detect new missions
        3. Fetch locations → full-replace bronze.location
        4. Load *new* traffic *xlsx* from DOWNLOAD_DIR → append to bronze.traffic

    Returns dict:
        new_mission_detected   bool
        rows_ingested          int   traffic rows appended to bronze.traffic
        mission_rows_added     int   new rows in bronze.mission
        location_rows_written  int   rows in bronze.location after refresh
    """
    logger.info("=== BRONZE LAYER START ===")

    auth = DDWebAuth()
    auth.ensure_authenticated()

    with get_traffic_engine() as engine:
        # Step 1 — Missions
        new_mission_detected, mission_rows_added = fetch_and_ingest_missions(auth, engine)

        # Step 2 — Locations
        location_rows = fetch_and_ingest_locations(auth, engine)

        # Step 3 — Traffic
        rows_ingested = ingest_traffic(engine)

    result = {
        "new_mission_detected":  new_mission_detected,
        "rows_ingested":         rows_ingested,
        "mission_rows_added":    mission_rows_added,
        "location_rows_written": location_rows,
    }
    logger.info("=== BRONZE LAYER DONE: %s ===", result)
    return result
