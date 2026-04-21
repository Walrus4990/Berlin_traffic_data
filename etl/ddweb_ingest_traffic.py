from __future__ import annotations
# INGEST TRAFFIC SENSOR DATA
    # following functions:
    #note: - private '_name' only to be used for this ingest purpose
    # 1. define all sorts of variables needed for the inputs matrix and the payload to the portal
    # 2. Single downloader for all data chunks for one mission_id
    # 3. Orchestrator (loops over all missions)

import time
import logging
import calendar
from pathlib import Path
from datetime import datetime, timezone
import pytz

import requests
import os
from etl.ddweb_auth import DDWebAuth
from utils.date import parse_date

logger = logging.getLogger(__name__)

BASE_URL = "https://ddweb.topo-web.com"
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "./data/raw/")) #check if teh ref to data/ rather than data/raw is oK

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

def _get_month_chunks(from_date: datetime, to_date: datetime) -> list[tuple[datetime, datetime]]:
    chunks = []
    cursor = from_date

    while cursor <= to_date:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]        # picks the last day of any month
        chunk_end = min(datetime(cursor.year, cursor.month, last_day, tzinfo=from_date.tzinfo), to_date) # picks whatever is sooner, the last day of the month  or mission end
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

def _download_excel(
    session: requests.Session,
    file_guid: str,
    mission_id: int,
    chunk_start: datetime,
    chunk_end: datetime,) -> Path:

    response = session.get(
        f"{BASE_URL}/AnalysisX/DownloadExcel",
        params={"fileGuid": file_guid, "filename": f"mission_{mission_id}.xlsx"},
    )
    response.raise_for_status()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"mission_{mission_id}_{chunk_start.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}.xlsx"
    filepath = DOWNLOAD_DIR / filename
    filepath.write_bytes(response.content)
    logger.info(f"Saved {filepath}")
    print(f"Saved {filepath}")
    return filepath


# ---  Download all monthly chunks for one mission

def download_mission(auth: DDWebAuth, mission_id: int, from_date: datetime, to_date: datetime) -> list[Path]:
    chunks = _get_month_chunks(from_date, to_date)
    mission_files = []

    for chunk_start, chunk_end in chunks:
        logger.info(f"Mission {mission_id}: downloading {chunk_start} to {chunk_end}")
        try:
            auth.ensure_authenticated()
            payload = _build_payload(mission_id, chunk_start, chunk_end)
            analysis_id = _do_analyze(auth.session, mission_id, payload)
            _get_partial_result(auth.session, analysis_id)
            file_guid, _ = _get_file_metadata(auth.session, analysis_id)
            print("Waiting 10s for portal to prepare file...")
            time.sleep(10)
            filepath = _download_excel(auth.session, file_guid, mission_id, chunk_start, chunk_end)
            mission_files.append(filepath)
        except Exception as e:
            logger.error(f"Mission {mission_id} chunk {chunk_start}–{chunk_end} failed: {e}")
            continue
        finally:
            time.sleep(20)      #ensure requesst come at human scale

    return mission_files


# --- Loop over all missions in DataFrame

def complete_download(auth: DDWebAuth, missions_df) -> None:

    today = datetime.now(tz=timezone.utc).astimezone(pytz.timezone("Europe/Berlin"))

    for _, row in missions_df.iterrows():
        mission_id = row["Id"]
        from_date = parse_date(row["FromDate"])
        to_date = min(parse_date(row["ToDate"]), today)

        try:
            download_mission(auth, mission_id, from_date, to_date)
        except Exception as e:
            logger.error(f"Mission {mission_id} aborted: {e}")
            # Continue to next mission rather than killing the whole run
            continue
