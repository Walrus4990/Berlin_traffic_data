"""
silver.py — Silver layer transformation
=========================================
Reads from bronze PostgreSQL tables, applies the full cleaning routine,
joins location context, and writes to silver tables.

No knowledge of file paths or the portal API — it reads only from bronze_*.

Tables written:
silver_active_mission  — one row per active device with current location + coords
silver_traffic         — cleaned, geo-enriched, flag-annotated passage rows (append)

Entry point: run_silver(new_mission_detected, engine)
"""

import logging
import warnings

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

warnings.filterwarnings("ignore", category=UserWarning)

logger = logging.getLogger(__name__)

# Cleaning thresholds
SPEED_MAX_MOTORISED = 100
SPEED_MIN_MOTORISED = 3
SPEED_MAX_BICYCLE   = 40
SPEED_RATIO_MAX     = 2.5

MOTORISED_CLASSES    = {2, 3, 5, 7, 8, 9, 10, 11, 64}
BICYCLE_CLASS        = 230
UNCLASSIFIABLE_CODES = {6, 250}

ACTIVE_SENTINELS = {
    pd.Timestamp("2049-01-01"),
    pd.Timestamp("2100-01-01"),
}

DEDUP_COLS = ["device_id", "datum_parsed", "vehicle_class", "speed_entry", "speed_exit", "length_dm"]


# Cleaning step functions

def step_parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Parse date_raw, extract date/hour/weekday, flag failures."""
    def _parse(series):
        if pd.api.types.is_datetime64_any_dtype(series):
            return series
        return pd.to_datetime(series, dayfirst=True, errors="coerce")

    df["datum_parsed"] = _parse(df["date_raw"])
    df["datum"]        = df["datum_parsed"].dt.date
    df["stunde"]       = df["datum_parsed"].dt.hour
    df["wochentag"]    = df["datum_parsed"].dt.day_name()
    df["flag_unparseable_timestamp"] = df["datum_parsed"].isna()
    return df


def step_flag_unknown_device(df: pd.DataFrame, known_ids: set) -> pd.DataFrame:
    """Flag rows where device_id has no entry in bronze_mission."""
    df["flag_unknown_device"] = ~df["device_id"].astype(str).isin(known_ids)
    return df


def step_flag_unclassifiable(df: pd.DataFrame) -> pd.DataFrame:
    """Flag vehicle_class 6 / 250 (unclassifiable) rows."""
    df["flag_unclassifiable"] = df["vehicle_class"].isin(UNCLASSIFIABLE_CODES)
    return df


def step_flag_speed(df: pd.DataFrame) -> pd.DataFrame:
    """Flag implausible absolute speeds per vehicle class."""
    is_motorised = df["vehicle_class"].isin(MOTORISED_CLASSES)
    is_bicycle   = df["vehicle_class"] == BICYCLE_CLASS

    flag_entry = (
        (is_motorised & ((df["speed_entry"] > SPEED_MAX_MOTORISED) | (df["speed_entry"] < SPEED_MIN_MOTORISED))) |
        (is_bicycle   &  (df["speed_entry"] > SPEED_MAX_BICYCLE)) |
        (df["speed_entry"] == 0)
    )
    flag_exit = (
        (is_motorised & ((df["speed_exit"] > SPEED_MAX_MOTORISED) | (df["speed_exit"] < SPEED_MIN_MOTORISED))) |
        (is_bicycle   &  (df["speed_exit"] > SPEED_MAX_BICYCLE)) |
        (df["speed_exit"] == 0)
    )
    df["flag_speed_entry"] = flag_entry
    df["flag_speed_exit"]  = flag_exit
    df["flag_speed"]       = flag_entry | flag_exit
    return df


def step_flag_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Flag exact duplicate passage rows."""
    df["flag_duplicate"] = df.duplicated(subset=DEDUP_COLS, keep=False)
    return df


def step_flag_speed_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """
    Proportional entry/exit speed delta check.
    Flags rows where max(entry, exit) / min(entry, exit) > SPEED_RATIO_MAX.
    Rows where either speed is zero are skipped.
    """
    both_pos    = (df["speed_entry"] > 0) & (df["speed_exit"] > 0)
    faster      = df[["speed_entry", "speed_exit"]].max(axis=1)
    slower      = df[["speed_entry", "speed_exit"]].min(axis=1).replace(0, np.nan)
    ratio       = faster / slower
    df["speed_ratio"]      = np.where(both_pos, ratio, np.nan)
    df["flag_speed_delta"] = both_pos & (ratio > SPEED_RATIO_MAX)
    return df


def step_flag_ambiguous_location(df: pd.DataFrame, df_active_mission: pd.DataFrame) -> pd.DataFrame:
    """
    Flag rows whose timestamp falls inside a period where the same device
    was simultaneously registered at two different locations in bronze.mission.

    Operates on the enriched mission table (output of build_mission) which has
    deploy_end already set. Mirrors notebook Section 8 overlap detection logic.
    """
    overlap_windows: list[dict] = []

    for device_id, group in df_active_mission.groupby("device_id"):
        rows = group.sort_values("start_date").reset_index(drop=True)
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a_start = rows.loc[i, "start_date"]
                a_end   = rows.loc[i, "deploy_end"]
                b_start = rows.loc[j, "start_date"]
                b_end   = rows.loc[j, "deploy_end"]
                if pd.isna(a_start) or pd.isna(b_start):
                    continue
                if a_start < b_end and b_start < a_end:
                    overlap_windows.append({
                        "device_id":     str(device_id),
                        "overlap_start": max(a_start, b_start),
                        "overlap_end":   min(a_end, b_end),
                    })

    if not overlap_windows:
        df["flag_ambiguous_location"] = False
        return df

    logger.warning(
        "%d overlapping deployment window pair(s) found — affected rows will be flagged.",
        len(overlap_windows),
    )

    def _in_overlap(row):
        ts  = row["datum_parsed"]
        gid = str(row["device_id"])
        if pd.isna(ts):
            return False
        return any(
            o["device_id"] == gid and o["overlap_start"] <= ts <= o["overlap_end"]
            for o in overlap_windows
        )

    df["flag_ambiguous_location"] = df.apply(_in_overlap, axis=1)
    return df


def step_consolidate_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Combine all flag columns into any_flag + human-readable flag_reasons string."""
    flag_cols = [c for c in [
        "flag_unparseable_timestamp",
        "flag_unknown_device",
        "flag_unclassifiable",
        "flag_speed",
        "flag_duplicate",
        "flag_speed_delta",
        "flag_ambiguous_location",
    ] if c in df.columns]

    df["any_flag"] = df[flag_cols].any(axis=1)

    def _reasons(row):
        triggered = [c.replace("flag_", "") for c in flag_cols if row.get(c)]
        return "; ".join(triggered) if triggered else ""

    df["flag_reasons"] = df.apply(_reasons, axis=1)
    return df


def build_mission(df_mission: pd.DataFrame, df_location: pd.DataFrame) -> pd.DataFrame:
    """
    Build silver_active_mission: one row per deployment,
    enriched with GPS coordinates from bronze_location.

    Join key: location_title (LocationTitle from both portal tables).
    This column is confirmed to match exactly between missions and locations.

    Adds deploy_end: sentinel dates (2049, 2100) → pd.Timestamp.max so that
    enrich_with_location can use it for open-ended time-window matching.
    """
    df_mission = df_mission.copy()
    df_mission["start_date"] = pd.to_datetime(df_mission["start_date"], errors="coerce")
    df_mission["end_date"]   = pd.to_datetime(df_mission["end_date"],   errors="coerce")

    loc_cols  = ["location_title", "street", "street_number", "zipcode", "driving_direction", "opposite_direction", "lat", "lon"]
    available = [c for c in loc_cols if c in df_location.columns]  # location_title included here

    silver = df_mission.merge(
        df_location[available].drop_duplicates("location_title"),
        on="location_title",
        how="left",
    )
    silver["device_id"]  = silver["device_id"].astype(str)
    silver["updated_at"] = pd.Timestamp.now()

    # deploy_end: sentinel dates mean "still active" → open-ended upper bound
    silver["deploy_end"] = silver["end_date"].apply(
        lambda d: pd.Timestamp.max if pd.isna(d) or d in ACTIVE_SENTINELS else d
    )
    return silver.reset_index(drop=True)


def _get_deployment_windows(engine: Engine) -> dict:
    """
    Load all deployment windows from bronze.mission as:
    { device_id: [(start, end), ...] }
    Sentinel end dates (2049, 2100) → pd.Timestamp.max (open-ended active deployments).
    Closed missions use their actual end_date.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT device_id::text, start_date, end_date FROM bronze.mission")
        ).fetchall()

    windows: dict = {}
    for device_id, start, end in rows:
        start_ts = pd.Timestamp(start) if start else None
        if not start_ts:
            continue
        raw_end = pd.Timestamp(end) if end else None
        end_ts = pd.Timestamp.max if (raw_end is None or raw_end in ACTIVE_SENTINELS) else raw_end
        windows.setdefault(str(device_id), []).append((start_ts, end_ts))
    return windows


def step_flag_outside_window(df: pd.DataFrame, windows: dict) -> pd.DataFrame:
    """Flag rows whose timestamp falls outside all known deployment windows."""
    def _outside(row):
        ts  = row["datum_parsed"]
        gid = str(row["device_id"])
        if pd.isna(ts) or gid not in windows:
            return True
        return not any(s <= ts <= e for s, e in windows[gid])

    df["flag_outside_deployment_window"] = df.apply(_outside, axis=1)
    return df


def enrich_with_location(df: pd.DataFrame, df_mission: pd.DataFrame) -> pd.DataFrame:
    """
    Join location columns onto traffic rows using a time-windowed merge:
    1. Left-join df to silver_active_mission on device_id
    2. Keep only the row where datum_parsed falls within [start_date, deploy_end)
    3. Rows with no matching window get NaN coordinates + flag_no_coords=True

    Uses a _row_id tag so the anti-join is exact: only rows that matched zero
    deployment windows appear in the unmatched bucket (not rows that matched a
    different window for the same device).
    """
    orig_cols = df.columns.tolist()
    df        = df.copy()
    df["device_id"] = df["device_id"].astype(str)

    df_mission = df_mission.copy()
    df_mission["device_id"] = df_mission["device_id"].astype(str)

    geo_cols  = ["location_title", "street", "street_number", "zipcode",
                 "driving_direction", "lat", "lon", "start_date", "deploy_end"]
    available = ["device_id"] + [c for c in geo_cols if c in df_mission.columns]

    df["_row_id"] = range(len(df))
    df_geo = df.merge(df_mission[available], on="device_id", how="left")

    window_match = (
        df_geo["datum_parsed"].ge(df_geo["start_date"]) &
        df_geo["datum_parsed"].lt(df_geo["deploy_end"])
    )
    matched     = df_geo[window_match].drop(columns=["_row_id"])
    matched_ids = set(df_geo.loc[window_match, "_row_id"])

    # Only rows that never matched any deployment window
    unmatched = df[~df["_row_id"].isin(matched_ids)].drop(columns=["_row_id"]).copy()
    for col in [c for c in geo_cols if c != "device_id"]:
        unmatched[col] = pd.NA

    final_cols = orig_cols + [c for c in geo_cols if c != "device_id"]
    out = pd.concat(
        [matched.reindex(columns=final_cols), unmatched.reindex(columns=final_cols)],
        ignore_index=True,
    )
    out["flag_no_coords"] = out["lat"].isna() | (out["lat"] == 0)
    return out


def run_silver(new_mission_detected: bool, engine: Engine) -> dict:
    """
    Silver transformation run. Reads from bronze_* tables, writes to silver_*.
    Silver uses this function to read bronze tables and write silver tables
    Returns dict with QA counts for the pipeline log.
    """
    logger.info("=== SILVER LAYER START (full=%s) ===", new_mission_detected)
    qa: dict = {}

    # Load two reference tables
    df_mission  = pd.read_sql("SELECT * FROM bronze.mission",  engine)
    df_location = pd.read_sql("SELECT * FROM bronze.location", engine)

    # Build silver_active_mission: mission + location joined, deploy_end set
    df_active_mission = build_mission(df_mission, df_location)
    df_active_mission.to_sql(
        "active_mission", engine, schema="silver", if_exists="replace", index=False
    )
    logger.info("Refreshed silver.active_mission: %d rows.", len(df_active_mission))

    # Load unprocessed bronze.traffic rows
    # "Unprocessed" = source_file not yet seen in silver.traffic
    df_bronze = pd.read_sql("SELECT * FROM bronze.traffic", engine)
    try:
        processed = pd.read_sql(
            "SELECT DISTINCT source_file FROM silver.traffic", engine
        )["source_file"].tolist()
        df = df_bronze[~df_bronze["source_file"].isin(processed)].copy()
    except Exception:
        df = df_bronze.copy()   # silver.traffic doesn't exist yet on first run

    if df.empty:
        logger.info("No new bronze.traffic rows to process.")
        return {"rows_processed": 0}

    logger.info("Processing %d new bronze.traffic rows.", len(df))

    known_ids = set(df_mission["device_id"].astype(str).unique())
    windows   = _get_deployment_windows(engine)

    # Cleaning steps
    df = step_parse_timestamps(df)
    qa["unparseable_timestamp"] = int(df["flag_unparseable_timestamp"].sum())

    if new_mission_detected:
        # Full path: run all checks
        df = step_flag_unknown_device(df, known_ids)
        qa["unknown_device"] = int(df["flag_unknown_device"].sum())

        df = step_flag_outside_window(df, windows)
        qa["outside_deployment_window"] = int(df["flag_outside_deployment_window"].sum())

        df = step_flag_ambiguous_location(df, df_active_mission)
        qa["ambiguous_location"] = int(df["flag_ambiguous_location"].sum())

    else:
        # Reduced path: set flags to False, skip the checks
        df["flag_unknown_device"]            = False
        df["flag_outside_deployment_window"] = False
        df["flag_ambiguous_location"]        = False

    df = step_flag_unclassifiable(df)
    qa["unclassifiable"] = int(df["flag_unclassifiable"].sum())

    df = step_flag_speed(df)
    qa["implausible_speed"] = int(df["flag_speed"].sum())

    df = step_flag_duplicates(df)
    qa["duplicates"] = int(df["flag_duplicate"].sum())

    df = step_flag_speed_ratio(df)
    qa["large_speed_ratio"] = int(df["flag_speed_delta"].sum())

    df = step_consolidate_flags(df)
    qa["total_flagged"] = int(df["any_flag"].sum())
    qa["total_clean"]   = int((~df["any_flag"]).sum())

    # Geo-enrichment
    # Uses df_active_mission (has lat/lon + deploy_end) not raw bronze.mission
    df = enrich_with_location(df, df_active_mission)
    qa["no_coords"] = int(df["flag_no_coords"].sum())

    # Write to silver.traffic
    df["processed_at"]  = pd.Timestamp.now()
    df["pipeline_path"] = "full" if new_mission_detected else "reduced"
    df.to_sql("traffic", engine, schema="silver", if_exists="append", index=False)

    qa["rows_processed"] = len(df)
    logger.info(
        "Appended %d rows to silver.traffic (%d flagged, %d clean).",
        len(df), qa["total_flagged"], qa["total_clean"],
    )
    logger.info("=== SILVER LAYER DONE ===")
    return qa
