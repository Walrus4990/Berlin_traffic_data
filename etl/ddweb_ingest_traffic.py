# INGEST TRAFFIC SENSOR DATA
    # following functions:
    #note: - private '_name' only to be used for this ingest purpose
    # 1. define all sorts of variables needed for the inputs matrix and the payload to the portal
    # 2. Single downloader for all data chunks for one mission_id
    # 3. Orchestrator (loops over all missions)

from __future__ import annotations
import time
import logging
import calendar
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytz
from minio import Minio
import io
import requests
import os
import pandas as pd

from etl.ddweb_auth import DDWebAuth
from etl.ddweb_ingest_ref import fetch_missions
from utils.date import parse_date
from utils.schema import TRAFFIC_COLS_DROP, TRAFFIC_RENAME
from utils.minio import MINIO_CLIENT, MINIO_BUCKET, read_tracker


logger = logging.getLogger(__name__)

BASE_URL = "https://ddweb.topo-web.com"

ANALYSIS_MODEL = 6

TRAFFIC_PAYLOAD_FIELDS = {
    "EntryExitVelocity": "True",
    "CarClassificationNew": "gkf",
    "TrafficLane": "1",
    "VelocityIntervalId": "2279",
    "TimeIntervalId": "763",
    "Interval": "3",
    "AudioTreshold": "60",
    "FilterName": "",
    "SaveFilter": "false",
}

VC_FIELDS = [
    "VC_Lkw","VC_Kfz","VC_Pkw","VC_Sgv","VC_PkwAe","VC_SV","VC_PkwG",
    "VC_LkwK","VC_LkwAe","VC_Lvm","VC_PkwA","VC_Bus","VC_LkwA",
    "VC_dkPkwA","VC_Lfw","VC_dkLfw","VC_SattelKfz","VC_dkLfwA",
    "VC_Krad","VC_KfzTv","VC_Fahrrad","VC_dkLkw","VC_dkLkwA",
    "VC_dkSattelKfz","VC_dkBus","VC_suft","VC_cabus","VC_siuta",
    "VC_suta","VC_subv","VC_sufa","VC_suv","VC_tufol","VC_tufa",
    "VC_tusa","VC_thufa","VC_combstv","VC_thusa","VC_thusoa",
    "VC_combmtv","VC_trsi","VC_combv","VC_bike","VC_dkKrad",
    "VC_mcyc","VC_dkPkw","VC_vph","VC_nkKfz","VC_pcar","VC_carsi",
    "VC_taftv","VC_umv","VC_cakfz"
]

VELOCITY_GROUPS = 6
WEEKDAYS = 7


# --- Chunking

def get_chunk_start(mission_id: int, from_date: datetime, tracker: dict) -> datetime:
    entry = tracker.get(str(mission_id))
    if entry and entry.get("last_downloaded_to"):
        last = datetime.strptime(entry["last_downloaded_to"], "%Y-%m-%d")
        last = pytz.timezone("Europe/Berlin").localize(last)
        return last + timedelta(days=1)
    return from_date


def get_chunks(from_date: datetime, to_date: datetime) -> list[tuple[datetime, datetime]]:
    if (to_date - from_date).days <= 31: #if the dowload timeframe is smaller than the portal limit,no chunking
        return [(from_date, to_date)]

    chunks = []
    cursor = from_date

    while cursor <= to_date:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]        # picks the last day of any month
        chunk_end = min(datetime(cursor.year, cursor.month, last_day, 23, 59, 59, tzinfo=from_date.tzinfo), to_date) # picks whatever is sooner, the last day of the month  or mission end
        chunks.append((cursor, chunk_end))

        if cursor.month == 12:
            cursor = datetime(cursor.year + 1, 1, 1, tzinfo=from_date.tzinfo)            # in December move to first month of next year
        else:
            cursor = datetime(cursor.year, cursor.month + 1, 1, tzinfo=from_date.tzinfo) # Move to first day of next month

    return chunks


# --- Build payload to pass parametres to DDWEB portal

def _build_payload(mission_id: int, chunk_start: datetime, chunk_end: datetime) -> list[tuple]:

    payload = [
        ("OrderId", str(mission_id)),         #confusingly the website uses OrderId sometimes for mission_id
        ("AnalysisModel", str(ANALYSIS_MODEL)),
    ]

    for key, value in TRAFFIC_PAYLOAD_FIELDS.items():
        payload.append((key, value))

    for key in VC_FIELDS:
        payload.append((key, "true"))
        payload.append((key, "false"))

    for i in range(VELOCITY_GROUPS):
        payload.append((f"VelocityGroup[{i}]", "true"))
        payload.append((f"VelocityGroup[{i}]", "false"))

    for i in range(WEEKDAYS):
        payload.append((f"Weekday[{i}]", "true"))
        payload.append((f"Weekday[{i}]", "false"))

    payload.append(("FromDate", chunk_start.strftime("%d.%m.%Y %H:%M")))
    payload.append(("ToDate", chunk_end.strftime("%d.%m.%Y %H:%M")))

    return payload

# --- 4-step download flow ---
#  Step 1: trigger analysis, return analysisresultid.

def _do_analyze(session: requests.Session, mission_id: int, payload: list) -> int:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/AnalysisX/Index?missionid={mission_id}&filterId=0",
    }
    response = session.post(f"{BASE_URL}/AnalysisX/DoAnalyze", data=payload, headers=headers)
    response.raise_for_status()
    body = response.json()
    if not body.get("Success"):
        raise RuntimeError(f"DoAnalyze failed for mission {mission_id}: {body}")
    return body["theModelId"]


# Step 2: poll until the server-side analysis is ready.
# The portal prepares the result asynchronously — we must wait before
# requesting the file, otherwise we get an empty Excel.

def _get_partial_result(session: requests.Session, analysis_id: int,
                        max_attempts: int = 10, wait_seconds: float = 3.0) -> None:
    for attempt in range(1, max_attempts + 1):
        timestmp = int(time.time() * 1000)
        response = session.get(
            f"{BASE_URL}/AnalysisX/GetPartialAnalysisResult",
            params={"analysisresultid": analysis_id, "_": timestmp},
        )
        response.raise_for_status()

        try:
            body = response.json()
            # Portal returns IsReady=true (or equivalent truthy key) when done.
            if body.get("IsReady") or body.get("isReady") or body.get("Ready"):
                return
        except Exception:
            # Non-JSON response — treat as ready (older portal behaviour)
            return

        logger.debug("Analysis %d not ready yet (attempt %d/%d) — waiting %.0fs",
                     analysis_id, attempt, max_attempts, wait_seconds)
        time.sleep(wait_seconds)

    # If we exhausted retries, continue anyway — worst case is an empty file.
    logger.warning("Analysis %d: readiness check timed out after %d attempts.",
                   analysis_id, max_attempts)


# Step 3: get FileGuid and FileName.

def _get_file_metadata(session: requests.Session, analysis_id: int) -> tuple[str, str]:

    timestmp = int(time.time() * 1000)  #server wants a different timestamp each time
    response = session.get(
        f"{BASE_URL}/AnalysisX/ExportAnalysisExcelJson",
        params={"id": ANALYSIS_MODEL, "analysisresultid": analysis_id, "_": timestmp},
    )
    response.raise_for_status()
    body = response.json()
    return body["FileGuid"], body["FileName"]


# Step 4: download binary xlsx, save with our own filename

def _download_into_parquet(
    session: requests.Session,
    file_guid: str,
    mission_id: int,
    chunk_start: datetime,
    chunk_end: datetime,) -> str | None:

    response = session.get(
        f"{BASE_URL}/AnalysisX/DownloadExcel",
        params={"fileGuid": file_guid, "filename": f"mission_{mission_id}.xlsx"},
    )
    response.raise_for_status()

    filename = f"mission_{mission_id}_{chunk_start.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}.parquet"

    # Convert xlsx bytes → DataFrame → parquet bytes in memory
    df = pd.read_excel(io.BytesIO(response.content))
    if df.empty:
        logger.warning("No data for mission %s chunk %s-%s, skipping upload", mission_id, chunk_start, chunk_end)
        return None

    df = df.drop(columns=TRAFFIC_COLS_DROP, errors="ignore")
    df = df.rename(columns=TRAFFIC_RENAME)
    df["device_id"] = df["device_id"].astype(str).str.strip()

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    parquet_bytes = buffer.getvalue()

    # Upload to MinIO
    MINIO_CLIENT.put_object(
        MINIO_BUCKET,
        filename,
        io.BytesIO(parquet_bytes),
        length=len(parquet_bytes),
        content_type="application/octet-stream"
    )
    logger.info(f"Uploaded {filename} to MinIO bucket {MINIO_BUCKET}")
    return filename


# ---  Download all monthly chunks for one mission

def download_mission(
    auth: DDWebAuth,
    mission_id: int,
    from_date: datetime,
    to_date: datetime,
    tracker:dict,
) -> list:
    """
    download_mission() determines the outer boundary of the download: chunk_start to chunk_end
    Passes both to _get_chunks() which decides: ≤31 days → one chunk, >31 days → monthly chunks
    Loop runs over whatever _get_chunks() returns
    """

    chunk_start = get_chunk_start(mission_id, from_date, tracker)
    today = datetime.now(tz=pytz.timezone("Europe/Berlin"))
    chunk_end = min(to_date, today)

    chunks = get_chunks(chunk_start, chunk_end)
    mission_files = []

    for chunk_start, chunk_end in chunks:
        logger.info("Mission %s: downloading %s to %s", mission_id, chunk_start.date(), chunk_end.date())
        try:
            auth.ensure_authenticated()
            payload = _build_payload(mission_id, chunk_start, chunk_end)
            analysis_id = _do_analyze(auth.session, mission_id, payload)
            _get_partial_result(auth.session, analysis_id)
            file_guid, _ = _get_file_metadata(auth.session, analysis_id)
            print("Waiting 10s for portal to prepare file...")
            time.sleep(10)
            filepath = _download_into_parquet(auth.session, file_guid, mission_id, chunk_start, chunk_end)
            if filepath:
                mission_files.append(filepath)

        except Exception as e:
            logger.error("Mission %s chunk %s-%s failed: %s", mission_id, chunk_start.date(), chunk_end.date(), e)
            continue
        finally:
            time.sleep(20)      #ensure requesst come at human scale

    return mission_files


# --- Loop over all missions for initial complete download

def complete_download() -> None:


    today = datetime.now(tz=pytz.timezone("Europe/Berlin"))
    tracker = read_tracker()

    auth = DDWebAuth()
    auth.ensure_authenticated()
    missions_df = fetch_missions(auth)

    logger.info("Initial download: %s missions total", len(missions_df))

    for _, row in missions_df.iterrows():
        mission_id = row["Id"]
        from_date = parse_date(row["FromDate"])
        to_date = min(parse_date(row["ToDate"]), today)

        try:
            download_mission(auth, mission_id, from_date, to_date, tracker)
        except Exception as e:
            logger.error("Mission %s aborted: %s", mission_id, e)
            # Continue to next mission rather than killing the whole run
            continue

# --- Loop over active missions only fro weekly download

def weekly_download() -> None:

    today = datetime.now(tz=pytz.timezone("Europe/Berlin"))
    tracker = read_tracker()

    auth = DDWebAuth()
    auth.ensure_authenticated()
    missions_df = fetch_missions(auth)

    active_missions = missions_df[
        missions_df["ToDate"].apply(lambda x: parse_date(x) > today)
    ]
    active_missions = active_missions[active_missions["Id"].isin([89637, 89639])]  # TEMP: test only

    logger.info("Weekly download: %s active missions", len(active_missions))

    for _, row in active_missions.iterrows():
        mission_id = row["Id"]
        from_date = parse_date(row["FromDate"])
        to_date = parse_date(row["ToDate"])

        try:
            download_mission(auth, mission_id, from_date, to_date, tracker)
        except Exception as e:
            logger.error("Mission %s aborted: %s", mission_id, e)
            continue
