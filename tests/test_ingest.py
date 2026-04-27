#Functions to test the pipeline go here

import pandas as pd
from sqlalchemy import text
import logging

from utils.db import get_traffic_engine, get_dq_engine, save
from utils.minio import read_tracker
from etl.ddweb_ingest_traffic import get_chunks, get_chunk_start



logger = logging.getLogger(__name__)

def check_bronze_completeness(run_type: str) -> dict:
    run_at = pd.Timestamp.now(tz="Europe/Berlin")

    with get_traffic_engine() as engine:
        missions = pd.read_sql("SELECT mission_id, start_date, end_date FROM bronze.mission", engine)
        loaded_files = pd.read_sql("SELECT DISTINCT source_file FROM bronze.traffic", engine)

    loaded_set = set(loaded_files["source_file"].tolist())

    tracker = read_tracker()

    summary_rows = []
    missing_rows = []

    for _, row in missions.iterrows():
        mission_id = str(row["mission_id"])
        if run_type == "initial":
            chunks = get_chunks(row["start_date"], row["end_date"])
        else:
            chunks = get_chunks(
                get_chunk_start(int(mission_id), row["start_date"], tracker),
                row["end_date"]
            )
        expected_files = [
            f"mission_{mission_id}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.parquet"
            for start, end in chunks
        ]

    actual = [f for f in expected_files if f in loaded_set]
    missing = [f for f in expected_files if f not in loaded_set]

    summary_rows.append({
        "run_at": run_at,
        "mission_id": mission_id,
        "expected_chunks": len(expected_files),
        "actual_chunks": len(actual),
        "missing_count": len(missing),
    })

    for f in missing:
        missing_rows.append({
            "run_at": run_at,
            "mission_id": mission_id,
            "expected_filename": f,
        })

    summary_df = pd.DataFrame(summary_rows)
    missing_df = pd.DataFrame(missing_rows)

    with get_dq_engine() as dq_engine:
        save(summary_df, "mission_completeness", "bronze", dq_engine)
        if not missing_df.empty:
            save(missing_df, "missing_chunks", "bronze", dq_engine)

    logger.info("Completeness check done: %d missions, %d missing chunks",
                len(summary_rows), len(missing_rows))

    return {"missions_checked": len(summary_rows), "missing_chunks": len(missing_rows)}
