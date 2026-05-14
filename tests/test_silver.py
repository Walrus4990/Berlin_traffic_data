
import pandas as pd
import logging
import pytz


from utils.db import get_traffic_engine, get_dq_engine, save


logger = logging.getLogger(__name__)

def check_silver_dq() -> dict:
    """
    Reads DQ flags from silver.staging_traffic and writes two reports
    to the DQ database:
    - silver.traffic_source_file_report: one row per source file with flag counts and proportions
    - silver.vehicle_length_profile: one row per source file per vehicle class with length stats
    Must run after load_traffic_to_silver and before the next run truncates staging.
    Returns dict with row counts for each report.
    """
    berlin = pytz.timezone("Europe/Berlin")
    run_at = pd.Timestamp.now(tz=berlin)
    engine = get_traffic_engine()
    dq_engine = get_dq_engine()

    # source file report
    source_file_df = pd.read_sql("""
        SELECT
            source_file,
            COUNT(*) AS rows_total,
            SUM(CASE WHEN NOT flag_duplicate THEN 1 ELSE 0 END) AS rows_written_to_silver,
            SUM(CASE WHEN flag_duplicate THEN 1 ELSE 0 END) AS flag_duplicate_n,
            ROUND(SUM(CASE WHEN flag_duplicate THEN 1 ELSE 0 END)::NUMERIC / COUNT(*), 4) AS flag_duplicate_pct,
            SUM(CASE WHEN flag_speed_entry_100 THEN 1 ELSE 0 END) AS flag_speed_entry_100_n,
            ROUND(SUM(CASE WHEN flag_speed_entry_100 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*), 4) AS flag_speed_entry_100_pct,
            SUM(CASE WHEN flag_speed_exit_100 THEN 1 ELSE 0 END) AS flag_speed_exit_100_n,
            ROUND(SUM(CASE WHEN flag_speed_exit_100 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*), 4) AS flag_speed_exit_100_pct,
            SUM(CASE WHEN flag_speed_100 THEN 1 ELSE 0 END) AS flag_speed_100_n,
            ROUND(SUM(CASE WHEN flag_speed_100 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(SUM(CASE WHEN vehicle_class IN (2,3,5,7,8,9,10,11) THEN 1 ELSE 0 END), 0), 4) AS flag_speed_100_pct,
            SUM(CASE WHEN flag_bike_speed_40 THEN 1 ELSE 0 END) AS flag_bike_speed_40_n,
            ROUND(SUM(CASE WHEN flag_bike_speed_40 THEN 1 ELSE 0 END)::NUMERIC / NULLIF(SUM(CASE WHEN vehicle_class = 230 THEN 1 ELSE 0 END), 0), 4) AS flag_bike_speed_40_pct
        FROM silver.staging_traffic
        GROUP BY source_file
    """, engine)
    source_file_df["run_at"] = run_at
    save(source_file_df, "traffic_source_file_report", "silver", dq_engine)

    # length profile
    length_df = pd.read_sql("""
        SELECT
            source_file,
            vehicle_class,
            vehicle_class_label,
            COUNT(*) AS n,
            MIN(length_dm) AS min_length_dm,
            MAX(length_dm) AS max_length_dm,
            ROUND(AVG(length_dm), 2) AS avg_length_dm,
            ROUND(SUM(CASE WHEN flag_length_below_min THEN 1 ELSE 0 END)::NUMERIC / COUNT(*), 4) AS pct_below_min,
            ROUND(SUM(CASE WHEN flag_length_above_max THEN 1 ELSE 0 END)::NUMERIC / COUNT(*), 4) AS pct_above_max
        FROM silver.staging_traffic
        GROUP BY source_file, vehicle_class, vehicle_class_label
    """, engine)
    length_df["run_at"] = run_at
    save(length_df, "vehicle_length_profile", "silver", dq_engine)

    logger.info("Silver DQ done: %d source files, %d length profile rows.",
                len(source_file_df), len(length_df))
    result = {"source_files_checked": len(source_file_df), "length_profile_rows": len(length_df)}
    return result
