from contextlib import contextmanager
from sqlalchemy import create_engine
import pandas as pd
import os
import logging

logger = logging.getLogger(__name__)


# ----manage connection to database

@contextmanager
def get_traffic_engine():
    engine = create_engine(
        f"postgresql+psycopg2://"
        f"{os.getenv('POSTGRES_TRAFFIC_USER')}:"
        f"{os.getenv('POSTGRES_TRAFFIC_PASSWORD')}@"
        f"postgres-traffic:5432/"
        f"{os.getenv('POSTGRES_TRAFFIC_DB')}"
    )
    try:
        yield engine
    finally:
        engine.dispose()


# ---function to help save to SQL

def save(df: pd.DataFrame, table_name: str, schema: str, engine) -> None:
    try:
        df.to_sql(table_name, engine, schema=schema, if_exists="append", index=False)
        logger.info(f"save: wrote {len(df)} rows to {schema}.{table_name}")
    except Exception as e:
        logger.error(f"save failed for {schema}.{table_name}: {e}")
        raise
