#Functions to test the pipeline go here

import pandas as pd
import logging
import pytz
from datetime import datetime

from utils.db import get_traffic_engine, get_dq_engine, save
from utils.minio import read_tracker
from utils.date import yesterday_end
from etl.ddweb_ingest_traffic import get_chunks, get_chunk_start


logger = logging.getLogger(__name__)

def check_bronze_completeness(run_type: str) -> dict:
    """
    Checks completeness of bronze.traffic against expected segments derived from bronze.mission.
    For each mission, computes expected parquet filenames, then compares against source_file values
    in bronze.traffic. Writes two reports to the DQ database:
    - bronze.mission_completeness: one row per mission with expected vs actual segment counts
    - bronze.missing_segments: one row per missing filename
    Returns dict with missions checked and missing segment count.
    """
    berlin = pytz.timezone("Europe/Berlin")
    run_at = pd.Timestamp.now(tz=berlin)

    engine= get_traffic_engine()
    missions = pd.read_sql("SELECT mission_id, start_date, end_date FROM bronze.mission", engine)
    loaded_files = pd.read_sql("SELECT DISTINCT source_file FROM bronze.traffic", engine)

    loaded_set = set(loaded_files["source_file"].tolist())

    tracker = read_tracker()
    ye = yesterday_end()
    summary_rows = []
    missing_rows = []

    for _, row in missions.iterrows():
        try:
            start = berlin.localize(row["start_date"].to_pydatetime())
            end = berlin.localize(row["end_date"].to_pydatetime())
            mission_id = str(row["mission_id"])

            if run_type == "initial":
                chunks = get_chunks(start, min(end, ye))
            else:
                chunks = get_chunks(
                    get_chunk_start(int(mission_id), start, tracker),
                    min(end, ye)
                )
            expected_files = [
                f"mission_{mission_id}_{seg_start.strftime('%Y%m%d')}_{seg_end.strftime('%Y%m%d')}.parquet"
                for seg_start, seg_end in chunks
            ]

            actual = [f for f in expected_files if f in loaded_set]
            missing = [f for f in expected_files if f not in loaded_set]

            summary_rows.append({
                "run_at": run_at,
                "mission_id": mission_id,
                "expected_segments": len(expected_files),
                "actual_segments": len(actual),
                "missing_count": len(missing),
            })

            for f in missing:
                missing_rows.append({
                    "run_at": run_at,
                    "mission_id": mission_id,
                    "expected_filename": f,
                })

        except Exception as e:
                logger.error("Mission %s failed in completeness check: %s", mission_id, e)
                continue

    summary_df = pd.DataFrame(summary_rows)
    missing_df = pd.DataFrame(missing_rows)

    dq_engine = get_dq_engine()
    save(summary_df, "mission_completeness", "bronze", dq_engine)
    if not missing_df.empty:
        save(missing_df, "missing_segments", "bronze", dq_engine)

    logger.info("Completeness check done: %d missions, %d missing segments",
                len(summary_rows), len(missing_rows))

    return {"missions_checked": len(summary_rows), "missing_segments": len(missing_rows)}
