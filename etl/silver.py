"""
Reads from bronze PostgreSQL tables, applies the full cleaning routine in Postgres database,
writes to silver tables.
Tables written:
silver_traffic         — cleaned rows (append)

"""

import logging
from sqlalchemy import text

from utils.db import get_loaded_files, get_traffic_engine

logger = logging.getLogger(__name__)


def load_traffic_to_silver() -> int:
    """
    Loads rows from bronze.traffic to silver.staging_traffic.
    While loading cleans them & loads clean rows to silver.
    Data quality reports are loaded to silver layer of DQ database.
    Returns number of rows appended.
    """
    engine = get_traffic_engine()
    logger.info("=== SILVER LAYER START ===")

    #truncate straging table
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE silver.staging_traffic"))
        conn.commit()


    # Identify already-processed files for idempotency
    silver_files = get_loaded_files(engine, "silver", "traffic")
    bronze_files = get_loaded_files(engine, "bronze", "traffic")
    new_files = bronze_files - silver_files

    logger.info("%d new source file(s) to process.", len(new_files))

    if not new_files:
        logger.info("No new source files — exiting.")
        return 0

    # insert new rows & clean them
    with engine.connect() as conn:
        conn.execute(text(
        """
        INSERT INTO silver.staging_traffic (
            mission_id, device_id, date_raw, date_parsed,
            speed_entry, speed_exit, flag_speed_entry_100, flag_speed_exit_100,
            flag_speed_100, flag_bike_speed_40, speed,
            length_dm, flag_length_below_min, flag_length_above_max,
            vehicle_class, vehicle_class_label,
            source_file, ingested_at, flag_duplicate
        )

        SELECT
            mission_id,
            device_id,
            date_raw,
            TO_TIMESTAMP(date_raw, 'YYYY-MM-DD HH24:MI:SS') AS date_parsed,

            speed_entry,
            speed_exit,
            speed_entry > 100 AS flag_speed_entry_100,
            speed_exit  > 100 AS flag_speed_exit_100,
            vehicle_class IN (2,3,5,7,8,9,10,11,64) AND GREATEST(speed_entry, speed_exit) > 100 AS flag_speed_100,
            vehicle_class = 230 AND GREATEST(speed_entry, speed_exit) > 40 AS flag_bike_speed_40,
            GREATEST(
                NULLIF(CASE WHEN speed_entry > 100 THEN NULL ELSE speed_entry END, 0),
                NULLIF(CASE WHEN speed_exit  > 100 THEN NULL ELSE speed_exit  END, 0)
            ) AS speed,

            length_dm,
            length_dm < CASE vehicle_class
                WHEN 2   THEN 55  WHEN 3  THEN 50  WHEN 5  THEN 60
                WHEN 6   THEN 15  WHEN 7  THEN 25  WHEN 8  THEN 80
                WHEN 9   THEN 100 WHEN 10 THEN 15  WHEN 11 THEN 35
                WHEN 230 THEN 10  ELSE NULL END AS flag_length_below_min,
            length_dm > CASE vehicle_class
                WHEN 2   THEN 188 WHEN 3  THEN 120 WHEN 5  THEN 188
                WHEN 6   THEN 120 WHEN 7  THEN 120 WHEN 8  THEN 188
                WHEN 9   THEN 165 WHEN 10 THEN 40  WHEN 11 THEN 120
                WHEN 230 THEN 20  ELSE NULL END AS flag_length_above_max,

            vehicle_class,
            vehicle_class_label,
            source_file,
            ingested_at,

            ROW_NUMBER() OVER (
                PARTITION BY device_id, date_raw, vehicle_class, speed_entry, speed_exit, length_dm
                ORDER BY ingested_at
            ) > 1 AS flag_duplicate

        FROM bronze.traffic
        WHERE source_file = ANY(:new_files);"""),
        {"new_files": list(new_files)}) #pass new files to only copy rows that are new
        conn.commit()
    logger.info("Staging loaded: %d new file(s) queued for cleaning.", len(new_files))

    #save clean rows to silver
    with engine.connect() as conn:
            conn.execute(text(
            """
            INSERT INTO silver.traffic (
                mission_id, device_id, date_raw, date_parsed,
                speed_entry, speed_exit, speed,
                length_dm, vehicle_class, vehicle_class_label,
                source_file, ingested_at
            )

            SELECT
                mission_id,
                device_id,
                date_raw,
                date_parsed,
                speed_entry,
                speed_exit,
                speed,
                length_dm,
                vehicle_class,
                vehicle_class_label,
                source_file,
                ingested_at

            FROM silver.staging_traffic
            WHERE NOT flag_duplicate"""))
            conn.commit()
            rows_written = conn.execute(text("""
                                     SELECT COUNT(*) FROM silver.traffic WHERE source_file = ANY(:new_files)"""),
                                    {"new_files": list(new_files)}).scalar()
    logger.info("Silver layer done: %d rows written from %d source file(s).", rows_written, len(new_files))
    return rows_written
