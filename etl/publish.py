import io
from datetime import date
import pandas as pd
import logging

from utils.db import get_traffic_engine
from utils.minio import get_minio_client, ensure_bucket, MINIO_BUCKET

logger = logging.getLogger(__name__)

COLUMN_TRANSLATIONS = {
    "mission_id":                   "Auftrag_Nr",
    "device_id":                    "Geräte_Nr",
    "start_date":                   "Startdatum",
    "end_date":                     "Enddatum",
    "date":                         "Datum",
    "hour":                         "Stunde",
    "day_of_week_num":              "Wochentag_Nr",
    "day_of_week_name":             "Wochentag",
    "street":                       "Straße",
    "street_number":                "Hausnummer",
    "zipcode":                      "PLZ",
    "city":                         "Bezirk",
    "location_description":         "Standortbeschreibung",
    "lat":                          "Breitengrad",
    "lon":                          "Längengrad",
    "motorised":                    "Motorisiert_gesamt",
    "car":                          "Auto",
    "bicycle":                      "Fahrrad",
    "delivery_van":                 "Lieferwagen",
    "motorbike":                    "Motorrad",
    "lorry":                        "LKW",
    "other_motorised_vehicle":      "Sonstige_motorisiert",
    "v_all_motorised":              "Geschw_motorisiert_gesamt",
    "v_car":                        "Geschw_Auto",
    "v_delivery_van":               "Geschw_Lieferwagen",
    "v_motorbike":                  "Geschw_Motorrad",
    "v_lorry":                      "Geschw_LKW",
    "v_other":                      "Geschw_Sonstige",
    "v85":                          "V85_motorisiert",
    "modal_share_car":              "Modalanteil_Auto",
    "modal_share_bicycle":          "Modalanteil_Fahrrad",
    "modal_share_delivery_van":     "Modalanteil_Lieferwagen",
    "modal_share_motorbike":        "Modalanteil_Motorrad",
    "modal_share_lorry":            "Modalanteil_LKW",
    "is_pair":                      "Hat_Gegenüber",
    "paired_mission_id":            "Gegenüber_Auftrag_ID",
    "driving_direction":            "Fahrtrichtung",
    "opposite_direction":           "Gegenrichtung",
    "gold_processed_at":            "Verarbeitet_am",
}

def publish_csv() -> str:
    """Export gold.export to a dated CSV in MinIO with German column names. Returns the filename."""
    engine = get_traffic_engine()
    logger.info("Reading gold.export from Postgres")

    df = pd.read_sql("SELECT * FROM gold.export ORDER BY date, hour", engine)
    logger.info("Read %d rows from gold.export", len(df))

    df = df.rename(columns=COLUMN_TRANSLATIONS)

    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig") #utf-8-sig ensures Umlaut correctly rendered
    buf.seek(0)

    filename = f"TS_Verkehrsdaten_{date.today().isoformat()}.csv"

    ensure_bucket()
    get_minio_client().put_object(
        MINIO_BUCKET,
        filename,
        buf,
        length=buf.getbuffer().nbytes,
        content_type="text/csv",
    )
    logger.info("Exported %d rows to MinIO: %s", len(df), filename)
    return filename
