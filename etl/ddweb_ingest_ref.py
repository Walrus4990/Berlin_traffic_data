# INGEST MISSION AND LOCATION REFERENCE TABLES

from etl.ddweb_auth import DDWebAuth
import pandas as pd
import logging
from utils.db import get_traffic_engine, save

logger = logging.getLogger(__name__)        # python error logging integrates with Airflow
auth = DDWebAuth()

###### INGEST MISSIONS into a dataframe

MISSIONS_URL = "https://ddweb.topo-web.com/Mission/ReadDataAjax"

MISSION_FIELDS = [          #fields to scrape content from
    "Id", "Created", "FromDate", "ToDate",
    "Description", "LocationTitle", "City",
    "Street", "StreetNumber", "Zipcode",
    "DeviceNumber", "DeviceType",
]

PAYLOAD = {             # info ddweb protal expects, also set rumber of rows to maximum
    "sort": "LocationTitle-asc",
        "page": 1,      #number of rows displayed
    "group": "",
    "filter": "",
}

def fetch_missions(auth: DDWebAuth) -> pd.DataFrame:

    auth.ensure_authenticated()
    try:
        response = auth.session.post(MISSIONS_URL, data=PAYLOAD)
        response.raise_for_status()
        data = response.json()["Data"]
        df_missions = pd.DataFrame(data)[MISSION_FIELDS]
        logger.info(f"fetch_missions: retrieved {len(df_missions)} rows")   #logs success in Airflow
        return df_missions
    except Exception as e:
        logger.error (f"fetch_missions failed: {e}")
        raise           #raises error to Airflow which marks task as failed


###### INGEST LOCATIONS into a dataframe

LOCATIONS_URL = "https://ddweb.topo-web.com/Location/ReadDataAjax"

LOCATION_FIELDS = [
    "Id", "Created", "Description", "LocationTitle",
    "Street", "StreetNumber", "Zipcode", "City",
    "DrivingDirection", "OppositeDirection",
    "PosUserLat", "PosUserLng",
]

def fetch_locations(auth: DDWebAuth) -> pd.DataFrame:
    try:
        auth.ensure_authenticated()
        response = auth.session.post(LOCATIONS_URL, data=PAYLOAD)
        response.raise_for_status()
        data = response.json()["Data"]
        df_locations = pd.DataFrame(data)[LOCATION_FIELDS]
        logger.info(f"fetch_locations: retrieved {len(df_locations)} rows")
        return df_locations
    except Exception as e:
        logger.error (f"fetch_locations failed: {e}")
        raise

def fetch_and_save_locations(auth: DDWebAuth) -> None:
    df_locations = fetch_locations(auth)
    with get_traffic_engine() as engine:
        save(df_locations, "location", "bronze", engine)
