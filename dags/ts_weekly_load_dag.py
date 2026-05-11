"""
Templehof Schöneberg Traffic Pipeline DAG
Weekly orchestration: ingest → bronze → silver → gold → Superset refresh
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "ts",
    "retries": 0,
    #"retry_delay": timedelta(minutes=5),
}

# ── Task functions ────────────────────────────────────────────────────────────

def run_load_ref_to_bronze(**kwargs):
    """Fetch missions and locations from DDWeb portal → bronze.mission, bronze.location"""
    from etl.bronze_data_layer import load_ref_to_bronze
    new_mission, new_location = load_ref_to_bronze()
    logger.info("%d new mission rows and %d new location rows appended", new_mission, new_location)


def run_ingest_traffic(**kwargs):
    """Download this week's traffic files from DDWeb portal → MinIO"""
    from etl.ddweb_ingest_traffic import weekly_download
    weekly_download()
    logger.info("Traffic files downloaded to MinIO")


def run_load_traffic_to_bronze(**kwargs):
    """Read new parquet files from MinIO → append to bronze.traffic"""
    from etl.bronze_data_layer import load_traffic_to_bronze
    rows = load_traffic_to_bronze()
    logger.info("Traffic rows appended to bronze: %d", rows)

def run_validate_bronze(**kwargs):
    from tests.test_ingest import check_bronze_completeness
    result = check_bronze_completeness("weekly")
    logger.info("Validation result: %s", result)


def run_silver_layer(**kwargs):
    """Clean and enrich bronze data into silver tables"""
    from etl.silver_data_layer import run_silver
    result = run_silver()
    logger.info("Silver layer result: %s", result)


def run_gold_layer(**kwargs):
    """Run gold aggregation using Monica's gold_data_layer.py"""
    from etl.gold_data_layer import run_gold
    from utils.db import get_traffic_engine
    engine= get_traffic_engine()
    result = run_gold(engine)
    logger.info("Gold layer result: %s", result)


def run_publish(**kwargs):
    """Export gold.traffic to MinIO as CSV"""
    from etl.publish import publish_gold
    publish_gold()
    logger.info("Gold data published to MinIO")


def refresh_superset(**kwargs):
    import os, requests
    from utils.db import get_traffic_engine

    base = "http://superset:8088"
    session = requests.Session()

    # --- login ---
    r = session.post(f"{base}/api/v1/security/login", json={
        "username": os.getenv("SUPERSET_ADMIN_USER", "admin"),  #remove hardcoding in prod
        "password": os.getenv("SUPERSET_ADMIN_PASSWORD", "admin"),
        "provider": "db"
    })
    r.raise_for_status()
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    csrf = session.get(f"{base}/api/v1/security/csrf_token/", headers=headers)
    csrf_token = csrf.json()["result"]
    headers["X-CSRFToken"] = csrf_token
    headers["Referer"] = base

   # ---------------- DB connection ----------------
    # TODO: replace with env var — get_traffic_engine() should not be used to extract URI

    engine= get_traffic_engine()
    sqlalchemy_uri = str(engine.url)

    dbs = session.get(f"{base}/api/v1/database/", headers=headers).json()

    db = next(
        (d for d in dbs.get("result", []) if d.get("database_name") == "traffic_db"),
        None
    )

    if not db:
        resp = session.post(f"{base}/api/v1/database/", json={
            "database_name": "traffic_db", #why the name, check on final tidy - it's teh superset db connection'
            "sqlalchemy_uri": sqlalchemy_uri
        }, headers=headers)
        db = resp.json()

    db_id = db["id"]

    # ---------------- dataset: gold.traffic ----------------
    datasets = session.get(f"{base}/api/v1/dataset/", headers=headers).json()

    exists = any(
        d.get("schema") == "gold" and d.get("table_name") == "traffic"
        for d in datasets.get("result", [])
    )

    if not exists:
        session.post(f"{base}/api/v1/dataset/", json={
            "database": db_id,
            "schema": "gold",
            "table_name": "traffic"
        }, headers=headers)

    # ---------------- dashboard import ----------------
    try:
        with open("/app/superset_home/exports/dashboard_export_20260419T194107.zip", "rb") as f:
            session.post(
                f"{base}/api/v1/dashboard/import/",
                headers=headers,
                files={"formData": f},
                data={"overwrite": "true", "passwords": '{"databases/traffic_db.yaml": "traffic"}'}
            )
    except FileNotFoundError:
        logger.warning("Dashboard zip not found, skipping import")


# ── DAG definition ────────────────────────────────────────────────────────────
with DAG(
    dag_id="ts_weekly_load_dag",
    default_args=default_args,
    start_date=days_ago(1),
    schedule_interval="@weekly",
    catchup=False,
    tags=["berlin", "traffic", "superset"],
) as dag:

    t_load_ref = PythonOperator(
        task_id="load_ref_to_bronze",
        python_callable=run_load_ref_to_bronze,
        execution_timeout=timedelta(minutes=10),
    )

    t_ingest_traffic = PythonOperator(
        task_id="ingest_traffic",
        python_callable=run_ingest_traffic,
        execution_timeout=timedelta(hours=3),
    )

    t_load_traffic = PythonOperator(
        task_id="load_traffic_to_bronze",
        python_callable=run_load_traffic_to_bronze,
        execution_timeout=timedelta(hours=1),
    )

    t_validate_bronze = PythonOperator(
        task_id="validate_bronze",
        python_callable=run_validate_bronze,
        execution_timeout=timedelta(minutes=30),
    )

    t_silver = PythonOperator(
        task_id="run_silver_layer",
        python_callable=run_silver_layer,
        execution_timeout=timedelta(hours=4),
    )

    t_gold = PythonOperator(
        task_id="run_gold_layer",
        python_callable=run_gold_layer,
    )

    t_publish = PythonOperator(
        task_id="publish_gold",
        python_callable=run_publish,
        execution_timeout=timedelta(minutes=30),
    )

    t_superset = PythonOperator(
        task_id="refresh_superset_cache",
        python_callable=refresh_superset,
        trigger_rule="all_done",
    )

    # ── Dependencies ──────────────────────────────────────────────────────────
    t_load_ref >> t_silver
    t_ingest_traffic >> t_load_traffic >> t_silver
    t_load_traffic >> t_validate_bronze
    t_silver >> t_gold >> t_publish >> t_superset
