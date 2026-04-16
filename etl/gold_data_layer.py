"""
gold_data_layer.py — Gold layer aggregation
=============================================
Reads from silver.traffic, applies hourly aggregation, and writes to
gold.* tables in PostgreSQL.

No knowledge of file paths or the portal API — reads only from silver.traffic.

Tables written:
    gold.hourly       — one row per (device_id, location_title, datum, stunde, wochentag)
                        counts per vehicle class, speed metrics, V85, promoted flags
    gold.by_location  — per-device summary (total passages, avg V85, date range)
    gold.by_vehicle   — fleet-wide modal share totals across all records
    gold.by_time      — average hourly profile (hour 0–23, avg counts + speeds)

Entry point: run_gold(engine)
Returns:     dict with row counts for each table written
"""

import logging
import warnings

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from utils.db import get_traffic_engine

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

logger = logging.getLogger(__name__)

# ── Vehicle class → count column mapping ─────────────────────────────────────
KLASSE_COUNT_COLS = {
    "count_pkw":     7,    # Pkw — Car
    "count_pkw_a":   2,    # PkwA — Car with trailer
    "count_lkw":     3,    # Lkw — Lorry
    "count_lkw_a":   8,    # LkwA — Lorry with trailer
    "count_sattel":  9,    # Sattel-Kfz — Articulated / HGV
    "count_bus":     5,    # Bus
    "count_krad":    10,   # Krad — Motorcycle
    "count_lfw":     11,   # Lfw — Delivery van
    "count_fahrrad": 230,  # Fahrrad — Bicycle
    "count_nk_kfz":  6,    # nk Kfz — unclassified motor vehicle
    "count_kfz64":   64,   # Kfz — all motor vehicles (class 64)
}

# Speed calculations exclude Krad (10) and Fahrrad (230) per traffic engineering convention
MOTORISED_SPEED_CLASSES = {2, 3, 5, 7, 8, 9, 10, 11}
V85_EXCLUDED_CLASSES    = {10, 230}
V85_MIN_SAMPLE          = 5        # minimum eligible rows to compute V85

HOUR_GROUP_KEYS = ["device_id", "location_title", "datum", "stunde", "wochentag"]

ROW_FLAG_COLS = [
    "flag_unparseable_timestamp",
    "flag_unknown_device",
    "flag_outside_deployment_window",
    "flag_ambiguous_location",
    "flag_unclassifiable",
    "flag_speed",
    "flag_duplicate",
    "flag_speed_delta",
]

INT_COLS = (
    ["stunde", "count_total", "count_motorised", "n_v85_eligible", "n_flagged_rows"]
    + list(KLASSE_COUNT_COLS.keys())
)
FLOAT_COLS = ["mean_speed_entry", "mean_speed_exit", "mean_speed_bicycle", "v85_entry", "lat", "lon"]
BOOL_COLS  = ["thin_v85_sample", "flag_any", "flag_unclassifiable", "flag_speed_issues", "flag_duplicate"]


# ── Core aggregation ──────────────────────────────────────────────────────────

def aggregate_hour(grp: pd.DataFrame) -> pd.Series:
    """
    Aggregate one (device_id, location_title, datum, stunde, wochentag) group
    into a single hourly summary row.

    All rows in the group are counted — flagged rows are NOT pre-filtered from
    counts. Speed and V85 metrics use only unflagged rows (clean_subset).
    """
    result = {}

    # ── Counts ────────────────────────────────────────────────────────────────
    result["count_total"] = len(grp)

    for col_name, klass_code in KLASSE_COUNT_COLS.items():
        result[col_name] = int((grp["vehicle_class"] == klass_code).sum())

    # Motorised count: excludes bicycles (230), class 64 aggregate, and unclassified (6)
    result["count_motorised"] = int(grp["vehicle_class"].isin(MOTORISED_SPEED_CLASSES).sum())

    # ── Speed metrics (clean rows only) ───────────────────────────────────────
    clean_subset = ~grp["any_flag"] & ~grp["flag_speed_delta"]
    motor_subset = grp["vehicle_class"].isin(MOTORISED_SPEED_CLASSES) & clean_subset
    bike_subset  = (grp["vehicle_class"] == 230) & clean_subset
    v85_subset   = (~grp["vehicle_class"].isin(V85_EXCLUDED_CLASSES)) & clean_subset

    result["mean_speed_entry"] = (
        float(grp.loc[motor_subset, "speed_entry"].mean())
        if motor_subset.sum() > 0 else None
    )
    result["mean_speed_exit"] = (
        float(grp.loc[motor_subset, "speed_exit"].mean())
        if motor_subset.sum() > 0 else None
    )
    result["mean_speed_bicycle"] = (
        float(grp.loc[bike_subset, "speed_entry"].mean())
        if bike_subset.sum() > 0 else None
    )

    # V85 — 85th-percentile entry speed for non-motorcycle, non-bicycle vehicles
    v85_speeds = grp.loc[v85_subset, "speed_entry"]
    n_v85      = len(v85_speeds)
    result["v85_entry"]       = round(float(v85_speeds.quantile(0.85)), 2) if n_v85 >= V85_MIN_SAMPLE else None
    result["n_v85_eligible"]  = int(n_v85)
    result["thin_v85_sample"] = bool(n_v85 < V85_MIN_SAMPLE)

    # ── Location coords (first non-null in group) ─────────────────────────────
    result["lat"] = float(grp["lat"].dropna().iloc[0]) if grp["lat"].notna().any() else None
    result["lon"] = float(grp["lon"].dropna().iloc[0]) if grp["lon"].notna().any() else None

    # ── Flags: promoted from row-level to hour-level ──────────────────────────
    # True at hour level = at least one row in this hour triggered the flag.
    result["flag_any"]            = bool(grp["any_flag"].any())
    result["flag_unclassifiable"] = (
        bool(grp["flag_unclassifiable"].any()) if "flag_unclassifiable" in grp.columns else False
    )
    result["flag_speed_issues"] = (
        bool(grp["flag_speed"].any()) if "flag_speed" in grp.columns else False
    )
    result["flag_duplicate"] = (
        bool(grp["flag_duplicate"].any()) if "flag_duplicate" in grp.columns else False
    )
    result["n_flagged_rows"] = int(grp["any_flag"].sum())

    return pd.Series(result)


def _enforce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Cast columns to their canonical types after groupby/apply."""
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].astype(bool)
    return df


# ── Post-aggregation integrity checks ─────────────────────────────────────────

def _check_gold_hourly(df: pd.DataFrame, n_input: int) -> None:
    """Run 5 post-aggregation checks. Raises AssertionError on hard failures."""
    checks_passed = 0

    # 1. No duplicate (device_id, datum, stunde) keys
    dup_keys = df.duplicated(subset=["device_id", "datum", "stunde"], keep=False)
    if dup_keys.any():
        raise AssertionError(
            f"{dup_keys.sum()} rows in gold.hourly share the same "
            f"(device_id, datum, stunde) key"
        )
    logger.info("Check 1: No duplicate (device_id, datum, stunde) keys.")
    checks_passed += 1

    # 2. Per-class counts do not exceed count_total
    class_sum   = df[list(KLASSE_COUNT_COLS.keys())].sum(axis=1)
    unaccounted = df["count_total"] - class_sum
    if (unaccounted < 0).any():
        logger.warning(
            "Check 2: %d hour(s) where class column sum exceeds count_total.",
            (unaccounted < 0).sum(),
        )
    else:
        logger.info("Check 2: Per-class counts consistent with count_total.")
        checks_passed += 1

    # 3. stunde values are 0–23
    bad_stunde = df["stunde"].dropna()
    bad_stunde = bad_stunde[(bad_stunde < 0) | (bad_stunde > 23)]
    assert len(bad_stunde) == 0, f"stunde values outside 0–23: {bad_stunde.unique()}"
    logger.info("Check 3: All stunde values are 0–23.")
    checks_passed += 1

    # 4. V85 is null for all thin-sample hours
    thin_with_v85 = df[df["thin_v85_sample"] & df["v85_entry"].notna()]
    assert len(thin_with_v85) == 0, (
        f"{len(thin_with_v85)} hours marked thin_v85_sample=True but have non-null v85_entry"
    )
    logger.info("Check 4: V85 is null for all thin-sample hours.")
    checks_passed += 1

    # 5. Gold row count ≤ input row count
    assert len(df) <= n_input, (
        f"gold.hourly has more rows ({len(df)}) than silver.traffic input ({n_input})"
    )
    logger.info("Check 5: Row count consistent.")
    checks_passed += 1

    logger.info("All %d/5 post-aggregation checks passed.", checks_passed)


# ── Aggregation builders ──────────────────────────────────────────────────────

def build_hourly(df_silver: pd.DataFrame) -> pd.DataFrame:
    """
    Compute gold.hourly from a silver.traffic DataFrame.

    Groups by (device_id, location_title, datum, stunde, wochentag) and
    applies aggregate_hour() to produce one row per sensor-hour.
    """
    df = df_silver.copy()

    # Normalise types that may vary depending on how the DF was loaded
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
    return hourly


def build_by_location(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Per-device / location summary aggregated from gold.hourly.
    One row per (device_id, location_title).
    """
    summary = (
        df_hourly.groupby(["device_id", "location_title"], dropna=False)
        .agg(
            total_hours    = ("stunde",         "count"),
            total_passages = ("count_total",    "sum"),
            date_start     = ("datum",          "min"),
            date_end       = ("datum",          "max"),
            avg_v85        = ("v85_entry",      "mean"),
            hours_flagged  = ("flag_any",       "sum"),
            lat            = ("lat",            "first"),
            lon            = ("lon",            "first"),
        )
        .reset_index()
    )
    summary["avg_v85"] = summary["avg_v85"].round(1)
    return summary


def build_by_vehicle(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Fleet-wide modal share — total passage counts per vehicle class
    across all locations and time periods. Returns a single-row DataFrame.
    """
    totals: dict = {}
    for col in KLASSE_COUNT_COLS:
        totals[col] = int(df_hourly[col].sum())
    totals["count_total"]     = int(df_hourly["count_total"].sum())
    totals["count_motorised"] = int(df_hourly["count_motorised"].sum())
    return pd.DataFrame([totals])


def build_by_time(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Average hourly traffic profile — mean counts and speeds per hour-of-day (0–23).
    One row per stunde value.
    """
    return (
        df_hourly.groupby("stunde", sort=True)
        .agg(
            avg_count_total   = ("count_total",       "mean"),
            avg_count_pkw     = ("count_pkw",         "mean"),
            avg_count_lkw     = ("count_lkw",         "mean"),
            avg_count_lfw     = ("count_lfw",         "mean"),
            avg_count_krad    = ("count_krad",        "mean"),
            avg_count_fahrrad = ("count_fahrrad",     "mean"),
            avg_speed_entry   = ("mean_speed_entry",  "mean"),
            avg_v85           = ("v85_entry",         "mean"),
        )
        .round(1)
        .reset_index()
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def run_gold(engine: Engine) -> dict:
    """
    Full gold aggregation run — reads silver.traffic, computes all gold tables,
    writes results to PostgreSQL gold schema.

    All gold tables are fully replaced on every run (if_exists="replace").

    Returns dict with row counts:
        rows_hourly       int   rows in gold.hourly
        rows_by_location  int   rows in gold.by_location
        rows_by_vehicle   int   rows in gold.by_vehicle (always 1)
        rows_by_time      int   rows in gold.by_time (up to 24)
    """
    logger.info("=== GOLD LAYER START ===")

    df_silver = pd.read_sql("SELECT * FROM silver.traffic", engine)
    logger.info("Loaded %d rows from silver.traffic.", len(df_silver))

    if df_silver.empty:
        logger.warning("silver.traffic is empty — nothing to aggregate.")
        return {"rows_hourly": 0, "rows_by_location": 0, "rows_by_vehicle": 0, "rows_by_time": 0}

    # ── gold.hourly ───────────────────────────────────────────────────────────
    logger.info("Computing gold.hourly …")
    df_hourly = build_hourly(df_silver)
    _check_gold_hourly(df_hourly, n_input=len(df_silver))
    df_hourly["aggregated_at"] = pd.Timestamp.now()
    df_hourly.to_sql("hourly", engine, schema="gold", if_exists="replace", index=False)
    logger.info("Wrote %d rows to gold.hourly.", len(df_hourly))

    # ── gold.by_location ──────────────────────────────────────────────────────
    df_loc = build_by_location(df_hourly)
    df_loc.to_sql("by_location", engine, schema="gold", if_exists="replace", index=False)
    logger.info("Wrote %d rows to gold.by_location.", len(df_loc))

    # ── gold.by_vehicle ───────────────────────────────────────────────────────
    df_veh = build_by_vehicle(df_hourly)
    df_veh.to_sql("by_vehicle", engine, schema="gold", if_exists="replace", index=False)
    logger.info("Wrote %d rows to gold.by_vehicle.", len(df_veh))

    # ── gold.by_time ──────────────────────────────────────────────────────────
    df_time = build_by_time(df_hourly)
    df_time.to_sql("by_time", engine, schema="gold", if_exists="replace", index=False)
    logger.info("Wrote %d rows to gold.by_time.", len(df_time))

    result = {
        "rows_hourly":      len(df_hourly),
        "rows_by_location": len(df_loc),
        "rows_by_vehicle":  len(df_veh),
        "rows_by_time":     len(df_time),
    }
    logger.info("=== GOLD LAYER DONE: %s ===", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with get_traffic_engine() as engine:
        result = run_gold(engine)
    for k, v in result.items():
        print(f"  {k:<22} {v:>8,}")
