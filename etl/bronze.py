"""
Fetches reference and traffic data and loads into PostgreSQL bronze schema.

Entry points:
    ingest_ref()              — fetches missions + locations from DDWeb portal
                                → bronze.mission, bronze.location
    load_traffic_to_bronze()  — reads parquet files from MinIO
                                → bronze.traffic
Tables written:
    bronze.mission   — deployment history, append new rows only
    bronze.location  — location reference, append new rows only
    bronze.traffic   — weekly append of raw sensor rows
"""

import logging
import warnings
import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy import text
from zoneinfo import ZoneInfo
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


def _get_existing_ids(engine: Engine, table: str) -> set:

    if not _table_exists(engine, table):
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT {table}_id FROM bronze.{table}")
        ).fetchall()
    return {r[0] for r in rows}


# Bronze layer functions

def _ingest_ref_table(
    auth: DDWebAuth,
    engine: Engine,
    table: str,
    date_cols: list[str]) -> int:
    """
    Fetch missions and location from DDWeb and load into bronze.mission.
    Only inserts new rows
    """

    fetch_functions = {
        "mission": fetch_missions,
        "location": fetch_locations
    }

    rename_schemas = {
        "mission": MISSION_RENAME,
        "location": LOCATION_RENAME
    }

    df = fetch_functions[table](auth).rename(columns=rename_schemas[table])

    for col in date_cols:
        df[col] = df[col].apply(parse_date)

    df["ingested_at"] = pd.Timestamp.now(tz=ZoneInfo("Europe/Berlin"))

    existing_ids = _get_existing_ids(engine, table)
    truly_new = df[~df[f"{table}_id"].isin(existing_ids)]

    if truly_new.empty:
        logger.info("No new %s detected — bronze.%s unchanged.", table, table)
        return 0

    save(truly_new, table, "bronze", engine)
    logger.info("Inserted %d new %s row(s) into bronze.%s.", len(truly_new), table, table)
    return len(truly_new)


def load_ref_to_bronze() -> tuple[int, int]:
    """
    Full bronze ingestion run for reference files — authenticates with DDWeb, then:
        1. fetches missions
        2. fetches locations
    Saves:
        - new rows in bronze.mission
        - new rows in bronze.location
    """
    logger.info("=== BRONZE LAYER START ===")

    auth = DDWebAuth()
    auth.ensure_authenticated()
    engine = get_traffic_engine()

    new_mission = _ingest_ref_table(auth, engine, "mission", date_cols=["created_at", "start_date", "end_date"])
    new_location = _ingest_ref_table(auth, engine, "location", date_cols=["created_at"])

    logger.info("=== BRONZE LAYER DONE ===")
    return new_mission, new_location


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
    logger.info("Found %d parquet files in MinIO, %d already loaded, %d new.",
            len(traffic_files), len(already_loaded), len(traffic_files) - len(already_loaded))
    total_rows = 0

    for filename in traffic_files:
        if filename in already_loaded:
            logger.info("  Skipping (already loaded): %s", filename)
            continue

        # save to bronze.traffic
        response = get_minio_client().get_object(MINIO_BUCKET, filename)
        df = pd.read_parquet(io.BytesIO(response.read()))
        df["source_file"] = filename
        df["ingested_at"] = pd.Timestamp.now(tz=ZoneInfo("Europe/Berlin"))
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
