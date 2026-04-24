# push final tables
# reads from gold.*, exports to MinIO, eventually handles open data portal

import io
from datetime import date
import pandas as pd
import logging

from utils.db import get_traffic_engine
from utils.minio import MINIO_CLIENT, MINIO_BUCKET

logger = logging.getLogger(__name__)

def publish_gold(**kwargs):
    """Upload gold.traffic to MinIO as Parquet """

    with get_traffic_engine() as engine:
        df = pd.read_sql("SELECT * FROM gold.traffic ORDER BY datum, stunde, geraet_id", engine)

    if df.empty:
        logger.warning("gold.traffic is empty — nothing to publish.")
        return

    if not MINIO_CLIENT.bucket_exists(MINIO_BUCKET):
        MINIO_CLIENT.make_bucket(MINIO_BUCKET)

    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    payload = buf.getvalue()

    today = date.today().isoformat()
    for key in (f"gold/traffic_{today}.parquet", "gold/traffic_latest.parquet"):
        MINIO_CLIENT.put_object(MINIO_BUCKET, key, io.BytesIO(payload), length=len(payload),
                                content_type="application/octet-stream")

    logger.info("Exported %d gold rows to MinIO (gold/traffic_%s.parquet)", len(df), today)
