import os
import json
from minio import Minio
import io
from dotenv import load_dotenv

load_dotenv()

# helper function to connect to MinIO bucket
MINIO_CLIENT = Minio(
    os.getenv("MINIO_ENDPOINT_LOCAL") or os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False
)
MINIO_BUCKET = os.getenv("MINIO_BUCKET")


# function to help read and write to a tracker file that ensures we do not duplicate download to MinIO

TRACKER_KEY = "download_tracker.json"

def read_tracker() -> dict:
    """Read download tracker from MinIO. Returns empty dict if not found."""
    try:
        response = MINIO_CLIENT.get_object(MINIO_BUCKET, TRACKER_KEY)
        return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}

def write_tracker(tracker: dict) -> None:
    """Write download tracker back to MinIO."""
    data = json.dumps(tracker, indent=2, default=str).encode("utf-8")
    MINIO_CLIENT.put_object(
        MINIO_BUCKET,
        TRACKER_KEY,
        io.BytesIO(data),
        length=len(data),
        content_type="application/json"
    )
