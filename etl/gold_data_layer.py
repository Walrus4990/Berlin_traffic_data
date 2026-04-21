"""
gold_data_layer.py — Gold layer aggregation
=============================================
Reads from silver.traffic, applies hourly aggregation, and writes to
gold.traffic in PostgreSQL.

It reads only from silver.traffic.

Table written:
    gold.traffic  — one row per (geraet_id, standort, datum, stunde) vehicle counts and speed metrics per sensor-hour

Entry point: run_gold(engine)
Returns:     dict with row counts for each table written
"""

import logging
import warnings
from sqlalchemy import text

import pandas as pd
from sqlalchemy.engine import Engine

from utils.db import get_traffic_engine

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

logger = logging.getLogger(__name__)

# All motorised vehicle classes (excludes bicycles class 230)
MOTORISED_CLASSES    = {2, 3, 5, 7, 8, 9, 10, 11}
V85_EXCLUDED_CLASSES = {10, 230}   # krad and fahrrad excluded from V85
V85_MIN_SAMPLE       = 5           # minimum eligible rows to compute V85

HOUR_GROUP_KEYS = ["device_id", "location_title", "datum", "stunde"]

INT_COLS   = ["stunde", "kfz", "pkw", "lkw", "lfw", "krad", "fahrrad"]
FLOAT_COLS = [
    "v_kfz", "v_pkw", "v_lkw", "v85", "latitude", "longitude",
    "modal_share_pkw", "modal_share_fahrrad", "modal_share_lkw", "modal_share_krad",
]


def aggregate_hour(grp: pd.DataFrame) -> pd.Series:
    """
    Aggregate one (device_id, location_title, datum, stunde) group into a single hourly summary row.
    Counts include all rows (flagged and clean).
    Speed and V85 metrics use only the clean subset.
    """
    result = {}
    clean = ~grp["any_flag"] & ~grp["flag_speed_delta"]

    result["pkw"]     = int((grp["vehicle_class"] == 7).sum())    # Pkw — car
    result["lkw"]     = int((grp["vehicle_class"] == 3).sum())    # Lkw — lorry
    result["lfw"]     = int((grp["vehicle_class"] == 11).sum())   # Lfw — delivery van
    result["krad"]    = int((grp["vehicle_class"] == 10).sum())   # Krad — motorcycle
    result["fahrrad"] = int((grp["vehicle_class"] == 230).sum())  # Fahrrad — bicycle
    result["kfz"]     = int(grp["vehicle_class"].isin(MOTORISED_CLASSES).sum())  # all motorised

    # Speed metrics (clean rows only)
    motor_clean = grp["vehicle_class"].isin(MOTORISED_CLASSES) & clean
    pkw_clean   = (grp["vehicle_class"] == 7) & clean
    lkw_clean   = (grp["vehicle_class"] == 3) & clean
    v85_mask    = ~grp["vehicle_class"].isin(V85_EXCLUDED_CLASSES) & clean

    result["v_kfz"] = (
        float(grp.loc[motor_clean, "speed_entry"].mean()) # Average speed all vehicles (km/h)
        if motor_clean.sum() > 0 else None
    )
    result["v_pkw"] = (
        float(grp.loc[pkw_clean, "speed_entry"].mean()) # Average speed cars (km/h)
        if pkw_clean.sum() > 0 else None
    )
    result["v_lkw"] = (
        float(grp.loc[lkw_clean, "speed_entry"].mean()) # Average speed lorries (km/h)
        if lkw_clean.sum() > 0 else None
    )

    v85_speeds    = grp.loc[v85_mask, "speed_entry"] # V85 — 85th-percentile entry speed, excluding krad and fahrrad
    result["v85"] = (
        round(float(v85_speeds.quantile(0.85)), 2)
        if len(v85_speeds) >= V85_MIN_SAMPLE else None
    )

    # Location coordinates (first non-null values found in the group)
    result["latitude"]  = float(grp["lat"].dropna().iloc[0]) if grp["lat"].notna().any() else None
    result["longitude"] = float(grp["lon"].dropna().iloc[0]) if grp["lon"].notna().any() else None
    return pd.Series(result)


def _enforce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """suggested by LLM: adding this function here to fix a common pandas issue
    where groupby().apply() returns numeric-looking columns as object. """
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# Post-aggregation integrity checks

def _check_gold_hourly(df: pd.DataFrame, n_input: int) -> None:
    """Run post-aggregation checks. Raises AssertionError on hard failures."""
    checks_passed = 0

    # 1. No duplicate keys (geraet_id, standort, datum, stunde)
    gold_key = ["geraet_id", "standort", "datum", "stunde"]
    dup_keys = df.duplicated(subset=gold_key, keep=False)
    if dup_keys.any():
        raise AssertionError(
            f"{dup_keys.sum()} rows in gold.traffic share the same "
            f"({', '.join(gold_key)}) key"
        )
    logger.info("Check 1: No duplicate (%s) keys.", ", ".join(gold_key))
    checks_passed += 1

    # 2. stunde values are 0–23
    off_stunde = df["stunde"].dropna()
    off_stunde = off_stunde[(off_stunde < 0) | (off_stunde > 23)]
    assert len(off_stunde) == 0, f"stunde values outside 0–23: {off_stunde.unique()}"
    logger.info("Check 2: All stunde values are 0–23.")
    checks_passed += 1

    # 3. Gold row count ≤ input silver row count
    assert len(df) <= n_input, (
        f"gold.traffic has more rows ({len(df)}) than silver.traffic input ({n_input})"
    )
    logger.info("Check 3: Row count consistent.")
    checks_passed += 1

    logger.info("All %d/3 post-aggregation checks passed.", checks_passed)


# Aggregation builder
def build_hourly(df_silver: pd.DataFrame) -> pd.DataFrame:
    """
    Compute gold.traffic from a silver.traffic DataFrame.

    Groups by (device_id, location_title, datum, stunde) and applies aggregate_hour() to produce one row per sensor-hour.
    """
    df = df_silver.copy()

    df["vehicle_class"]  = pd.to_numeric(df["vehicle_class"], errors="coerce")
    df["datum"]          = pd.to_datetime(df["datum"], errors="coerce").dt.date
    df["stunde"]         = pd.to_numeric(df["stunde"], errors="coerce")
    df["location_title"] = df["location_title"].fillna("unknown")

    hourly = (
        df.groupby(HOUR_GROUP_KEYS, sort=True, dropna=False)
        .apply(aggregate_hour)
        .reset_index()
    )
    hourly = _enforce_dtypes(hourly)
    hourly = hourly.rename(columns={
        "device_id":      "geraet_id",
        "location_title": "standort",
    })

    hourly["datum_iso"] = hourly["datum"].astype(str)

    # Modal shares
    total_all = hourly["kfz"].fillna(0) + hourly["fahrrad"].fillna(0)
    for cls in ["pkw", "fahrrad", "lkw", "krad"]:
        hourly[f"modal_share_{cls}"] = (hourly[cls] / total_all * 100).round(1)

    # Reorder columns to match the target table
    col_order = [
        "datum", "datum_iso", "stunde", "geraet_id", "standort",
        "latitude", "longitude",
        "kfz", "pkw", "lkw", "lfw", "krad", "fahrrad",
        "v_kfz", "v_pkw", "v_lkw", "v85",
        "modal_share_pkw", "modal_share_fahrrad", "modal_share_lkw", "modal_share_krad",
    ]
    hourly = hourly[[c for c in col_order if c in hourly.columns]]

    return hourly


# Execution entry point
def run_gold(engine: Engine) -> dict:
    """
    Full gold aggregation run: reads silver.traffic, computes the hourly aggregation, and writes to gold.traffic.
    Write the final table to gold.traffic.
    """
    df_silver = pd.read_sql("SELECT * FROM silver.traffic", engine)
    logger.info("Loaded %d rows from silver.traffic.", len(df_silver))

    if df_silver.empty:
        logger.warning("silver.traffic is empty — nothing to aggregate.")
        return {"rows_traffic": 0}

    df_hourly = build_hourly(df_silver)
    _check_gold_hourly(df_hourly, n_input=len(df_silver))
    #df_hourly.to_sql("traffic", engine, schema="gold", if_exists="replace", index=False) - replaces Gold table, risks breaking Superset
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE gold.traffic"))       #TRUNCATE TABLE gold.traffic empties the table completely but leaves the table structure 
    df_hourly.to_sql("traffic", engine, schema="gold", if_exists="append", index=False)
    logger.info("Wrote %d rows to gold.traffic.", len(df_hourly))
    result = {"rows_traffic": len(df_hourly)}
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with get_traffic_engine() as engine:
        result = run_gold(engine)
    for k, v in result.items():
        print(f"  {k:<22} {v:>8,}")
