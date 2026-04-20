"""
preview_gold.py — Visual inspection of gold_data_layer outputs
==============================================================
Shows what each gold table would contain after aggregation,
without requiring a running database or Docker.

Builds the full silver pipeline from local Excel files, then runs the
gold aggregation functions on the resulting DataFrame.

Inputs (all local files — no API calls, no DB):
  bronze.traffic  ← DDWEB_Downloads/DDweb_VI_Rohdaten_*.xlsx
  bronze.mission  ← DDWEB_Downloads/DDweb_Auftrag_*.xlsx
  bronze.location ← DDWEB_Downloads/DDweb_Standort_*.xlsx

Usage (from project root):
    python tests/preview_gold.py
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from etl.silver_data_layer import (
    ACTIVE_SENTINELS,
    build_mission,
    enrich_with_location,
    step_consolidate_flags,
    step_flag_ambiguous_location,
    step_flag_duplicates,
    step_flag_outside_window,
    step_flag_speed,
    step_flag_speed_ratio,
    step_flag_unclassifiable,
    step_flag_unknown_device,
    step_parse_timestamps,
)
from etl.gold_data_layer import build_hourly, _check_gold_hourly

DATA_DIR = ROOT / "data" / "DDWEB_Downloads"


# ── Display helpers ───────────────────────────────────────────────────────────

def _section(title: str) -> None:
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}")


def _show(df: pd.DataFrame, n: int = 5, label: str = "") -> None:
    tag = f" ({label})" if label else ""
    print(f"\nShape{tag}: {df.shape[0]:,} rows × {df.shape[1]} cols")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_colwidth", 28)
    if not df.empty:
        print(df.head(n).to_string(index=False))


# ── Load bronze inputs from local Excel files ─────────────────────────────────

def _load_bronze_traffic() -> pd.DataFrame:
    TRAFFIC_COLS_DROP = ["Schall (dB)", "Abstand (cm)", "Fahrspur",
                         "Geschwindigkeit (km/h)", "Richtung"]
    TRAFFIC_RENAME = {
        "Geräte-ID":                       "device_id",
        "Datum":                           "date_raw",
        "Eintrittsgeschwindigkeit (km/h)": "speed_entry",
        "Austrittsgeschwindigkeit (km/h)": "speed_exit",
        "Länge (dm)":                      "length_dm",
        "Klasse":                          "vehicle_class",
        "Fahrzeugklassen-Bezeichnung":     "vehicle_class_label",
    }
    files = sorted(DATA_DIR.glob("DDweb_VI_Rohdaten_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No DDweb_VI_Rohdaten_*.xlsx found in {DATA_DIR}")
    frames = []
    for f in files:
        df = pd.read_excel(f, dtype={"Geräte-ID": str})
        if df.empty:
            continue
        df["source_file"] = f.name
        df = df.drop(columns=TRAFFIC_COLS_DROP, errors="ignore")
        df = df.rename(columns=TRAFFIC_RENAME)
        df["device_id"] = df["device_id"].astype(str).str.strip()
        df["ingested_at"] = pd.Timestamp.now()
        frames.append(df)
        print(f"  traffic: {f.name}  →  {len(df):,} rows")
    return pd.concat(frames, ignore_index=True)


def _load_bronze_mission() -> pd.DataFrame:
    RENAME = {
        "Geräte-ID":     "device_id",
        "Startdatum":    "start_date",
        "Enddatum":      "end_date",
        "Beschreibung":  "description",
        "Gerätetyp":     "device_type",
        "Standorttitel": "location_title",
        "Stadt":         "city",
        "Erstellt":      "created_at",
    }
    files = sorted(DATA_DIR.glob("DDweb_Auftrag_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No DDweb_Auftrag_*.xlsx found in {DATA_DIR}")
    df = pd.read_excel(files[-1])
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})
    df["device_id"]  = df["device_id"].astype(str).str.strip()
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"]   = pd.to_datetime(df["end_date"],   errors="coerce")
    df["mission_id"] = range(1, len(df) + 1)
    print(f"  missions: {files[-1].name}  →  {len(df)} rows, "
          f"{df['device_id'].nunique()} unique devices")
    return df


def _load_bronze_location() -> pd.DataFrame:
    RENAME = {
        "Standorttitel":          "location_title",
        "Beschreibung":           "description",
        "Straße":                 "street",
        "Hausnummer":             "street_number",
        "Postleitzahl":           "zipcode",
        "Stadt":                  "city",
        "Fahrtrichtung":          "driving_direction",
        "Gegenrichtung":          "opposite_direction",
        "Benutzer Position Lat":  "lat",
        "Benutzer Position Long": "lon",
        "Erstellt":               "created_at",
    }
    files = sorted(DATA_DIR.glob("DDweb_Standort_*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No DDweb_Standort_*.xlsx found in {DATA_DIR}")
    df = pd.read_excel(files[-1])
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})
    for col in ("lat", "lon"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    print(f"  locations: {files[-1].name}  →  {len(df)} rows")
    return df


def _build_windows(df_mission: pd.DataFrame) -> dict:
    windows: dict = {}
    for _, row in df_mission.iterrows():
        start    = row.get("start_date")
        end      = row.get("end_date")
        start_ts = pd.Timestamp(start) if pd.notna(start) else None
        if not start_ts:
            continue
        raw_end  = pd.Timestamp(end) if pd.notna(end) else None
        end_ts   = pd.Timestamp.max if (raw_end is None or raw_end in ACTIVE_SENTINELS) else raw_end
        windows.setdefault(str(row["device_id"]), []).append((start_ts, end_ts))
    return windows


# ── Build silver DataFrame (mirrors run_silver logic, no DB) ──────────────────

def _build_silver(df_traffic: pd.DataFrame, df_mission: pd.DataFrame,
                  df_location: pd.DataFrame) -> pd.DataFrame:
    known_ids = set(df_mission["device_id"].unique())
    windows   = _build_windows(df_mission)
    df_active = build_mission(df_mission, df_location)

    df = step_parse_timestamps(df_traffic)
    df = step_flag_unknown_device(df, known_ids)
    df = step_flag_outside_window(df, windows)
    df = step_flag_ambiguous_location(df, df_active)
    df = step_flag_unclassifiable(df)
    df = step_flag_speed(df)
    df = step_flag_duplicates(df)
    df = step_flag_speed_ratio(df)
    df = step_consolidate_flags(df)
    df = enrich_with_location(df, df_active)
    df["processed_at"]  = pd.Timestamp.now()
    df["pipeline_path"] = "preview"
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nGOLD LAYER OUTPUT PREVIEW")
    print("(no database required — shows DataFrames that would be written)\n")

    # ── Load inputs ───────────────────────────────────────────────────────────
    _section("INPUTS")
    print("\nLoading bronze.traffic …")
    df_traffic = _load_bronze_traffic()
    print(f"\n  Total traffic rows loaded: {len(df_traffic):,}")

    print("\nLoading bronze.mission …")
    df_mission = _load_bronze_mission()

    print("\nLoading bronze.location …")
    df_location = _load_bronze_location()

    # ── Build silver ──────────────────────────────────────────────────────────
    _section("SILVER (intermediate — not written in this preview)")
    print("\nApplying silver cleaning and geo-enrichment …")
    df_silver = _build_silver(df_traffic, df_mission, df_location)
    print(f"\n  silver.traffic shape: {df_silver.shape[0]:,} rows × {df_silver.shape[1]} cols")
    print(f"  any_flag=True:  {df_silver['any_flag'].sum():,}  ({df_silver['any_flag'].mean()*100:.1f}%)")
    print(f"  Clean rows:     {(~df_silver['any_flag']).sum():,}")
    print(f"  flag_no_coords: {df_silver['flag_no_coords'].sum():,}")

    # ── gold.hourly ───────────────────────────────────────────────────────────
    _section("gold.hourly  ←  build_hourly(silver.traffic)")
    print("\nAggregating to hourly rows …")
    df_hourly = build_hourly(df_silver)

    print(f"\nRunning post-aggregation checks …")
    try:
        _check_gold_hourly(df_hourly, n_input=len(df_silver))
        print("  All 3 checks passed.")
    except AssertionError as e:
        print(f"  CHECK FAILED: {e}")

    print(f"\nColumns ({len(df_hourly.columns)}):")
    for col in df_hourly.columns:
        print(f"  {col:<40} {df_hourly[col].dtype}")

    _show(df_hourly, n=5, label="first 5 hourly rows")

    # Summary stats
    print(f"\nDate range:        {df_hourly['datum'].min()} → {df_hourly['datum'].max()}")
    print(f"Unique devices:    {df_hourly['geraet_id'].nunique()}")
    print(f"Unique locations:  {df_hourly['standort'].nunique()}")
    gold_key = ["geraet_id", "standort", "datum", "stunde"]
    dup_count = int(df_hourly.duplicated(subset=gold_key, keep=False).sum())
    print(f"Duplicate gold keys: {dup_count:,}")
    print(f"Hours with V85:    {df_hourly['v85'].notna().sum():,}  "
          f"({df_hourly['v85'].notna().mean()*100:.1f}%)")
    v85_valid = df_hourly["v85"].dropna()
    if len(v85_valid):
        print(f"V85 mean:          {v85_valid.mean():.1f} km/h  "
              f"(min {v85_valid.min():.1f}, max {v85_valid.max():.1f})")

    # Vehicle class breakdown (totals)
    print("\nVehicle class totals across all hours:")
    total = df_hourly["kfz"].sum() + df_hourly["fahrrad"].sum()
    class_cols = ["kfz", "pkw", "lkw", "lfw", "krad", "fahrrad"]
    for col in class_cols:
        n   = df_hourly[col].sum()
        pct = n / total * 100 if total else 0
        print(f"  {col:<22}  {n:>10,}  ({pct:.1f}%)")

    # Top slices for quick preview
    _section("Top Device Hours")
    top_hours = df_hourly.sort_values(["kfz", "fahrrad"], ascending=False).head(10)
    _show(top_hours, n=10)

    _section("Top Locations")
    df_loc = (
        df_hourly.groupby(["geraet_id", "standort"], dropna=False)
        .agg(
            total_kfz=("kfz", "sum"),
            total_fahrrad=("fahrrad", "sum"),
            avg_v_kfz=("v_kfz", "mean"),
            hours=("stunde", "count"),
        )
        .reset_index()
        .sort_values(["total_kfz", "total_fahrrad"], ascending=False)
    )
    _show(df_loc, n=10)

    _section("Hourly Profile")
    df_time = (
        df_hourly.groupby("stunde", dropna=False)
        .agg(
            total_kfz=("kfz", "sum"),
            total_fahrrad=("fahrrad", "sum"),
            avg_v_kfz=("v_kfz", "mean"),
            avg_v85=("v85", "mean"),
        )
        .reset_index()
        .sort_values("stunde")
    )
    _show(df_time, n=24)

    # ── run_gold() return value ───────────────────────────────────────────────
    _section("run_gold() return value")
    result = {
        "rows_traffic": len(df_hourly),
    }
    print()
    for k, v in result.items():
        print(f"  {k:<22} {v:>8,}")

    print("\nDone.\n")
