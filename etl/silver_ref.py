import pandas as pd
import logging
import re
from sqlalchemy import text
from math import radians, sin, cos, sqrt, atan2

from utils.db import get_traffic_engine, save

logger = logging.getLogger(__name__)


def _distance_m(lat1, lon1, lat2, lon2):
    """
    calcualtes distance between two points in m using Haversine formula (curved version of Pythagoras)
    """
    R = 6371000
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

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

def _pair(df: pd.DataFrame) -> pd.DataFrame:
    unpaired = df['is_pair'] == False

    for i, row in df[unpaired].iterrows():
        candidates = []
        for j, other in df.iterrows():
            if i == j: continue
            d = -_distance_m(row.lat, row.lon, other.lat, other.lon)
            if d <= 75:
                mirror = (str(row.driving_direction).strip() == str(other.opposite_direction).strip() and
                          str(other.driving_direction).strip() == str(row.opposite_direction).strip())
                candidates.append((j, d, mirror))

        if not candidates:
            continue

        candidates.sort(key=lambda x: x[1])
        best_j, _, best_mirror = candidates[0]
        df.at[i, 'is_pair']           = True
        df.at[i, 'paired_mission_id'] = df.at[best_j, 'mission_id']
        df.at[i, 'pair_confidence']   = 'high' if best_mirror else 'low'

    return df


def build_ref_mission_location() -> int:
    engine = get_traffic_engine()
    logger.info("=== BUILD ref_mission_location START ===")

    # 1. read existing silver
    try:
        existing = pd.read_sql(text("SELECT * FROM silver.ref_mission_location"), engine.connect())
    except Exception:
        existing = pd.DataFrame()

    # 2. fresh bronze join
    bronze = pd.read_sql(text("""
        SELECT
            m.mission_id,
            m.start_date,
            m.end_date,
            m.device_id,
            l.description       AS location_description,
            l.street,
            l.street_number,
            l.zipcode,
            l.city,
            l.driving_direction,
            l.opposite_direction,
            l.lat,
            l.lon
        FROM bronze.mission m
        INNER JOIN bronze.location l ON m.location_title = l.location_title
        ORDER BY m.start_date, m.mission_id
    """), engine.connect())

    # clean
    for col, fn in [('street', _clean_street), ('street_number', _clean_street_number),
                    ('zipcode', _clean_zipcode), ('city', _clean_city)]:
        bronze[col] = bronze[col].apply(fn)

    # initialise pair cols on bronze rows
    bronze['is_pair']           = False
    bronze['paired_mission_id'] = None
    bronze['pair_confidence']   = None

    # 3. merge — bronze wins for existing rows, portal-deleted rows preserved from silver
    if not existing.empty:
        existing_only = existing[~existing['mission_id'].isin(bronze['mission_id'])]
        df = pd.concat([bronze, existing_only], ignore_index=True)
    else:
        df = bronze

    # 4. re-pair unpaired rows against full dataset
    df = _pair(df)

    # 5. truncate + insert
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE silver.ref_mission_location"))
    save(df, 'ref_mission_location', 'silver', engine)

    # 6. update gold pair cols (no-op if gold not yet built)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE gold.dashboard g
                SET is_pair           = r.is_pair,
                    paired_mission_id = r.paired_mission_id
                FROM silver.ref_mission_location r
                WHERE g.mission_id = r.mission_id
            """))
    except Exception as e:
        logger.warning("Gold update skipped: %s", e)

    logger.info("ref_mission_location written: %d rows.", len(df))
    return len(df)
