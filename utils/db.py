from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
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
        f"{os.getenv('POSTGRES_TRAFFIC_HOST', 'postgres-traffic')}:"
        f"{os.getenv('POSTGRES_TRAFFIC_PORT', '5432')}/"
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


# ---function to identify duplicate rows in SQL table

def get_loaded_files(engine: Engine, schema: str, table: str) -> set:
    """Returns the filenames previously loaded into SQL database"""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT DISTINCT source_file FROM {schema}.{table}")
            ).fetchall()
            return {r[0] for r in rows}
    except Exception:
        return set()  # table doesn't exist yet on first run
