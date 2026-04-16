"""
preview_bronze.py — Visual inspection of bronze_data_layer outputs
===================================================================
Shows exactly what each bronze table would contain after ingestion,
without requiring a running database or Docker.

Inputs:
  - Mock missions / locations DataFrames (matching fetch_missions() /
    fetch_locations() API field names from ddweb_ingest_ref.py)
  - Real traffic file(s) from data/raw/mission_*.xlsx

Usage (run from project root):
    python tests/preview_bronze.py
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent

# ── Constants inlined from bronze_data_layer.py ───────────────────────────────
# Kept in sync with etl/bronze_data_layer.py — no SQLAlchemy import needed here.

DOWNLOAD_DIR = ROOT / "data" / "DDWEB_Downloads"

MISSION_RENAME = {
    "Id":            "mission_id",
    "Created":       "created_at",
    "FromDate":      "start_date",
    "ToDate":        "end_date",
    "Description":   "description",
    "LocationTitle": "location_title",
    "City":          "city",
    "Street":        "street",
    "StreetNumber":  "street_number",
    "Zipcode":       "zipcode",
    "DeviceNumber":  "device_id",
    "DeviceType":    "device_type",
}

LOCATION_RENAME = {
    "Id":                "location_id",
    "Created":           "created_at",
    "Description":       "description",
    "LocationTitle":     "location_title",
    "Street":            "street",
    "StreetNumber":      "street_number",
    "Zipcode":           "zipcode",
    "City":              "city",
    "DrivingDirection":  "driving_direction",
    "OppositeDirection": "opposite_direction",
    "PosUserLat":        "lat",
    "PosUserLng":        "lon",
}

TRAFFIC_COLS_DROP = [
    "Schall (dB)", "Abstand (cm)", "Fahrspur",
    "Geschwindigkeit (km/h)", "Richtung",
]

TRAFFIC_RENAME = {
    "Geräte-ID":                        "device_id",
    "Datum":                            "date_raw",
    "Eintrittsgeschwindigkeit (km/h)":  "speed_entry",
    "Austrittsgeschwindigkeit (km/h)":  "speed_exit",
    "Länge (dm)":                       "length_dm",
    "Klasse":                           "vehicle_class",
    "Fahrzeugklassen-Bezeichnung":      "vehicle_class_label",
}


def _load_traffic_file(fpath: Path) -> pd.DataFrame:
    """Mirrors _load_traffic_file() in bronze_data_layer.py."""
    df = pd.read_excel(fpath, dtype={"Geräte-ID": str})
    df["source_file"] = fpath.name
    df = df.drop(columns=TRAFFIC_COLS_DROP, errors="ignore")
    df = df.rename(columns=TRAFFIC_RENAME)
    df["device_id"] = df["device_id"].astype(str).str.strip()
    return df


# ── Display helpers ───────────────────────────────────────────────────────────

def _section(title: str) -> None:
    width = 70
    print(f"\n{'═' * width}")
    print(f"  {title}")
    print(f"{'═' * width}")


def _show(df: pd.DataFrame, n: int = 5) -> None:
    print(f"\nShape : {df.shape[0]} rows × {df.shape[1]} cols")
    print(f"Columns ({len(df.columns)}):")
    for col in df.columns:
        print(f"    {col:<35} {df[col].dtype}")
    print(f"\nFirst {min(n, len(df))} row(s):")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 140)
    pd.set_option("display.max_colwidth", 30)
    print(df.head(n).to_string(index=False))


# ── Mock input DataFrames ─────────────────────────────────────────────────────
#
# Column names match what fetch_missions() / fetch_locations() return from the
# portal API (see MISSION_FIELDS / LOCATION_FIELDS in ddweb_ingest_ref.py).
#
# FromDate / ToDate: the portal returns these as millisecond-epoch strings,
# e.g. "1643673600000" (handled by _parse_date in ddweb_ingest_traffic.py).
# Here we use ISO strings so pd.to_datetime() can parse them cleanly.

MOCK_MISSIONS = pd.DataFrame([
    {
        "Id": 40671,
        "Created": "2021-01-01",
        "FromDate": "2022-02-01",
        "ToDate":   "2049-01-01",   # sentinel = still active
        "Description":   "Tempelhof Hauptstraße Nord",
        "LocationTitle": "Tempelhof HS Nord",
        "City":          "Berlin",
        "Street":        "Hauptstraße",
        "StreetNumber":  "123",
        "Zipcode":       "12101",
        "DeviceNumber":  "DG_40671",
        "DeviceType":    "SENSYS",
    },
    {
        "Id": 40687,
        "Created": "2021-01-01",
        "FromDate": "2022-02-01",
        "ToDate":   "2022-12-31",   # closed mission
        "Description":   "Tempelhof Hauptstraße Süd",
        "LocationTitle": "Tempelhof HS Süd",
        "City":          "Berlin",
        "Street":        "Hauptstraße",
        "StreetNumber":  "123",
        "Zipcode":       "12101",
        "DeviceNumber":  "DG_40687",
        "DeviceType":    "SENSYS",
    },
])

MOCK_LOCATIONS = pd.DataFrame([
    {
        "Id": 1,
        "Created": "2021-01-01",
        "Description":       "Tempelhof HS Nord",
        "LocationTitle":     "Tempelhof HS Nord",
        "Street":            "Hauptstraße",
        "StreetNumber":      "123",
        "Zipcode":           "12101",
        "City":              "Berlin",
        "DrivingDirection":  "Nord → Süd",
        "OppositeDirection": "Süd → Nord",
        "PosUserLat":        "52.4567",
        "PosUserLng":        "13.3456",
    },
    {
        "Id": 2,
        "Created": "2021-01-01",
        "Description":       "Tempelhof HS Süd",
        "LocationTitle":     "Tempelhof HS Süd",
        "Street":            "Hauptstraße",
        "StreetNumber":      "123",
        "Zipcode":           "12101",
        "City":              "Berlin",
        "DrivingDirection":  "Süd → Nord",
        "OppositeDirection": "Nord → Süd",
        "PosUserLat":        "52.4560",
        "PosUserLng":        "13.3450",
    },
])


# ── Transformation previews ───────────────────────────────────────────────────
#
# Each function replicates the exact logic inside the corresponding
# ingest_*() function in bronze_data_layer.py, minus the DB write.

def preview_mission(df_missions: pd.DataFrame) -> pd.DataFrame:
    """Mirror of ingest_mission() — no DB write."""
    df = df_missions.rename(columns=MISSION_RENAME)
    df["device_id"] = df["device_id"].astype(str).str.strip()
    for col in ("start_date", "end_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["ingested_at"] = pd.Timestamp.now()
    return df


def preview_location(df_locations: pd.DataFrame) -> pd.DataFrame:
    """Mirror of ingest_location() — no DB write."""
    df = df_locations.rename(columns=LOCATION_RENAME)
    for col in ("lat", "lon"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ingested_at"] = pd.Timestamp.now()
    return df


def preview_traffic() -> pd.DataFrame | None:
    """Mirror of ingest_traffic() — reads real files from DOWNLOAD_DIR, no DB write."""
    traffic_files = sorted(DOWNLOAD_DIR.glob("DDweb_VI_Rohdaten_*.xlsx"))
    if not traffic_files:
        print(f"  ⚠  No mission_*.xlsx files found in {DOWNLOAD_DIR}")
        print(f"     Download traffic data first via ddweb_ingest_traffic.py")
        return None

    frames = []
    for fpath in traffic_files:
        df = _load_traffic_file(fpath)
        df["ingested_at"] = pd.Timestamp.now()
        frames.append(df)
        print(f"  ✓  {fpath.name}  →  {len(df)} rows")

    return pd.concat(frames, ignore_index=True)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nBRONZE LAYER OUTPUT PREVIEW")
    print("(no database required — shows DataFrames that would be written)\n")

    # ── bronze.mission ────────────────────────────────────────────────────────
    _section("bronze.mission  ←  ingest_mission(df_missions)")
    print("\nRAW INPUT (from fetch_missions()):")
    print(MOCK_MISSIONS.to_string(index=False))

    df_mission = preview_mission(MOCK_MISSIONS)
    print("\nAFTER TRANSFORMATION (written to bronze.mission):")
    _show(df_mission)

    # ── bronze.location ───────────────────────────────────────────────────────
    _section("bronze.location  ←  ingest_location(df_locations)")
    print("\nRAW INPUT (from fetch_locations()):")
    print(MOCK_LOCATIONS.to_string(index=False))

    df_location = preview_location(MOCK_LOCATIONS)
    print("\nAFTER TRANSFORMATION (written to bronze.location):")
    _show(df_location)

    # ── bronze.traffic ────────────────────────────────────────────────────────
    _section("bronze.traffic  ←  ingest_traffic()")
    print(f"\nLooking for traffic files in: {DOWNLOAD_DIR}")
    df_traffic = preview_traffic()

    if df_traffic is not None:
        print("\nAFTER TRANSFORMATION (written to bronze.traffic):")
        _show(df_traffic, n=10)

        # Show column drops explicitly
        print(f"\nDropped columns (always-zero in raw Excel):")
        for col in TRAFFIC_COLS_DROP:
            print(f"    {col}")
    else:
        print("\nSkipping bronze.traffic preview — no files found.")

    # ── run_bronze() return dict ──────────────────────────────────────────────
    _section("run_bronze() return value")
    result = {
        "new_mission_detected":  True,    # True when DB has fewer missions than incoming
        "mission_rows_added":    len(df_mission),
        "location_rows_written": len(df_location),
        "rows_ingested":         len(df_traffic) if df_traffic is not None else 0,
    }
    print()
    for k, v in result.items():
        print(f"  {k:<28} {v}")

    print("\nDone.\n")
