"""
bronze.py — Bronze layer ingestion
====================================
Fetches reference and traffic data and loads into PostgreSQL bronze schema.

Entry points:
    ingest_ref()              — fetches missions + locations from DDWeb portal
                                → bronze.mission, bronze.location
    load_traffic_to_bronze()  — reads parquet files from MinIO
                                → bronze.traffic

Tables written:
    bronze.mission   — deployment history, append new rows only
    bronze.location  — location reference, full reload for now (see TODO)
    bronze.traffic   — weekly append of raw sensor rows
"""

from __future__ import annotations
import logging
import warnings
import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy import text
from typing import Set, Tuple
import io

from utils.db import get_traffic_engine, save, get_loaded_files
from utils.date import parse_date
from utils.schema import MISSION_RENAME, LOCATION_RENAME
from utils.minio import get_minio_client, MINIO_BUCKET, read_tracker, write_tracker
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


def _get_existing_mission_ids(engine: Engine) -> set:

    if not _table_exists(engine, "mission"):
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT mission_id FROM bronze.mission")
        ).fetchall()
    return {r[0] for r in rows}


# Bronze layer functions

def ingest_missions(auth: DDWebAuth, engine: Engine) -> tuple[bool, int]:
    """
    Fetch missions from DDWeb and load into bronze.mission.
    Only inserts rows whose (mission_id) key is new.

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


def ingest_locations(auth: DDWebAuth, engine: Engine) -> int:
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



def ingest_ref() -> dict:
    """
    Full bronze ingestion run for reference files — authenticates with DDWeb, then:

        1. fetches missions
        2. if new mission detected fetch location → full-replace bronze.location (for now)

    Returns dict:
        new_mission_detected   bool
        mission_rows_added     int   new rows in bronze.mission
        location_rows_written  int   rows in bronze.location after refresh
    """
    logger.info("=== BRONZE LAYER START ===")

    auth = DDWebAuth()
    auth.ensure_authenticated()

    engine = get_traffic_engine()
    # Step 1 — Missions
    new_mission_detected, mission_rows_added = ingest_missions(auth, engine)

    # Step 2 — Locations (only if new mission detected)
    if new_mission_detected:
        location_rows = ingest_locations(auth, engine)
    else:
        location_rows = 0
        logger.info("No new mission — skipping location fetch.")

    result = {
        "new_mission_detected":  new_mission_detected,
        "mission_rows_added":    mission_rows_added,
        "location_rows_written": location_rows,
    }
    logger.info("=== BRONZE LAYER DONE: %s ===", result)
    return result


def load_traffic_to_bronze() -> int:
    """
    List new parquet files from MinIO and append to bronze.traffic.
    Skips files already loaded — idempotent.
    Returns number of rows appended.
    """
    tracker = read_tracker()

    engine = get_traffic_engine()
    objects = get_minio_client().list_objects(MINIO_BUCKET, prefix="mission_")
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

        # save to bronze.traffic
        response = get_minio_client().get_object(MINIO_BUCKET, filename)
        df = pd.read_parquet(io.BytesIO(response.read()))
        df["source_file"] = filename
        df["ingested_at"] = pd.Timestamp.now()
        save(df, "traffic", "bronze", engine)
        total_rows += len(df)
        logger.info("  Loaded %d rows from %s", len(df), filename)

        # update the tracker with files loaded to avoide double downloads at next download
        parts = filename.replace(".parquet", "").split("_")
        mission_id = parts[1]
        chunk_end = parts[3]
        tracker[mission_id] = {"last_downloaded_to": chunk_end}
        write_tracker(tracker)
        logger.info("Tracker updated for mission %s: last_downloaded_to=%s", mission_id, chunk_end)

    logger.info("Traffic ingestion complete: %d rows appended.", total_rows)
    return total_rows
