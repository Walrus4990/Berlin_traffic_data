"""
bronze.py — Bronze layer ingestion
====================================
Reads parqet files from MinIO and and loads them into
PostgreSQL bronze schema tables.

Inputs:
    df_missions  — DataFrame returned by ddweb_ingest_ref.fetch_missions()
    df_locations — DataFrame returned by ddweb_ingest_ref.fetch_locations()
    Traffic parquet — files in MinIO written by ddweb_ingest_traffic.py

Tables written:
    bronze.mission   — deployment history, updated when changed
    bronze.location  — location reference, full reload each run
    bronze.traffic   — weekly append of raw sensor passage rows

Entry point: run_bronze(df_missions, df_locations)
Returns:     dict with "new_mission_detected" (bool) and row counts
"""

from __future__ import annotations
import logging
import warnings
from pathlib import Path
import os
import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy import text
from typing import Set, Tuple
import io
import re

from utils.db import get_traffic_engine, save, get_loaded_files
from utils.date import parse_date
from utils.schema import MISSION_RENAME, LOCATION_RENAME, TRAFFIC_COLS_DROP, TRAFFIC_RENAME
from utils.minio import MINIO_CLIENT, MINIO_BUCKET
from etl.ddweb_auth import DDWebAuth
from etl.ddweb_ingest_ref import fetch_missions
from etl.ddweb_ingest_ref import fetch_locations

warnings.filterwarnings("ignore", category=UserWarning)

logger = logging.getLogger(__name__)


def _table_exists(engine: Engine, table: str, schema: str = "bronze") -> bool:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_schema=:s AND table_name=:t"
                ")"
            ).bindparams(s=schema, t=table)
        ).scalar()


def _get_existing_mission_ids(engine: Engine) -> Set[Tuple]:

    if not _table_exists(engine, "mission"):
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT mission_id FROM bronze.mission")
        ).fetchall()
    return {r[0] for r in rows}


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
        df[col] = df[col].apply(parse_date)

    df["ingested_at"] = pd.Timestamp.now()

    existing_ids = _get_existing_mission_ids(engine)
    truly_new = df[~df["mission_id"].isin(existing_ids)]

    if truly_new.empty:
        logger.info("No new missions detected — bronze.mission unchanged.")
        return False, 0

    save(truly_new, "mission", "bronze", engine)
    logger.info(
        "Inserted %d new mission row(s) into bronze.mission.", len(truly_new)
    )
    return True, len(truly_new)


def fetch_and_ingest_locations(auth: DDWebAuth, engine: Engine) -> int:
    """
    Fetch locations from DDWeb and fully replace bronze.location.
    Returns number of rows written.
    """
    df = fetch_locations(auth).rename(columns=LOCATION_RENAME)

    df["created_at"] = df["created_at"].apply(parse_date)

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
    List all parquet objects in MinIO bucket
    Skips files whose source_file name already exists in bronze.traffic -> idempotent
    Returns number of rows appended.
    """

    objects = MINIO_CLIENT.list_objects(MINIO_BUCKET, prefix="mission_")
    traffic_files = [obj.object_name for obj in objects if obj.object_name.endswith(".parquet")]

    if not traffic_files:
        logger.warning("No parquet files found in MinIO bucket %s", MINIO_BUCKET)
        return 0

    # Check what's already loaded
    already_loaded = get_loaded_files(engine, "bronze", "traffic")

    total_rows = 0
    for filename in traffic_files:
        if filename in already_loaded:
            logger.info("  Skipping (already loaded): %s", filename)
            continue

        response = MINIO_CLIENT.get_object(MINIO_BUCKET, filename)
        df = pd.read_parquet(io.BytesIO(response.read()))
        df["source_file"] = filename
        df["ingested_at"] = pd.Timestamp.now()
        save(df, "traffic", "bronze", engine)
        total_rows += len(df)
        logger.info("  Loaded %d rows from %s", len(df), filename)

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
        #rows_ingested = ingest_traffic(engine) Traffic ingestion handled by t_ingest_traffic task upstream

    result = {
        "new_mission_detected":  new_mission_detected,
        "rows_ingested":         0,         #handled upstream
        "mission_rows_added":    mission_rows_added,
        "location_rows_written": location_rows,
    }
    logger.info("=== BRONZE LAYER DONE: %s ===", result)
    return result
