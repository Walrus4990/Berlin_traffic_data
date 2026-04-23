"""
gold_data_layer.py — Gold layer aggregation
=============================================
Reads from silver.traffic, applies hourly aggregation via SQL, and writes to
gold.traffic in PostgreSQL.

All aggregation happens inside the database — no full-table load into Python.
Only the aggregated result (~few thousand rows) is fetched for integrity checks.

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

INT_COLS = ["stunde", "kfz", "pkw", "lkw", "lfw", "krad", "fahrrad"]
FLOAT_COLS = [
    "v_kfz",
    "v_pkw",
    "v_lkw",
    "v85",
    "latitude",
    "longitude",
    "modal_share_pkw",
    "modal_share_fahrrad",
    "modal_share_lkw",
    "modal_share_krad",
]

# Motorised vehicle classes: 2, 3, 5, 7, 8, 9, 10, 11
# V85 excludes krad (10) and fahrrad (230), requires >= 5 clean rows
_AGGREGATE_SQL = text("""
    WITH agg AS (
        SELECT
            datum::date                          AS datum,
            stunde::int                          AS stunde,
            device_id                            AS geraet_id,
            COALESCE(location_title, 'unknown')  AS standort,
            MIN(lat)                             AS latitude,
            MIN(lon)                             AS longitude,

            -- vehicle counts (all rows, including flagged)
            COUNT(*) FILTER (WHERE vehicle_class::int IN (2,3,5,7,8,9,10,11)) AS kfz,
            COUNT(*) FILTER (WHERE vehicle_class::int = 7)   AS pkw,
            COUNT(*) FILTER (WHERE vehicle_class::int = 3)   AS lkw,
            COUNT(*) FILTER (WHERE vehicle_class::int = 11)  AS lfw,
            COUNT(*) FILTER (WHERE vehicle_class::int = 10)  AS krad,
            COUNT(*) FILTER (WHERE vehicle_class::int = 230) AS fahrrad,

            -- average speeds (clean rows only)
            AVG(speed_entry) FILTER (WHERE vehicle_class::int IN (2,3,5,7,8,9,10,11) AND NOT any_flag AND NOT flag_speed_delta) AS v_kfz,
            AVG(speed_entry) FILTER (WHERE vehicle_class::int = 7  AND NOT any_flag AND NOT flag_speed_delta) AS v_pkw,
            AVG(speed_entry) FILTER (WHERE vehicle_class::int = 3  AND NOT any_flag AND NOT flag_speed_delta) AS v_lkw,

            -- V85: 85th-percentile speed, clean rows only, excluding krad+fahrrad, NULL if < 5 samples.
            -- The CASE inside ORDER BY turns ineligible rows into NULL; percentile_cont skips NULLs.
            CASE
                WHEN COUNT(*) FILTER (WHERE vehicle_class::int NOT IN (10, 230) AND NOT any_flag AND NOT flag_speed_delta) >= 5
                THEN ROUND(CAST(
                    percentile_cont(0.85) WITHIN GROUP (
                        ORDER BY CASE
                            WHEN vehicle_class::int NOT IN (10, 230) AND NOT any_flag AND NOT flag_speed_delta
                            THEN speed_entry ELSE NULL
                        END
                    ) AS numeric
                ), 2)
                ELSE NULL
            END AS v85

        FROM silver.traffic
        GROUP BY datum::date, stunde::int, device_id, COALESCE(location_title, 'unknown')
    )

    SELECT
        datum,
        datum::text                                             AS datum_iso,
        stunde,
        geraet_id,
        standort,
        latitude,
        longitude,
        kfz, pkw, lkw, lfw, krad, fahrrad,
        v_kfz, v_pkw, v_lkw, v85,
        ROUND(100.0 * pkw     / NULLIF(kfz + fahrrad, 0), 1)  AS modal_share_pkw,
        ROUND(100.0 * fahrrad / NULLIF(kfz + fahrrad, 0), 1)  AS modal_share_fahrrad,
        ROUND(100.0 * lkw     / NULLIF(kfz + fahrrad, 0), 1)  AS modal_share_lkw,
        ROUND(100.0 * krad    / NULLIF(kfz + fahrrad, 0), 1)  AS modal_share_krad
    FROM agg
    ORDER BY datum, stunde, geraet_id, standort
""")


def _enforce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _check_gold_hourly(df: pd.DataFrame, n_input: int) -> None:
    """Run post-aggregation checks."""
    checks_passed = 0

    gold_key = ["geraet_id", "standort", "datum", "stunde"]
    dup_keys = df.duplicated(subset=gold_key, keep=False)
    if dup_keys.any():
        raise AssertionError(
            f"{dup_keys.sum()} rows in gold.traffic share the same "
            f"({', '.join(gold_key)}) key"
        )
    logger.info("Check 1: No duplicate (%s) keys.", ", ".join(gold_key))
    checks_passed += 1

    off_stunde = df["stunde"].dropna()
    off_stunde = off_stunde[(off_stunde < 0) | (off_stunde > 23)]
    assert len(off_stunde) == 0, f"stunde values outside 0–23: {off_stunde.unique()}"
    logger.info("Check 2: All stunde values are 0–23.")
    checks_passed += 1

    assert (
        len(df) <= n_input
    ), f"gold.traffic has more rows ({len(df)}) than silver.traffic input ({n_input})"
    logger.info("Check 3: Row count consistent.")
    checks_passed += 1

    logger.info("All %d/3 post-aggregation checks passed.", checks_passed)


def run_gold(engine: Engine) -> dict:
    """
    Full gold aggregation run: aggregates silver.traffic entirely in SQL and writes to gold.traffic.
    No full-table load — only the aggregated result is fetched into Python.
    """
    n_silver = pd.read_sql("SELECT COUNT(*) FROM silver.traffic", engine).iloc[0, 0]
    logger.info("silver.traffic has %d rows.", n_silver)

    if n_silver == 0:
        logger.warning("silver.traffic is empty — nothing to aggregate.")
        return {"rows_traffic": 0}

    df_hourly = pd.read_sql(_AGGREGATE_SQL, engine)
    logger.info("Aggregated to %d gold rows.", len(df_hourly))

    df_hourly = _enforce_dtypes(df_hourly)
    _check_gold_hourly(df_hourly, n_input=n_silver)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE gold.traffic"))
    df_hourly.to_sql("traffic", engine, schema="gold", if_exists="append", index=False)
    logger.info("Wrote %d rows to gold.traffic.", len(df_hourly))

    return {"rows_traffic": len(df_hourly)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with get_traffic_engine() as engine:
        result = run_gold(engine)
    for k, v in result.items():
        print(f"  {k:<22} {v:>8,}")
