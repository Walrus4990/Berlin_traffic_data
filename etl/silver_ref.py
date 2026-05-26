"""
Reads from bronze PostgreSQL location adn mission tables, merges them,
applies the full cleaning routine in pandas.
Tables written:
silver_ref_mission_location  — one row per active device with current location + coords
"""

import pandas as pd
import logging
from datetime import datetime, timedelta
import re
from sqlalchemy import text
from math import radians, sin, cos, sqrt, atan2

from utils.db import get_traffic_engine, save

logger = logging.getLogger(__name__)

MISSION_PAIR_MAX_DISTANCE_M = 100
PAIRING_WINDOW_DAYS = 45  #sensor pairs are identified if less than 45 elapse between each of their set-up


# def _distance_m(lat1, lon1, lat2, lon2):
#     """
#     calcualtes distance between two points in m using Haversine formula (curved version of Pythagoras)
#     """
#     R = 6371000
#     lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
#     dlat, dlon = lat2 - lat1, lon2 - lon1
#     a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
#     return R * 2 * atan2(sqrt(a), sqrt(1-a))

def _clean_street(s):
    if pd.isna(s): return None
    s = re.sub(r'\bDD\s*\d+\b', '', str(s), flags=re.IGNORECASE)
    s = re.sub(r'\bNr\.?\s*[\d\-\w]*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\b\d+\b', '', s)
    return re.sub(r'\s+', ' ', s).strip(' -.,')

def _clean_street_number(nr):
    if pd.isna(nr): return None
    return re.sub(r'(?i)i\.?\s*h[öo]?\.?\s*|in\s+h[öo]?\.\s*', '', str(nr)).strip()

def _clean_zipcode(z):
    if pd.isna(z): return None
    return re.sub(r'\s+', '', str(z)).strip()

def _clean_city(c):
    if pd.isna(c): return None
    c = re.sub(r'\s+', ' ', str(c)).strip()
    return c.replace('Belin ', 'Berlin ')

def _pair(df: pd.DataFrame, run_type) -> pd.DataFrame:
    """
    three filters for the candidate pool who are eligible to be paired:
    - is_pair = FALSE — not yet paired
    - end_date > NOW() — active missions only
    - created_at >= NOW() - 45 days — within pairing window
    the new pairing conditions:
    - Same cleaned street name
    - driving_direction of A matches opposite_direction of B and vice versa
    - created_at within 45 days of each other
    """

    if run_type=="initial":
        candidates = df[
            (df['is_pair'] == False)
        ]
    else:
        candidates = df[
            (df['is_pair'] == False) &
            (df['end_date'] > datetime.now()) &
            (df['created_at'] >= datetime.now() - timedelta(days=PAIRING_WINDOW_DAYS))
        ]

    for i, row in candidates.iterrows():
        for j, other in df[df['is_pair'] == False].iterrows():
            if i == j:
                continue
            if (row['street'] == other['street'] and
                row['driving_direction'].strip() == other['opposite_direction'].strip() and
                row['opposite_direction'].strip() == other['driving_direction'].strip()):
                df.at[i, 'is_pair']           = True
                df.at[i, 'paired_mission_id'] = int(other['mission_id'])
                df.at[j, 'is_pair']           = True
                df.at[j, 'paired_mission_id'] = int(row['mission_id'])
                break

    return df


def build_mission_location_to_silver(run_type) -> int:
    engine = get_traffic_engine()
    logger.info("=== BUILD ref_mission_location START ===")

    # 1. read existing silver
    try:
        with engine.connect() as conn:
            existing = pd.read_sql(text("SELECT * FROM silver.ref_mission_location"), conn)
    except Exception:
        existing = pd.DataFrame()

    # 2. fresh bronze join
    with engine.connect() as conn:
        bronze = pd.read_sql(text("""
            SELECT
                m.mission_id,
                m.created_at,
                m.start_date,
                m.end_date,
                m.device_id,
                l.street,
                l.street_number,
                l.zipcode,
                l.city,
                l.description AS location_description,
                l.driving_direction,
                l.opposite_direction,
                l.lat,
                l.lon
            FROM bronze.mission m
            INNER JOIN bronze.location l ON m.location_title = l.location_title
            ORDER BY m.start_date, m.mission_id
            """), conn)

    # clean
    for col, fn in [('street', _clean_street), ('street_number', _clean_street_number),
                    ('zipcode', _clean_zipcode), ('city', _clean_city)]:
        bronze[col] = bronze[col].apply(fn)

    # initialise pair cols on bronze rows
    bronze['is_pair']           = False
    bronze['paired_mission_id'] = None

    # 3. merge — bronze wins for existing rows, portal-deleted rows preserved from silver
    if not existing.empty:
        existing_only = existing[~existing['mission_id'].isin(bronze['mission_id'])]
        df = pd.concat([bronze, existing_only], ignore_index=True)
    else:
        df = bronze

    # 4. re-pair unpaired rows against full dataset
    df = _pair(df, run_type)

    # 5. truncate + insert
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE silver.ref_mission_location"))
    save(df, 'ref_mission_location', 'silver', engine)



    logger.info("ref_mission_location written: %d rows.", len(df))
    return len(df)
