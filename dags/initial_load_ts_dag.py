"""
Templehof Schöneberg initial traffic data ingest DAG
one off orchestration: ingest → hand over to weekly DAG
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from datetime import datetime, timedelta
import logging
import pytz

logger = logging.getLogger(__name__)

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "ts",
    "retries": 0,
    #"retry_delay": timedelta(minutes=5),
}

# ── Task functions ────────────────────────────────────────────────────────────

def run_ingest_ref(**kwargs):
    """Fetch missions and locations from DDWeb portal → bronze.mission, bronze.location"""
    from etl.bronze_data_layer import ingest_ref
    result = ingest_ref()
    kwargs["ti"].xcom_push(key="new_mission_detected", value=result["new_mission_detected"])
    logger.info("ingest_ref result: %s", result)


def run_complete_download(**kwargs):
    """Complete download of historical traffic data"""
    from etl.ddweb_ingest_traffic import complete_download
    logger.info("Initial download started at %s", datetime.now(tz=pytz.timezone("Europe/Berlin")))
    complete_download()
    logger.info("Initial download finished at %s", datetime.now(tz=pytz.timezone("Europe/Berlin")))


def run_load_traffic(**kwargs):
    from etl.bronze_data_layer import load_traffic_to_bronze
    logger.info("Loading traffic to bronze started at %s", datetime.now(tz=pytz.timezone("Europe/Berlin")))
    rows = load_traffic_to_bronze()
    logger.info("Loaded %d rows to bronze", rows)


def run_validate_bronze(**kwargs):
    from tests.test_ingest import check_bronze_completeness
    result = check_bronze_completeness("initial")
    logger.info("Validation result: %s", result)


# ── DAG definition ────────────────────────────────────────────────────────────
with DAG(
    dag_id="initial_load_ts",
    default_args=default_args,
    start_date=days_ago(1),
    schedule_interval=None,
    catchup=False,
    max_active_runs=1,
    tags=["ts", "traffic", "initial"],
) as dag:


    t_ingest_ref = PythonOperator(
        task_id="ingest_ref",
        python_callable=run_ingest_ref,
        execution_timeout=timedelta(minutes=10),
    )

    t_complete_download = PythonOperator(
        task_id="complete_download",
        python_callable=run_complete_download,
        execution_timeout=timedelta(hours=24),
    )

    t_load_traffic = PythonOperator(
        task_id="load_traffic_to_bronze",
        python_callable=run_load_traffic,
        execution_timeout=timedelta(hours=3),
    )

    t_validate_bronze = PythonOperator(
        task_id="validate_bronze",
        python_callable=run_validate_bronze,
        execution_timeout=timedelta(minutes=30),
    )


    # ── Dependencies ──────────────────────────────────────────────────────────
    t_ingest_ref >> t_complete_download >> t_load_traffic >> t_validate_bronze
