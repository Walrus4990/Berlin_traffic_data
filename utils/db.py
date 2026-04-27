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


@contextmanager
def get_dq_engine():
    engine = create_engine(
        f"postgresql+psycopg2://"
        f"{os.getenv('POSTGRES_DQ_USER')}:"
        f"{os.getenv('POSTGRES_DQ_PASSWORD')}@"
        f"{os.getenv('POSTGRES_DQ_HOST', 'postgres-dq')}:"
        f"{os.getenv('POSTGRES_DQ_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DQ_DB')}"
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


def save_qa_report(qa: dict, layer: str, dq_engine: Engine) -> None:
    """Persist QA metrics to postgres-dq public.qa_runs (one row per metric)."""
    run_at = pd.Timestamp.now()
    rows = [{"run_at": run_at, "layer": layer, "metric": k, "count": int(v)} for k, v in qa.items()]
    df = pd.DataFrame(rows)
    with dq_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.qa_runs (
                id      SERIAL    PRIMARY KEY,
                run_at  TIMESTAMP NOT NULL,
                layer   TEXT      NOT NULL,
                metric  TEXT      NOT NULL,
                count   BIGINT    NOT NULL
            )
        """))
    df.to_sql("qa_runs", dq_engine, schema="public", if_exists="append", index=False)
    logger.info("QA report persisted to postgres-dq: %d metrics for layer=%s", len(rows), layer)


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
