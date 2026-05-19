from sqlalchemy import text
from sqlalchemy.engine import Engine
from airflow.providers.postgres.hooks.postgres import PostgresHook
import pandas as pd
import logging

logger = logging.getLogger(__name__)


# ----manage connection to database
def get_traffic_engine():
    return PostgresHook(postgres_conn_id="postgres_traffic").get_sqlalchemy_engine()

def get_dq_engine():
    return PostgresHook(postgres_conn_id="postgres_dq").get_sqlalchemy_engine()



# ---function to help save to SQL

def save(df: pd.DataFrame, table_name: str, schema: str, engine) -> None:
    try:
        with engine.begin() as conn:
            df.to_sql(table_name, conn, schema=schema, if_exists="append", index=False)
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
