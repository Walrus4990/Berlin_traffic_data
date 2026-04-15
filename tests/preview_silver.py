"""
preview_silver.py — Visual inspection of silver_data_layer outputs
===================================================================
Shows what each silver table would contain after transformation,
without requiring a running database or Docker.

Inputs (all local files — no API calls, no DB):
  bronze.traffic  ← DDWEB_Downloads/DDweb_VI_Rohdaten_*.xlsx  (real traffic)
  bronze.mission  ← DDWEB_Downloads/DDweb_Auftrag_*.xlsx      (real missions)
  bronze.location ← DDWEB_Downloads/DDweb_Standort_*.xlsx     (real locations)

Usage (from project root):
    python tests/preview_silver.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Silver functions import cleanly — sqlalchemy is installed
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
    pd.set_option("display.width", 150)
    pd.set_option("display.max_colwidth", 28)
    if not df.empty:
        print(df.head(n).to_string(index=False))


def _flag_counts(df: pd.DataFrame, flags: list[str]) -> None:
    print()
    for col in flags:
        if col in df.columns:
            n = int(df[col].sum())
            pct = n / len(df) * 100 if len(df) else 0
            print(f"  {col:<40} {n:>7,}  ({pct:.1f}%)")


# ── Step 1: Load real traffic data (bronze.traffic equivalent) ────────────────

def _load_bronze_traffic() -> pd.DataFrame:
    TRAFFIC_COLS_DROP = ["Schall (dB)", "Abstand (cm)", "Fahrspur",
                         "Geschwindigkeit (km/h)", "Richtung"]
    TRAFFIC_RENAME = {
        "Geräte-ID":                       "device_id",
        "Datum":                           "datum_raw",
        "Eintrittsgeschwindigkeit (km/h)": "speed_entry",
        "Austrittsgeschwindigkeit (km/h)": "speed_exit",
        "Länge (dm)":                      "laenge_dm",
        "Klasse":                          "klasse",
        "Fahrzeugklassen-Bezeichnung":     "klasse_label",
    }
    files = sorted(DATA_DIR.glob("DDweb_VI_Rohdaten_*.xlsx"))
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


# ── Step 2: Load real mission data (bronze.mission equivalent) ────────────────

def _load_bronze_mission() -> pd.DataFrame:
    # Auftrag file column → bronze.mission column
    RENAME = {
        "Geräte-ID":   "device_id",
        "Startdatum":  "startdatum",
        "Enddatum":    "enddatum",
        "Beschreibung": "beschreibung",
        "Gerätetyp":   "geraetetyp",
        "Standorttitel": "standorttitel",
        "Stadt":       "stadt",
        "Erstellt":    "erstellt",
    }
    files = sorted(DATA_DIR.glob("DDweb_Auftrag_*.xlsx"))
    if not files:
        raise FileNotFoundError("No DDweb_Auftrag_*.xlsx found in DDWEB_Downloads")
    df = pd.read_excel(files[-1])   # most recent
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})
    df["device_id"]  = df["device_id"].astype(str).str.strip()
    df["startdatum"] = pd.to_datetime(df["startdatum"], errors="coerce")
    df["enddatum"]   = pd.to_datetime(df["enddatum"],   errors="coerce")
    df["mission_id"] = range(1, len(df) + 1)   # Auftrag export has no Id column
    print(f"  missions: {files[-1].name}  →  {len(df)} rows, "
          f"{df['device_id'].nunique()} unique devices")
    return df


# ── Step 3: Load real location data (bronze.location equivalent) ──────────────

def _load_bronze_location() -> pd.DataFrame:
    # Standort file column → bronze.location column
    RENAME = {
        "Standorttitel":          "standorttitel",
        "Beschreibung":           "beschreibung",
        "Straße":                 "strasse",
        "Hausnummer":             "hausnummer",
        "Postleitzahl":           "postleitzahl",
        "Stadt":                  "stadt",
        "Fahrtrichtung":          "fahrtrichtung",
        "Gegenrichtung":          "gegenrichtung",
        "Benutzer Position Lat":  "lat",
        "Benutzer Position Long": "lon",
        "Erstellt":               "erstellt",
    }
    files = sorted(DATA_DIR.glob("DDweb_Standort_*.xlsx"))
    if not files:
        raise FileNotFoundError("No DDweb_Standort_*.xlsx found in DDWEB_Downloads")
    df = pd.read_excel(files[-1])
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})
    for col in ("lat", "lon"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    print(f"  locations: {files[-1].name}  →  {len(df)} rows")
    return df


# ── Helper: build deployment windows dict from mission DataFrame ───────────────
# Mirrors _get_deployment_windows() in silver_data_layer.py without a DB.

def _build_windows(df_mission: pd.DataFrame) -> dict:
    windows: dict = {}
    for _, row in df_mission.iterrows():
        start = row.get("startdatum")
        end   = row.get("enddatum")
        start_ts = pd.Timestamp(start) if pd.notna(start) else None
        if not start_ts:
            continue
        raw_end = pd.Timestamp(end) if pd.notna(end) else None
        end_ts = pd.Timestamp.max if (raw_end is None or raw_end in ACTIVE_SENTINELS) else raw_end
        windows.setdefault(str(row["device_id"]), []).append((start_ts, end_ts))
    return windows


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nSILVER LAYER OUTPUT PREVIEW")
    print("(no database required — shows DataFrames that would be written)\n")

    # ── Load inputs ───────────────────────────────────────────────────────────
    _section("INPUTS")
    print("\nLoading bronze.traffic …")
    df = _load_bronze_traffic()
    print(f"\n  Total traffic rows loaded: {len(df):,}")

    print("\nLoading bronze.mission …")
    df_mission = _load_bronze_mission()

    print("\nLoading bronze.location …")
    df_location = _load_bronze_location()

    known_ids = set(df_mission["device_id"].unique())
    windows   = _build_windows(df_mission)
    print(f"\n  Known device IDs: {sorted(known_ids)}")
    print(f"  Deployment windows built: {sum(len(v) for v in windows.values())} total")

    # ── silver.active_mission ─────────────────────────────────────────────────
    _section("silver.active_mission  ←  build_mission(bronze.mission, bronze.location)")
    df_active = build_mission(df_mission, df_location)
    print(f"\nColumns ({len(df_active.columns)}): {list(df_active.columns)}")
    _show(df_active, n=5)
    no_coords = df_active["lat"].isna() | (df_active["lat"] == 0)
    print(f"\n  Rows with missing coordinates: {no_coords.sum()} of {len(df_active)}")

    # ── Cleaning steps ────────────────────────────────────────────────────────
    _section("CLEANING STEPS  (applied to bronze.traffic)")

    print("\n── Step 1: parse timestamps ─────────────────────────────")
    df = step_parse_timestamps(df)
    print(f"  Date range: {df['datum_parsed'].min()} → {df['datum_parsed'].max()}")
    print(f"  flag_unparseable_timestamp: {df['flag_unparseable_timestamp'].sum():,}")
    _show(df[["device_id", "datum_raw", "datum_parsed", "datum", "stunde", "wochentag"]], n=3)

    print("\n── Step 2: unknown device check ────────────────────────")
    df = step_flag_unknown_device(df, known_ids)
    unregistered = df.loc[df["flag_unknown_device"], "device_id"].unique()
    print(f"  flag_unknown_device: {df['flag_unknown_device'].sum():,} rows")
    if len(unregistered):
        print(f"  Unregistered device IDs: {sorted(unregistered)}")

    print("\n── Step 3: outside deployment window ───────────────────")
    df = step_flag_outside_window(df, windows)
    print(f"  flag_outside_deployment_window: {df['flag_outside_deployment_window'].sum():,} rows")

    print("\n── Step 4: ambiguous location (overlapping windows) ────")
    df = step_flag_ambiguous_location(df, df_active)
    print(f"  flag_ambiguous_location: {df['flag_ambiguous_location'].sum():,} rows")

    print("\n── Step 5: unclassifiable vehicles (Klasse 6 / 250) ───")
    df = step_flag_unclassifiable(df)
    print(f"  flag_unclassifiable: {df['flag_unclassifiable'].sum():,} rows")

    print("\n── Step 6: speed plausibility ──────────────────────────")
    df = step_flag_speed(df)
    print(f"  flag_speed_entry: {df['flag_speed_entry'].sum():,}")
    print(f"  flag_speed_exit:  {df['flag_speed_exit'].sum():,}")
    print(f"  flag_speed (either): {df['flag_speed'].sum():,}")

    print("\n── Step 7: duplicate detection ─────────────────────────")
    df = step_flag_duplicates(df)
    print(f"  flag_duplicate: {df['flag_duplicate'].sum():,} rows")

    print("\n── Step 8: entry/exit speed ratio (>{} x) ─────────────".format(2.5))
    df = step_flag_speed_ratio(df)
    print(f"  flag_speed_delta: {df['flag_speed_delta'].sum():,} rows")

    print("\n── Step 9: consolidate all flags ───────────────────────")
    df = step_consolidate_flags(df)
    print(f"  Total rows:   {len(df):,}")
    print(f"  any_flag=True: {df['any_flag'].sum():,}  ({df['any_flag'].mean()*100:.1f}%)")
    print(f"  Clean rows:    {(~df['any_flag']).sum():,}")

    # ── silver.traffic ────────────────────────────────────────────────────────
    _section("silver.traffic  ←  enrich_with_location() + flag consolidation")
    print("\nRunning geo-enrichment (time-windowed join on device_id) …")
    df_silver = enrich_with_location(df, df_active)
    df_silver["processed_at"]  = pd.Timestamp.now()
    df_silver["pipeline_path"] = "full"

    print(f"\nShape: {df_silver.shape[0]:,} rows × {df_silver.shape[1]} cols")
    print(f"\nColumns ({len(df_silver.columns)}):")
    for col in df_silver.columns:
        print(f"  {col:<40} {df_silver[col].dtype}")

    print("\nSample rows (geo-enriched, any_flag=False):")
    clean = df_silver[~df_silver["any_flag"]]
    _show(clean[["device_id", "datum_parsed", "klasse_label", "speed_entry",
                 "speed_exit", "standorttitel", "lat", "lon", "flag_no_coords"]], n=5)

    print("\nFlag summary on silver.traffic:")
    _flag_counts(df_silver, [
        "flag_unparseable_timestamp",
        "flag_unknown_device",
        "flag_outside_deployment_window",
        "flag_ambiguous_location",
        "flag_unclassifiable",
        "flag_speed",
        "flag_duplicate",
        "flag_speed_delta",
        "flag_no_coords",
        "any_flag",
    ])

    # ── QA report (mirrors run_silver return value) ───────────────────────────
    _section("run_silver() QA return value")
    qa = {
        "rows_processed":            len(df_silver),
        "unparseable_timestamp":     int(df_silver["flag_unparseable_timestamp"].sum()),
        "unknown_device":            int(df_silver["flag_unknown_device"].sum()),
        "outside_deployment_window": int(df_silver["flag_outside_deployment_window"].sum()),
        "ambiguous_location":        int(df_silver["flag_ambiguous_location"].sum()),
        "unclassifiable":            int(df_silver["flag_unclassifiable"].sum()),
        "implausible_speed":         int(df_silver["flag_speed"].sum()),
        "duplicates":                int(df_silver["flag_duplicate"].sum()),
        "large_speed_ratio":         int(df_silver["flag_speed_delta"].sum()),
        "no_coords":                 int(df_silver["flag_no_coords"].sum()),
        "total_flagged":             int(df_silver["any_flag"].sum()),
        "total_clean":               int((~df_silver["any_flag"]).sum()),
    }
    print()
    for k, v in qa.items():
        print(f"  {k:<35} {v:>8,}")

    print("\nDone.\n")
